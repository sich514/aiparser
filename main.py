from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class FetchConfig:
    """Runtime configuration for market data collection."""

    symbols: list[str]
    timeframe: str = "5m"
    since_ms: int | None = None
    limit: int = 500
    pages: int = 3
    exchanges: list[str] = field(default_factory=lambda: ["binance", "bybit"])
    market_types: list[str] = field(default_factory=lambda: ["spot", "swap"])


class ExchangeCollector:
    """Collect OHLCV and funding history from one exchange with CCXT."""

    DATASET_COLUMNS = [
        "timestamp",
        "exchange",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "funding",
        "type",
    ]

    def __init__(self, exchange_id: str):
        ccxt = __import__("ccxt")
        self.exchange_id = exchange_id
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({"enableRateLimit": True})

    def fetch_ohlcv_pages(
        self,
        symbol: str,
        timeframe: str,
        since_ms: int | None,
        limit: int,
        pages: int,
        market_type: str,
    ) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        current_since = since_ms

        for _ in range(pages):
            candles = self.exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=current_since,
                limit=limit,
                params={"defaultType": market_type},
            )
            if not candles:
                break

            frame = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
            frames.append(frame)

            current_since = int(frame["timestamp"].iloc[-1].timestamp() * 1000) + 1

        if not frames:
            return pd.DataFrame(columns=self.DATASET_COLUMNS)

        out = pd.concat(frames, ignore_index=True)
        out = out.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
        out["exchange"] = self.exchange_id
        out["symbol"] = symbol
        out["funding"] = float("nan")
        out["type"] = market_type
        return out[self.DATASET_COLUMNS]

    def fetch_funding_pages(self, symbol: str, since_ms: int | None, limit: int, pages: int) -> pd.DataFrame:
        if not self.exchange.has.get("fetchFundingRateHistory"):
            return pd.DataFrame(columns=["timestamp", "funding"])

        rows: list[dict[str, Any]] = []
        current_since = since_ms

        for _ in range(pages):
            batch = self.exchange.fetch_funding_rate_history(symbol=symbol, since=current_since, limit=limit)
            if not batch:
                break
            rows.extend(batch)
            current_since = int(batch[-1]["timestamp"]) + 1

        if not rows:
            return pd.DataFrame(columns=["timestamp", "funding"])

        funding = pd.DataFrame(rows)
        funding = funding[["timestamp", "fundingRate"]].rename(columns={"fundingRate": "funding"})
        funding["timestamp"] = pd.to_datetime(funding["timestamp"], unit="ms", utc=True)
        return funding.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")


def _timeframe_to_pandas_rule(timeframe: str) -> str:
    if timeframe.endswith("m"):
        return timeframe.replace("m", "min")
    if timeframe.endswith("h"):
        return timeframe.replace("h", "H")
    return timeframe


def collect_dataset(config: FetchConfig) -> pd.DataFrame:
    """Fetch spot/swap candles + funding for all configured exchanges/symbols."""
    all_frames: list[pd.DataFrame] = []

    for exchange_id in config.exchanges:
        collector = ExchangeCollector(exchange_id)
        for symbol in config.symbols:
            for market_type in config.market_types:
                candles = collector.fetch_ohlcv_pages(
                    symbol=symbol,
                    timeframe=config.timeframe,
                    since_ms=config.since_ms,
                    limit=config.limit,
                    pages=config.pages,
                    market_type=market_type,
                )
                if candles.empty:
                    continue

                if market_type == "swap":
                    funding = collector.fetch_funding_pages(
                        symbol=symbol,
                        since_ms=config.since_ms,
                        limit=config.limit,
                        pages=config.pages,
                    )
                    if not funding.empty:
                        candles = pd.merge_asof(
                            candles.sort_values("timestamp"),
                            funding.sort_values("timestamp"),
                            on="timestamp",
                            direction="backward",
                            suffixes=("", "_hist"),
                        )
                        candles["funding"] = candles["funding_hist"].combine_first(candles["funding"])
                        candles = candles.drop(columns=["funding_hist"])

                all_frames.append(candles)

    if not all_frames:
        return pd.DataFrame(columns=ExchangeCollector.DATASET_COLUMNS)

    return pd.concat(all_frames, ignore_index=True).sort_values(["timestamp", "exchange", "symbol", "type"])


def build_spread_table(df: pd.DataFrame, symbol: str, timeframe: str) -> pd.DataFrame:
    """Synchronize and calculate spreads, basis, premium proxies, and funding divergence."""
    pair = df[df["symbol"] == symbol].copy()
    if pair.empty:
        return pd.DataFrame()

    rule = _timeframe_to_pandas_rule(timeframe)
    grouped = (
        pair.set_index("timestamp")
        .groupby(["exchange", "type"])
        .apply(lambda x: x.resample(rule).agg({"close": "last", "volume": "sum", "funding": "last"}))
        .reset_index()
    )

    close = grouped.pivot_table(index="timestamp", columns=["exchange", "type"], values="close", aggfunc="last")
    funding = grouped.pivot_table(index="timestamp", columns=["exchange", "type"], values="funding", aggfunc="last")

    result = pd.DataFrame(index=close.index)

    if ("binance", "spot") in close and ("bybit", "spot") in close:
        result["spread_spot_binance_bybit"] = close[("binance", "spot")] - close[("bybit", "spot")]
    if ("binance", "swap") in close and ("bybit", "swap") in close:
        result["spread_swap_binance_bybit"] = close[("binance", "swap")] - close[("bybit", "swap")]

    if ("binance", "swap") in close and ("binance", "spot") in close:
        result["basis_binance_swap_spot"] = close[("binance", "swap")] - close[("binance", "spot")]
        result["premium_index_binance"] = result["basis_binance_swap_spot"] / close[("binance", "spot")]
    if ("bybit", "swap") in close and ("bybit", "spot") in close:
        result["basis_bybit_swap_spot"] = close[("bybit", "swap")] - close[("bybit", "spot")]
        result["premium_index_bybit"] = result["basis_bybit_swap_spot"] / close[("bybit", "spot")]

    if ("binance", "swap") in funding:
        result["funding_binance"] = funding[("binance", "swap")]
    if ("bybit", "swap") in funding:
        result["funding_bybit"] = funding[("bybit", "swap")]
    if "funding_binance" in result and "funding_bybit" in result:
        result["funding_divergence"] = result["funding_binance"] - result["funding_bybit"]

    if "spread_spot_binance_bybit" in result:
        result["spread_change"] = result["spread_spot_binance_bybit"].diff()
        result["spread_volatility_12"] = result["spread_spot_binance_bybit"].rolling(12).std()

    return result.dropna(how="all").reset_index()


def detect_signals(spread_table: pd.DataFrame, zscore_threshold: float = 2.5) -> pd.DataFrame:
    """Flag timepoints where spread/funding divergence materially deviates from baseline."""
    if spread_table.empty or "spread_spot_binance_bybit" not in spread_table:
        return pd.DataFrame()

    out = spread_table.copy()
    spread = out["spread_spot_binance_bybit"]
    spread_std = spread.std(ddof=0)
    out["spread_zscore"] = (spread - spread.mean()) / spread_std if spread_std else 0.0
    out["signal_spread_extreme"] = out["spread_zscore"].abs() >= zscore_threshold

    if "funding_divergence" in out:
        f = out["funding_divergence"].fillna(0.0)
        f_std = f.std(ddof=0)
        out["funding_zscore"] = (f - f.mean()) / f_std if f_std else 0.0
        out["signal_funding_extreme"] = out["funding_zscore"].abs() >= zscore_threshold
    else:
        out["signal_funding_extreme"] = False

    out["signal_any"] = out["signal_spread_extreme"] | out["signal_funding_extreme"]
    return out


def train_baseline_model(spread_table: pd.DataFrame) -> tuple[Any | None, str]:
    """Train baseline classifier for profitable-next-bar spread expansion."""
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import classification_report
        from sklearn.model_selection import train_test_split
    except Exception:
        return None, "sklearn not installed; ML block skipped"

    if spread_table.empty or "spread_spot_binance_bybit" not in spread_table:
        return None, "not enough data columns for model training"

    data = spread_table.copy()
    data["future_spread"] = data["spread_spot_binance_bybit"].shift(-1)
    data["profitable_next_5m"] = (data["future_spread"].abs() > data["spread_spot_binance_bybit"].abs()).astype(int)
    data = data.dropna()

    if len(data) < 50:
        return None, "dataset too small for stable ML training"

    feature_columns = [c for c in ["spread_spot_binance_bybit", "spread_change", "spread_volatility_12", "funding_divergence"] if c in data]
    x = data[feature_columns].fillna(0)
    y = data["profitable_next_5m"]

    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.3, random_state=42, shuffle=False)
    model = RandomForestClassifier(n_estimators=250, random_state=42)
    model.fit(x_train, y_train)
    pred = model.predict(x_test)
    return model, classification_report(y_test, pred)


def write_summary_report(symbol: str, signals: pd.DataFrame, report_path: Path) -> None:
    total = len(signals)
    flagged = int(signals["signal_any"].sum()) if "signal_any" in signals else 0
    ratio = flagged / total if total else 0.0

    lines = [
        f"# Spread/Funding report for {symbol}",
        "",
        f"- Rows analyzed: **{total}**",
        f"- Signal rows: **{flagged}** ({ratio:.2%})",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Binance/Bybit spread, funding and premium analysis")
    parser.add_argument("--symbols", nargs="+", default=["BTC/USDT", "ETH/USDT"])
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--since-ms", type=int, default=None)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--output-dir", default="data")
    parser.add_argument("--zscore-threshold", type=float, default=2.5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = FetchConfig(
        symbols=args.symbols,
        timeframe=args.timeframe,
        since_ms=args.since_ms,
        limit=args.limit,
        pages=args.pages,
    )

    dataset = collect_dataset(config)
    if dataset.empty:
        print("No data fetched. Check symbols, API limits, and exchange availability.")
        return

    dataset_path = output_dir / "market_dataset.parquet"
    dataset.to_parquet(dataset_path, index=False)

    for symbol in config.symbols:
        spread = build_spread_table(dataset, symbol=symbol, timeframe=args.timeframe)
        if spread.empty:
            continue

        signals = detect_signals(spread, zscore_threshold=args.zscore_threshold)
        safe_symbol = symbol.replace("/", "_")

        spread.to_csv(output_dir / f"spread_{safe_symbol}.csv", index=False)
        signals.to_csv(output_dir / f"signals_{safe_symbol}.csv", index=False)
        write_summary_report(symbol, signals, output_dir / f"report_{safe_symbol}.md")

        _, ml_report = train_baseline_model(spread)
        print(f"\n=== {symbol} ===")
        print(ml_report)

    print(f"Saved unified dataset: {dataset_path}")


if __name__ == "__main__":
    main()

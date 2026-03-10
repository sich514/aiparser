from __future__ import annotations

from aiparser.utils import timeframe_to_pandas_rule


def collect_dataset(config):
    pd = __import__("pandas")
    from aiparser.collector import ExchangeCollector

    all_frames = []
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


def build_spread_table(df, symbol: str, timeframe: str):
    pd = __import__("pandas")
    pair = df[df["symbol"] == symbol].copy()
    if pair.empty:
        return pd.DataFrame()

    rule = timeframe_to_pandas_rule(timeframe)
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

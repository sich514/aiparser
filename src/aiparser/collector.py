from __future__ import annotations

from typing import Any


class ExchangeCollector:
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
        self.exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})

    def fetch_ohlcv_pages(
        self,
        symbol: str,
        timeframe: str,
        since_ms: int | None,
        limit: int,
        pages: int,
        market_type: str,
    ):
        pd = __import__("pandas")
        frames: list[Any] = []
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

        out = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
        out["exchange"] = self.exchange_id
        out["symbol"] = symbol
        out["funding"] = float("nan")
        out["type"] = market_type
        return out[self.DATASET_COLUMNS]

    def fetch_funding_pages(self, symbol: str, since_ms: int | None, limit: int, pages: int):
        pd = __import__("pandas")
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

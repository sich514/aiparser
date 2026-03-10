from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FetchConfig:
    symbols: list[str]
    timeframe: str = "5m"
    since_ms: int | None = None
    limit: int = 500
    pages: int = 3
    exchanges: list[str] = field(default_factory=lambda: ["binance", "bybit"])
    market_types: list[str] = field(default_factory=lambda: ["spot", "swap"])


@dataclass
class RuntimeConfig:
    fetch: FetchConfig
    output_dir: str = "data"
    zscore_threshold: float = 2.5

from __future__ import annotations

import argparse

from aiparser.config import FetchConfig, RuntimeConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Binance/Bybit spread, funding and premium analysis")
    parser.add_argument("--symbols", nargs="+", default=["BTC/USDT", "ETH/USDT"])
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--since-ms", type=int, default=None)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--output-dir", default="data")
    parser.add_argument("--zscore-threshold", type=float, default=2.5)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    fetch = FetchConfig(
        symbols=args.symbols,
        timeframe=args.timeframe,
        since_ms=args.since_ms,
        limit=args.limit,
        pages=args.pages,
    )
    runtime = RuntimeConfig(fetch=fetch, output_dir=args.output_dir, zscore_threshold=args.zscore_threshold)

    try:
        from aiparser.pipeline import run_pipeline
    except ModuleNotFoundError as exc:
        missing = exc.name or "dependency"
        print(
            "Missing dependency: "
            f"{missing}. Install requirements first: pip install -r requirements.txt"
        )
        return 2

    return run_pipeline(runtime)

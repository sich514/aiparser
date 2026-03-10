from __future__ import annotations

from pathlib import Path

from aiparser.analysis import build_spread_table, collect_dataset
from aiparser.ml import train_baseline_model
from aiparser.reporting import write_summary_report
from aiparser.signals import detect_signals


def run_pipeline(runtime_config) -> int:
    dataset = collect_dataset(runtime_config.fetch)
    if dataset.empty:
        print("No data fetched. Check symbols, API limits, and exchange availability.")
        return 1

    output_dir = Path(runtime_config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = output_dir / "market_dataset.parquet"
    dataset.to_parquet(dataset_path, index=False)

    for symbol in runtime_config.fetch.symbols:
        spread = build_spread_table(dataset, symbol=symbol, timeframe=runtime_config.fetch.timeframe)
        if spread.empty:
            continue

        signals = detect_signals(spread, zscore_threshold=runtime_config.zscore_threshold)
        safe_symbol = symbol.replace("/", "_")

        spread.to_csv(output_dir / f"spread_{safe_symbol}.csv", index=False)
        signals.to_csv(output_dir / f"signals_{safe_symbol}.csv", index=False)
        write_summary_report(symbol, signals, output_dir / f"report_{safe_symbol}.md")

        _, ml_report = train_baseline_model(spread)
        print(f"\n=== {symbol} ===")
        print(ml_report)

    print(f"Saved unified dataset: {dataset_path}")
    return 0

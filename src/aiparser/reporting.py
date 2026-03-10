from __future__ import annotations

from pathlib import Path


def write_summary_report(symbol: str, signals, report_path: Path) -> None:
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

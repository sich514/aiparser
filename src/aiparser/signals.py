from __future__ import annotations


def detect_signals(spread_table, zscore_threshold: float = 2.5):
    pd = __import__("pandas")
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

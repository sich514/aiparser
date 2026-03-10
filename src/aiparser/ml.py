from __future__ import annotations

from typing import Any


def train_baseline_model(spread_table) -> tuple[Any | None, str]:
    if spread_table.empty or "spread_spot_binance_bybit" not in spread_table:
        return None, "not enough data columns for model training"

    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import classification_report
        from sklearn.model_selection import train_test_split
    except Exception:
        return None, "sklearn not installed; ML block skipped"

    data = spread_table.copy()
    data["future_spread"] = data["spread_spot_binance_bybit"].shift(-1)
    data["profitable_next_5m"] = (data["future_spread"].abs() > data["spread_spot_binance_bybit"].abs()).astype(int)
    data = data.dropna()

    if len(data) < 50:
        return None, "dataset too small for stable ML training"

    feature_columns = [
        c
        for c in [
            "spread_spot_binance_bybit",
            "spread_change",
            "spread_volatility_12",
            "funding_divergence",
        ]
        if c in data
    ]

    x = data[feature_columns].fillna(0)
    y = data["profitable_next_5m"]

    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.3, random_state=42, shuffle=False)
    model = RandomForestClassifier(n_estimators=250, random_state=42)
    model.fit(x_train, y_train)
    pred = model.predict(x_test)
    return model, classification_report(y_test, pred)

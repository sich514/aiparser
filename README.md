# AI Parser: Binance + Bybit Spread/Funding Analyzer

Полноценная модульная программа для:
- выкачки данных с Binance и Bybit (spot + swap);
- синхронизации по времени;
- расчёта спредов, basis, premium index proxy, divergence по funding;
- детекции аномалий (z-score сигналы);
- подготовки CSV/Parquet отчётов и baseline ML-классификации.

## Структура

- `main.py` — точка входа
- `src/aiparser/cli.py` — CLI
- `src/aiparser/config.py` — конфиг
- `src/aiparser/collector.py` — сбор данных через CCXT
- `src/aiparser/analysis.py` — синхронизация и расчёт метрик
- `src/aiparser/signals.py` — сигнал-детектор
- `src/aiparser/ml.py` — baseline ML
- `src/aiparser/reporting.py` — генерация markdown-отчётов
- `src/aiparser/pipeline.py` — orchestration

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Запуск

```bash
PYTHONPATH=src python main.py \
  --symbols BTC/USDT ETH/USDT \
  --timeframe 5m \
  --pages 10 \
  --limit 1000 \
  --output-dir data \
  --zscore-threshold 2.5
```

## Результаты

В `output-dir` сохраняются:
- `market_dataset.parquet`
- `spread_<SYMBOL>.csv`
- `signals_<SYMBOL>.csv`
- `report_<SYMBOL>.md`

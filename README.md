# MetalScope — Gold & Silver Market Analysis Dashboard

A Streamlit browser dashboard for a paper-trading research prototype.

## Run locally

1. Install Python 3.10+.
2. In this folder, run:

   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   pip install -r requirements.txt
   streamlit run app.py
   ```

3. Open the local URL Streamlit prints (usually `http://localhost:8501`).

## Important prototype limitations

- All prices and macro proxy series are generated synthetic data, not real historical prices.
- The economic calendar is a manually described placeholder; no live feed is connected.
- The backtest is a simple illustrative, bar-level strategy with a basic turnover cost.
- The risk budget setting is not yet used to size positions; the current backtest uses full notional exposure. The drawdown threshold is an alert only.
- No brokerage connection or order execution exists.

## Recommended next build stage

Integrate real, licensed XAU/USD and XAG/USD historical candles; official calendar timestamps and actual/consensus values; US dollar and Treasury yield series; realistic spread/slippage; risk-based sizing; and out-of-sample walk-forward testing. Keep paper trading until the complete pipeline has been independently validated.

# MetalScope Live — paper research

Run:
```bash
pip install -r requirements.txt
streamlit run app.py
```

The app requests market candles through Yahoo Finance via yfinance. Gold and silver use `GC=F` and `SI=F` futures proxies; dollar and Treasury yield proxies are also queried. Data can be delayed or unavailable and is not guaranteed to be a live spot quote.

Signal rules use EMA(8)/EMA(21), six-candle momentum, RSI(14), and two macro proxies. Hypothetical levels use the latest close, 1.5 × ATR(14) stop distance, and a configurable target multiple. No broker integration or order execution exists. The risk amount and units are generic estimates and ignore contract-specific multipliers, spreads, slippage, and fees. A live economic calendar is not yet integrated.

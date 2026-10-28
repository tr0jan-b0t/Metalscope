import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timezone

st.set_page_config(page_title="MetalScope Live", page_icon="📊", layout="wide")
st.title("MetalScope Live")
st.caption("Gold & silver market monitor · Intraday paper research · No order execution")
st.warning("Research-only prototype. Yahoo Finance data can be delayed or incomplete. GC=F and SI=F are futures proxies, not necessarily your broker's spot XAU/USD or XAG/USD. Signals and levels are hypothetical, not guarantees.")
with st.sidebar:
    st.header("Settings")
    interval = st.selectbox("Candle interval", ["5m", "15m", "30m", "60m"], index=1)
    period = st.selectbox("History window", ["5d", "1mo", "3mo"], index=0)
    equity = st.number_input("Paper equity ($)", min_value=100., max_value=10_000_000., value=10_000., step=500.)
    risk_pct = st.slider("Illustrative risk budget (%)", 0.1, 1.0, 0.25, 0.05)
    rr = st.selectbox("Target multiple (R)", [1.0, 1.5, 2.0, 2.5, 3.0], index=2)
    alert_dd = st.slider("Drawdown alert (%)", 5, 20, 10)
    st.caption("No orders are placed. Generic units ignore broker-specific contract rules.")

TICKERS = {"Gold futures proxy (GC=F)": "GC=F", "Silver futures proxy (SI=F)": "SI=F",
           "Dollar index proxy": "DX-Y.NYB", "10-year Treasury yield proxy": "^TNX"}

@st.cache_data(ttl=90, show_spinner=False)
def fetch(ticker, period, interval):
    try:
        d = yf.download(ticker, period=period, interval=interval, auto_adjust=False, progress=False, threads=False)
        if d is None or d.empty:
            return pd.DataFrame()
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        d.columns = [str(c).title() for c in d.columns]
        d = d[[c for c in ["Open", "High", "Low", "Close", "Volume"] if c in d.columns]].dropna(subset=["Close"])
        if d.index.tz is None:
            d.index = d.index.tz_localize("UTC")
        else:
            d.index = d.index.tz_convert("UTC")
        return d
    except Exception:
        return pd.DataFrame()

def rsi(s, n=14):
    delta = s.diff()
    up = delta.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def indicators(d):
    x = d.copy()
    x["EMA8"] = x.Close.ewm(span=8, adjust=False).mean()
    x["EMA21"] = x.Close.ewm(span=21, adjust=False).mean()
    x["RSI14"] = rsi(x.Close)
    prev = x.Close.shift(1)
    tr = pd.concat([x.High-x.Low, (x.High-prev).abs(), (x.Low-prev).abs()], axis=1).max(axis=1)
    x["ATR14"] = tr.ewm(alpha=1/14, adjust=False).mean()
    x["Mom6"] = x.Close.pct_change(6)*100
    return x

metal = st.radio("Metal", ["Gold futures proxy (GC=F)", "Silver futures proxy (SI=F)"], horizontal=True)
symbol = TICKERS[metal]
with st.spinner("Fetching available market data…"):
    raw = fetch(symbol, period, interval)
    usd = fetch(TICKERS["Dollar index proxy"], period, interval)
    yld = fetch(TICKERS["10-year Treasury yield proxy"], period, interval)
if raw.empty or len(raw) < 30:
    st.error("Market data is unavailable or too short. Try another interval/history window or retry later. No synthetic prices are substituted.")
    st.stop()

d = indicators(raw)
last = d.iloc[-1]
price = float(last.Close)
usd_change = float(usd.Close.iloc[-1]/usd.Close.iloc[-7]-1) if len(usd) >= 7 else None
yield_change = float(yld.Close.iloc[-1]-yld.Close.iloc[-7]) if len(yld) >= 7 else None
trend_up = bool(last.EMA8 > last.EMA21)
mom_up = bool(pd.notna(last.Mom6) and last.Mom6 > 0)
rsi_ok = bool(pd.notna(last.RSI14) and 50 <= last.RSI14 <= 68)
usd_support = usd_change is not None and usd_change < 0
yield_support = yield_change is not None and yield_change < 0
checks = [
    ("EMA 8 above EMA 21", trend_up, "Trend"),
    ("Six-candle momentum positive", mom_up, "Momentum"),
    ("RSI between 50 and 68", rsi_ok, "Momentum quality"),
    ("Dollar proxy weakening", usd_support, "Macro proxy"),
    ("Treasury yield proxy falling", yield_support, "Macro proxy"),
]
score = sum(int(ok) for _, ok, _ in checks)
if trend_up and mom_up and score >= 4:
    signal, direction = "BUY SETUP WATCH", 1
elif not trend_up and not mom_up and score <= 1:
    signal, direction = "SELL SETUP WATCH", -1
else:
    signal, direction = "WAIT", 0

atr = float(last.ATR14)
levels = None
if direction and np.isfinite(atr) and atr > 0:
    stop_dist = 1.5 * atr
    risk_cash = equity * risk_pct / 100
    levels = {"entry": price, "stop": price-direction*stop_dist,
              "target": price+direction*stop_dist*rr, "dist": stop_dist,
              "risk": risk_cash, "units": risk_cash/stop_dist}

stamp = d.index[-1].to_pydatetime()
age = max(0, (datetime.now(timezone.utc)-stamp).total_seconds()/60)
a,b,c,e = st.columns(4)
a.metric("Latest available close", f"${price:,.3f}" if "Silver" in metal else f"${price:,.2f}")
b.metric("Signal state", signal, f"{score}/5 rule checks")
c.metric("Latest candle (UTC)", stamp.strftime("%Y-%m-%d %H:%M"))
e.metric("Candle age", f"{age:.0f} min", "May be delayed")
if age > 45:
    st.warning("Latest candle is over 45 minutes old. Treat any calculated levels as stale.")

left, right = st.columns([1.7,1])
with left:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=d.index, open=d.Open, high=d.High, low=d.Low, close=d.Close, name="Market candles"))
    fig.add_trace(go.Scatter(x=d.index, y=d.EMA8, name="EMA 8", line=dict(width=1)))
    fig.add_trace(go.Scatter(x=d.index, y=d.EMA21, name="EMA 21", line=dict(width=1)))
    if levels:
        for key, dash in [("entry","dot"),("stop","dash"),("target","dash")]:
            fig.add_hline(y=levels[key], line_dash=dash, annotation_text=key.title())
    fig.update_layout(title="Price and trend", height=440, xaxis_rangeslider_visible=False, margin=dict(l=8,r=8,t=40,b=8))
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.subheader("Signal explanation")
    st.markdown(f"### `{signal}`")
    st.write(f"Rule score: **{score}/5**; not a probability of profit.")
    for label, ok, category in checks:
        st.write(("✅ " if ok else "— ") + label)
    st.caption("Unavailable macro data counts as unconfirmed, not as a positive condition.")

st.subheader("Hypothetical entry / stop / target levels")
if levels:
    st.info("These are mechanical paper-research levels from the latest candle and ATR, not executable quotes or a recommendation to trade.")
    fmt = (lambda v: f"${v:,.3f}") if "Silver" in metal else (lambda v: f"${v:,.2f}")
    x1,x2,x3 = st.columns(3)
    x1.metric("Reference entry", fmt(levels["entry"]))
    x2.metric("Hypothetical stop", fmt(levels["stop"]))
    x3.metric(f"Hypothetical target ({rr:g}R)", fmt(levels["target"]))
    x4,x5,x6 = st.columns(3)
    x4.metric("Stop distance", fmt(levels["dist"]))
    x5.metric("Risk budget amount", f"${levels['risk']:,.2f}")
    x6.metric("Generic units estimate*", f"{levels['units']:.4f}")
    st.caption("*Mathematical estimate only. Futures, CFDs, and broker lots have different multipliers, tick values, minimum sizes, and margin.")
else:
    st.info("No aligned setup. The engine stays on WAIT instead of forcing a trade.")

st.subheader("Macro proxies")
m1,m2 = st.columns(2)
m1.metric("Dollar index proxy", f"{float(usd.Close.iloc[-1]):.3f}" if not usd.empty else "Unavailable",
          f"{usd_change*100:+.2f}% over six candles" if usd_change is not None else "No confirmation")
m2.metric("10-year Treasury yield proxy", f"{float(yld.Close.iloc[-1]):.3f}" if not yld.empty else "Unavailable",
          f"{yield_change:+.3f} yield points over six candles" if yield_change is not None else "No confirmation")
st.caption("These proxies are not a full real-yield series and do not establish causation.")

st.subheader("Economic-event awareness")
st.write("A verified live calendar is not connected in this version. Check official schedules for US CPI, PCE inflation, employment reports, and Federal Reserve decisions before interpreting signals.")
st.dataframe(pd.DataFrame([
    {"Event":"US CPI", "Potential channel":"Inflation surprise → rate expectations", "Feed":"Not connected"},
    {"Event":"US PCE inflation", "Potential channel":"Federal Reserve policy expectations", "Feed":"Not connected"},
    {"Event":"US employment report", "Potential channel":"Growth, wages and rate expectations", "Feed":"Not connected"},
    {"Event":"Federal Reserve decision", "Potential channel":"Policy path, dollar and yields", "Feed":"Not connected"},
]), use_container_width=True, hide_index=True)

st.subheader("Risk monitor")
st.write(f"Configured drawdown alert: **{alert_dd}%**. This app does not track a broker account or enforce a loss limit.")
st.progress(min(1.0, risk_pct), text=f"Illustrative risk budget: {risk_pct:.2f}% of paper equity")
st.caption("Stops may slip during gaps or fast markets. No live orders, broker integration, or guaranteed maximum drawdown.")

with st.expander("Methodology and limitations"):
    st.markdown("""
    - **Data:** Yahoo Finance via `yfinance`; `GC=F` and `SI=F` are COMEX futures proxies. Data can be delayed, unavailable, or subject to provider terms.
    - **Rules:** EMA(8)/EMA(21), six-candle momentum, RSI(14), dollar-index proxy direction, and 10-year Treasury yield proxy direction.
    - **Levels:** latest candle close as reference entry; stop distance = 1.5 × ATR(14); target = selected reward multiple.
    - **Costs:** levels omit spreads, slippage, fees, and contract multipliers.
    - **Events:** no live economic calendar is integrated.
    - **No guarantee:** signal score is not a win probability; this app cannot guarantee a loss cap or profitability.
    """)
st.caption(f"App refreshed {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} · 90-second data cache · Paper research only")

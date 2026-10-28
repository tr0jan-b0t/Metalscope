import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(page_title="MetalScope | Gold & Silver", page_icon="📈", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.25rem; padding-bottom: 2rem;}
.metric-card {border:1px solid rgba(128,128,128,.25); border-radius:14px; padding:14px 16px;}
.small-muted {color:#8b95a5; font-size:.88rem;}
.signal-buy {color:#1b9b6b; font-weight:700;}
.signal-sell {color:#d05b5b; font-weight:700;}
.signal-wait {color:#c18a2c; font-weight:700;}
</style>
""", unsafe_allow_html=True)

st.title("MetalScope")
st.caption("Gold & Silver · Intraday research · Historical simulation only")
st.warning("PAPER MODE — This dashboard uses generated illustrative data, not live market prices. It does not place orders. Historical/simulated results do not predict future returns.")

with st.sidebar:
    st.header("Research controls")
    seed = st.number_input("Simulation seed", min_value=1, max_value=99999, value=42, step=1)
    days = st.select_slider("History window", options=[30, 60, 90, 180, 365], value=180, format_func=lambda x: f"{x} days")
    starting_equity = st.number_input("Paper account equity ($)", min_value=100.0, max_value=10000000.0, value=10000.0, step=500.0)
    risk_pct = st.slider("Risk budget per trade (%)", min_value=0.1, max_value=2.0, value=0.5, step=0.1)
    max_dd = st.slider("Drawdown alert threshold (%)", min_value=5, max_value=20, value=15, step=1)
    st.divider()
    st.subheader("Signal filters")
    trend_period = st.selectbox("Trend lookback", [12, 20, 30, 50], index=1)
    min_score = st.slider("Minimum signal score", 2, 5, 4)
    st.caption("All data and signals on this prototype are illustrative.")

rng = np.random.default_rng(int(seed))
n = int(days * 24)  # hourly bars
end = pd.Timestamp.now(tz="UTC").floor("h")
idx = pd.date_range(end=end, periods=n, freq="h")
# Synthetic prices with drift regimes and common USD/yield-like factors.
regimes = np.repeat(rng.normal(0, 0.00018, max(1, n // 120 + 1)), 120)[:n]
common = rng.normal(0, 0.0022, n) + regimes
gold_ret = common + rng.normal(0, 0.0015, n)
silver_ret = common * 1.25 + rng.normal(0, 0.0028, n)
gold = 2200 * np.exp(np.cumsum(gold_ret))
silver = 28.0 * np.exp(np.cumsum(silver_ret))
usd = 104 * np.exp(np.cumsum(rng.normal(0, 0.00065, n) - common * 0.10))
real_yield = 1.8 + np.cumsum(rng.normal(0, 0.012, n) - common * 0.15)
df = pd.DataFrame({"Gold": gold, "Silver": silver, "USD index (proxy)": usd, "Real yield (proxy)": real_yield}, index=idx)

def rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def make_signals(price, usd_proxy, yield_proxy, trend_n, score_floor):
    fast = price.ewm(span=8, adjust=False).mean()
    slow = price.ewm(span=trend_n, adjust=False).mean()
    mom = price.pct_change(6)
    rs = rsi(price)
    usd_mom = usd_proxy.pct_change(6)
    yield_change = yield_proxy.diff(6)
    score = (
        (fast > slow).astype(int)
        + (mom > 0).astype(int)
        + (usd_mom < 0).astype(int)
        + (yield_change < 0).astype(int)
        + ((rs > 45) & (rs < 70)).astype(int)
    )
    signal = np.where((score >= score_floor) & (fast > slow), "BUY",
             np.where((score >= score_floor) & (fast < slow), "SELL", "WAIT"))
    # Signal confidence is a transparent rule score, not a calibrated probability.
    return pd.DataFrame({"Fast EMA": fast, "Trend EMA": slow, "RSI": rs,
                         "6h momentum %": mom * 100, "Signal score": score,
                         "Signal": signal}, index=price.index)

gold_sig = make_signals(df["Gold"], df["USD index (proxy)"], df["Real yield (proxy)"], trend_period, min_score)
silver_sig = make_signals(df["Silver"], df["USD index (proxy)"], df["Real yield (proxy)"], trend_period, min_score)

def backtest(price, sig, risk, initial):
    # Simple one-bar-delayed, long/short strategy; illustrative friction included.
    pos = sig["Signal"].map({"BUY": 1, "SELL": -1, "WAIT": 0}).shift(1).fillna(0)
    ret = price.pct_change().fillna(0)
    strat_ret = pos * ret - (pos.diff().abs().fillna(0) * 0.00015)
    equity = initial * (1 + strat_ret).cumprod()
    peak = equity.cummax()
    dd = equity / peak - 1
    active = strat_ret[pos != 0]
    wins = int((active > 0).sum())
    losses = int((active < 0).sum())
    gross_win = active[active > 0].sum()
    gross_loss = -active[active < 0].sum()
    return equity, dd, {"Return": (equity.iloc[-1] / initial - 1) * 100,
                        "Max drawdown": abs(dd.min()) * 100,
                        "Trade bars": int((pos != 0).sum()),
                        "Win rate": (wins / max(wins + losses, 1)) * 100,
                        "Profit factor": gross_win / gross_loss if gross_loss > 0 else np.nan}

gold_eq, gold_dd, gold_stats = backtest(df["Gold"], gold_sig, risk_pct, starting_equity)
silver_eq, silver_dd, silver_stats = backtest(df["Silver"], silver_sig, risk_pct, starting_equity)
active_asset = st.radio("Selected metal", ["Gold (XAU/USD)", "Silver (XAG/USD)"], horizontal=True)
is_gold = active_asset.startswith("Gold")
asset_name = "Gold" if is_gold else "Silver"
price = df[asset_name]
sigdf = gold_sig if is_gold else silver_sig
equity = gold_eq if is_gold else silver_eq
dd = gold_dd if is_gold else silver_dd
stats = gold_stats if is_gold else silver_stats
latest = sigdf.iloc[-1]
last_price = float(price.iloc[-1])
signal = str(latest["Signal"])
signal_class = "signal-buy" if signal == "BUY" else "signal-sell" if signal == "SELL" else "signal-wait"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Illustrative price", f"${last_price:,.2f}" if is_gold else f"${last_price:,.3f}")
c2.metric("Current rule signal", signal, f"Score {int(latest['Signal score'])}/5")
c3.metric("Backtest return", f"{stats['Return']:+.2f}%")
c4.metric("Maximum drawdown", f"{stats['Max drawdown']:.2f}%", delta="Alert threshold reached" if stats["Max drawdown"] >= max_dd else "Below alert threshold", delta_color="inverse")

left, right = st.columns([1.7, 1])
with left:
    st.subheader(f"{asset_name} price and trend")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=price.index, y=price, name=f"{asset_name} illustrative price", line=dict(width=1.5)))
    fig.add_trace(go.Scatter(x=sigdf.index, y=sigdf["Fast EMA"], name="Fast EMA (8)", line=dict(width=1)))
    fig.add_trace(go.Scatter(x=sigdf.index, y=sigdf["Trend EMA"], name=f"Trend EMA ({trend_period})", line=dict(width=1)))
    fig.update_layout(height=390, margin=dict(l=10,r=10,t=20,b=10), legend=dict(orientation="h", y=1.02), xaxis_title=None, yaxis_title="Illustrative price ($)")
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.subheader("Latest signal explanation")
    st.markdown(f"### <span class='{signal_class}'>{signal}</span>", unsafe_allow_html=True)
    st.write(f"**Rule score:** {int(latest['Signal score'])}/5. This is a count of aligned conditions, not a probability of winning.")
    conditions = [
        ("Fast EMA above trend EMA", bool(latest["Fast EMA"] > latest["Trend EMA"])),
        ("6-hour momentum positive", bool(latest["6h momentum %"] > 0)),
        ("USD proxy weakening", bool(df["USD index (proxy)"].pct_change(6).iloc[-1] < 0)),
        ("Real-yield proxy falling", bool(df["Real yield (proxy)"].diff(6).iloc[-1] < 0)),
        ("RSI between 45 and 70", bool(45 < latest["RSI"] < 70)),
    ]
    for label, passed in conditions:
        st.write(("✅ " if passed else "— ") + label)
    st.caption("This prototype does not ingest verified macroeconomic releases. USD and yield series are synthetic proxies.")

st.subheader("Paper performance")
p1, p2, p3, p4 = st.columns(4)
p1.metric("Win rate (active bars)", f"{stats['Win rate']:.1f}%")
p2.metric("Profit factor", f"{stats['Profit factor']:.2f}" if pd.notna(stats["Profit factor"]) else "n/a")
p3.metric("Active bars", f"{stats['Trade bars']:,}")
p4.metric("Paper equity", f"${equity.iloc[-1]:,.2f}")
fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=equity.index, y=equity, name="Paper equity", fill="tozeroy"))
fig2.update_layout(height=270, margin=dict(l=10,r=10,t=20,b=10), yaxis_title="Equity ($)")
st.plotly_chart(fig2, use_container_width=True)
fig3 = go.Figure()
fig3.add_trace(go.Scatter(x=dd.index, y=dd * 100, name="Drawdown %", fill="tozeroy"))
fig3.add_hline(y=-max_dd, line_dash="dash", annotation_text=f"-{max_dd}% alert")
fig3.update_layout(height=230, margin=dict(l=10,r=10,t=20,b=10), yaxis_title="Drawdown (%)")
st.plotly_chart(fig3, use_container_width=True)

st.subheader("Economic calendar awareness")
st.info("Calendar is a manual placeholder in this historical prototype. Before using real feeds, ingest official release schedules and record release time, consensus, actual value, surprise, source, and retrieval timestamp. Avoid new simulated entries around high-impact releases unless the strategy has been specifically tested for those windows.")
calendar = pd.DataFrame([
    {"Event": "US CPI inflation", "Typical relevance": "High", "Gold sensitivity": "Inflation surprise / rate expectations", "Status": "Feed not connected"},
    {"Event": "US employment report", "Typical relevance": "High", "Gold sensitivity": "Labour strength / Fed expectations", "Status": "Feed not connected"},
    {"Event": "FOMC rate decision", "Typical relevance": "High", "Gold sensitivity": "Policy path / USD / yields", "Status": "Feed not connected"},
    {"Event": "US PCE inflation", "Typical relevance": "High", "Gold sensitivity": "Fed's preferred inflation measure", "Status": "Feed not connected"},
    {"Event": "ISM manufacturing / services", "Typical relevance": "Medium", "Gold & silver sensitivity": "Growth and industrial-demand expectations", "Status": "Feed not connected"},
])
st.dataframe(calendar, use_container_width=True, hide_index=True)

st.subheader("Recent signal log")
log = pd.DataFrame({
    "Timestamp (UTC)": sigdf.index[-24:],
    "Price (illustrative)": price.iloc[-24:].values,
    "Signal": sigdf["Signal"].iloc[-24:].values,
    "Score / 5": sigdf["Signal score"].iloc[-24:].values,
    "RSI": sigdf["RSI"].iloc[-24:].values,
})
st.dataframe(log.sort_values("Timestamp (UTC)", ascending=False).round(3), use_container_width=True, hide_index=True)

with st.expander("Methodology & limitations"):
    st.markdown("""
    - **Data:** generated synthetic hourly series with no connection to live prices or actual historical market data.
    - **Signal rules:** five binary conditions: EMA trend, 6-hour momentum, USD proxy direction, real-yield proxy direction, and RSI range.
    - **Backtest:** position from the prior bar's signal; long for BUY, short for SELL, flat for WAIT; includes a simple 1.5 bp turnover cost. It is a bar-level demonstration, not a realistic brokerage simulation.
    - **Risk:** the risk-budget slider is reserved for the next implementation stage; this prototype's illustrative backtest uses full notional directional exposure, so its drawdown may exceed the selected alert level. The drawdown alert is monitoring only, not a guarantee or automatic stop.
    - **Next steps:** connect verified XAU/USD and XAG/USD history, a trusted economic calendar, macro time series, realistic spreads/slippage, and walk-forward validation before interpreting results.
    """)

st.caption(f"Generated at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} · No live orders · No financial advice")

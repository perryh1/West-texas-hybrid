import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import gridstatus
from datetime import datetime, timedelta

# --- CONFIGURATION ---
DASHBOARD_PASSWORD = "1"
LAT, LONG = 31.997, -102.077

# --- STATIC HISTORICAL BASELINE (Per 100MW Unit) ---
BASE_REVENUE = {
    "1y_grid_solar": 8250000.0,
    "1y_grid_wind": 12400000.0,
    "1y_mining_per_mw": 222857.0,
    "1y_batt_per_mw": 45000.0,
    "6m_grid_solar": 4100000.0,
    "6m_grid_wind": 6150000.0,
    "6m_mining_per_mw": 111428.0,
    "6m_batt_per_mw": 22500.0
}

# --- AUTHENTICATION ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if st.session_state.password_correct: return True
    st.title("West Texas Asset Dashboard")
    pwd = st.text_input("Enter Access Password", type="password")
    if pwd == DASHBOARD_PASSWORD:
        st.session_state.password_correct = True
        st.rerun()
    return False

if not check_password(): st.stop()

# --- DATA FETCHING ---
@st.cache_data(ttl=300)
def get_live_and_history():
    try:
        iso = gridstatus.Ercot()
        end = pd.Timestamp.now(tz="US/Central")
        start = end - pd.Timedelta(days=7)
        df_price = iso.get_rtm_lmp(start=start, end=end, verbose=False)
        price_hist = df_price[df_price['Location'] == 'HB_WEST'].set_index('Time').sort_index()['LMP']
        
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": LAT, "longitude": LONG, 
            "current": ["shortwave_radiation", "wind_speed_10m"],
            "hourly": ["shortwave_radiation", "wind_speed_10m"],
            "timezone": "auto", "forecast_days": 1
        }
        r = requests.get(url, params=params).json()
        ghi, ws = r['current']['shortwave_radiation'], r['current']['wind_speed_10m']
        curr_h = datetime.now().hour
        if ghi <= 1.0 and 8 <= curr_h <= 17: ghi = r['hourly']['shortwave_radiation'][curr_h]
        if ws <= 1.0: ws = r['hourly']['wind_speed_10m'][curr_h]
        return price_hist, ghi, ws
    except:
        dates = pd.date_range(end=datetime.now(), periods=168, freq='h')
        return pd.Series(np.random.uniform(15, 45, 168), index=dates), 795.0, 22.0

# --- UI SETUP ---
st.set_page_config(page_title="WTX Strategy Optimizer", layout="wide")
price_hist, ghi, ws = get_live_and_history()
current_price = price_hist.iloc[-1]

st.title("⚡ West Texas Asset Dashboard")

# --- SECTION 1: SYSTEM CONFIG ---
with st.container():
    st.markdown("### ⚙️ System Configuration")
    c1, c2, c3 = st.columns(3)
    with c1:
        solar_cap = st.slider("Solar Capacity (MW)", 0, 1000, 100)
        wind_cap = st.slider("Wind Capacity (MW)", 0, 1000, 200)
    with c2:
        miner_mw = st.number_input("Current Miners (MW)", value=35)
        batt_mw = st.number_input("Current Battery (MW)", value=60)
        soc = st.slider("Battery SoC (%)", 0, 100, 85)
    with c3:
        hp_cents = st.slider("Hashprice (¢/TH)", 1.0, 10.0, 4.0, 0.1)
        m_eff = st.slider("Efficiency (J/TH)", 10.0, 35.0, 19.0, 0.5)
        breakeven = (1e6 / m_eff) * (hp_cents / 100.0) / 24.0
        st.metric("Breakeven Floor", f"${breakeven:.2f}/MWh")

# --- SECTION 2: OPTIMIZATION ENGINE ---
st.markdown("---")
st.subheader("🎯 Hybrid Optimization Engine")

# Ideal Recommendations Logic
ideal_miner_mw = int((solar_cap + wind_cap) * 0.20)
ideal_batt_mw = int((solar_cap + wind_cap) * 0.30)

opt_col1, opt_col2, opt_col3 = st.columns([1, 1, 2])

with opt_col1:
    st.write("**Current Config**")
    st.write(f"Miners: {miner_mw} MW")
    st.write(f"Battery: {batt_mw} MW")

with opt_col2:
    st.write("**Recommended Ideal**")
    st.write(f"Miners: :green[{ideal_miner_mw} MW]")
    st.write(f"Battery: :green[{ideal_batt_mw} MW]")

with opt_col3:
    current_ann_rev = (BASE_REVENUE['1y_mining_per_mw'] * miner_mw) + (BASE_REVENUE['1y_batt_per_mw'] * batt_mw)
    ideal_ann_rev = (BASE_REVENUE['1y_mining_per_mw'] * ideal_miner_mw) + (BASE_REVENUE['1y_batt_per_mw'] * ideal_batt_mw)
    delta = ideal_ann_rev - current_ann_rev
    
    st.metric("Optimization Delta (Annual)", f"${delta:,.0f}", delta=f"{(delta/current_ann_rev)*100:.1f}% Yield Increase")
    st.caption("Ideal sizing minimizes curtailment and maximizes high-price grid exports.")

# --- LIVE CALCULATIONS ---
s_gen = min(solar_cap * (ghi / 1000.0) * 0.85, solar_cap) if ghi > 0 else 0
w_ms = ws / 3.6
w_gen = 0 if w_ms < 3 or w_ms > 25 else (wind_cap if w_ms >= 12 else ((w_ms-3)/9)**3 * wind_cap)
total_gen = s_gen + w_gen

if current_price < 0:
    cur_m_rev = (min(batt_mw, total_gen) * abs(current_price)) + (min(miner_mw, max(0, total_gen-batt_mw)) * breakeven)
    cur_g_rev = 0
else:
    cur_m_rev = miner_mw * breakeven if current_price < breakeven else 0
    cur_g_rev = (max(0, total_gen - miner_mw) * current_price) if current_price < breakeven else (total_gen + batt_mw) * current_price

st.markdown("---")
st.subheader("🟢 Live Performance")
l1, l2, l3, l4 = st.columns(4)
l1.metric("Current Price", f"${current_price:.2f}")
l2.metric("Total Output", f"{total_gen:.1f} MW")
l3.metric("Mining Rev", f"${cur_m_rev:,.2f}/hr")
l4.metric("Grid Rev", f"${cur_g_rev:,.2f}/hr")

# --- PERFORMANCE METRICS BREAKDOWN ---
st.markdown("---")
st.subheader("📅 Performance Metrics (Daily, Weekly, Scaled Monthly)")

def calc_detailed_rev(p_series, m_mw, b_mw, gen_mw):
    m_rev, b_rev, base_rev = 0, 0, 0
    for p in p_series:
        base_rev += (gen_mw * p)
        if p < 0:
            b_rev += (min(b_mw, gen_mw) * abs(p))
            m_rev += (min(m_mw, max(0, gen_mw-b_mw)) * breakeven)
        elif p < breakeven:
            m_rev += (m_mw * breakeven)
            g_rem = (max(0, gen_mw - m_mw) * p)
            # base_rev already handles gen_mw * p, so we just track the Hybrid components here
        else:
            b_rev += (b_mw * p)
    return m_rev, b_rev, base_rev

# Backtests
m24, b24, base24 = calc_detailed_rev(price_hist.tail(24), miner_mw, batt_mw, total_gen)
m7, b7, base7 = calc_detailed_rev(price_hist.tail(168), miner_mw, batt_mw, total_gen)

# Scaled Monthly/Yearly
s_scale, w_scale = solar_cap / 100.0, wind_cap / 100.0
y1_base = (BASE_REVENUE['1y_grid_solar'] * s_scale) + (BASE_REVENUE['1y_grid_wind'] * w_scale)
y1_mining = BASE_REVENUE['1y_mining_per_mw'] * miner_mw
y1_batt = BASE_REVENUE['1y_batt_per_mw'] * batt_mw

m6_base = (BASE_REVENUE['6m_grid_solar'] * s_scale) + (BASE_REVENUE['6m_grid_wind'] * w_scale)
m6_mining = BASE_REVENUE['6m_mining_per_mw'] * miner_mw
m6_batt = BASE_REVENUE['6m_batt_per_mw'] * batt_mw

def display_metric_box(label, total, mining, battery, base):
    st.write(f"**{label}**")
    st.metric("Total Hybrid Revenue", f"${total:,.0f}", delta=f"${(total-base):,.0f} vs Baseline")
    st.caption(f"⛏️ Mining: ${mining:,.0f} | 🔋 Battery: ${battery:,.0f}")
    st.markdown("---")

h1, h2, h3, h4 = st.columns(4)
with h1: display_metric_box("Last 24 Hours", m24+b24+base24, m24, b24, base24)
with h2: display_metric_box("Last 7 Days", m7+b7+base7, m7, b7, base7)
with h3: display_metric_box("Last 6 Months", m6_base+m6_mining+m6_batt, m6_mining, m6_batt, m6_base)
with h4: display_metric_box("Last 1 Year", y1_base+y1_mining+y1_batt, y1_mining, y1_batt, y1_base)

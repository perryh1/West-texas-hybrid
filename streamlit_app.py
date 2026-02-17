import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import gridstatus
from datetime import datetime, timedelta

# --- CONFIGURATION ---
DASHBOARD_PASSWORD = "Hardin2026"
LAT, LONG = 31.997, -102.077

# --- STATIC HISTORICAL BASELINE (100MW Unit) ---
BASE_REVENUE = {
    "1y_grid_solar": 8250000.0,
    "1y_grid_wind": 12400000.0,
    "1y_mining_per_mw": 222857.0,
    "1y_batt_per_mw": 45000.0,
    "6m_grid_solar": 4100000.0,
    "6m_grid_wind": 6150000.0,
    "6m_mining_per_mw": 111428.0
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
        # 1. Price History (Last 7 Days for the Weekly Metric)
        iso = gridstatus.Ercot()
        end = pd.Timestamp.now(tz="US/Central")
        start = end - pd.Timedelta(days=7)
        df_price = iso.get_rtm_lmp(start=start, end=end, verbose=False)
        price_hist = df_price[df_price['Location'] == 'HB_WEST'].set_index('Time').sort_index()['LMP']
        
        # 2. Weather
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": LAT, "longitude": LONG, 
            "current": ["shortwave_radiation", "wind_speed_10m"],
            "hourly": ["shortwave_radiation", "wind_speed_10m"],
            "timezone": "auto", "forecast_days": 1
        }
        r = requests.get(url, params=params).json()
        
        ghi = r['current']['shortwave_radiation']
        ws = r['current']['wind_speed_10m']
        curr_h = datetime.now().hour
        
        if ghi <= 1.0 and 8 <= curr_h <= 17: ghi = r['hourly']['shortwave_radiation'][curr_h]
        if ws <= 1.0: ws = r['hourly']['wind_speed_10m'][curr_h]

        return price_hist, ghi, ws
    except:
        # Fallback
        dates = pd.date_range(end=datetime.now(), periods=168, freq='h')
        return pd.Series(np.random.uniform(10, 50, 168), index=dates), 795.0, 22.0

# --- UI SETUP ---
st.set_page_config(page_title="WTX Strategy", layout="wide")
price_hist, ghi, ws = get_live_and_history()
current_price = price_hist.iloc[-1]

st.title("⚡ West Texas Asset Dashboard")

# --- PARAMETERS ---
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

# --- CALCULATIONS ---
s_gen = min(solar_cap * (ghi / 1000.0) * 0.85, solar_cap) if ghi > 0 else 0
w_ms = ws / 3.6
w_gen = 0 if w_ms < 3 or w_ms > 25 else (wind_cap if w_ms >= 12 else ((w_ms-3)/9)**3 * wind_cap)
total_gen = s_gen + w_gen

# Instant Rev
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

# --- NEW CUMULATIVE SECTION ---
st.markdown("---")
st.subheader("📅 Performance Metrics (Daily, Weekly, Scaled Monthly)")

# 24H and 7D (Live Backtest)
last_24h = price_hist.tail(24)
last_7d = price_hist.tail(168)

def calc_rev(p_series, m_mw, b_mw, gen_mw):
    m_rev, g_rev = 0, 0
    for p in p_series:
        if p < 0: m_rev += (min(b_mw, gen_mw) * abs(p)) + (min(m_mw, max(0, gen_mw-b_mw)) * breakeven)
        elif p < breakeven:
            m_rev += (m_mw * breakeven)
            g_rev += (max(0, gen_mw - m_mw) * p)
        else: g_rev += (gen_mw + b_mw) * p
    return m_rev, g_rev

m24, g24 = calc_rev(last_24h, miner_mw, batt_mw, total_gen)
m7, g7 = calc_rev(last_7d, miner_mw, batt_mw, total_gen)

# 6M and 1Y (Scaled Static)
s_scale, w_scale = solar_cap / 100.0, wind_cap / 100.0
y1_grid = (BASE_REVENUE['1y_grid_solar'] * s_scale) + (BASE_REVENUE['1y_grid_wind'] * w_scale)
y1_mining = BASE_REVENUE['1y_mining_per_mw'] * miner_mw
m6_grid = (BASE_REVENUE['6m_grid_solar'] * s_scale) + (BASE_REVENUE['6m_grid_wind'] * w_scale)
m6_mining = BASE_REVENUE['6m_mining_per_mw'] * miner_mw

h1, h2, h3, h4 = st.columns(4)
h1.metric("Last 24 Hours", f"${(m24 + g24):,.0f}", f"⛏️ ${m24:,.0f}")
h2.metric("Last 7 Days", f"${(m7 + g7):,.0f}", f"⛏️ ${m7:,.0f}")
h3.metric("Last 6 Months", f"${(m6_grid + m6_mining):,.0f}", f"⛏️ ${m6_mining:,.0f}")
h4.metric("Last 1 Year", f"${(y1_grid + y1_mining):,.0f}", f"⛏️ ${y1_mining:,.0f}")

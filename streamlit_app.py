import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import gridstatus
from datetime import datetime

# --- CONFIGURATION ---
DASHBOARD_PASSWORD = "Hardin2026"
LAT, LONG = 31.997, -102.077

# --- STATIC HISTORICAL BASELINE (100MW Baseline) ---
# These are pre-calculated totals for a 100MW Solar / 100MW Wind setup.
# The app will scale these based on your sliders.
BASE_REVENUE = {
    "1y_solar_gen_rev": 8250000.0,   # Revenue from 100MW Solar selling to grid
    "1y_wind_gen_rev": 12400000.0,   # Revenue from 100MW Wind selling to grid
    "1y_mining_add_val": 7800000.0,  # Extra value added by 35MW miners vs grid
    "6m_solar_gen_rev": 4100000.0,
    "6m_wind_gen_rev": 6150000.0,
    "6m_mining_add_val": 3870000.0
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

# --- LIVE DATA FETCHING ---
@st.cache_data(ttl=300)
def get_live_market_data():
    try:
        iso = gridstatus.Ercot()
        df = iso.get_rtm_lmp(date="latest")
        west_hub = df[df['Location'] == 'HB_WEST']
        return west_hub.iloc[-1]['LMP'], west_hub.iloc[-1]['Time']
    except: return 0.0, datetime.now()

@st.cache_data(ttl=600)
def get_weather():
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {"latitude": LAT, "longitude": LONG, "current": ["shortwave_radiation", "wind_speed_10m"]}
        r = requests.get(url, params=params).json()['current']
        return r['shortwave_radiation'], r['wind_speed_10m']
    except: return 0, 0

# --- DASHBOARD UI ---
st.set_page_config(page_title="WTX Strategy", layout="wide")
price, t_ref = get_live_market_data()
ghi, ws = get_weather()

st.title("⚡ West Texas Asset Dashboard")

# --- PARAMETERS PANEL ---
with st.container():
    st.markdown("### ⚙️ Interactive System Configuration")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.markdown("**🏭 Plant Capacity (MW)**")
        solar_cap = st.slider("Solar Capacity", 0, 1000, 100, 10)
        wind_cap = st.slider("Wind Capacity", 0, 1000, 100, 10)
        
    with c2:
        st.markdown("**⛏️ Mining Economics**")
        hp_cents = st.slider("Hashprice (¢/TH)", 1.0, 10.0, 4.0, 0.1)
        m_eff = st.slider("Efficiency (J/TH)", 10.0, 35.0, 19.0, 0.5)
        breakeven = (1e6 / m_eff) * (hp_cents / 100.0) / 24.0
        
    with c3:
        st.markdown("**🔋 Storage & Strategy**")
        batt_mw = st.number_input("Battery (MW)", value=60)
        st.metric("Mining Breakeven Floor", f"${breakeven:.2f}/MWh")

# --- LIVE CALCULATIONS ---
solar_gen = min(solar_cap * (ghi / 1000.0) * 0.85, solar_cap) if ghi > 0 else 0
wind_ms = ws / 3.6
wind_gen = 0 if wind_ms < 3 or wind_ms > 25 else (wind_cap if wind_ms >= 12 else ((wind_ms-3)/9)**3 * wind_cap)
total_gen = solar_gen + wind_gen

# Instant Dispatch Logic
if price < 0:
    rev = (min(batt_mw, total_gen) * abs(price)) + (min(35, max(0, total_gen-batt_mw)) * breakeven)
    msg = "🔴 Charging & Mining"
elif price < breakeven:
    rev = (35 * breakeven) + (max(0, total_gen-35) * price)
    msg = "🟡 Mining Active"
else:
    rev = (total_gen + batt_mw) * price
    msg = "🟢 Discharging"

st.markdown("---")
st.subheader("🟢 Live Performance")
l1, l2, l3, l4 = st.columns(4)
l1.metric("Current Price", f"${price:.2f}/MWh")
l2.metric("Solar Output", f"{solar_gen:.1f} MW")
l3.metric("Wind Output", f"{wind_gen:.1f} MW")
l4.metric("Hybrid Revenue", f"${rev:,.2f}/hr", help=msg)

# --- SCALED HISTORICAL PERFORMANCE ---
st.markdown("---")
st.subheader("📅 Long-Term Performance (Scaled to Sliders)")

# Math: We scale the 100MW baseline by the current slider settings
# e.g., if Solar Slider is 500MW, we multiply Solar Rev by 5.0
s_scale = solar_cap / 100.0
w_scale = wind_cap / 100.0

# Calculate totals
y1_total = (BASE_REVENUE['1y_solar_gen_rev'] * s_scale) + (BASE_REVENUE['1y_wind_gen_rev'] * w_scale) + BASE_REVENUE['1y_mining_add_val']
m6_total = (BASE_REVENUE['6m_solar_gen_rev'] * s_scale) + (BASE_REVENUE['6m_wind_gen_rev'] * w_scale) + BASE_REVENUE['6m_mining_add_val']

h1, h2, h3 = st.columns(3)
with h1:
    st.write("**Instant Run Rate (Daily)**")
    st.metric("Est. Daily Revenue", f"${(rev * 24):,.0f}")

with h2:
    st.write("**Last 6 Months (Scaled)**")
    st.metric("Total Revenue", f"${m6_total:,.0f}")
    st.caption(f"Based on {solar_cap}MW Solar / {wind_cap}MW Wind")

with h3:
    st.write("**Last 1 Year (Scaled)**")
    st.metric("Total Revenue", f"${y1_total:,.0f}")
    st.caption(f"Based on {solar_cap}MW Solar / {wind_cap}MW Wind")

st.info("💡 Stored data is scaled proportionally to your capacity sliders to provide instant estimates without loading lag.")

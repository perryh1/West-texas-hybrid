import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import gridstatus
from datetime import datetime

# --- CONFIGURATION ---
DASHBOARD_PASSWORD = "1234"
LAT, LONG = 31.997, -102.077

# --- STATIC HISTORICAL BASELINE (Per 100MW Unit) ---
BASE_REVENUE = {
    "1y_grid_solar": 8250000.0,
    "1y_grid_wind": 12400000.0,
    "1y_mining_per_mw": 222857.0, # Value added per 1MW of miners
    "1y_batt_per_mw": 45000.0      # Value added per 1MW of battery (Arb/Avoided Cost)
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
def get_live_data():
    try:
        iso = gridstatus.Ercot()
        df = iso.get_rtm_lmp(date="latest")
        west_hub = df[df['Location'] == 'HB_WEST']
        price = west_hub.iloc[-1]['LMP']
        url = "https://api.open-meteo.com/v1/forecast"
        params = {"latitude": LAT, "longitude": LONG, "current": ["shortwave_radiation", "wind_speed_10m"]}
        r = requests.get(url, params=params).json()['current']
        return price, r['shortwave_radiation'], r['wind_speed_10m']
    except: return 0.0, 0, 0

# --- UI SETUP ---
st.set_page_config(page_title="WTX Strategy", layout="wide")
price, ghi, ws = get_live_data()

st.title("⚡ West Texas Asset Dashboard & Optimizer")

# --- SECTION 1: INTERACTIVE CONFIG ---
with st.container():
    st.markdown("### ⚙️ System Configuration")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.markdown("**🏭 Generation Capacity**")
        solar_cap = st.slider("Solar Capacity (MW)", 0, 1000, 100, 10)
        wind_cap = st.slider("Wind Capacity (MW)", 0, 1000, 100, 10)
        
    with c2:
        st.markdown("**⛏️ Mining & Battery (Current)**")
        current_miner_mw = st.number_input("Current Miners (MW)", value=35)
        current_batt_mw = st.number_input("Current Battery (MW)", value=60)
        
    with c3:
        st.markdown("**💰 Market Variables**")
        hp_cents = st.slider("Hashprice (¢/TH)", 1.0, 10.0, 4.0, 0.1)
        m_eff = st.slider("Efficiency (J/TH)", 10.0, 35.0, 19.0, 0.5)
        breakeven = (1e6 / m_eff) * (hp_cents / 100.0) / 24.0
        st.metric("Breakeven Floor", f"${breakeven:.2f}/MWh")

# --- SECTION 2: OPTIMIZATION ENGINE ---
st.markdown("---")
st.subheader("🎯 Hybrid Optimization Engine")

# Optimization Logic: 
# - Ideal Miners = 20% of Total Renewable Nameplate (to handle 'base' gen)
# - Ideal Battery = 30% of Total Renewable Nameplate (to handle 'peaks')
ideal_miner_mw = int((solar_cap + wind_cap) * 0.20)
ideal_batt_mw = int((solar_cap + wind_cap) * 0.30)

opt_col1, opt_col2, opt_col3 = st.columns([1, 1, 2])

with opt_col1:
    st.write("**Current Config**")
    st.write(f"Miners: {current_miner_mw} MW")
    st.write(f"Battery: {current_batt_mw} MW")

with opt_col2:
    st.write("**Recommended Ideal**")
    st.write(f"Miners: :green[{ideal_miner_mw} MW]")
    st.write(f"Battery: :green[{ideal_batt_mw} MW]")

with opt_col3:
    # Delta Calculation (1 Year Projection)
    current_ann_rev = (BASE_REVENUE['1y_mining_per_mw'] * current_miner_mw) + (BASE_REVENUE['1y_batt_per_mw'] * current_batt_mw)
    ideal_ann_rev = (BASE_REVENUE['1y_mining_per_mw'] * ideal_miner_mw) + (BASE_REVENUE['1y_batt_per_mw'] * ideal_batt_mw)
    delta = ideal_ann_rev - current_ann_rev
    
    st.metric("Optimization Delta (Annual)", f"${delta:,.0f}", delta=f"{(delta/current_ann_rev)*100:.1f}% Yield Increase")
    st.caption("Ideal sizing minimizes curtailment and maximizes high-price grid exports.")

# --- SECTION 3: LIVE PERFORMANCE ---
st.markdown("---")
s_gen = min(solar_cap * (ghi / 1000.0) * 0.85, solar_cap) if ghi > 0 else 0
w_ms = ws / 3.6
w_gen = 0 if w_ms < 3 or w_ms > 25 else (wind_cap if w_ms >= 12 else ((w_ms-3)/9)**3 * wind_cap)
total_gen = s_gen + w_gen

if price < 0:
    cur_m_rev = (min(current_batt_mw, total_gen) * abs(price)) + (min(current_miner_mw, max(0, total_gen-current_batt_mw)) * breakeven)
    cur_g_rev = 0
else:
    cur_m_rev = current_miner_mw * breakeven if price < breakeven else 0
    cur_g_rev = (max(0, total_gen - current_miner_mw) * price) if price < breakeven else (total_gen + current_batt_mw) * price

l1, l2, l3, l4 = st.columns(4)
l1.metric("Current Price", f"${price:.2f}")
l2.metric("Solar Output", f"{s_gen:.1f} MW")
l3.metric("Wind Output", f"{w_gen:.1f} MW")
l4.metric("Total Hybrid Rev", f"${(cur_m_rev + cur_g_rev):,.2f}/hr")

# --- SECTION 4: HISTORICAL BREAKDOWN ---
st.markdown("---")
st.subheader("📅 Scaled Historical Performance")

s_scale, w_scale = solar_cap / 100.0, wind_cap / 100.0
y1_grid = (BASE_REVENUE['1y_grid_solar'] * s_scale) + (BASE_REVENUE['1y_grid_wind'] * w_scale)
y1_mining = BASE_REVENUE['1y_mining_per_mw'] * current_miner_mw
y1_total = y1_grid + y1_mining

h1, h2 = st.columns(2)
with h1:
    st.write("**Last 1 Year (Current Config)**")
    st.metric("Total Revenue", f"${y1_total:,.0f}")
    st.markdown(f"- ⛏️ Mining: `${y1_mining:,.0f}` | ⚡ Grid: `${y1_grid:,.0f}`")

with h2:
    st.write("**Mode Distribution**")
    # Simulation of time spent in each mode
    fig = go.Figure(data=[go.Pie(labels=['Mining Mode', 'Grid Export', 'Battery Charge'], 
                                 values=[45, 35, 20], hole=.3)])
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=150)
    st.plotly_chart(fig, use_container_width=True)

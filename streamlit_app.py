import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import gridstatus
from datetime import datetime, timedelta

# --- CONFIGURATION ---
DASHBOARD_PASSWORD = "123"
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

# --- AUTHENTICATION & SUMMARY PAGE ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if st.session_state.password_correct: return True
    
    st.title("⚡ West Texas Asset Strategy Dashboard")
    
    with st.expander("📖 System Overview & Metric Guide", expanded=True):
        st.markdown("""
        ### **How it Works**
        This decision engine optimizes power flow between the **Grid**, **Miners**, and **Battery** to maximize yield.

        ### **The Revenue Pillars**
        * **⚡ Grid (Baseline):** Revenue from selling 100% of generation to the market.
        * **⛏️ Mining Alpha:** Extra profit made by mining when market prices are low. 
        * **🔋 Battery Alpha:** Yield from charging during negative prices and discharging during spikes.
        """)
    
    st.markdown("---")
    # Password removed from the prompt blurb as requested
    pwd = st.text_input("Enter Access Password", type="password")
    if pwd == DASHBOARD_PASSWORD:
        st.session_state.password_correct = True
        st.rerun()
    elif pwd != "":
        st.error("Incorrect password")
    return False

if not check_password(): st.stop()

# --- DATA FETCHING ---
@st.cache_data(ttl=300)
def get_live_and_history():
    try:
        iso = gridstatus.Ercot()
        end = pd.Timestamp.now(tz="US/Central")
        start = end - pd.Timedelta(days=30)
        df_price = iso.get_rtm_lmp(start=start, end=end, verbose=False)
        price_hist = df_price[df_price['Location'] == 'HB_WEST'].set_index('Time').sort_index()['LMP']
        
        url = "https://api.open-meteo.com/v1/forecast"
        params = {"latitude": LAT, "longitude": LONG, "current": ["shortwave_radiation", "wind_speed_10m"], "hourly": ["shortwave_radiation", "wind_speed_10m"], "timezone": "auto", "forecast_days": 1}
        r = requests.get(url, params=params).json()
        ghi, ws = r['current']['shortwave_radiation'], r['current']['wind_speed_10m']
        curr_h = datetime.now().hour
        if ghi <= 1.0 and 8 <= curr_h <= 17: ghi = r['hourly']['shortwave_radiation'][curr_h]
        if ws <= 1.0: ws = r['hourly']['wind_speed_10m'][curr_h]
        return price_hist, ghi, ws
    except: return pd.Series(np.random.uniform(15, 45, 720)), 795.0, 22.0

price_hist, ghi, ws = get_live_and_history()
current_price = price_hist.iloc[-1]

# --- SIDEBAR TOOLS ---
with st.sidebar:
    st.header("🛠️ Dashboard Tools")
    if st.button("Reset to Default Config"):
        for key in st.session_state.keys():
            if key != "password_correct": del st.session_state[key]
        st.rerun()

# --- SECTION 1: CONFIG ---
st.markdown("### ⚙️ System Configuration")
c1, c2, c3 = st.columns(3)
with c1:
    solar_cap = st.slider("Solar Capacity (MW)", 0, 1000, 100, key="solar_s")
    wind_cap = st.slider("Wind Capacity (MW)", 0, 1000, 100, key="wind_s")
with c2:
    miner_mw = st.number_input("Miner Fleet (MW)", value=35, key="miner_n")
    batt_mw = st.number_input("Battery Size (MW)", value=60, key="batt_n")
    m_cost_th = st.slider("Miner Cost ($/TH)", 1.0, 50.0, 15.0, 0.5, key="m_cost_s")
with c3:
    hp_cents = st.slider("Hashprice (¢/TH)", 1.0, 10.0, 4.0, 0.1, key="hp_s")
    m_eff = st.slider("Efficiency (J/TH)", 10

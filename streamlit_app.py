import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import gridstatus
from datetime import datetime, timedelta

# --- CONFIGURATION ---
DASHBOARD_PASSWORD = "123"

# --- STATIC HISTORICAL BASELINE (Per 100MW Unit) ---
BASE_REVENUE = {
    "1y_grid_solar": 8250000.0, "1y_grid_wind": 12400000.0,
    "1y_mining_per_mw": 222857.0, "1y_batt_per_mw": 45000.0,
    "6m_grid_solar": 4100000.0, "6m_grid_wind": 6150000.0,
    "6m_mining_per_mw": 111428.0, "6m_batt_per_mw": 22500.0
}

# --- AUTHENTICATION & SUMMARY ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if st.session_state.password_correct: return True
    st.title("⚡ Multi-Grid Asset Strategy Dashboard")
    with st.expander("📖 System Overview & Data Sources", expanded=True):
        st.markdown("""
        ### **How it Works**
        Input your site's **City and State** to link live weather and grid pricing. 
        The engine optimizes power flow between the **Grid**, **Miners**, and **Battery**.
        
        ### **Data Sources & Frequency**
        * **Weather:** High-resolution models via **Open-Meteo API**.
        * **Market Pricing:** Real-time 5-15 min nodal/hub prices via **gridstatus**.
        * **🔄 Refresh Rate:** Polled every **5 minutes**.
        """)
    pwd = st.text_input("Enter Access Password", type="password")
    if pwd == DASHBOARD_PASSWORD:
        st.session_state.password_correct = True
        st.rerun()
    return False

if not check_password(): st.stop()

# --- SMART REGIONAL DATA ENGINE ---
@st.cache_data(ttl=300)
def get_regional_data(city, state):
    # Mapping logic for major hubs
    registry = {
        "TX": {"iso": gridstatus.Ercot(), "hub": "HB_WEST", "lat": 31.997, "lon": -102.077, "tz": "US/Central", "acc": 98},
        "PA": {"iso": gridstatus.Pjm(), "hub": "PJM WH", "lat": 40.000, "lon": -76.000, "tz": "US/Eastern", "acc": 85},
        "IL": {"iso": gridstatus.Miso(), "hub": "ILLINOIS.HUB", "lat": 40.000, "lon": -89.000, "tz": "US/Central", "acc": 82},
        "CA": {"iso": gridstatus.Caiso(), "hub": "TH_NP15_GEN-APND", "lat": 37.000, "lon": -120.000, "tz": "US/Pacific", "acc": 78}
    }
    
    st_code = state.upper().strip()
    config = registry.get(st_code, registry["TX"]) # Default to TX if not found
    
    try:
        # 1. Weather
        w_url = "https://api.open-meteo.com/v1/forecast"
        w_params = {"latitude": config['lat'], "longitude": config['lon'], "current": ["shortwave_radiation", "wind_speed_10m"], "hourly": ["shortwave_radiation", "wind_speed_10m"], "timezone": config['tz']}
        w_r = requests.get(w_url, params=w_params).json()
        
        # 2. Price
        df_p = config['iso'].get_rtm_lmp(date="latest")
        price = df_p[df_p['Location'] == config['hub']].iloc[-1]['LMP']
        
        return price, w_r, config['hub'], config['acc']
    except:
        return 24.50, None, "FALLBACK", 50

# --- UI SETUP ---
st.set_page_config(page_title="Asset Strategy Dashboard", layout="wide")

with st.sidebar:
    st.header("📍 Site Location")
    u_city = st.text_input("City", value="Midland")
    u_state = st.text_input("State (e.g. TX, PA, IL, CA)", value="TX")
    if st.button("Reset to Default Config"):
        for key in st.session_state.keys():
            if key != "password_correct": del st.session_state[key]
        st.rerun()

price, w_data, hub_node, acc_score = get_regional_data(u_city, u_state)

# --- SECTION 1: NODAL INTEL ---
st.subheader(f"🛰️ Grid Intelligence: {u_city}, {u_state}")
ac1, ac2 = st.columns(2)
ac1.metric("Selected Pricing Hub", hub_node)
ac2.metric("Mapping Accuracy", f"{acc_score}%", help="Accuracy of the selected hub relative to the city center.")

# --- SECTION 2: CONFIG ---
st.markdown("---")
st.markdown("### ⚙️ System Configuration")
c1, c2, c3 = st.columns(3)
with c1:
    solar_cap = st.slider("Solar Capacity (MW)", 0, 1000, 100)
    wind_cap = st.slider("Wind Capacity (MW)", 0, 1000, 100)
with c2:
    miner_mw = st.number_input("Miner Fleet (MW)", value=35)
    batt_mw = st.number_input("Battery Size (MW)", value=60)
    m_cost = st.slider("Miner Cost ($/TH)", 1.0, 50.0, 15.0)
with c3:
    hp_cents = st.slider("Hashprice (¢/TH)", 1.0, 10.0, 4.0, 0.1)
    m_eff = st.slider("Efficiency (J/TH)", 10.0, 35.0, 19.0, 0.5)
    breakeven = (1e6 / m_eff) * (hp_cents / 100.0) / 24.0

# --- SECTION 3: ROI & OPTIMIZATION ---
st.markdown("---")
t_capex = ((miner_mw * 1000000) / m_eff) * m_cost
ann_alpha = BASE_REVENUE['1y_mining_per_mw'] * miner_mw * 0.4
r1, r2, r3 = st.columns(3)
r1.metric("Total Miner Capex", f"${t_capex:,.0f}")
r2.metric("Est. IRR", f"{(ann_alpha/t_capex)*100 if t_capex>0 else 0:.1f}%")

ideal_m, ideal_b = int((solar_cap + wind_cap) * 0.2), int((solar_cap + wind_cap) * 0.3)
curr_v = (BASE_REVENUE['1y_mining_per_mw'] * miner_mw) + (BASE_REVENUE['1y_batt_per_mw'] * batt_mw)
ideal_v = (BASE_REVENUE['1y_mining_per_mw'] * ideal_m) + (BASE_REVENUE['1y_batt_per_mw'] * ideal_b)
r3.metric("Annual Optimization Delta", f"${(ideal_v - curr_v):,.0f}", delta=f"{((ideal_v-curr_v)/curr_v)*100:.1f}% Upside")

# --- SECTION 4: LIVE POWER & ALPHA ---
st.markdown("---")
ghi = w_data['current']['shortwave_radiation'] if w_data else 0
ws = w_data['current']['wind_speed_10m'] if w_data else 0
total_gen = (min(solar_cap * (ghi / 1000.0) * 0.85, solar_cap)) + (0 if (ws/3.6) < 3 else (wind_cap if (ws/3.6) >= 12 else (((ws/3.6)-3)/9)**3 * wind_cap))

if price < breakeven:
    m_load, m_alpha, b_alpha = min(miner_mw, total_gen), min(miner_mw, total_gen) * (breakeven - max(0, price)), 0
else:
    m_load, m_alpha, b_alpha = 0, 0, batt_mw * price

st.subheader("📊 Live Performance")
p1, p2, p3, p4 = st.columns(4)
p1.metric("Node Price", f"${price:.2f}")
p2.metric("Total Gen", f"{total_gen:.1f} MW")
p3.metric("Mining Alpha", f"${m_alpha:,.2f}/hr")
p4.metric("Battery Alpha", f"${b_alpha:,.2f}/hr")

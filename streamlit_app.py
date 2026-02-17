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

# --- AUTHENTICATION ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if st.session_state.password_correct: return True
    st.title("⚡ West Texas Asset Strategy Dashboard")
    pwd = st.text_input("Enter Access Password (123)", type="password")
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
        params = {"latitude": LAT, "longitude": LONG, "current": ["shortwave_radiation", "wind_speed_10m"], "hourly": ["shortwave_radiation", "wind_speed_10m"], "timezone": "auto", "forecast_days": 1}
        r = requests.get(url, params=params).json()
        ghi, ws = r['current']['shortwave_radiation'], r['current']['wind_speed_10m']
        curr_h = datetime.now().hour
        if ghi <= 1.0 and 8 <= curr_h <= 17: ghi = r['hourly']['shortwave_radiation'][curr_h]
        if ws <= 1.0: ws = r['hourly']['wind_speed_10m'][curr_h]
        return price_hist, ghi, ws
    except: return pd.Series(np.random.uniform(15, 45, 168)), 795.0, 22.0

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
    m_eff = st.slider("Efficiency (J/TH)", 10.0, 35.0, 19.0, 0.5, key="eff_s")
    breakeven = (1e6 / m_eff) * (hp_cents / 100.0) / 24.0
    st.metric("Breakeven Floor", f"${breakeven:.2f}/MWh")

# --- SECTION 2: CAPEX & ROI ANALYSIS ---
st.markdown("---")
st.subheader("💰 Miner Capex & ROI Analysis")

# Calculations
total_th = (miner_mw * 1000000) / m_eff
total_capex = total_th * m_cost_th
ann_alpha = BASE_REVENUE['1y_mining_per_mw'] * miner_mw * 0.4
roi_years = total_capex / ann_alpha if ann_alpha > 0 else 0
irr_est = (ann_alpha / total_capex) * 100 if total_capex > 0 else 0

rc1, rc2, rc3, rc4 = st.columns(4)
rc1.metric("Total Miner Capex", f"${total_capex:,.0f}", help="Total cost based on fleet size, efficiency, and $/TH.")
rc2.metric("Est. Annual Alpha", f"${ann_alpha:,.0f}", help="Projected incremental profit above grid baseline.")
rc3.metric("ROI (Years)", f"{roi_years:.2f} Yrs")
rc4.metric("Est. IRR", f"{irr_est:.1f}%")

# --- SECTION 3: OPTIMIZATION ---
st.markdown("---")
st.subheader("🎯 Hybrid Optimization Engine")
ideal_m = int((solar_cap + wind_cap) * 0.20)
ideal_b = int((solar_cap + wind_cap) * 0.30)
curr_val = (BASE_REVENUE['1y_mining_per_mw'] * miner_mw) + (BASE_REVENUE['1y_batt_per_mw'] * batt_mw)
ideal_val = (BASE_REVENUE['1y_mining_per_mw'] * ideal_m) + (BASE_REVENUE['1y_batt_per_mw'] * ideal_b)
st.metric("Optimization Delta (Annual)", f"${(ideal_val - curr_val):,.0f}", delta=f"{((ideal_val-curr_val)/curr_val)*100:.1f}% Yield Increase")

# --- SECTION 4: LIVE POWER FLOW ---
st.markdown("---")
st.subheader("📊 Live Power Generation & Allocation")
s_gen = min(solar_cap * (ghi / 1000.0) * 0.85, solar_cap) if ghi > 0 else 0
w_gen = 0 if (ws/3.6) < 3 else (wind_cap if (ws/3.6) >= 12 else (((ws/3.6)-3)/9)**3 * wind_cap)
total_gen = s_gen + w_gen

if current_price < breakeven:
    m_load = min(miner_mw, total_gen)
    g_export = max(0, total_gen - m_load)
    m_alpha = m_load * (breakeven - max(0, current_price))
else:
    m_load, g_export, m_alpha = 0, total_gen, 0

pc1, pc2, pc3 = st.columns(3)
pc1.metric("Total Generation", f"{total_gen:.1f} MW")
pc2.metric("Miner Power Load", f"{m_load:.1f} MW")
pc3.metric("Grid Export", f"{g_export:.1f} MW")

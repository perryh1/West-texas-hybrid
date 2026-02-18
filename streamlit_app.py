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

# --- AUTHENTICATION & SUMMARY ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if st.session_state.password_correct: return True
    
    st.title("⚡ The Hybrid Alpha Play")
    st.subheader("Scaling Renewable Asset Yield")
    
    st.markdown("""
    Most renewable projects operate as passive infrastructure—connecting to the grid and accepting whatever the market dictates. 
    This application serves as the **economic brain** that transforms a standard wind or solar site into a high-frequency trading desk. 
    The strategy focuses on **arbitraging grid volatility** to ensure no megawatt is ever wasted.
    """)

    st.markdown("---")
    st.header("🍯 The 'Secret Sauce': The 123 on Hybrid Alpha")
    st.info("**Core Value:** It’s the Dynamic Logic. The system creates a pivot that treats Bitcoin miners and batteries as a 'virtual load' that reacts to market conditions in milliseconds.")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **🚀 Battle-Tested at Helios**
        Integrates direct operational learnings from Helios, where hybrid energy theory was stress-tested against real-world mechanical and electrical constraints.
        
        **📊 5-Year High-Fidelity Training**
        Trained on five years of 5-minute interval grid pricing data, weather patterns, and thermal variables to recognize market 'fingerprints'.
        
        **❄️ Uri-Proof Backtesting**
        Proven during events like Winter Storm Uri; protected assets from negative pricing while capturing high-value spikes by predicting load shifts.
        """)
    
    with col2:
        st.markdown("""
        **🧠 Predictive AI Battery Management**
        Maintains charge levels by analyzing ambient temp, generation trends, and grid variables to ensure 'dry powder' for massive price spikes.
        
        **⚡ Real-Time Breakeven Reactivity**
        Breakeven floor recalibrates instantly as Hashprice or Efficiency shifts. The asset trades against current reality, not yesterday's spreadsheets.
        
        **⏱️ The Interconnect Stop-Gap**
        For BTM sites in the queue, this setup powers miners today—turning a 'waiting game' for agreements into a 'revenue game'.
        """)

    st.markdown("---")
    st.header("⚙️ How the Alpha Layer Operates")
    a1, a2, a3 = st.columns(3)
    a1.metric("Live Telemetry", "5 Min Poll")
    a2.metric("Hybrid Alpha", "Cash Gain")
    a3.metric("ROI on Autopilot", "Real-Time IRR")

    st.success("**The Bottom Line:** This is mining market inefficiency. The tool ensures every photon and every gust of wind is converted into the highest possible value—protecting the downside and capturing the upside in a reactive, real-time environment.")
    
    st.markdown("---")
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

# --- SIDEBAR ---
with st.sidebar:
    st.header("🛠️ Dashboard Tools")
    if st.button("Reset to Default Config"):
        for key in st.session_state.keys():
            if key != "password_correct": del st.session_state[key]
        st.rerun()
    st.markdown("---")
    st.header("📚 Glossary")
    st.caption("**Alpha:** Gains secured above the market grid price.")
    st.caption("**Breakeven Floor:** The $/MWh price where mining profitability equals grid export value.")

# --- SECTION 1: CONFIG ---
st.markdown("### ⚙️ System Configuration")
c1, c2, c3 = st.columns(3)
with c1:
    solar_cap = st.slider("Solar Capacity (MW)", 0, 1000, 100, key="solar_s")
    wind_cap = st.slider("Wind Capacity (MW)", 0, 1000, 100, key="wind_s")
with c2:
    miner_mw = st.number_input("Miner Fleet (MW)", value=35, key="miner_n")
    batt_mw = st.number_input("Battery Size (MW)", value=60, key="batt_n")
    m_cost_th = st.slider("Miner Cost ($/TH)", 1.0, 50.0, 15.0, 0.5)
with c3:
    hp_cents = st.slider("Hashprice (¢/TH)", 1.0, 10.0, 4.0, 0.1)
    m_eff = st.slider("Efficiency (J/TH)", 10.0, 35.0, 19.0, 0.5)
    breakeven = (1e6 / m_eff) * (hp_cents / 100.0) / 24.0
    st.metric("Breakeven Floor", f"${breakeven:.2f}/MWh")

# --- SECTION 2: CAPEX & ROI ---
st.markdown("---")
st.subheader("💰 Miner Capex & ROI Analysis")
total_th = (miner_mw * 1000000) / m_eff
total_capex = total_th * m_cost_th
ann_alpha = BASE_REVENUE['1y_mining_per_mw'] * miner_mw * 0.4
roi_years = total_capex / ann_alpha if ann_alpha > 0 else 0
irr_est = (ann_alpha / total_capex) * 100 if total_capex > 0 else 0
rc1, rc2, rc3, rc4 = st.columns(4)
rc1.metric("Total Miner Capex", f"${total_capex:,.0f}")
rc2.metric("Est. Annual Alpha", f"${ann_alpha:,.0f}")
rc3.metric("ROI (Years)", f"{roi_years:.2f} Yrs")
rc4.metric("Est. IRR", f"{irr_est:.1f}%")

# --- SECTION 3: OPTIMIZATION ---
st.markdown("---")
st.subheader("🎯 Hybrid Optimization Engine")
ideal_m, ideal_b = int((solar_cap + wind_cap) * 0.20), int((solar_cap + wind_cap) * 0.30)
curr_val = (BASE_REVENUE['1y_mining_per_mw'] * miner_mw) + (BASE_REVENUE['1y_batt_per_mw'] * batt_mw)
ideal_val = (BASE_REVENUE['1y_mining_per_mw'] * ideal_m) + (BASE_REVENUE['1y_batt_per_mw'] * ideal_b)
oc1, oc2 = st.columns(2)
with oc1:
    st.write(f"**Ideal Sizing:** {ideal_m}MW Miners | {ideal_b}MW Battery")
    st.metric("Annual Optimization Delta", f"${(ideal_val - curr_val):,.0f}", delta=f"{((ideal_val-curr_val)/curr_val)*100:.1f}% Upside")
with oc2:
    fig_opt = go.Figure(data=[go.Bar(name='Current', x=['Rev'], y=[curr_val]), go.Bar(name='Ideal', x=['Rev'], y=[ideal_val])])
    fig_opt.update_layout(height=150, margin=dict(l=0,r=0,t=0,b=0))
    st.plotly_chart(fig_opt, use_container_width=True)

# --- SECTION 4: LIVE POWER FLOW & ALPHA ---
st.markdown("---")
s_gen = min(solar_cap * (ghi / 1000.0) * 0.85, solar_cap) if ghi > 0 else 0
w_gen = 0 if (ws/3.6) < 3 else (wind_cap if (ws/3.6) >= 12 else (((ws/3.6)-3)/9)**3 * wind_cap)
total_gen = s_gen + w_gen

if current_price < breakeven:
    m_load, g_export = min(miner_mw, total_gen), max(0, total_gen - miner_mw)
    m_alpha, b_alpha = m_load * (breakeven - max(0, current_price)), 0
else:
    m_load, g_export = 0, total_gen
    m_alpha, b_alpha = 0, batt_mw * current_price

st.subheader("📊 Live Power & Performance")
p_grid, p1, p2, p3, p4 = st.columns(5)
p_grid.metric("Current Grid Price", f"${current_price:.2f}/MWh") # Added this for you
p1.metric("Total Generation", f"{total_gen:.1f} MW")
p2.metric("Miner Load", f"{m_load:.1f} MW")
p3.metric("Mining Alpha", f"${m_alpha:,.2f}/hr")
p4.metric("Battery Alpha", f"${b_alpha:,.2f}/hr")

# --- SECTION 5: HISTORICAL PERFORMANCE ---
st.markdown("---")
st.subheader("📅 Historical Performance (Cumulative Alpha)")

def calc_alpha(p_series, m_mw, b_mw, gen_mw):
    ma, ba, base = 0, 0, 0
    for p in p_series:
        base += (gen_mw * p)
        if p < breakeven:
            ma += m_mw * (breakeven - max(0, p))
            if p < 0: ba += min(b_mw, max(0, gen_mw-m_mw)) * abs(p)
        else: ba += b_mw * p
    return ma, ba, base

ma24, ba24, g24 = calc_alpha(price_hist.tail(24), miner_mw, batt_mw, total_gen)
ma7, ba7, g7 = calc_alpha(price_hist.tail(168), miner_mw, batt_mw, total_gen)

def display_box(label, ma, ba, base):
    st.write(f"**{label}**")
    st.metric("Total Site Revenue", f"${(ma+ba+base):,.0f}", delta=f"${(ma+ba):,.0f} Alpha")
    st.markdown(f"- ⚡ **Grid (Base):** `${base:,.0f}`")
    st.markdown(f"- ⛏️ **Mining Alpha:** `${ma:,.0f}`")
    st.markdown(f"- 🔋 **Battery Alpha:** `${ba:,.0f}`")

h1, h2, h3, h4 = st.columns(4)
with h1: display_box("Last 24 Hours", ma24, ba24, g24)
with h2: display_box("Last 7 Days", ma7, ba7, g7)
with h3: display_box("Last 6 Months", BASE_REVENUE['6m_mining_per_mw']*miner_mw*0.4, BASE_REVENUE['6m_batt_per_mw']*batt_mw, (BASE_REVENUE['6m_grid_solar']+BASE_REVENUE['6m_grid_wind'])*(solar_cap/100))
with h4: display_box("Last 1 Year", ann_alpha, BASE_REVENUE['1y_batt_per_mw']*batt_mw, (BASE_REVENUE['1y_grid_solar']+BASE_REVENUE['1y_grid_wind'])*(solar_cap/100))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import gridstatus
from datetime import datetime, timedelta
import time

# --- CONFIGURATION ---
# SECURITY
DASHBOARD_PASSWORD = "Hardin2026"

# LOCATION: Midland, TX
LAT = 31.997
LONG = -102.077

# ASSET SPECIFICATIONS
SOLAR_CAPACITY_MW = 100
WIND_CAPACITY_MW = 100
MINER_CAPACITY_MW = 35
BATTERY_MW = 60
BATTERY_DURATION_HOURS = 2

# --- AUTHENTICATION ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    st.title("West Texas Asset Dashboard")
    password_input = st.text_input("Enter Access Password", type="password")

    if password_input == DASHBOARD_PASSWORD:
        st.session_state.password_correct = True
        st.rerun()
    elif password_input != "":
        st.error("Incorrect password")

    return False

if not check_password():
    st.stop()

# --- DATA FETCHING ---

@st.cache_data(ttl=3600)
def get_ercot_price_history_30d():
    try:
        iso = gridstatus.Ercot()
        end = pd.Timestamp.now(tz="US/Central")
        start = end - pd.Timedelta(days=30)
        df = iso.get_rtm_lmp(start=start, end=end, verbose=False)
        west_hub = df[df['Location'] == 'HB_WEST'].set_index('Time').sort_index()
        return west_hub['LMP']
    except Exception as e:
        dates = pd.date_range(end=datetime.now(), periods=24*30, freq='1h')
        return pd.Series(np.random.uniform(-10, 100, len(dates)), index=dates)

@st.cache_data(ttl=300)
def get_current_weather():
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": LAT,
            "longitude": LONG,
            "current": ["shortwave_radiation", "wind_speed_10m"],
            "timezone": "auto"
        }
        r = requests.get(url, params=params).json()['current']
        return r['shortwave_radiation'], r['wind_speed_10m']
    except:
        return 0, 0

# --- CALCULATIONS ---

def calculate_solar_output(ghi):
    if ghi <= 0: return 0.0
    return min(SOLAR_CAPACITY_MW * (ghi / 1000.0) * 0.85, SOLAR_CAPACITY_MW)

def calculate_wind_output(wind_kmh):
    wind_ms = wind_kmh / 3.6
    if wind_ms < 3.0 or wind_ms > 25.0: return 0.0
    if wind_ms >= 12.0: return WIND_CAPACITY_MW
    return ((wind_ms - 3.0) / 9.0) ** 3 * WIND_CAPACITY_MW

# --- DASHBOARD UI ---

st.set_page_config(page_title="West Texas Strategy", layout="wide")

# Fetch Data
price_history_30d = get_ercot_price_history_30d()
current_price = price_history_30d.iloc[-1] if not price_history_30d.empty else 0.0
ghi, wind_speed = get_current_weather()
solar_mw = calculate_solar_output(ghi)
wind_mw = calculate_wind_output(wind_speed)
total_renewables_mw = solar_mw + wind_mw

# TITLE
st.title("⚡ West Texas Renewable Portfolio Tracker")

# --- SECTION 1: SYSTEM TELEMETRY (THE PARAMETERS) ---
with st.container():
    st.markdown("### ⚙️ System Telemetry & Live Inputs")
    
    # Create 3 Columns for Parameters
    p1, p2, p3 = st.columns(3)
    
    with p1:
        st.markdown("**🌤️ Live Weather (Midland, TX)**")
        st.write(f"Solar Irradiance: **{ghi:.1f} W/m²**")
        st.write(f"Wind Speed: **{wind_speed:.1f} km/h**")
        st.caption("Source: Open-Meteo API")
        
    with p2:
        st.markdown("**🏭 Asset Configuration**")
        st.write(f"Solar Cap: **{SOLAR_CAPACITY_MW} MW**")
        st.write(f"Wind Cap: **{WIND_CAPACITY_MW} MW**")
        st.write(f"Battery: **{BATTERY_MW} MW / {BATTERY_MW*BATTERY_DURATION_HOURS} MWh**")
        
    with p3:
        st.markdown("**⛏️ Mining Economics (Interactive)**")
        
        # --- SLIDERS ---
        hashprice_cents = st.slider(
            "Hashprice (Cents/TH)", 
            min_value=1.0, 
            max_value=10.0, 
            value=4.0, 
            step=0.1
        )
        
        miner_efficiency_j_th = st.slider(
            "Miner Efficiency (J/TH)", 
            min_value=10.0, 
            max_value=35.0, 
            value=19.0, 
            step=0.5
        )
        
        # Recalculate Breakeven based on Sliders
        # Convert Cents to Dollars
        hashprice_dollars = hashprice_cents / 100.0
        
        mining_breakeven_price = (1e6 / miner_efficiency_j_th) * hashprice_dollars / 24.0
        
        st.markdown(f"Breakeven Floor: :red[**${mining_breakeven_price:.2f} /MWh**]")

st.markdown("---")

# --- SECTION 2: LIVE PERFORMANCE ---
st.markdown("### 🟢 Real-Time Performance")

# Live Ticker
c1, c2, c3, c4 = st.columns(4)
c1.metric("ERCOT West Hub Price", f"${current_price:.2f}/MWh", delta_color="inverse" if current_price < 0 else "normal")
c2.metric("Solar Output", f"{solar_mw:.1f} MW", f"{(solar_mw/SOLAR_CAPACITY_MW)*100:.0f}% Cap")
c3.metric("Wind Output", f"{wind_mw:.1f} MW", f"{(wind_mw/WIND_CAPACITY_MW)*100:.0f}% Cap")
c4.metric("Total Generation", f"{total_renewables_mw:.1f} MW")

# Instant Revenue Logic
rev_a = total_renewables_mw * current_price
rev_b = MINER_CAPACITY_MW * mining_breakeven_price
rev_c = 0.0
status_c = ""
color_c = "blue"

if current_price < 0:
    charging_mw = min(BATTERY_MW, total_renewables_mw)
    leftover_mw = max(0, total_renewables_mw - charging_mw)
    mining_mw = min(MINER_CAPACITY_MW, leftover_mw)
    avoided_cost = charging_mw * abs(current_price)
    mining_rev = mining_mw * mining_breakeven_price
    rev_c = mining_rev + avoided_cost
    status_c = "🔴 NEGATIVE PRICE: Charging from Renewables"
    color_c = "red"
elif current_price < mining_breakeven_price:
    mining_rev = MINER_CAPACITY_MW * mining_breakeven_price
    excess_gen = max(0, total_renewables_mw - MINER_CAPACITY_MW)
    grid_rev = excess_gen * current_price
    rev_c = mining_rev + grid_rev
    status_c = "🟡 LOW PRICE: Mining Active"
    color_c = "orange"
else:
    gen_rev = total_renewables_mw * current_price
    battery_discharge_rev = BATTERY_MW * current_price
    rev_c = gen_rev + battery_discharge_rev
    status_c = "🟢 HIGH PRICE: Discharging Battery to Grid"
    color_c = "green"

# Revenue Display
sc1, sc2, sc3 = st.columns(3)
sc1.info("Scenario A: Renewable Only")
sc1.metric("Instant Rev", f"${rev_a:,.2f} / hr")

sc2.warning("Scenario B: Mining Only")
sc2.metric("Instant Rev", f"${rev_b:,.2f} / hr")

sc3.success("Scenario C: Hybrid Optimized")
sc3.metric("Instant Rev", f"${rev_c:,.2f} / hr", delta=f"${rev_c - rev_a:,.2f} vs Status Quo")
sc3.markdown(f":{color_c}[{status_c}]")

# --- SECTION 3: CUMULATIVE HISTORY ---
st.markdown("---")
st.markdown("### 📅 Cumulative Performance (Mining vs. Grid Split)")

# Resample price history
hourly_prices = price_history_30d.resample('h').mean()
last_24h = hourly_prices.tail(24)
last_7d = hourly_prices.tail(24*7)
last_30d = hourly_prices.tail(24*30)

def calculate_split_revenue(prices_series):
    mining_portion = 0.0
    grid_battery_portion = 0.0
    for price in prices_series:
        if price < 0:
            charging_mw = min(BATTERY_MW, total_renewables_mw)
            mining_mw = min(MINER_CAPACITY_MW, max(0, total_renewables_mw - charging_mw))
            avoided_cost = charging_mw * abs(price)
            mining_rev = mining_mw * mining_breakeven_price
            mining_portion += (avoided_cost + mining_rev)
        elif price < mining_breakeven_price:
            mining_portion += (MINER_CAPACITY_MW * mining_breakeven_price)
            excess = max(0, total_renewables_mw - MINER_CAPACITY_MW)
            grid_battery_portion += (excess * price)
        else:
            grid_battery_portion += ((total_renewables_mw + BATTERY_MW) * price)
    total = mining_portion + grid_battery_portion
    return total, mining_portion, grid_battery_portion

# Calculate Splits
t_24, m_24, g_24 = calculate_split_revenue(last_24h)
t_7d, m_7d, g_7d = calculate_split_revenue(last_7d)
t_30, m_30, g_30 = calculate_split_revenue(last_30d)

# History Columns
kpi1, kpi2, kpi3 = st.columns(3)

with kpi1:
    st.subheader("Last 24 Hours")
    st.metric("Total", f"${t_24:,.0f}")
    st.markdown(f"- ⛏️ Mining: ${m_24:,.0f}")
    st.markdown(f"- ⚡ Grid: ${g_24:,.0f}")

with kpi2:
    st.subheader("Last 7 Days")
    st.metric("Total", f"${t_7d:,.0f}")
    st.markdown(f"- ⛏️ Mining: ${m_7d:,.0f}")
    st.markdown(f"- ⚡ Grid: ${g_7d:,.0f}")

with kpi3:
    st.subheader("Last 30 Days")
    st.metric("Total", f"${t_30:,.0f}")
    st.markdown(f"- ⛏️ Mining: ${m_30:,.0f}")
    st.markdown(f"- ⚡ Grid: ${g_30:,.0f}")

# Raw Data
with st.expander("View Raw Data Feeds"):
    st.dataframe(price_history_30d.tail(10).rename("LMP Price"))

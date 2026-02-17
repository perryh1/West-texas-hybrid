import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import gridstatus
from datetime import datetime
import time

# --- CONFIGURATION ---
# SECURITY: Simple password protection
DASHBOARD_PASSWORD = "Hardin2026" 

# LOCATION: Midland, TX (Representative for West Texas)
LAT = 31.997
LONG = -102.077

# ASSET SPECS
SOLAR_CAPACITY_MW = 100
WIND_CAPACITY_MW = 100
MINER_CAPACITY_MW = 35
BATTERY_MW = 60

# MINING ECONOMICS
# Efficiency: 19 J/TH
# Hashprice: $0.04 / TH/s / Day
# Breakeven Calculation:
# (1 MW / 19 J/TH) * $0.04 * (1e6 / (24*3600)) is roughly $87.72/MWh
MINING_BREAKEVEN_PRICE = 87.72 

# --- AUTHENTICATION ---
def check_password():
    """Returns `True` if the user had the correct password."""
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

# --- DATA FETCHING FUNCTIONS (CACHED) ---

@st.cache_data(ttl=300) # Cache for 5 minutes to prevent API limits
def get_ercot_price():
    """Fetches real-time LMP for ERCOT West Hub via GridStatus."""
    try:
        iso = gridstatus.Ercot()
        # Get latest Real-Time Market (RTM) LMPs
        df = iso.get_rtm_lmp(date="latest")
        
        # Filter for West Hub (HB_WEST)
        west_hub = df[df['Location'] == 'HB_WEST']
        
        if west_hub.empty:
            return 0.0, "Data Delayed"
            
        latest_price = west_hub.iloc[-1]['LMP']
        timestamp = west_hub.iloc[-1]['Time']
        return latest_price, timestamp
    except Exception as e:
        st.error(f"GridStatus API Error: {e}")
        return 0.0, datetime.now()

@st.cache_data(ttl=300)
def get_weather_data():
    """Fetches real-time GHI and Wind Speed from Open-Meteo."""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": LAT,
            "longitude": LONG,
            "current": ["shortwave_radiation", "wind_speed_10m"],
            "timezone": "auto",
            "forecast_days": 1
        }
        response = requests.get(url, params=params)
        data = response.json()['current']
        
        # Extract variables
        ghi = data['shortwave_radiation'] # Watts/m2
        wind_speed = data['wind_speed_10m'] # km/h
        
        return ghi, wind_speed
    except Exception as e:
        st.error(f"Weather API Error: {e}")
        return 0, 0

# --- CALCULATION MODELS ---

def calculate_solar_output(ghi):
    # Standard Test Conditions: 1000 W/m2. Performance Ratio: 0.85
    if ghi <= 0: return 0.0
    output = SOLAR_CAPACITY_MW * (ghi / 1000.0) * 0.85
    return min(output, SOLAR_CAPACITY_MW)

def calculate_wind_output(wind_kmh):
    # Convert km/h to m/s
    wind_ms = wind_kmh / 3.6
    
    # Generic 2.5MW Turbine Power Curve (Scaled)
    if wind_ms < 3.0 or wind_ms > 25.0: return 0.0
    if wind_ms >= 12.0: return WIND_CAPACITY_MW
    
    # Cubic curve approximation
    factor = ((wind_ms - 3.0) / (12.0 - 3.0)) ** 3
    return factor * WIND_CAPACITY_MW

# --- DASHBOARD UI ---

st.set_page_config(page_title="West Texas Strategy", layout="wide")

# 1. Fetch Data
price, time_ref = get_ercot_price()
ghi, wind_speed = get_weather_data()
solar_mw = calculate_solar_output(ghi)
wind_mw = calculate_wind_output(wind_speed)
total_renewables_mw = solar_mw + wind_mw

# 2. Header
st.title("⚡ West Texas Renewable Portfolio Tracker")
st.markdown(f"**Last Update:** {time_ref} | **Location:** Midland, TX")
st.markdown("---")

# 3. Live Ticker
col1, col2, col3, col4 = st.columns(4)
with col1:
    delta_color = "inverse" if price < 0 else "normal"
    st.metric("ERCOT West Hub Price", f"${price:.2f}/MWh", delta_color=delta_color)
with col2:
    st.metric("Solar Output", f"{solar_mw:.1f} MW")
with col3:
    st.metric("Wind Output", f"{wind_mw:.1f} MW")
with col4:
    st.metric("Mining Breakeven", f"${MINING_BREAKEVEN_PRICE:.2f}/MWh")

# 4. The Three Scenarios (Core Logic)
st.markdown("### 💰 Financial Strategy Comparison")

# Scenario A: Renewable Only (Status Quo)
# We sell everything to the grid, even if price is negative
rev_a = total_renewables_mw * price

# Scenario B: Mining Only (Theoretical)
# We run 35MW miners 24/7.
# Revenue is fixed at the breakeven equivalent ($87.72)
rev_b = MINER_CAPACITY_MW * MINING_BREAKEVEN_PRICE

# Scenario C: Hybrid Optimization (Smart Dispatch)
# Logic:
# 1. Price < 0: Charge Battery (60MW) + Run Miners (35MW)
# 2. 0 < Price < 87.72: Run Miners (35MW) + Sell Excess Renewable to Grid
# 3. Price > 87.72: Shut Down Miners + Discharge Battery (60MW) + Sell All Renewable

rev_c = 0.0
status_c = ""
color_c = "blue"

if price < 0:
    # State 1: Negative Pricing (Charge + Mine)
    # We get paid to charge battery (Abs(Price) * 60MW)
    # We earn mining revenue (35MW * Breakeven)
    battery_rev = abs(price) * BATTERY_MW 
    mining_rev = MINER_CAPACITY_MW * MINING_BREAKEVEN_PRICE
    rev_c = battery_rev + mining_rev
    status_c = "🔴 NEGATIVE PRICE: Charging & Mining"
    color_c = "red"
    
elif price < MINING_BREAKEVEN_PRICE:
    # State 2: Low Price (Mine + Sell Excess)
    # Miners are more profitable than grid
    mining_rev = MINER_CAPACITY_MW * MINING_BREAKEVEN_PRICE
    
    # Remaining power goes to grid
    # (Note: In reality, BTM implies we use our own power first)
    # If Gen > 35MW, sell excess. If Gen < 35MW, we just mine.
    excess_gen = max(0, total_renewables_mw - MINER_CAPACITY_MW)
    grid_rev = excess_gen * price
    
    rev_c = mining_rev + grid_rev
    status_c = "🟡 LOW PRICE: Mining Active"
    color_c = "orange"

else:
    # State 3: High Price (Discharge + Sell All)
    # Price is higher than mining, so sell everything to grid
    gen_rev = total_renewables_mw * price
    battery_discharge_rev = BATTERY_MW * price
    rev_c = gen_rev + battery_discharge_rev
    status_c = "🟢 HIGH PRICE: Discharging to Grid"
    color_c = "green"

# Display The 3 Columns
sc1, sc2, sc3 = st.columns(3)

with sc1:
    st.info("Scenario A: Renewable Only")
    st.metric("Instant Revenue", f"${rev_a:,.2f} / hr")
    if price < 0:
        st.error("Losing money on negative pricing")

with sc2:
    st.warning("Scenario B: Mining Only (35MW)")
    st.metric("Instant Revenue", f"${rev_b:,.2f} / hr")
    st.caption("Assumes 100% Uptime")

with sc3:
    st.success("Scenario C: Hybrid Optimized")
    st.metric("Instant Revenue", f"${rev_c:,.2f} / hr", delta=f"${rev_c - rev_a:,.2f} vs Status Quo")
    st.markdown(f"**Strategy:** :{color_c}[{status_c}]")

# 5. Raw Data
with st.expander("View System Inputs"):
    st.table(pd.DataFrame({
        "Metric": ["Irradiance", "Wind Speed", "Miner Breakeven"],
        "Value": [f"{ghi} W/m²", f"{wind_speed} km/h", f"${MINING_BREAKEVEN_PRICE}/MWh"]
    }))
    if st.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import gridstatus
from datetime import datetime, timedelta
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
BATTERY_DURATION_HOURS = 2  # 120 MWh

# MINING ECONOMICS
# Efficiency: 19 J/TH
# Hashprice: $0.04 / TH/s / Day
# Breakeven Calculation: (1 MW / 19 J/TH) * $0.04 * (1e6 / (24*3600)) = ~$87.72/MWh
MINING_BREAKEVEN_PRICE = 87.72

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

# --- DATA FETCHING FUNCTIONS (CACHED) ---

@st.cache_data(ttl=3600) # Cache for 1 hour since 30 days is a lot of data
def get_ercot_price_history_30d():
    """Fetches last 30 days of price history for calculations."""
    try:
        iso = gridstatus.Ercot()
        # Fetch last 30 days of LMPs
        end = pd.Timestamp.now(tz="US/Central")
        start = end - pd.Timedelta(days=30)
        
        # GridStatus get_rtm_lmp can take a date range
        df = iso.get_rtm_lmp(start=start, end=end, verbose=False)
        
        # Filter for West Hub
        west_hub = df[df['Location'] == 'HB_WEST'].set_index('Time').sort_index()
        return west_hub['LMP']
    except Exception as e:
        # Fallback: Generate dummy history for demo if API fails
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

# --- CALCULATION MODELS ---

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

# 1. Fetch Data
price_history_30d = get_ercot_price_history_30d()
current_price = price_history_30d.iloc[-1] if not price_history_30d.empty else 0.0
ghi, wind_speed = get_current_weather()

solar_mw = calculate_solar_output(ghi)
wind_mw = calculate_wind_output(wind_speed)
total_renewables_mw = solar_mw + wind_mw

# 2. Header
st.title("⚡ West Texas Renewable Portfolio Tracker")
st.markdown(f"**Status:** Online | **Strategy:** Hybrid Optimization | **Hub:** ERCOT West")
st.markdown("---")

# 3. Live Ticker
c1, c2, c3, c4 = st.columns(4)
c1.metric("ERCOT West Hub Price", f"${current_price:.2f}/MWh", delta_color="inverse" if current_price < 0 else "normal")
c2.metric("Solar Output", f"{solar_mw:.1f} MW", f"{(solar_mw/SOLAR_CAPACITY_MW)*100:.0f}% Cap")
c3.metric("Wind Output", f"{wind_mw:.1f} MW", f"{(wind_mw/WIND_CAPACITY_MW)*100:.0f}% Cap")
c4.metric("Mining Breakeven", f"${MINING_BREAKEVEN_PRICE:.2f}/MWh")

# 4. Instant Revenue (Hourly Run Rate)
st.markdown("### 💰 Instant Revenue (Hourly Rate)")

# Logic Calculations
rev_a = total_renewables_mw * current_price
rev_b = MINER_CAPACITY_MW * MINING_BREAKEVEN_PRICE

# Hybrid Logic (Scenario C) with BTM Correction
rev_c = 0.0
status_c = ""
color_c = "blue"

if current_price < 0:
    charging_mw = min(BATTERY_MW, total_renewables_mw)
    leftover_mw = max(0, total_renewables_mw - charging_mw)
    mining_mw = min(MINER_CAPACITY_MW, leftover_mw)
    avoided_cost = charging_mw * abs(current_price)
    mining_rev = mining_mw * MINING_BREAKEVEN_PRICE
    rev_c = mining_rev + avoided_cost
    status_c = "🔴 NEGATIVE PRICE: Charging from Renewables"
    color_c = "red"

elif current_price < MINING_BREAKEVEN_PRICE:
    mining_rev = MINER_CAPACITY_MW * MINING_BREAKEVEN_PRICE
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

sc1, sc2, sc3 = st.columns(3)
sc1.info("Scenario A: Renewable Only")
sc1.metric("Instant Rev", f"${rev_a:,.2f} / hr")

sc2.warning("Scenario B: Mining Only")
sc2.metric("Instant Rev", f"${rev_b:,.2f} / hr")

sc3.success("Scenario C: Hybrid Optimized")
sc3.metric("Instant Rev", f"${rev_c:,.2f} / hr", delta=f"${rev_c - rev_a:,.2f} vs Status Quo")
sc3.markdown(f":{color_c}[{status_c}]")

# 5. HISTORICAL PERFORMANCE (Broken Down)
st.markdown("---")
st.markdown("### 📅 Cumulative Performance (Mining vs. Grid Split)")

# Resample price history to hourly
hourly_prices = price_history_30d.resample('h').mean()
last_24h = hourly_prices.tail(24)
last_7d = hourly_prices.tail(24*7)
last_30d = hourly_prices.tail(24*30)

def calculate_split_revenue(prices_series):
    """Calculates Total, Mining Portion, and Grid/Battery Portion."""
    mining_portion = 0.0
    grid_battery_portion = 0.0
    
    # We iterate to handle the logic split (Vectorized would be faster but this is clearer)
    for price in prices_series:
        if price < 0:
            # Negative: Mining + Charging (Avoided Cost)
            # Charging 'Avoided Cost' counts towards 'Mining/Storage' efficiency bucket
            charging_mw = min(BATTERY_MW, total_renewables_mw)
            mining_mw = min(MINER_CAPACITY_MW, max(0, total_renewables_mw - charging_mw))
            
            avoided_cost = charging_mw * abs(price)
            mining_rev = mining_mw * MINING_BREAKEVEN_PRICE
            
            mining_portion += (avoided_cost + mining_rev)
            
        elif price < MINING_BREAKEVEN_PRICE:
            # Low: Mine + Sell Excess
            mining_portion += (MINER_CAPACITY_MW * MINING_BREAKEVEN_PRICE)
            excess = max(0, total_renewables_mw - MINER_CAPACITY_MW)
            grid_battery_portion += (excess * price)
            
        else:
            # High: Discharge + Sell All
            # Everything goes to Grid bucket
            grid_battery_portion += ((total_renewables_mw + BATTERY_MW) * price)
            
    total = mining_portion + grid_battery_portion
    return total, mining_portion, grid_battery_portion

# Calculate Splits
t_24, m_24, g_24 = calculate_split_revenue(last_24h)
t_7d, m_7d, g_7d = calculate_split_revenue(last_7d)
t_30, m_30, g_30 = calculate_split_revenue(last_30d)

# Display Columns
kpi1, kpi2, kpi3 = st.columns(3)

with kpi1:
    st.subheader("Last 24 Hours")
    st.metric("Total Hybrid Revenue", f"${t_24:,.0f}")
    st.markdown(f"""
    - ⛏️ **Mining:** ${m_24:,.0f} ({m_24/t_24*100:.1f}%)
    - ⚡ **Grid/Batt:** ${g_24:,.0f} ({g_24/t_24*100:.1f}%)
    """)

with kpi2:
    st.subheader("Last 7 Days")
    st.metric("Total Hybrid Revenue", f"${t_7d:,.0f}")
    st.markdown(f"""
    - ⛏️ **Mining:** ${m_7d:,.0f} ({m_7d/t_7d*100:.1f}%)
    - ⚡ **Grid/Batt:** ${g_7d:,.0f} ({g_7d/t_7d*100:.1f}%)
    """)

with kpi3:
    st.subheader("Last 30 Days")
    st.metric("Total Hybrid Revenue", f"${t_30:,.0f}")
    st.markdown(f"""
    - ⛏️ **Mining:** ${m_30:,.0f} ({m_30/t_30*100:.1f}%)
    - ⚡ **Grid/Batt:** ${g_30:,.0f} ({g_30/t_30*100:.1f}%)
    """)

# 6. Raw Data
with st.expander("View Raw Data Feeds"):
    st.dataframe(price_history_30d.tail(10).rename("LMP Price"))

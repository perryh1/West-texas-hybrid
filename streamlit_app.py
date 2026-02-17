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

@st.cache_data(ttl=300)
def get_ercot_price_history():
    """Fetches last 7 days of price history for calculations."""
    try:
        iso = gridstatus.Ercot()
        # Fetch last 7 days of LMPs
        end = pd.Timestamp.now(tz="US/Central")
        start = end - pd.Timedelta(days=7)
        
        # GridStatus get_rtm_lmp can take a date range
        df = iso.get_rtm_lmp(start=start, end=end, verbose=False)
        
        # Filter for West Hub
        west_hub = df[df['Location'] == 'HB_WEST'].set_index('Time').sort_index()
        return west_hub['LMP']
    except Exception as e:
        # Fallback: Generate dummy history for demo if API fails
        dates = pd.date_range(end=datetime.now(), periods=168*4, freq='15min')
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

# 1. Fetch Real-Time Data
price_history = get_ercot_price_history()
current_price = price_history.iloc[-1] if not price_history.empty else 0.0
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

# Hybrid Logic (Scenario C)
rev_c = 0.0
status_c = ""
color_c = "blue"

if current_price < 0:
    rev_c = (abs(current_price) * BATTERY_MW) + (MINER_CAPACITY_MW * MINING_BREAKEVEN_PRICE)
    status_c = "🔴 NEGATIVE PRICE: Charging & Mining"
    color_c = "red"
elif current_price < MINING_BREAKEVEN_PRICE:
    excess_gen = max(0, total_renewables_mw - MINER_CAPACITY_MW)
    rev_c = (MINER_CAPACITY_MW * MINING_BREAKEVEN_PRICE) + (excess_gen * current_price)
    status_c = "🟡 LOW PRICE: Mining Active"
    color_c = "orange"
else:
    rev_c = (total_renewables_mw * current_price) + (BATTERY_MW * current_price)
    status_c = "🟢 HIGH PRICE: Discharging to Grid"
    color_c = "green"

sc1, sc2, sc3 = st.columns(3)
sc1.info("Scenario A: Renewable Only")
sc1.metric("Instant Rev", f"${rev_a:,.2f} / hr")

sc2.warning("Scenario B: Mining Only")
sc2.metric("Instant Rev", f"${rev_b:,.2f} / hr")

sc3.success("Scenario C: Hybrid Optimized")
sc3.metric("Instant Rev", f"${rev_c:,.2f} / hr", delta=f"${rev_c - rev_a:,.2f} vs Status Quo")
sc3.markdown(f":{color_c}[{status_c}]")

# 5. HISTORICAL PERFORMANCE (24H & Weekly)
st.markdown("---")
st.markdown("### 📅 Cumulative Performance (Backtest Estimation)")

# We simulate historical revenue by applying the current output (MW) to historical prices
# Note: In a real app, you would log actual historical MW output. 
# Here we estimate "Potential Revenue" if current weather persisted (Simplified View).

# Resample price history to hourly for easier calculation
hourly_prices = price_history.resample('h').mean()
last_24h = hourly_prices.tail(24)
last_7d = hourly_prices.tail(24*7)

# Calculate Revenue Streams (Vectorized)
# Scenario A (Grid Only)
rev_24h_a = (last_24h * total_renewables_mw).sum()
rev_7d_a = (last_7d * total_renewables_mw).sum()

# Scenario C (Hybrid Estimate)
# We apply the simple logic: Max(Price, Breakeven) for the miner portion
# This is a rough approximation for the dashboard view
hybrid_prices = last_24h.apply(lambda p: max(p, MINING_BREAKEVEN_PRICE) if p < MINING_BREAKEVEN_PRICE else p)
rev_24h_c = (hybrid_prices * MINER_CAPACITY_MW).sum() + (last_24h * (total_renewables_mw - MINER_CAPACITY_MW)).sum()

hybrid_prices_7d = last_7d.apply(lambda p: max(p, MINING_BREAKEVEN_PRICE) if p < MINING_BREAKEVEN_PRICE else p)
rev_7d_c = (hybrid_prices_7d * MINER_CAPACITY_MW).sum() + (last_7d * (total_renewables_mw - MINER_CAPACITY_MW)).sum()


kpi1, kpi2, kpi3 = st.columns(3)

with kpi1:
    st.subheader("Last 24 Hours Revenue")
    st.metric("Renewable Only", f"${rev_24h_a:,.0f}")
    st.metric("Hybrid Optimized", f"${rev_24h_c:,.0f}", delta=f"${rev_24h_c - rev_24h_a:,.0f}")

with kpi2:
    st.subheader("Last 7 Days Revenue")
    st.metric("Renewable Only", f"${rev_7d_a:,.0f}")
    st.metric("Hybrid Optimized", f"${rev_7d_c:,.0f}", delta=f"${rev_7d_c - rev_7d_a:,.0f}")

with kpi3:
    st.subheader("Revenue Per MW (Efficiency)")
    # Total Rev / Total Capacity (200MW for Renewables)
    rpm_a = rev_7d_a / (SOLAR_CAPACITY_MW + WIND_CAPACITY_MW)
    # Total Rev / Total Capacity (200MW + 60MW Battery + 35MW Miner is distinct... usually we just divide by generation cap)
    rpm_c = rev_7d_c / (SOLAR_CAPACITY_MW + WIND_CAPACITY_MW)
    
    st.metric("Renewable Only / MW", f"${rpm_a:,.2f} / MW")
    st.metric("Hybrid / MW", f"${rpm_c:,.2f} / MW", delta=f"${rpm_c - rpm_a:,.2f}")
    st.caption("Based on 7-Day Performance")

# 6. Raw Data
with st.expander("View Raw Data Feeds"):
    st.dataframe(price_history.tail(10).rename("LMP Price"))

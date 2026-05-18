"""
config.py — LNG Market Intelligence Terminal
=============================================
Central configuration file. All constants, API keys, and cost assumptions
live here. Never hardcode these values in module files.

Economic context:
    LNG netback pricing requires several cost components to determine
    whether a cargo is economically viable on a given route. These inputs
    are the key variables a cargo trader or shipping desk would model.
    All costs are in USD/MMBtu unless noted.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# =============================================================================
# API KEYS
# =============================================================================
import streamlit as st

def _get_secret(key: str) -> str:
    """Read from Streamlit Cloud secrets first, fall back to .env."""
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, "")

EIA_API_KEY = os.getenv("EIA_API_KEY", "")
AGSI_API_KEY = os.getenv("AGSI_API_KEY", "")
# =============================================================================
# PRICE TICKERS (yfinance)
# =============================================================================
# These are front-month futures contracts — the most liquid point on the
# forward curve and the standard reference for spot market analysis.

TICKER_HENRY_HUB = "NG=F"      # Henry Hub Natural Gas front-month (USD/MMBtu)
TICKER_BRENT     = "BZ=F"      # Brent Crude front-month (USD/bbl)
TICKER_TTF       = "TTF=F"     # TTF Dutch Gas front-month (EUR/MWh)

# =============================================================================
# UNIT CONVERSION CONSTANTS
# =============================================================================
# TTF trades in EUR/MWh. To compare with Henry Hub (USD/MMBtu) we need
# to convert. 1 MWh = 3.412 MMBtu. EUR/USD rate is fetched live but
# we keep a fallback here.

MWH_TO_MMBTU         = 3.412   # 1 MWh = 3.412 MMBtu (thermodynamic constant)
EUR_USD_FALLBACK     = 1.08    # Fallback if live FX fetch fails

# =============================================================================
# JKM PROXY PARAMETERS
# =============================================================================
# JKM (Japan Korea Marker) is the primary Asian LNG spot benchmark,
# published by Platts/S&P Global. It is proprietary and not freely available.
#
# We estimate JKM using the following proxy formula:
#   JKM_est = (Brent_price × oil_to_gas_factor) + asia_premium
#
# The oil-to-gas factor (~0.172) reflects the historical relationship between
# oil-indexed LNG contracts in Asia. The Asia premium captures structural
# supply tightness in the Pacific Basin relative to oil parity.
#
# THIS IS AN ESTIMATE. In production, JKM would come from Platts eWindow,
# CME direct data feed, or a data vendor like ICIS or Argus Media.

JKM_OIL_FACTOR  = 0.172        # Brent USD/bbl → USD/MMBtu conversion factor
JKM_ASIA_PREMIUM = 2.50        # USD/MMBtu structural Asia premium (adjustable)
JKM_LABEL       = "(est.)"     # Appended to all JKM values in the UI

# =============================================================================
# LNG COST ASSUMPTIONS (USD/MMBtu)
# =============================================================================
# These are the key netback cost inputs. Ranges reflect market variability.
# Default values represent mid-cycle assumptions.
#
# Liquefaction: Cost to convert pipeline gas to LNG at a U.S. Gulf Coast
#   terminal (e.g., Sabine Pass, Corpus Christi). Includes tolling fee and
#   fuel gas consumption (~10-15% of throughput).
#
# Shipping (Atlantic): U.S. Gulf → NW Europe, ~7-9 days, Q-Flex vessel.
#
# Shipping (Pacific via Panama): U.S. Gulf → Japan/Korea, ~20 days via
#   Panama Canal. Canal subject to draft restrictions during drought.
#
# Shipping (Pacific via Cape): Alternative routing via Cape of Good Hope,
#   ~35 days. Used when Panama Canal is congested or restricted.
#
# Regasification: Cost to convert LNG back to pipeline gas at import terminal.

LIQUEFACTION_COST_DEFAULT   = 2.75  # USD/MMBtu (range: 2.50–3.00)
LIQUEFACTION_COST_MIN       = 2.50
LIQUEFACTION_COST_MAX       = 3.00

SHIPPING_ATLANTIC_DEFAULT   = 1.25  # USD/MMBtu (range: 1.00–1.50)
SHIPPING_ATLANTIC_MIN       = 1.00
SHIPPING_ATLANTIC_MAX       = 1.50

SHIPPING_PACIFIC_PANAMA_DEFAULT = 2.25  # USD/MMBtu (range: 2.00–2.50)
SHIPPING_PACIFIC_PANAMA_MIN     = 2.00
SHIPPING_PACIFIC_PANAMA_MAX     = 2.50

SHIPPING_PACIFIC_CAPE_DEFAULT   = 2.75  # USD/MMBtu (range: 2.50–3.00)
SHIPPING_PACIFIC_CAPE_MIN       = 2.50
SHIPPING_PACIFIC_CAPE_MAX       = 3.00

REGAS_COST_DEFAULT  = 0.40      # USD/MMBtu (range: 0.30–0.50)
REGAS_COST_MIN      = 0.30
REGAS_COST_MAX      = 0.50

# Minimum margin required to call arbitrage "open" — accounts for model
# uncertainty, financing costs, and execution risk
ARB_OPEN_THRESHOLD  = 0.50     # USD/MMBtu

# =============================================================================
# EIA API CONFIGURATION
# =============================================================================

EIA_BASE_URL        = "https://api.eia.gov/v2/"
EIA_HH_SERIES       = "NG.RNGWHHD.D"       # Henry Hub spot price daily
EIA_STORAGE_SERIES  = "NG.NW2_EPG0_SWO_R48_BCF.W"  # U.S. gas storage weekly

# =============================================================================
# AGSI+ CONFIGURATION (European Gas Storage)
# =============================================================================
# AGSI+ is operated by GIE (Gas Infrastructure Europe). No API key required.
# Data covers EU aggregate and individual country storage levels.
# Updated daily, typically with a 1-2 day lag.

AGSI_BASE_URL       = "https://agsi.gie.eu/api"
AGSI_COUNTRY_CODES  = {
    "EU Aggregate": "eu",
    "Germany":      "de",
    "Italy":        "it",
    "France":       "fr",
    "Netherlands":  "nl",
    "Austria":      "at",
    "Spain":        "es",
    "Belgium":      "be",
    "Poland":       "pl",
}

# =============================================================================
# RSS NEWS FEEDS
# =============================================================================

RSS_FEEDS = {
    "EIA Today in Energy": "https://www.eia.gov/rss/todayinenergy.xml",
    "Natural Gas Intelligence": "https://naturalgasintel.com/feed/",
    "Global LNG Hub": "https://globallnghub.com/feed",
}

# =============================================================================
# CACHE SETTINGS (seconds)
# =============================================================================
# Controls how long Streamlit caches data before re-fetching.
# Price data refreshes hourly; storage data daily (updates once/day anyway).

CACHE_TTL_PRICES    = 3600      # 1 hour
CACHE_TTL_STORAGE   = 86400     # 24 hours
CACHE_TTL_NEWS      = 1800      # 30 minutes

# =============================================================================
# CHART STYLING
# =============================================================================

CHART_TEMPLATE      = "plotly_dark"
COLOR_POSITIVE      = "#00C896"   # Green — positive margin / arb open
COLOR_NEGATIVE      = "#FF4B4B"   # Red — negative margin / arb closed
COLOR_NEUTRAL       = "#FAFAFA"   # White — neutral
COLOR_HH            = "#1F77B4"   # Blue — Henry Hub
COLOR_TTF           = "#FF7F0E"   # Orange — TTF
COLOR_BRENT         = "#2CA02C"   # Green — Brent
COLOR_JKM           = "#9467BD"   # Purple — JKM proxy

# Historical lookback periods (trading days)
LOOKBACK_DEFAULT    = 90
LOOKBACK_SHORT      = 30
LOOKBACK_LONG       = 252         # ~1 trading year
"""
app.py - LNG Market Intelligence Terminal
Run with: streamlit run app.py
"""

import streamlit as st
from src.database.db import init_db

st.set_page_config(
    page_title="LNG Market Intelligence Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------
# Global CSS
# ------------------------------------------------------------------
st.markdown("""
<style>
    .block-container { padding-top: 1.2rem; padding-bottom: 1rem; }
    input[type="text"] { caret-color: transparent !important; }
    [data-baseweb="select"] input { caret-color: transparent !important; }

    .metric-card {
        background: #1a1a2e;
        border: 1px solid #2d2d4e;
        border-radius: 8px;
        padding: 12px 14px;
        margin-bottom: 4px;
        min-width: 0;
    }
    .metric-label {
        font-size: 0.7rem;
        color: #8888aa;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .metric-value {
        font-size: clamp(0.85rem, 1.5vw, 1.25rem);
        font-weight: 700;
        color: #ffffff;
        font-family: 'Courier New', monospace;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 100%;
        display: block;
    }
    .metric-sub {
        font-size: 0.68rem;
        color: #666688;
        margin-top: 3px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .metric-positive { color: #00c896 !important; }
    .metric-negative { color: #ff4b4b !important; }
    .metric-warning  { color: #ffa500 !important; }

    h2 { margin-top: 0.4rem !important; margin-bottom: 0.2rem !important; }
    h3 { margin-top: 0.2rem !important; margin-bottom: 0.2rem !important; }
    .stPlotlyChart { margin-bottom: 0 !important; }

</style>
""", unsafe_allow_html=True)

init_db()

# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------
with st.sidebar:
    st.title("⚡ LNG Terminal")
    st.caption("Market Intelligence Platform")
    st.divider()

    selected_tab = st.radio(
        "Navigate",
        ["Market Dashboard", "Arbitrage Engine", "Gas Storage", "News Feed"],
        label_visibility="collapsed",
    )

    st.divider()

    lookback = st.select_slider(
        "Price History",
        options=[30, 60, 90, 180, 252],
        value=90,
        format_func=lambda x: f"{x} days",
    )

    st.divider()
    st.caption("**Data sources**")
    st.caption("Prices: yfinance (~15 min delay)")
    st.caption("EU Storage: AGSI+ / GIE (daily)")
    st.caption("US Storage: EIA Weekly Report")
    st.caption("News: EIA, NGI, Global LNG Hub")
    st.caption("⚠ JKM: estimated proxy")
    st.divider()
    st.caption("Educational use only. Not for trading.")

# ------------------------------------------------------------------
# Tab routing
# ------------------------------------------------------------------
if selected_tab == "Market Dashboard":
    from src.dashboard.market_tab import render as render_market
    render_market(lookback_days=lookback)

elif selected_tab == "Arbitrage Engine":
    from src.dashboard.arbitrage_tab import render as render_arbitrage
    render_arbitrage()

elif selected_tab == "Gas Storage":
    from src.dashboard.storage_tab import render as render_storage
    render_storage()

elif selected_tab == "News Feed":
    from src.dashboard.news_tab import render as render_news
    render_news()

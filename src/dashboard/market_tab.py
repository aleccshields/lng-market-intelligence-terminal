"""
src/dashboard/market_tab.py - LNG Market Intelligence Terminal
Market Dashboard tab: live prices, spreads, rolling metrics, volatility.
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timezone
from src.pricing.yfinance_client import fetch_all_prices, fetch_all_histories
from src.pricing.price_utils import (
    build_price_summary,
    estimate_jkm_series,
    estimate_jkm,
    compute_spread,
    compute_rolling_average,
    compute_realized_volatility,
)
from src.dashboard.ui_utils import render_cards_row
from config import (
    CHART_TEMPLATE,
    COLOR_HH, COLOR_TTF, COLOR_BRENT, COLOR_JKM,
    COLOR_POSITIVE, COLOR_NEGATIVE,
    LOOKBACK_DEFAULT,
    JKM_LABEL, MWH_TO_MMBTU,
)


def render(lookback_days: int = LOOKBACK_DEFAULT):
    st.header("Market Dashboard")

    with st.spinner("Fetching prices..."):
        prices   = fetch_all_prices()
        histories = fetch_all_histories(days=lookback_days)

    if not any(v for k, v in prices.items() if k.endswith("price")):
        st.error("Unable to fetch price data. Check network connection.")
        return

    # ------------------------------------------------------------------
    # Timestamp — shown immediately below the header
    # ------------------------------------------------------------------
    fetched_at = prices.get("fetched_at", "")
    if fetched_at:
        try:
            dt = datetime.fromisoformat(fetched_at)
            ts = dt.strftime("%H:%M:%S UTC, %b %d %Y")
        except ValueError:
            ts = fetched_at
    else:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC, %b %d %Y")

    st.caption(
        f"Last fetched: **{ts}** · yfinance front-month futures (~15 min delay) · "
        f"Brent: EIA spot · JKM: proxy estimate (Brent × 0.172 + premium) · "
        "Not for trading."
    )

    _render_metric_cards(prices)

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        _render_price_history(histories, prices.get("eur_usd", 1.08))
    with col2:
        _render_spread_chart(histories, prices.get("eur_usd", 1.08))

    col3, col4 = st.columns(2)
    with col3:
        _render_rolling_averages(histories)
    with col4:
        _render_volatility(histories)


def _render_metric_cards(prices: dict):
    hh    = prices.get("hh_price")
    ttf   = prices.get("ttf_usd_mmbtu")
    brent = prices.get("brent_price")
    jkm   = estimate_jkm(brent) if brent else None

    ttf_hh_spread = (ttf - hh) if (ttf and hh) else None
    jkm_hh_spread = (jkm - hh) if (jkm and hh) else None

    def spread_class(v):
        if v is None:
            return ""
        return "metric-positive" if v >= 0 else "metric-negative"

    render_cards_row([
        {"label": "Henry Hub",
         "value": f"${hh:.3f}" if hh else "N/A",
         "sub": "USD/MMBtu"},
        {"label": "TTF (converted)",
         "value": f"${ttf:.3f}" if ttf else "N/A",
         "sub": "USD/MMBtu"},
        {"label": "Brent Crude",
         "value": f"${brent:.2f}" if brent else "N/A",
         "sub": "USD/bbl"},
        {"label": f"JKM {JKM_LABEL}",
         "value": f"${jkm:.3f}" if jkm else "N/A",
         "sub": "USD/MMBtu · proxy",
         "color_class": "metric-warning"},
        {"label": "TTF−HH Spread",
         "value": f"${ttf_hh_spread:+.3f}" if ttf_hh_spread is not None else "N/A",
         "sub": "USD/MMBtu",
         "color_class": spread_class(ttf_hh_spread)},
        {"label": f"JKM−HH {JKM_LABEL}",
         "value": f"${jkm_hh_spread:+.3f}" if jkm_hh_spread is not None else "N/A",
         "sub": "USD/MMBtu · proxy",
         "color_class": spread_class(jkm_hh_spread)},
    ])


def _render_price_history(histories: dict, eur_usd: float):
    st.subheader("Price History")
    fig = go.Figure()

    hh_df = histories.get("henry_hub", pd.DataFrame())
    if not hh_df.empty:
        fig.add_trace(go.Scatter(
            x=hh_df.index, y=hh_df["Close"],
            name="Henry Hub ($/MMBtu)",
            line=dict(color=COLOR_HH, width=2),
        ))

    ttf_df = histories.get("ttf", pd.DataFrame())
    if not ttf_df.empty:
        ttf_conv = ttf_df["Close"] * eur_usd / MWH_TO_MMBTU
        fig.add_trace(go.Scatter(
            x=ttf_df.index, y=ttf_conv,
            name="TTF conv. ($/MMBtu)",
            line=dict(color=COLOR_TTF, width=2),
        ))

    brent_df = histories.get("brent", pd.DataFrame())
    if not brent_df.empty:
        fig.add_trace(go.Scatter(
            x=brent_df.index, y=brent_df["Close"],
            name="Brent ($/bbl)",
            line=dict(color=COLOR_BRENT, width=2, dash="dot"),
            yaxis="y2",
        ))

    fig.update_layout(
        template=CHART_TEMPLATE, height=320,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=11)),
        yaxis=dict(title="USD/MMBtu"),
        yaxis2=dict(title="USD/bbl", overlaying="y", side="right"),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, key="price_history")


def _render_spread_chart(histories: dict, eur_usd: float):
    st.subheader("Spreads vs Henry Hub")
    hh_df    = histories.get("henry_hub", pd.DataFrame())
    ttf_df   = histories.get("ttf", pd.DataFrame())
    brent_df = histories.get("brent", pd.DataFrame())

    if hh_df.empty:
        st.warning("Henry Hub data unavailable.")
        return

    fig = go.Figure()

    if not ttf_df.empty:
        ttf_conv   = ttf_df["Close"] * eur_usd / MWH_TO_MMBTU
        spread_ttf = compute_spread(ttf_conv, hh_df["Close"])
        fig.add_trace(go.Scatter(
            x=spread_ttf.index, y=spread_ttf.values,
            name="TTF−HH",
            line=dict(color=COLOR_TTF, width=2),
            fill="tozeroy", fillcolor="rgba(255,127,14,0.12)",
        ))

    if not brent_df.empty:
        jkm_series = estimate_jkm_series(brent_df["Close"])
        spread_jkm = compute_spread(jkm_series, hh_df["Close"])
        fig.add_trace(go.Scatter(
            x=spread_jkm.index, y=spread_jkm.values,
            name=f"JKM−HH {JKM_LABEL}",
            line=dict(color=COLOR_JKM, width=2, dash="dash"),
        ))

    fig.add_hline(y=0, line_dash="solid", line_color="white", opacity=0.2)
    fig.update_layout(
        template=CHART_TEMPLATE, height=320,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=11)),
        yaxis=dict(title="USD/MMBtu"),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, key="spread_chart")


def _render_rolling_averages(histories: dict):
    st.subheader("HH Rolling Averages")
    hh_df = histories.get("henry_hub", pd.DataFrame())
    if hh_df.empty:
        st.warning("Henry Hub history unavailable.")
        return

    s    = hh_df["Close"]
    ra7  = compute_rolling_average(s, 7)
    ra30 = compute_rolling_average(s, 30)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s.values, name="Daily",
        line=dict(color=COLOR_HH, width=1), opacity=0.4))
    fig.add_trace(go.Scatter(x=ra7.index, y=ra7.values, name="7-Day MA",
        line=dict(color=COLOR_TTF, width=2)))
    fig.add_trace(go.Scatter(x=ra30.index, y=ra30.values, name="30-Day MA",
        line=dict(color=COLOR_BRENT, width=2)))
    fig.update_layout(
        template=CHART_TEMPLATE, height=280,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=11)),
        yaxis=dict(title="USD/MMBtu"), hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, key="rolling_avg")


def _render_volatility(histories: dict):
    st.subheader("HH Realized Volatility (30-Day Ann.)")
    hh_df = histories.get("henry_hub", pd.DataFrame())
    if hh_df.empty:
        st.warning("Henry Hub history unavailable.")
        return

    vol = compute_realized_volatility(hh_df["Close"], window=30) * 100
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=vol.index, y=vol.values, name="30-Day Vol (%)",
        line=dict(color=COLOR_POSITIVE, width=2),
        fill="tozeroy", fillcolor="rgba(0,200,150,0.12)",
    ))
    fig.update_layout(
        template=CHART_TEMPLATE, height=280,
        margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title="Ann. Vol (%)"), hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, key="volatility")
    st.caption("Annualized std dev of daily log returns.")

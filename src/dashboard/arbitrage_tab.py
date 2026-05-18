"""
src/dashboard/arbitrage_tab.py - LNG Market Intelligence Terminal
Arbitrage Engine tab: netback calculations, route status, sensitivity table.
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from src.pricing.yfinance_client import fetch_all_prices
from src.pricing.price_utils import estimate_jkm
from src.arbitrage.netback import (
    CostAssumptions,
    calculate_all_routes,
    build_sensitivity_table,
    format_result_for_display,
)
from src.database.db import log_arb_calculation, get_arb_history
from src.dashboard.ui_utils import metric_card, status_badge, render_cards_row
from config import (
    CHART_TEMPLATE,
    COLOR_POSITIVE, COLOR_NEGATIVE,
    LIQUEFACTION_COST_MIN, LIQUEFACTION_COST_MAX, LIQUEFACTION_COST_DEFAULT,
    SHIPPING_ATLANTIC_MIN, SHIPPING_ATLANTIC_MAX, SHIPPING_ATLANTIC_DEFAULT,
    SHIPPING_PACIFIC_PANAMA_MIN, SHIPPING_PACIFIC_PANAMA_MAX, SHIPPING_PACIFIC_PANAMA_DEFAULT,
    REGAS_COST_MIN, REGAS_COST_MAX, REGAS_COST_DEFAULT,
    JKM_LABEL,
)


def render():
    st.header("LNG Arbitrage Engine")
    st.caption(
        "Netback calculations for U.S. Gulf Coast LNG exports. "
        f"JKM values are proxy estimates {JKM_LABEL}. "
        "Adjust cost assumptions with sliders below."
    )

    with st.spinner("Fetching prices..."):
        prices = fetch_all_prices()

    hh    = prices.get("hh_price")
    ttf   = prices.get("ttf_usd_mmbtu")
    brent = prices.get("brent_price")

    if not all([hh, ttf, brent]):
        st.error("Unable to fetch required prices.")
        return

    jkm = estimate_jkm(brent)

    # ------------------------------------------------------------------
    # Cost sliders
    # ------------------------------------------------------------------
    with st.expander("Adjust Cost Assumptions (USD/MMBtu)", expanded=False):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            liquefaction = st.slider("Liquefaction",
                LIQUEFACTION_COST_MIN, LIQUEFACTION_COST_MAX,
                LIQUEFACTION_COST_DEFAULT, 0.05)
        with col2:
            shipping_atl = st.slider("Shipping (Atlantic)",
                SHIPPING_ATLANTIC_MIN, SHIPPING_ATLANTIC_MAX,
                SHIPPING_ATLANTIC_DEFAULT, 0.05)
        with col3:
            shipping_pac = st.slider("Shipping (Pacific/Panama)",
                SHIPPING_PACIFIC_PANAMA_MIN, SHIPPING_PACIFIC_PANAMA_MAX,
                SHIPPING_PACIFIC_PANAMA_DEFAULT, 0.05)
        with col4:
            regas = st.slider("Regasification",
                REGAS_COST_MIN, REGAS_COST_MAX, REGAS_COST_DEFAULT, 0.05)

    costs = CostAssumptions(
        liquefaction=liquefaction,
        shipping_atlantic=shipping_atl,
        shipping_pacific_panama=shipping_pac,
        shipping_pacific_cape=shipping_pac + 0.50,
        regas=regas,
    )

    results = calculate_all_routes(hh, ttf, jkm, costs)

    for route_key in ["atlantic", "pacific_panama", "pacific_cape"]:
        r  = results[route_key]
        sc = costs.shipping_atlantic if route_key == "atlantic" else costs.shipping_pacific_panama
        log_arb_calculation(
            route=r.route, hh_price=r.hh_price,
            destination_price=r.destination_price,
            liquefaction_cost=costs.liquefaction,
            shipping_cost=sc, regas_cost=costs.regas,
            netback=r.netback, margin=r.margin, arb_open=r.arb_open,
        )

    # ------------------------------------------------------------------
    # Price input cards
    # ------------------------------------------------------------------
    st.subheader("Current Price Inputs")
    render_cards_row([
        {"label": "Henry Hub",        "value": f"${hh:.3f}",   "sub": "USD/MMBtu"},
        {"label": "TTF (converted)",  "value": f"${ttf:.3f}",  "sub": "USD/MMBtu"},
        {"label": "Brent Crude",      "value": f"${brent:.2f}","sub": "USD/bbl"},
        {"label": f"JKM {JKM_LABEL}", "value": f"${jkm:.3f}",  "sub": "USD/MMBtu · est. proxy",
         "color_class": "metric-warning"},
    ])

    st.divider()

    # ------------------------------------------------------------------
    # Route result cards
    # ------------------------------------------------------------------
    st.subheader("Netback by Route")
    route_cols = st.columns(3)
    configs = [
        ("atlantic",       "Atlantic Basin",      "U.S. Gulf → Europe"),
        ("pacific_panama", "Pacific (Panama)",    "U.S. Gulf → Asia ~20d"),
        ("pacific_cape",   "Pacific (Cape)",      "U.S. Gulf → Asia ~35d"),
    ]

    for i, (route_key, title, subtitle) in enumerate(configs):
        r   = results[route_key]
        fmt = format_result_for_display(r)
        margin_class = "metric-positive" if r.arb_open else "metric-negative"

        with route_cols[i]:
            st.markdown(
                metric_card(
                    label=title,
                    value=fmt["margin"],
                    sub=f"{subtitle} · {fmt['status']}",
                    color_class=margin_class,
                ),
                unsafe_allow_html=True,
            )
            st.markdown(status_badge(r.arb_open), unsafe_allow_html=True)

            with st.expander("Full breakdown"):
                details = [
                    ("Destination price", fmt["destination_price"]),
                    ("Liquefaction",      fmt["liquefaction"]),
                    ("Shipping",          fmt["shipping"]),
                    ("Regas",             fmt["regas"]),
                    ("Total cost",        fmt["total_cost"]),
                    ("Netback",           fmt["netback"]),
                    ("Margin",            fmt["margin"]),
                ]
                for k, v in details:
                    st.write(f"**{k}:** {v}")

    st.divider()

    # ------------------------------------------------------------------
    # Marginal destination
    # ------------------------------------------------------------------
    dest  = results["marginal_label"]
    best  = results["best_margin"]
    is_open = results["marginal_dest"] != "none"
    color = COLOR_POSITIVE if is_open else COLOR_NEGATIVE
    st.markdown(
        f"**Marginal cargo destination:** "
        f"<span style='color:{color}'>{dest}</span> "
        f"— best margin **${best:+.3f}/MMBtu**",
        unsafe_allow_html=True,
    )

    st.divider()

    # ------------------------------------------------------------------
    # Sensitivity table
    # ------------------------------------------------------------------
    st.subheader("Atlantic Arb Sensitivity")
    st.caption("Margin ($/MMBtu) by TTF price and shipping cost scenario. Green = arb open.")

    sens_df = build_sensitivity_table(hh, ttf, costs)

    def color_cell(val):
        if not isinstance(val, float):
            return ""
        if val > 0.5:
            return "background-color: rgba(0,200,150,0.3)"
        elif val > 0:
            return "background-color: rgba(0,200,150,0.1)"
        else:
            return "background-color: rgba(255,75,75,0.2)"

    st.dataframe(
        sens_df.style.map(color_cell).format("{:.2f}"),
        use_container_width=True, key="sensitivity_table",
    )

    st.divider()

    # ------------------------------------------------------------------
    # Historical margin chart
    # ------------------------------------------------------------------
    st.subheader("Atlantic Margin History")
    _render_arb_history()


def _render_arb_history():
    history = get_arb_history(route="atlantic", limit=500)
    if not history:
        st.info("No margin history yet. Data accumulates as you use this tab.")
        return

    df = pd.DataFrame(history)
    df["calculated_at"] = pd.to_datetime(df["calculated_at"])
    df["day"] = df["calculated_at"].dt.date

    daily = (
        df.groupby("day")
        .agg(avg_margin=("margin_usd_mmbtu", "mean"), arb_open=("arb_open", "max"))
        .reset_index()
    )

    if len(daily) < 2:
        latest = df.iloc[-1]
        st.info(
            f"Only {len(daily)} day of data so far. "
            f"Current Atlantic margin: **${latest['margin_usd_mmbtu']:+.3f}/MMBtu** "
            f"({'OPEN' if latest['arb_open'] else 'CLOSED'}). "
            "Return tomorrow to see a trend chart."
        )
        return

    colors = [COLOR_POSITIVE if v else COLOR_NEGATIVE for v in daily["arb_open"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=daily["day"], y=daily["avg_margin"],
        marker_color=colors, name="Daily Avg Margin",
    ))
    fig.add_hline(y=0.5, line_dash="dash", line_color="white",
                  opacity=0.5, annotation_text="Arb threshold ($0.50)")
    fig.add_hline(y=0, line_color="white", opacity=0.2)
    fig.update_layout(
        template=CHART_TEMPLATE, height=280,
        margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title="Avg Margin ($/MMBtu)"),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, key="arb_history")
    st.caption("Daily average of intraday calculations. Green = arb open, red = closed.")

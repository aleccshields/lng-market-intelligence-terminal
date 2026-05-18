"""
src/dashboard/storage_tab.py - LNG Market Intelligence Terminal

Storage tab: EU gas storage (AGSI+) and US natural gas storage (EIA).
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from src.storage.agsi_client import (
    fetch_eu_storage,
    fetch_country_storage,
    get_storage_summary,
)
from src.pricing.eia_client import fetch_us_gas_storage, US_STORAGE_REGIONS
from src.dashboard.ui_utils import metric_card, render_cards_row
from config import CHART_TEMPLATE, COLOR_POSITIVE, COLOR_NEGATIVE, AGSI_COUNTRY_CODES


def render():
    st.header("Gas Storage Tracker")
    st.caption(
        "EU storage from AGSI+ (GIE, daily). "
        "US storage from EIA Weekly Natural Gas Storage Report (weekly, Thursdays)."
    )

    eu_tab, us_tab = st.tabs(["EU", "US"])

    with eu_tab:
        _render_eu_section()

    with us_tab:
        _render_us_section()


# =============================================================================
# US STORAGE — mirrors the LNG Storage Tracker logic exactly
# =============================================================================

def _render_us_section():
    """
    US regional natural gas storage tracker.

    Replicates the logic from the standalone LNG Storage Tracker:
        - 6 EIA regions: Lower 48, East, Midwest, South Central,
          Mountain, Pacific
        - 52-week history per region
        - Latest Bcf, 52-week rolling average, surplus/deficit vs avg
        - Line chart with rolling average reference line
        - Week-on-week change (injection vs withdrawal)

    Data: EIA Weekly Natural Gas Storage Report
    Series: natural-gas/stor/wkly/data/ with duoarea facet
    """
    from config import EIA_API_KEY
    if not EIA_API_KEY:
        st.warning(
            "US storage requires an EIA API key. "
            "Register free at [eia.gov/opendata](https://www.eia.gov/opendata/) "
            "and add `EIA_API_KEY=yourkey` to your `.env` file."
        )
        return

    # Region selector
    region_label = st.selectbox(
        "Select region",
        options=list(US_STORAGE_REGIONS.keys()),
        index=0,
        key="us_region_select",
    )
    region_code = US_STORAGE_REGIONS[region_label]

    with st.spinner(f"Fetching {region_label} storage from EIA..."):
        df = fetch_us_gas_storage(weeks=104, region_code=region_code)

    if df.empty:
        st.error(
            f"No data returned for {region_label}. "
            "Check EIA_API_KEY and network connection."
        )
        return

    df = df.sort_values("date").reset_index(drop=True)

    # Trim to last 52 weeks for display metrics (matches original tracker)
    df_52 = df.tail(52).reset_index(drop=True)

    latest      = df_52.iloc[-1]
    prev_week   = df_52.iloc[-2] if len(df_52) >= 2 else None

    current_bcf  = latest["storage_bcf"]
    rolling_avg  = round(df_52["storage_bcf"].mean())
    surplus      = round(current_bcf - rolling_avg)
    wow_change   = round(current_bcf - prev_week["storage_bcf"]) if prev_week is not None else None
    date_str     = latest["date"].strftime("%b %d, %Y")

    injection        = wow_change is not None and wow_change > 0
    surplus_positive = surplus >= 0

    # ------------------------------------------------------------------
    # Header cards — same three metrics as the original tracker
    # ------------------------------------------------------------------
    render_cards_row([
        {
            "label": "Latest Storage",
            "value": f"{current_bcf:,.0f} Bcf",
            "sub":   f"week ending {date_str}",
        },
        {
            "label": "52-Wk Rolling Avg",
            "value": f"{rolling_avg:,} Bcf",
            "sub":   f"{region_label}",
        },
        {
            "label": "vs 52-Wk Avg",
            "value": f"{'+' if surplus_positive else ''}{surplus:,} Bcf",
            "sub":   "SURPLUS" if surplus_positive else "DEFICIT",
            "color_class": "metric-positive" if surplus_positive else "metric-negative",
        },
        {
            "label": "Week-on-Week",
            "value": f"{'+' if injection else ''}{wow_change:,} Bcf" if wow_change is not None else "N/A",
            "sub":   "Injection" if injection else "Withdrawal",
            "color_class": "metric-positive" if injection else "metric-negative",
        },
    ])

    st.divider()

    # ------------------------------------------------------------------
    # Main chart — line chart with 52-wk average reference line
    # ------------------------------------------------------------------
    _render_us_storage_chart(df_52, region_label, rolling_avg)

    st.divider()

    # ------------------------------------------------------------------
    # All-regions summary table
    # ------------------------------------------------------------------
    st.subheader("All Regions — Latest Week")
    _render_all_regions_table()

    st.divider()

    # ------------------------------------------------------------------
    # HH price signal
    # ------------------------------------------------------------------
    _render_us_storage_signal(current_bcf, surplus, region_label)


def _render_us_storage_chart(df: pd.DataFrame, region_label: str, rolling_avg: float):
    """
    Line chart matching the original LNG Storage Tracker design:
    storage line + 52-week average reference line.
    """
    st.subheader(f"{region_label} — Working Gas in Storage (Bcf)")

    fig = go.Figure()

    # Storage line
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=df["storage_bcf"],
        name="Storage (Bcf)",
        line=dict(color="#ff3333", width=2.5),
        mode="lines",
    ))

    # 52-week rolling average reference line
    fig.add_hline(
        y=rolling_avg,
        line_dash="dash",
        line_color="#ffcc00",
        line_width=2,
        annotation_text=f"52-wk avg: {rolling_avg:,} Bcf",
        annotation_font_color="#ffcc00",
        annotation_position="top left",
    )

    # Shade surplus/deficit area
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=df["storage_bcf"],
        fill="tonexty",
        mode="none",
        showlegend=False,
        fillcolor="rgba(255,51,51,0.08)",
    ))

    fig.update_layout(
        template=CHART_TEMPLATE,
        height=360,
        margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title="Working Gas (Bcf)"),
        xaxis=dict(title="Week Ending"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    st.plotly_chart(fig, use_container_width=True, key=f"us_storage_{df['region'].iloc[0]}")
    st.caption("Source: EIA Weekly Natural Gas Storage Report. Updated weekly, released Thursdays.")


def _render_all_regions_table():
    """
    Fetch latest week for all 6 regions and display as a summary table.
    Gives a quick cross-regional snapshot without separate API calls for each chart.
    """
    rows = []
    for label, code in US_STORAGE_REGIONS.items():
        df = fetch_us_gas_storage(weeks=4, region_code=code)
        if df.empty or len(df) < 2:
            continue
        df = df.sort_values("date")
        latest   = df.iloc[-1]["storage_bcf"]
        prev     = df.iloc[-2]["storage_bcf"]
        wow      = latest - prev
        df_52    = fetch_us_gas_storage(weeks=52, region_code=code)
        avg_52   = round(df_52["storage_bcf"].mean()) if not df_52.empty else None
        surplus  = round(latest - avg_52) if avg_52 else None

        rows.append({
            "Region":        label,
            "Storage (Bcf)": f"{latest:,.0f}",
            "WoW Change":    f"{'+' if wow >= 0 else ''}{wow:,.0f}",
            "vs 52-Wk Avg":  f"{'+' if surplus and surplus >= 0 else ''}{surplus:,}" if surplus else "N/A",
            "Signal":        "Injection ↑" if wow >= 0 else "Withdrawal ↓",
        })

    if rows:
        summary_df = pd.DataFrame(rows)

        def color_wow(val):
            if isinstance(val, str):
                return "color: #00c896" if val.startswith("+") else "color: #ff4b4b"
            return ""

        def color_surplus(val):
            if isinstance(val, str) and val not in ["N/A"]:
                return "color: #00c896" if val.startswith("+") else "color: #ff4b4b"
            return ""

        st.dataframe(
            summary_df.style
                .map(color_wow, subset=["WoW Change"])
                .map(color_surplus, subset=["vs 52-Wk Avg"]),
            use_container_width=True,
            hide_index=True,
            key="us_regions_table",
        )
    else:
        st.info("Regional summary unavailable — check EIA_API_KEY.")


def _render_us_storage_signal(current_bcf: float, surplus: float, region: str):
    """Henry Hub price signal interpretation from storage position."""
    st.subheader("Henry Hub Storage Signal")

    if surplus > 200:
        signal, css = "BEARISH HH", "metric-negative"
        note = (
            f"{region} storage is {surplus:,} Bcf above its 52-week average. "
            "A significant surplus suggests ample supply, weighing on Henry Hub prices."
        )
    elif surplus > 0:
        signal, css = "MILDLY BEARISH", "metric-warning"
        note = (
            f"{region} storage is {surplus:,} Bcf above its 52-week average. "
            "A modest surplus provides a soft ceiling on Henry Hub prices."
        )
    elif surplus > -200:
        signal, css = "MILDLY BULLISH", "metric-warning"
        note = (
            f"{region} storage is {abs(surplus):,} Bcf below its 52-week average. "
            "A modest deficit provides support for Henry Hub prices."
        )
    else:
        signal, css = "BULLISH HH", "metric-positive"
        note = (
            f"{region} storage is {abs(surplus):,} Bcf below its 52-week average. "
            "A significant deficit is supportive of higher Henry Hub prices "
            "and tighter LNG export economics."
        )

    st.markdown(
        metric_card(label="HH Signal", value=signal, sub=note, color_class=css),
        unsafe_allow_html=True,
    )
    st.caption(
        "Signal based on surplus/deficit vs 52-week rolling average. "
        "Professional analysis uses EIA 5-year average published in the weekly storage report."
    )


# =============================================================================
# EU STORAGE
# =============================================================================

def _render_eu_section():
    with st.spinner("Fetching EU storage..."):
        eu_df = fetch_eu_storage(days=365)

    if eu_df.empty:
        st.error("Unable to fetch EU storage data. Check AGSI_API_KEY in .env")
        return

    summary = get_storage_summary(eu_df)
    trend   = summary.get("trend_7d")
    yoy     = summary.get("yoy_change")
    date_str = summary["latest_date"].strftime("%b %d, %Y") if summary.get("latest_date") else "N/A"

    render_cards_row([
        {"label": "EU Storage Fill",
         "value": f"{summary['latest_pct']:.1f}%",
         "sub": "of working capacity"},
        {"label": "As of",
         "value": date_str,
         "sub": "AGSI+ report date"},
        {"label": "7-Day Change",
         "value": f"{trend:+.2f} pp" if trend is not None else "N/A",
         "sub": "percentage points",
         "color_class": "metric-positive" if trend and trend >= 0 else "metric-negative"},
        {"label": "Year-on-Year",
         "value": f"{yoy:+.2f} pp" if yoy is not None else "N/A",
         "sub": "vs same date last year",
         "color_class": "metric-positive" if yoy and yoy >= 0 else "metric-negative"},
    ])

    st.divider()

    col1, col2 = st.columns([2, 1])
    with col1:
        _render_eu_fill_chart(eu_df, key="eu_fill_main")
    with col2:
        _render_storage_gauge(summary.get("latest_pct", 0), key="eu_gauge_main")

    st.divider()

    st.subheader("Country Storage")
    country_names  = [k for k in AGSI_COUNTRY_CODES if AGSI_COUNTRY_CODES[k] != "eu"]
    country_option = st.selectbox("Select country", country_names, index=0, key="eu_country_select")
    country_code   = AGSI_COUNTRY_CODES[country_option]

    with st.spinner(f"Fetching {country_option}..."):
        country_df = fetch_country_storage(country_code, days=365)

    if not country_df.empty:
        _render_country_chart(country_df, country_option, key=f"country_{country_code}")
        cs = get_storage_summary(country_df)
        t  = cs.get("trend_7d")
        y  = cs.get("yoy_change")
        render_cards_row([
            {"label": f"{country_option} Fill",
             "value": f"{cs.get('latest_pct', 0):.1f}%",
             "sub": "of working capacity"},
            {"label": "7-Day Trend",
             "value": f"{t:+.2f} pp" if t is not None else "N/A",
             "color_class": "metric-positive" if t and t >= 0 else "metric-negative"},
            {"label": "YoY Change",
             "value": f"{y:+.2f} pp" if y is not None else "N/A",
             "color_class": "metric-positive" if y and y >= 0 else "metric-negative"},
        ], n_cols=3)
    else:
        st.warning(f"No data for {country_option}")

    st.divider()
    _render_eu_storage_signal(summary.get("latest_pct", 0), summary.get("yoy_change"))


def _render_eu_fill_chart(eu_df, key="eu_fill"):
    st.subheader("EU Aggregate Fill (%)")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=eu_df["date"], y=eu_df["full_pct"],
        line=dict(color=COLOR_POSITIVE, width=2),
        fill="tozeroy", fillcolor="rgba(0,200,150,0.1)", name="EU Fill (%)",
    ))
    fig.add_hline(y=80, line_dash="dash", line_color="yellow",
                  opacity=0.7, annotation_text="EU Mandate (80%)")
    fig.add_hline(y=90, line_dash="dot", line_color="white",
                  opacity=0.3, annotation_text="Near Full (90%)")
    fig.update_layout(
        template=CHART_TEMPLATE, height=320,
        margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title="Fill (%)", range=[0, 100]),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, key=key)


def _render_storage_gauge(fill_pct, key="eu_gauge"):
    st.subheader("Current Level")
    bar_color = COLOR_POSITIVE if fill_pct > 80 else ("orange" if fill_pct > 50 else COLOR_NEGATIVE)
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=fill_pct,
        title={"text": "EU Storage (%)"},
        delta={"reference": 80, "suffix": "% vs mandate"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar":  {"color": bar_color},
            "steps": [
                {"range": [0, 50],   "color": "rgba(255,75,75,0.2)"},
                {"range": [50, 80],  "color": "rgba(255,165,0,0.2)"},
                {"range": [80, 100], "color": "rgba(0,200,150,0.2)"},
            ],
            "threshold": {"line": {"color": "yellow", "width": 3},
                          "thickness": 0.75, "value": 80},
        },
        number={"suffix": "%"},
    ))
    fig.update_layout(template=CHART_TEMPLATE, height=320,
                      margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig, use_container_width=True, key=key)


def _render_country_chart(df, country_name, key="country_chart"):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["full_pct"],
        line=dict(color=COLOR_POSITIVE, width=2),
        name=f"{country_name} Fill (%)",
    ))
    fig.add_hline(y=80, line_dash="dash", line_color="yellow",
                  opacity=0.6, annotation_text="80% mandate")
    fig.update_layout(
        template=CHART_TEMPLATE, height=280,
        margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title="Fill (%)", range=[0, 100]),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, key=key)


def _render_eu_storage_signal(fill_pct, yoy_change=None):
    if fill_pct >= 80:
        signal, css = "BEARISH FOR TTF", "metric-negative"
        note = (
            f"At {fill_pct:.1f}%, storage is at or above the EU mandate. "
            "Europe has limited near-term need for spot LNG. "
            "Bearish for TTF; may redirect U.S. cargoes toward Asia."
        )
    elif fill_pct >= 60:
        signal, css = "NEUTRAL", "metric-warning"
        note = (
            f"At {fill_pct:.1f}%, seasonal injection is underway. "
            "Europe needs continued purchases to reach the 80% winter target."
        )
    else:
        signal, css = "BULLISH FOR TTF", "metric-positive"
        note = (
            f"At {fill_pct:.1f}%, storage is below comfortable levels. "
            "Aggressive injection buying needed, supporting TTF and "
            "Atlantic Basin LNG import demand."
        )

    yoy_note = ""
    if yoy_change is not None:
        direction = "above" if yoy_change >= 0 else "below"
        yoy_note = f" Storage is {abs(yoy_change):.1f} pp {direction} last year."

    st.subheader("EU Storage Signal")
    st.markdown(
        metric_card(label="EU Signal", value=signal,
                    sub=note + yoy_note, color_class=css),
        unsafe_allow_html=True,
    )
    st.caption(
        "Simplified heuristic. Professional analysis incorporates "
        "5-year averages, injection rates, and demand forecasts."
    )

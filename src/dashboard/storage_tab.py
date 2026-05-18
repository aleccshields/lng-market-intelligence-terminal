"""
src/dashboard/storage_tab.py - LNG Market Intelligence Terminal

Storage tab: EU gas storage (AGSI+) and US natural gas storage (EIA).

Market context:
    Two storage markets matter most for LNG pricing:

    European storage (AGSI+):
        Drives TTF prices and EU LNG import demand. The EU 80% mandate
        creates a structural autumn buying season that tightens Atlantic
        Basin balances.

    US storage (EIA Weekly):
        Drives Henry Hub prices. The storage surplus/deficit vs. the
        5-year average is the most-watched short-term HH signal.
        Released every Thursday at 10:30am ET.
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from src.storage.agsi_client import (
    fetch_eu_storage,
    fetch_country_storage,
    get_storage_summary,
)
from src.pricing.eia_client import fetch_us_gas_storage
from src.dashboard.ui_utils import metric_card, render_cards_row
from config import CHART_TEMPLATE, COLOR_POSITIVE, COLOR_NEGATIVE, AGSI_COUNTRY_CODES


def render():
    st.header("Gas Storage Tracker")
    st.caption(
        "EU storage from AGSI+ (GIE). "
        "US storage from EIA Weekly Natural Gas Storage Report. "
        "Both updated daily."
    )

    # Two sub-tabs
    eu_tab, us_tab = st.tabs(["🇪🇺  European Storage", "🇺🇸  US Natural Gas Storage"])

    with eu_tab:
        _render_eu_section()

    with us_tab:
        _render_us_section()


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

    # Header cards
    trend_val   = summary.get("trend_7d")
    yoy_val     = summary.get("yoy_change")
    latest_date = summary["latest_date"].strftime("%b %d, %Y") if summary.get("latest_date") else "N/A"

    trend_class = ("metric-positive" if trend_val and trend_val >= 0 else "metric-negative") if trend_val is not None else ""
    yoy_class   = ("metric-positive" if yoy_val and yoy_val >= 0 else "metric-negative") if yoy_val is not None else ""

    render_cards_row([
        {"label": "EU Storage Fill",  "value": f"{summary['latest_pct']:.1f}%",
         "sub": "of working capacity"},
        {"label": "As of",            "value": latest_date,         "sub": "AGSI+ report date"},
        {"label": "7-Day Change",
         "value": f"{trend_val:+.2f} pp" if trend_val is not None else "N/A",
         "sub": "percentage points", "color_class": trend_class},
        {"label": "Year-on-Year",
         "value": f"{yoy_val:+.2f} pp" if yoy_val is not None else "N/A",
         "sub": "vs same date last year", "color_class": yoy_class},
    ])

    st.divider()

    col1, col2 = st.columns([2, 1])
    with col1:
        _render_eu_fill_chart(eu_df, key="eu_fill_main")
    with col2:
        _render_storage_gauge(summary.get("latest_pct", 0), key="eu_gauge_main")

    st.divider()

    st.subheader("Country Storage")
    country_names = [k for k in AGSI_COUNTRY_CODES if AGSI_COUNTRY_CODES[k] != "eu"]
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
            {"label": f"{country_option} Fill", "value": f"{cs.get('latest_pct',0):.1f}%",
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


# =============================================================================
# US STORAGE
# =============================================================================

def _render_us_section():
    """
    US natural gas storage tracker using EIA weekly data.

    The EIA Weekly Natural Gas Storage Report (released every Thursday)
    shows working gas in underground storage for the Lower 48 states.
    The surplus/deficit vs. the 5-year average is the most-watched
    short-term Henry Hub price signal.

    High storage (surplus) = bearish HH, reduces need for imports
    Low storage (deficit)  = bullish HH, tightens supply balance
    """
    if not _check_eia_key():
        return

    with st.spinner("Fetching US storage from EIA..."):
        df = fetch_us_gas_storage(weeks=104)   # 2 years

    if df.empty:
        st.error("Unable to fetch US storage data. Check EIA_API_KEY in .env")
        return

    # Sort ascending
    df = df.sort_values("date").reset_index(drop=True)

    latest      = df.iloc[-1]
    prev_week   = df.iloc[-2] if len(df) >= 2 else None
    yoy_row     = _get_yoy_row(df)

    current_bcf = latest["storage_bcf"]
    wow_change  = (current_bcf - prev_week["storage_bcf"]) if prev_week is not None else None
    yoy_change  = (current_bcf - yoy_row["storage_bcf"]) if yoy_row is not None else None
    date_str    = latest["date"].strftime("%b %d, %Y")

    # Injection/withdrawal flag
    injection = wow_change is not None and wow_change > 0
    inj_label = f"{'Injection' if injection else 'Withdrawal'} week"
    inj_class = "metric-positive" if injection else "metric-negative"

    render_cards_row([
        {"label": "US Working Gas",
         "value": f"{current_bcf:,.0f} Bcf",
         "sub": f"as of {date_str}"},
        {"label": "Week-on-Week",
         "value": f"{wow_change:+,.0f} Bcf" if wow_change is not None else "N/A",
         "sub": inj_label,
         "color_class": inj_class},
        {"label": "Year-on-Year",
         "value": f"{yoy_change:+,.0f} Bcf" if yoy_change is not None else "N/A",
         "sub": "vs same week last year",
         "color_class": "metric-positive" if yoy_change and yoy_change >= 0 else "metric-negative"},
        {"label": "5-Year Avg Range",
         "value": "2,800–3,800",
         "sub": "Bcf typical end-Oct range"},
    ])

    st.divider()

    col1, col2 = st.columns([3, 1])
    with col1:
        _render_us_storage_chart(df)
    with col2:
        _render_us_storage_signal(current_bcf, yoy_change)


def _check_eia_key() -> bool:
    """Show a friendly message if EIA key is not configured."""
    from config import EIA_API_KEY
    if not EIA_API_KEY:
        st.warning(
            "US storage requires an EIA API key. "
            "Register free at [eia.gov/opendata](https://www.eia.gov/opendata/) "
            "and add `EIA_API_KEY=yourkey` to your `.env` file."
        )
        return False
    return True


def _get_yoy_row(df: pd.DataFrame):
    """Find the row closest to 52 weeks ago."""
    if df.empty or len(df) < 10:
        return None
    latest      = df.iloc[-1]["date"]
    target      = latest - pd.Timedelta(weeks=52)
    df_copy     = df.copy()
    df_copy["diff"] = (df_copy["date"] - target).abs()
    return df_copy.loc[df_copy["diff"].idxmin()]


def _render_us_storage_chart(df: pd.DataFrame):
    """US storage level over time with YoY comparison."""
    st.subheader("US Working Gas in Storage (Lower 48, Bcf)")

    # Split into current year and prior year for overlay
    if df.empty:
        return

    latest_year = df["date"].dt.year.max()
    curr = df[df["date"].dt.year == latest_year].copy()
    prev = df[df["date"].dt.year == latest_year - 1].copy()

    fig = go.Figure()

    if not prev.empty:
        fig.add_trace(go.Scatter(
            x=prev["date"], y=prev["storage_bcf"],
            name=f"{latest_year - 1}",
            line=dict(color="#555577", width=1.5, dash="dot"),
            opacity=0.7,
        ))

    if not curr.empty:
        fig.add_trace(go.Scatter(
            x=curr["date"], y=curr["storage_bcf"],
            name=str(latest_year),
            line=dict(color=COLOR_POSITIVE, width=2.5),
            fill="tozeroy",
            fillcolor="rgba(0,200,150,0.08)",
        ))

    # Reference bands for seasonal context
    fig.add_hrect(y0=3500, y1=4000, fillcolor="rgba(0,200,150,0.05)",
                  line_width=0, annotation_text="High storage band")
    fig.add_hrect(y0=1500, y1=2000, fillcolor="rgba(255,75,75,0.05)",
                  line_width=0, annotation_text="Low storage band")

    fig.update_layout(
        template=CHART_TEMPLATE, height=340,
        margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title="Bcf"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, key="us_storage_chart")


def _render_us_storage_signal(current_bcf: float, yoy_change: float = None):
    """Henry Hub price signal from US storage levels."""
    st.subheader("HH Signal")

    # Rough seasonal context: use absolute level as signal
    if current_bcf >= 3500:
        signal, color = "BEARISH HH", "#ff4b4b"
        note = "Storage is elevated. Bearish for Henry Hub prices near term."
    elif current_bcf >= 2500:
        signal, color = "NEUTRAL", "orange"
        note = "Storage within normal range. HH direction driven by weather and demand."
    else:
        signal, color = "BULLISH HH", "#00c896"
        note = "Storage is below seasonal norms. Supportive of higher Henry Hub prices."

    st.markdown(
        metric_card(
            label="Storage Signal",
            value=signal,
            sub=note,
            color_class="metric-positive" if "BULL" in signal else (
                "metric-negative" if "BEAR" in signal else "metric-warning"
            ),
        ),
        unsafe_allow_html=True,
    )

    if yoy_change is not None:
        direction = "above" if yoy_change >= 0 else "below"
        st.caption(
            f"Storage is {abs(yoy_change):,.0f} Bcf {direction} "
            f"the same week last year."
        )

    st.caption(
        "Signal uses absolute storage level as a heuristic. "
        "Professional analysis uses the 5-year average comparison "
        "published in the EIA Weekly Natural Gas Storage Report."
    )


# =============================================================================
# EU CHART HELPERS
# =============================================================================

def _render_eu_fill_chart(eu_df: pd.DataFrame, key: str = "eu_fill"):
    st.subheader("EU Aggregate Fill (%)")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=eu_df["date"], y=eu_df["full_pct"],
        name="EU Fill (%)",
        line=dict(color=COLOR_POSITIVE, width=2),
        fill="tozeroy", fillcolor="rgba(0,200,150,0.1)",
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


def _render_storage_gauge(fill_pct: float, key: str = "eu_gauge"):
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
    fig.update_layout(
        template=CHART_TEMPLATE, height=320,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig, use_container_width=True, key=key)


def _render_country_chart(df: pd.DataFrame, country_name: str, key: str = "country_chart"):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["full_pct"],
        name=f"{country_name} Fill (%)",
        line=dict(color=COLOR_POSITIVE, width=2),
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


def _render_eu_storage_signal(fill_pct: float, yoy_change: float = None):
    if fill_pct >= 80:
        signal, color = "BEARISH FOR TTF", "#ff4b4b"
        explanation = (
            f"At {fill_pct:.1f}%, storage is at or above the EU mandate. "
            "Europe has limited near-term need for spot LNG. "
            "Bearish for TTF; may redirect U.S. cargoes toward Asia."
        )
    elif fill_pct >= 60:
        signal, color = "NEUTRAL", "orange"
        explanation = (
            f"At {fill_pct:.1f}%,  seasonal injection is underway. "
            "Europe needs continued purchases to reach the 80% winter target."
        )
    else:
        signal, color = "BULLISH FOR TTF", "#00c896"
        explanation = (
            f"At {fill_pct:.1f}%, storage is below comfortable levels. "
            "Aggressive injection buying is needed, supporting TTF and "
            "Atlantic Basin LNG import demand."
        )

    yoy_note = ""
    if yoy_change is not None:
        direction = "above" if yoy_change >= 0 else "below"
        yoy_note = f" Storage is {abs(yoy_change):.1f} pp {direction} last year."

    st.subheader("Storage Signal")
    st.markdown(
        metric_card(
            label="EU Signal",
            value=signal,
            sub=explanation + yoy_note,
            color_class="metric-positive" if "BULL" in signal else (
                "metric-negative" if "BEAR" in signal else "metric-warning"
            ),
        ),
        unsafe_allow_html=True,
    )
    st.caption(
        "Simplified heuristic. Professional analysis incorporates "
        "5-year averages, injection rate trends, and demand forecasts."
    )

"""
src/dashboard/ui_utils.py - LNG Market Intelligence Terminal

Shared UI helper functions for consistent card and metric formatting
across all dashboard tabs.
"""

import streamlit as st


def metric_card(label: str, value: str, sub: str = "",
                color_class: str = "") -> str:
    """
    Return an HTML metric card string for use with st.markdown().

    Args:
        label       : Small uppercase label above the value
        value       : Main display value (monospace, large)
        sub         : Optional subtitle below the value (unit, note)
        color_class : CSS class for value color:
                      'metric-positive' | 'metric-negative' | 'metric-warning' | ''

    Returns:
        HTML string to pass to st.markdown(..., unsafe_allow_html=True)

    Usage:
        st.markdown(metric_card("Henry Hub", "$3.008", sub="USD/MMBtu"),
                    unsafe_allow_html=True)
    """
    val_class = f"metric-value {color_class}".strip()
    sub_html  = f'<div class="metric-sub">{sub}</div>' if sub else ""
    return f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="{val_class}">{value}</div>
        {sub_html}
    </div>
    """


def status_badge(open: bool, open_label: str = "OPEN",
                 closed_label: str = "CLOSED") -> str:
    """
    Return an HTML status badge string.

    Args:
        open         : True for positive/open status
        open_label   : Text when open (default 'OPEN')
        closed_label : Text when closed (default 'CLOSED')

    Returns:
        HTML string
    """
    color = "#00c896" if open else "#ff4b4b"
    emoji = "✅" if open else "❌"
    label = open_label if open else closed_label
    return (
        f"<span style='color:{color}; font-weight:700; font-size:1.05em'>"
        f"{emoji} {label}</span>"
    )


def render_cards_row(cards: list[dict], n_cols: int = None):
    """
    Render a row of metric cards from a list of card dicts.

    Each card dict should have keys:
        label       : str
        value       : str
        sub         : str (optional)
        color_class : str (optional)

    Args:
        cards  : List of card specification dicts
        n_cols : Number of columns (defaults to len(cards))
    """
    n = n_cols or len(cards)
    cols = st.columns(n)
    for i, card in enumerate(cards):
        if i >= n:
            break
        with cols[i]:
            st.markdown(
                metric_card(
                    label=card.get("label", ""),
                    value=card.get("value", "N/A"),
                    sub=card.get("sub", ""),
                    color_class=card.get("color_class", ""),
                ),
                unsafe_allow_html=True,
            )

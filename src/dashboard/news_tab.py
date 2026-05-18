"""
src/dashboard/news_tab.py - LNG Market Intelligence Terminal

News Intelligence tab: RSS feed display with keyword-based topic badges.

Badge categories match the classification scheme a real LNG analyst
would use to triage headlines quickly:
    supply_outage   : Terminal outages, force majeure, production curtailments
    geopolitical    : Sanctions, conflict, trade restrictions, diplomacy
    shipping        : Canal disruptions, vessel congestion, freight rates
    storage         : Injection/withdrawal data, storage levels
    weather         : Cold snaps, heat waves, heating/cooling demand
    price_move      : Price rallies, selloffs, benchmark moves
    regulatory      : FERC approvals, EU policy, permitting decisions
    demand          : Import trends, industrial demand, power sector
"""

import streamlit as st
from datetime import datetime
from src.news.rss_ingestor import ingest_all_feeds, get_news_for_display
from src.database.db import init_db


# ------------------------------------------------------------------
# Keyword classification rules
# Order matters — first match wins
# ------------------------------------------------------------------
BADGE_RULES = [
    ("supply_outage", "#ff4b4b", [
        "outage", "shutdown", "offline", "force majeure", "curtail",
        "disruption", "unplanned", "restart", "maintenance", "explosion",
        "sabotage", "attack", "strike", "workers", "freeport", "sabine",
        "corpus christi", "cove point", "elba", "cameron",
    ]),
    ("geopolitical", "#ff8c00", [
        "sanction", "war", "conflict", "russia", "ukraine", "iran",
        "hormuz", "taiwan", "china", "embargo", "nato", "military",
        "diplomat", "ceasefire", "weapon", "blockade", "treaty",
        "geopolit",
    ]),
    ("shipping", "#9467bd", [
        "vessel", "tanker", "ship", "lng carrier", "panama canal",
        "canal", "freight", "charter", "congestion", "port", "terminal",
        "cargo", "fleet", "voyage", "draft restriction", "queuing",
    ]),
    ("storage", "#17becf", [
        "storage", "injection", "withdrawal", "inventory", "stockpile",
        "underground", "working gas", "bcf", "agsi", "twh",
        "storage report", "eia storage",
    ]),
    ("weather", "#2ca02c", [
        "cold snap", "freeze", "winter", "polar vortex", "heat wave",
        "summer", "temperature", "weather", "heating demand", "cooling",
        "hdd", "cdd", "degree day", "storm", "hurricane", "drought",
    ]),
    ("regulatory", "#8c564b", [
        "ferc", "permit", "approval", "regulation", "policy", "law",
        "legislation", "commission", "ruling", "licence", "license",
        "doe", "department of energy", "eu", "european commission",
        "mandate", "directive", "compliance",
    ]),
    ("demand", "#e377c2", [
        "demand", "consumption", "import", "buyer", "purchase",
        "kogas", "tepco", "tokyo gas", "cpc", "petronas", "sinopec",
        "cnpc", "india", "pakistan", "bangladesh", "emerging market",
        "industrial", "power sector",
    ]),
    ("price_move", "#bcbd22", [
        "price", "rally", "surge", "spike", "drop", "fall", "decline",
        "ttf", "jkm", "henry hub", "nbp", "benchmark", "spread",
        "netback", "arb", "arbitrage", "futures", "$/mmbtu",
    ]),
]

BADGE_LABELS = {
    "supply_outage": "Supply Outage",
    "geopolitical":  "Geopolitical",
    "shipping":      "Shipping",
    "storage":       "Storage",
    "weather":       "Weather",
    "regulatory":    "Regulatory",
    "demand":        "Demand",
    "price_move":    "Price Move",
}


def classify_headline(title: str, summary: str = "") -> tuple[str, str] | tuple[None, None]:
    """
    Classify a news item into a badge category using keyword matching.

    Checks title first (weighted higher), then summary.
    Returns (category_key, color) or (None, None) if no match.

    Args:
        title   : Headline text
        summary : Article summary text

    Returns:
        Tuple of (category_key, hex_color) or (None, None)
    """
    text = (title + " " + (summary or "")).lower()
    for category, color, keywords in BADGE_RULES:
        if any(kw in text for kw in keywords):
            return category, color
    return None, None


def render():
    """Render the news intelligence tab."""
    st.header("LNG & Energy News Feed")
    st.caption(
        "Headlines from EIA Today in Energy, Natural Gas Intelligence, "
        "and Global LNG Hub. Badges are keyword-classified."
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        refresh = st.button("Refresh News", type="primary")

    if refresh:
        with st.spinner("Ingesting latest news..."):
            stats = ingest_all_feeds()
        total_new = sum(s["inserted"] for s in stats)
        if total_new > 0:
            st.success(f"Added {total_new} new articles.")
        else:
            st.info("No new articles — feeds are up to date.")

    items = get_news_for_display(limit=50)

    if not items:
        st.info("No news items yet. Click Refresh News to load articles.")
        return

    # ------------------------------------------------------------------
    # Filter controls
    # ------------------------------------------------------------------
    filter_col1, filter_col2 = st.columns([2, 3])

    with filter_col1:
        sources      = sorted(set(item["source"] for item in items))
        sel_sources  = st.multiselect("Source", sources, default=sources, key="news_sources")

    with filter_col2:
        all_categories = list(BADGE_LABELS.keys()) + ["unclassified"]
        sel_categories = st.multiselect(
            "Topic badge",
            options=all_categories,
            default=all_categories,
            format_func=lambda x: BADGE_LABELS.get(x, "Unclassified"),
            key="news_categories",
        )

    # ------------------------------------------------------------------
    # Classify and filter
    # ------------------------------------------------------------------
    classified = []
    for item in items:
        cat, color = classify_headline(
            item.get("title", ""),
            item.get("summary", ""),
        )
        item["_category"] = cat or "unclassified"
        item["_color"]    = color or "#555577"
        classified.append(item)

    filtered = [
        i for i in classified
        if i["source"] in sel_sources
        and i["_category"] in sel_categories
    ]

    # Badge count summary
    from collections import Counter
    cat_counts = Counter(i["_category"] for i in classified)
    badge_summary = " · ".join(
        f"{BADGE_LABELS.get(k, k.title())}: {v}"
        for k, v in sorted(cat_counts.items(), key=lambda x: -x[1])
        if k != "unclassified"
    )
    st.caption(f"Showing {len(filtered)} articles · {badge_summary}")

    st.divider()

    # ------------------------------------------------------------------
    # News cards
    # ------------------------------------------------------------------
    for item in filtered:
        _render_news_card(item)


def _render_news_card(item: dict):
    """Render a single news item card with badge."""
    source   = item.get("source", "Unknown")
    title    = item.get("title", "")
    url      = item.get("url", "#")
    summary  = item.get("summary", "")
    pub_date = item.get("published_at", "")
    category = item.get("_category", "unclassified")
    color    = item.get("_color", "#555577")

    date_str = ""
    if pub_date:
        try:
            dt       = datetime.fromisoformat(pub_date)
            date_str = dt.strftime("%b %d, %Y")
        except ValueError:
            date_str = pub_date[:10]

    badge_label = BADGE_LABELS.get(category, "General")

    with st.container():
        col1, col2 = st.columns([5, 1])

        with col1:
            # Badge inline with title
            badge_html = (
                f"<span style='background:{color}22; color:{color}; "
                f"border:1px solid {color}66; border-radius:4px; "
                f"padding:1px 7px; font-size:0.68rem; font-weight:600; "
                f"text-transform:uppercase; letter-spacing:0.04em; "
                f"margin-right:8px'>{badge_label}</span>"
            )
            st.markdown(
                f"{badge_html}**[{title}]({url})**",
                unsafe_allow_html=True,
            )
            if summary:
                st.caption(summary[:200] + "..." if len(summary) > 200 else summary)

        with col2:
            st.caption(source)
            if date_str:
                st.caption(date_str)

        st.divider()

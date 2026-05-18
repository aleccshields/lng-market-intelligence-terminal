"""
src/dashboard/news_tab.py - LNG Market Intelligence Terminal

News Intelligence tab: RSS feed display with manual refresh.
"""

import streamlit as st
from datetime import datetime
from src.news.rss_ingestor import ingest_all_feeds, get_news_for_display
from src.database.db import init_db


def render():
    """Render the news intelligence tab."""
    st.header("LNG & Energy News Feed")
    st.caption(
        "Headlines from EIA Today in Energy, Natural Gas Intelligence, "
        "and Global LNG Hub. Click Refresh to ingest latest articles."
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
            st.info("No new articles found — feeds are up to date.")

    # ------------------------------------------------------------------
    # Display news items
    # ------------------------------------------------------------------
    items = get_news_for_display(limit=50)

    if not items:
        st.info("No news items yet. Click Refresh News to load articles.")
        return

    # Source filter
    sources = sorted(set(item["source"] for item in items))
    selected_sources = st.multiselect(
        "Filter by source", sources, default=sources
    )

    filtered = [i for i in items if i["source"] in selected_sources]
    st.caption(f"Showing {len(filtered)} articles")

    st.divider()

    for item in filtered:
        _render_news_card(item)


def _render_news_card(item: dict):
    """Render a single news item card."""
    source = item.get("source", "Unknown")
    title  = item.get("title", "")
    url    = item.get("url", "#")
    summary = item.get("summary", "")
    pub_date = item.get("published_at", "")

    # Format date
    date_str = ""
    if pub_date:
        try:
            dt = datetime.fromisoformat(pub_date)
            date_str = dt.strftime("%b %d, %Y")
        except ValueError:
            date_str = pub_date[:10]

    with st.container():
        col1, col2 = st.columns([5, 1])
        with col1:
            st.markdown(f"**[{title}]({url})**")
            if summary:
                st.caption(summary[:200] + "..." if len(summary) > 200 else summary)
        with col2:
            st.caption(source)
            if date_str:
                st.caption(date_str)
        st.divider()

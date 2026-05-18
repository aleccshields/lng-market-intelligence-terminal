"""
src/news/rss_ingestor.py - LNG Market Intelligence Terminal

RSS feed ingestion pipeline for LNG and energy market news.

Market context:
    LNG prices are highly sensitive to news events. Key categories that
    move markets:

    Supply disruptions: Freeport LNG outage (2022) removed ~2 Bcf/d of
        U.S. export capacity for months, contributing to the TTF spike.
        Any unplanned outage at a major liquefaction terminal is an
        immediate Atlantic Basin tightening signal.

    Geopolitical events: Russian pipeline curtailments to Europe (2022)
        structurally shifted European demand toward LNG, permanently
        elevating the TTF-HH spread baseline.

    Weather: Cold snaps in Northeast Asia drive JKM spikes. European
        heating demand determines winter storage draw rates.

    Regulatory: FERC approvals for new U.S. export terminals, EU gas
        demand reduction targets, and Panama Canal draft restrictions
        all affect medium-term supply/demand balances.

    This module ingests RSS feeds, deduplicates against the database,
    and stores headlines for display in the news tab. In production,
    a news intelligence system would also pull from Dow Jones Newswires,
    Bloomberg headlines, and LNG-specialist sources like LNG Intelligence
    or Gas Matters.
"""

import feedparser
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from src.database.db import insert_news_item, get_recent_news
from config import RSS_FEEDS


def _parse_published_date(entry: dict) -> str | None:
    """
    Extract and normalize the published date from an RSS entry.

    feedparser provides published_parsed as a time.struct_time.
    We convert to ISO format string for database storage.

    Args:
        entry : feedparser entry dict

    Returns:
        ISO format datetime string, or None if not parseable
    """
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return datetime(*entry.published_parsed[:6]).isoformat()
    except (TypeError, ValueError):
        pass
    return None


def _clean_summary(raw: str | None) -> str | None:
    """
    Strip HTML tags from RSS summary fields.

    Many RSS feeds include HTML markup in the description field.
    BeautifulSoup extracts clean text.

    Args:
        raw : Raw summary string, possibly containing HTML

    Returns:
        Clean text string, or None if input is None/empty
    """
    if not raw:
        return None
    try:
        soup = BeautifulSoup(raw, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        # Truncate long summaries for database storage
        return text[:500] if len(text) > 500 else text
    except Exception:
        return raw[:500] if raw else None


def ingest_feed(feed_name: str, feed_url: str) -> dict:
    """
    Fetch and parse a single RSS feed, storing new items to the database.

    Deduplication is handled at the database layer via the UNIQUE
    constraint on the url column in news_items. insert_news_item()
    returns False for duplicates without raising an error.

    Args:
        feed_name : Display name for the feed source
        feed_url  : RSS feed URL

    Returns:
        Dict with keys:
            feed_name   : Feed identifier
            fetched     : Total entries in feed
            inserted    : New entries added to DB
            duplicates  : Entries already in DB (skipped)
            errors      : Entries that failed to parse
    """
    stats = {
        "feed_name":  feed_name,
        "fetched":    0,
        "inserted":   0,
        "duplicates": 0,
        "errors":     0,
    }

    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        print(f"Failed to fetch feed '{feed_name}': {e}")
        return stats

    entries = feed.get("entries", [])
    stats["fetched"] = len(entries)

    for entry in entries:
        try:
            url   = entry.get("link") or entry.get("id")
            title = entry.get("title", "").strip()

            if not url or not title:
                stats["errors"] += 1
                continue

            published = _parse_published_date(entry)
            summary   = _clean_summary(
                entry.get("summary") or entry.get("description")
            )

            inserted = insert_news_item(
                url=url,
                title=title,
                source=feed_name,
                published_at=published,
                summary=summary,
            )

            if inserted:
                stats["inserted"] += 1
            else:
                stats["duplicates"] += 1

        except Exception as e:
            print(f"Error processing entry in '{feed_name}': {e}")
            stats["errors"] += 1

    return stats


def ingest_all_feeds(feeds: dict = None) -> list[dict]:
    """
    Ingest all configured RSS feeds.

    Args:
        feeds : Dict of {name: url} pairs. Uses RSS_FEEDS from config
                if not provided.

    Returns:
        List of stats dicts from ingest_feed(), one per feed.
    """
    if feeds is None:
        feeds = RSS_FEEDS

    all_stats = []
    for feed_name, feed_url in feeds.items():
        print(f"  Ingesting: {feed_name}...")
        stats = ingest_feed(feed_name, feed_url)
        print(f"    Fetched: {stats['fetched']} | "
              f"New: {stats['inserted']} | "
              f"Dupes: {stats['duplicates']} | "
              f"Errors: {stats['errors']}")
        all_stats.append(stats)

    return all_stats


def get_news_for_display(limit: int = 50) -> list[dict]:
    """
    Retrieve recent news items formatted for the Streamlit news tab.

    Returns items sorted by ingestion time descending (newest first).
    Each item includes a truncated title and source label suitable
    for rendering as a news feed card.

    Args:
        limit : Maximum number of items to return

    Returns:
        List of news item dicts from the database
    """
    return get_recent_news(limit=limit)


if __name__ == "__main__":
    # Initialize DB first to ensure tables exist
    from src.database.db import init_db
    init_db()

    print("\nIngesting all RSS feeds...")
    stats = ingest_all_feeds()

    total_inserted = sum(s["inserted"] for s in stats)
    total_fetched  = sum(s["fetched"] for s in stats)
    print(f"\nTotal fetched : {total_fetched}")
    print(f"Total inserted: {total_inserted}")

    print("\nMost recent 5 items in database:")
    items = get_news_for_display(limit=5)
    for item in items:
        print(f"  [{item['source']}] {item['title'][:80]}")

    print("\nrss_ingestor.py OK")

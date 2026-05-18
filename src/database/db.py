"""
src/database/db.py - LNG Market Intelligence Terminal

SQLite database setup and query helpers.

Why SQLite:
    For a portfolio project running locally, SQLite is sufficient.
    It requires no server, no credentials, and no setup beyond this file.
    In production (e.g., deployed on Render), this would be swapped for
    PostgreSQL with minimal code changes thanks to SQLAlchemy's abstraction.

Schema design:
    - price_snapshots: Caches fetched price data with timestamps so the
      app does not hammer APIs on every page reload.
    - news_items: Stores ingested RSS headlines for the news feed tab.
    - arb_log: Records arbitrage calculations over time so users can
      see how margins have evolved.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

# Database file lives in the data/ directory, not source control
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "lng_terminal.db"


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row_factory set to return dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Create all tables if they do not already exist.
    Safe to call on every app startup.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT NOT NULL,
            price       REAL NOT NULL,
            currency    TEXT NOT NULL DEFAULT 'USD',
            unit        TEXT NOT NULL DEFAULT 'MMBtu',
            fetched_at  TEXT NOT NULL,
            source      TEXT NOT NULL DEFAULT 'yfinance'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news_items (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            url             TEXT UNIQUE NOT NULL,
            title           TEXT NOT NULL,
            source          TEXT NOT NULL,
            published_at    TEXT,
            ingested_at     TEXT NOT NULL,
            summary         TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS arb_log (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            calculated_at       TEXT NOT NULL,
            route               TEXT NOT NULL,
            hh_price            REAL,
            destination_price   REAL,
            liquefaction_cost   REAL,
            shipping_cost       REAL,
            regas_cost          REAL,
            netback             REAL,
            margin_usd_mmbtu    REAL,
            arb_open            INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
    print(f"Database initialized at: {DB_PATH}")


def insert_news_item(url: str, title: str, source: str,
                     published_at: str = None, summary: str = None) -> bool:
    """
    Insert a news item. Returns True if inserted, False if duplicate.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO news_items (url, title, source, published_at, ingested_at, summary)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (url, title, source, published_at,
              datetime.utcnow().isoformat(), summary))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_recent_news(limit: int = 50) -> list:
    """Fetch the most recently ingested news items."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM news_items
        ORDER BY ingested_at DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def log_arb_calculation(route: str, hh_price: float, destination_price: float,
                         liquefaction_cost: float, shipping_cost: float,
                         regas_cost: float, netback: float,
                         margin: float, arb_open: bool) -> None:
    """Record a single arbitrage calculation to the arb_log table."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO arb_log (
            calculated_at, route, hh_price, destination_price,
            liquefaction_cost, shipping_cost, regas_cost,
            netback, margin_usd_mmbtu, arb_open
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().isoformat(), route, hh_price, destination_price,
        liquefaction_cost, shipping_cost, regas_cost,
        netback, margin, int(arb_open)
    ))
    conn.commit()
    conn.close()


def get_arb_history(route: str = None, limit: int = 90) -> list:
    """Fetch historical arbitrage calculations, optionally filtered by route."""
    conn = get_connection()
    cursor = conn.cursor()
    if route:
        cursor.execute("""
            SELECT * FROM arb_log
            WHERE route = ?
            ORDER BY calculated_at DESC
            LIMIT ?
        """, (route, limit))
    else:
        cursor.execute("""
            SELECT * FROM arb_log
            ORDER BY calculated_at DESC
            LIMIT ?
        """, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


if __name__ == "__main__":
    init_db()

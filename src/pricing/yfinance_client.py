"""
src/pricing/yfinance_client.py - LNG Market Intelligence Terminal

Fetches front-month futures prices via yfinance.
Brent crude is sourced from EIA API (series PET.RBRTE.D) rather than
yfinance BZ=F, which returns unreliable values on Python 3.14.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from config import (
    TICKER_HENRY_HUB,
    TICKER_TTF,
    MWH_TO_MMBTU,
    EUR_USD_FALLBACK,
    LOOKBACK_DEFAULT,
)


def fetch_eur_usd() -> float:
    """
    Fetch the current EUR/USD exchange rate via yfinance.
    Falls back to EUR_USD_FALLBACK if the fetch fails.
    """
    try:
        ticker = yf.Ticker("EURUSD=X")
        hist = ticker.history(period="2d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return EUR_USD_FALLBACK


def fetch_price_history(ticker: str, days: int = LOOKBACK_DEFAULT) -> pd.DataFrame:
    """
    Fetch daily closing price history for a single yfinance ticker.

    Args:
        ticker : yfinance ticker string (e.g. 'NG=F')
        days   : Number of calendar days to look back

    Returns:
        DataFrame with columns [Close, ticker] indexed by Date.
    """
    try:
        end   = datetime.today()
        start = end - timedelta(days=days)
        df = yf.download(ticker, start=start, end=end,
                         progress=False, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df = df[["Close"]].copy()
        df.columns = ["Close"]
        df.index.name = "Date"
        df["ticker"] = ticker
        return df
    except Exception as e:
        print(f"yfinance fetch failed for {ticker}: {e}")
        return pd.DataFrame()


def fetch_latest_price(ticker: str) -> float | None:
    """Fetch only the most recent closing price for a yfinance ticker."""
    try:
        t    = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"Latest price fetch failed for {ticker}: {e}")
    return None


def fetch_brent_from_eia() -> float | None:
    """
    Fetch Brent crude spot price from EIA API.

    Series: PET.RBRTE.D (Europe Brent Spot Price FOB, Dollars per Barrel)

    This replaces the yfinance BZ=F ticker which returns unreliable
    values on Python 3.14. EIA Brent spot is the same series cited
    in IEA reports and most energy market publications.

    Returns:
        Latest Brent spot price in USD/bbl, or None on failure.
    """
    from config import EIA_API_KEY, EIA_BASE_URL
    import requests

    if not EIA_API_KEY:
        return None

    try:
        response = requests.get(
            EIA_BASE_URL + "petroleum/pri/spt/data/",
            params={
                "api_key":              EIA_API_KEY,
                "frequency":            "daily",
                "data[0]":              "value",
                "facets[series][]":     "RBRTE",
                "sort[0][column]":      "period",
                "sort[0][direction]":   "desc",
                "length":               5,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        rows = data["response"]["data"]
        if rows:
            return float(rows[0]["value"])
    except Exception as e:
        print(f"EIA Brent fetch failed: {e}")
    return None


def fetch_brent_history_from_eia(days: int = LOOKBACK_DEFAULT) -> pd.DataFrame:
    """
    Fetch Brent crude spot price history from EIA API.

    Returns:
        DataFrame with columns [Close] indexed by Date.
    """
    from config import EIA_API_KEY, EIA_BASE_URL
    import requests

    if not EIA_API_KEY:
        return pd.DataFrame()

    start_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        response = requests.get(
            EIA_BASE_URL + "petroleum/pri/spt/data/",
            params={
                "api_key":              EIA_API_KEY,
                "frequency":            "daily",
                "data[0]":              "value",
                "facets[series][]":     "RBRTE",
                "start":                start_date,
                "sort[0][column]":      "period",
                "sort[0][direction]":   "asc",
                "length":               500,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        rows = data["response"]["data"]
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)[["period", "value"]].copy()
        df.columns = ["Date", "Close"]
        df["Date"]  = pd.to_datetime(df["Date"])
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        df = df.dropna().set_index("Date").sort_index()
        df["ticker"] = "BRENT_EIA"
        return df
    except Exception as e:
        print(f"EIA Brent history fetch failed: {e}")
        return pd.DataFrame()


def fetch_all_prices() -> dict:
    """
    Fetch latest prices for all core tickers.

    Brent is sourced from EIA (accurate spot price).
    HH and TTF are sourced from yfinance (front-month futures).
    TTF is converted from EUR/MWh to USD/MMBtu.

    Returns:
        Dict with keys: hh_price, ttf_raw, ttf_usd_mmbtu,
                        brent_price, eur_usd, fetched_at
    """
    eur_usd = fetch_eur_usd()
    hh      = fetch_latest_price(TICKER_HENRY_HUB)
    ttf     = fetch_latest_price(TICKER_TTF)

    # Brent from EIA — accurate spot price
    brent = fetch_brent_from_eia()

    ttf_converted = None
    if ttf is not None:
        ttf_converted = ttf * eur_usd / MWH_TO_MMBTU

    return {
        "hh_price":      hh,
        "ttf_raw":       ttf,
        "ttf_usd_mmbtu": ttf_converted,
        "brent_price":   brent,
        "eur_usd":       eur_usd,
        "fetched_at":    datetime.now().isoformat(),
    }


def fetch_all_histories(days: int = LOOKBACK_DEFAULT) -> dict:
    """
    Fetch price history DataFrames for all core tickers.

    Returns:
        Dict with keys 'henry_hub', 'brent', 'ttf'
    """
    return {
        "henry_hub": fetch_price_history(TICKER_HENRY_HUB, days),
        "brent":     fetch_brent_history_from_eia(days),
        "ttf":       fetch_price_history(TICKER_TTF, days),
    }


if __name__ == "__main__":
    print("Fetching latest prices...")
    prices = fetch_all_prices()
    print(f"  Henry Hub : ${prices['hh_price']:.3f}/MMBtu" if prices['hh_price'] else "  Henry Hub : fetch failed")
    print(f"  Brent(EIA): ${prices['brent_price']:.2f}/bbl" if prices['brent_price'] else "  Brent     : fetch failed")
    print(f"  TTF (raw) : {prices['ttf_raw']:.2f} EUR/MWh"  if prices['ttf_raw'] else "  TTF       : fetch failed")
    print(f"  TTF (conv): ${prices['ttf_usd_mmbtu']:.3f}/MMBtu" if prices['ttf_usd_mmbtu'] else "  TTF (conv): fetch failed")
    print(f"  EUR/USD   : {prices['eur_usd']:.4f}")

"""
src/pricing/yfinance_client.py - LNG Market Intelligence Terminal

Fetches front-month futures prices via yfinance.

Market context:
    We pull three tickers:
        NG=F  Henry Hub natural gas front-month (USD/MMBtu)
        BZ=F  Brent crude front-month (USD/bbl)
        TTF=F TTF Dutch gas front-month (EUR/MWh)

    Front-month futures are the most liquid point on the forward curve
    and serve as the de facto spot price reference for LNG analysis.

    TTF requires unit conversion before it can be compared to Henry Hub.
    TTF trades in EUR/MWh; we convert to USD/MMBtu using:
        price_usd_mmbtu = price_eur_mwh * eur_usd_rate / MWH_TO_MMBTU

    In a production system these prices would come from a Bloomberg
    terminal (BFIX/BGN) or ICE direct feed with real-time streaming.
    yfinance provides delayed data (~15 min) which is acceptable for
    portfolio and analytical purposes.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from config import (
    TICKER_HENRY_HUB,
    TICKER_BRENT,
    TICKER_TTF,
    MWH_TO_MMBTU,
    EUR_USD_FALLBACK,
    LOOKBACK_DEFAULT,
)


def fetch_eur_usd() -> float:
    """
    Fetch the current EUR/USD exchange rate via yfinance.
    Falls back to EUR_USD_FALLBACK if the fetch fails.

    Returns:
        EUR/USD rate as a float (e.g. 1.08)
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
    Fetch daily closing price history for a single ticker.

    Args:
        ticker : yfinance ticker string (e.g. 'NG=F')
        days   : Number of calendar days to look back

    Returns:
        DataFrame with columns [Date, Close, ticker] indexed by Date.
        Returns empty DataFrame if fetch fails.
    """
    try:
        end = datetime.today()
        start = end - timedelta(days=days)
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
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
    """
    Fetch only the most recent closing price for a ticker.

    Args:
        ticker : yfinance ticker string

    Returns:
        Latest closing price as float, or None if fetch fails.
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"Latest price fetch failed for {ticker}: {e}")
    return None


def fetch_all_prices() -> dict:
    """
    Fetch latest prices for all three core tickers and return a
    unified dict with values converted to USD/MMBtu where needed.

    TTF conversion:
        EUR/MWh -> USD/MMBtu = price * eur_usd / MWH_TO_MMBTU

    JKM is not fetched here — it is estimated in price_utils.py
    using the Brent proxy formula.

    Returns:
        Dict with keys:
            hh_price        : Henry Hub USD/MMBtu
            ttf_raw         : TTF in native EUR/MWh
            ttf_usd_mmbtu   : TTF converted to USD/MMBtu
            brent_price     : Brent in USD/bbl
            eur_usd         : EUR/USD rate used for conversion
            fetched_at      : UTC timestamp string
        Any value may be None if its fetch failed.
    """
    eur_usd = fetch_eur_usd()

    hh    = fetch_latest_price(TICKER_HENRY_HUB)
    brent = fetch_latest_price(TICKER_BRENT)
    ttf   = fetch_latest_price(TICKER_TTF)

    ttf_converted = None
    if ttf is not None:
        ttf_converted = ttf * eur_usd / MWH_TO_MMBTU

    return {
        "hh_price":       hh,
        "ttf_raw":        ttf,
        "ttf_usd_mmbtu":  ttf_converted,
        "brent_price":    brent,
        "eur_usd":        eur_usd,
        "fetched_at":     datetime.utcnow().isoformat(),
    }


def fetch_all_histories(days: int = LOOKBACK_DEFAULT) -> dict:
    """
    Fetch price history DataFrames for all core tickers.

    Args:
        days : Lookback period in calendar days

    Returns:
        Dict with keys 'henry_hub', 'brent', 'ttf', each containing
        a DataFrame from fetch_price_history(), or empty DataFrame on failure.
    """
    return {
        "henry_hub": fetch_price_history(TICKER_HENRY_HUB, days),
        "brent":     fetch_price_history(TICKER_BRENT, days),
        "ttf":       fetch_price_history(TICKER_TTF, days),
    }


if __name__ == "__main__":
    print("Fetching latest prices...")
    prices = fetch_all_prices()
    print(f"  Henry Hub : ${prices['hh_price']:.3f}/MMBtu" if prices['hh_price'] else "  Henry Hub : fetch failed")
    print(f"  Brent     : ${prices['brent_price']:.2f}/bbl" if prices['brent_price'] else "  Brent     : fetch failed")
    print(f"  TTF (raw) : {prices['ttf_raw']:.2f} EUR/MWh" if prices['ttf_raw'] else "  TTF       : fetch failed")
    print(f"  TTF (conv): ${prices['ttf_usd_mmbtu']:.3f}/MMBtu" if prices['ttf_usd_mmbtu'] else "  TTF (conv): fetch failed")
    print(f"  EUR/USD   : {prices['eur_usd']:.4f}")
    print(f"  Fetched at: {prices['fetched_at']}")

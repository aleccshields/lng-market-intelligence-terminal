"""
src/pricing/eia_client.py - LNG Market Intelligence Terminal

Fetches U.S. natural gas data from the EIA Open Data API v2.

Market context:
    The EIA (U.S. Energy Information Administration) publishes free,
    high-quality natural gas data including:
        - Henry Hub spot prices (daily)
        - U.S. natural gas storage (weekly, every Thursday)
        - LNG export volumes by terminal (monthly)

    Henry Hub is the primary U.S. natural gas pricing hub and the
    reference point for most U.S. LNG export contracts. Sabine Pass,
    Corpus Christi, and other Gulf Coast terminals sell LNG at contracts
    typically priced as 115% x Henry Hub + a fixed liquefaction fee.

    Storage data matters because U.S. gas storage vs. the 5-year average
    is a key short-term price signal — low storage = bullish Henry Hub.

    In production, traders use Platts or Bloomberg for real-time HH
    pricing, but EIA spot data (1-day lag) is the gold standard for
    historical analysis and is the source most academic work cites.

Requires:
    EIA_API_KEY set in .env file.
    Register free at: https://www.eia.gov/opendata/
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
from config import EIA_API_KEY, EIA_BASE_URL


def _get(endpoint: str, params: dict) -> dict | None:
    """
    Internal helper — makes a GET request to the EIA API v2.

    Args:
        endpoint : API path after base URL (e.g. 'natural-gas/pri/sum/data/')
        params   : Query parameters dict

    Returns:
        Parsed JSON response dict, or None on failure.
    """
    if not EIA_API_KEY:
        print("Warning: EIA_API_KEY not set. Skipping EIA fetch.")
        return None

    params["api_key"] = EIA_API_KEY
    url = EIA_BASE_URL + endpoint

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"EIA API request failed: {e}")
        return None


def fetch_henry_hub_spot(days: int = 90) -> pd.DataFrame:
    """
    Fetch Henry Hub daily spot prices from EIA.

    Series: NG.RNGWHHD.D (Henry Hub Natural Gas Spot Price, Dollars per MMBtu)

    Args:
        days : Number of days of history to fetch

    Returns:
        DataFrame with columns [date, price_usd_mmbtu], sorted ascending.
        Returns empty DataFrame if API key missing or request fails.
    """
    start_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    data = _get("natural-gas/pri/sum/data/", {
        "frequency": "daily",
        "data[0]": "value",
        "facets[series][]": "RNGWHHD",
        "start": start_date,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 500,
    })

    if not data:
        return pd.DataFrame()

    try:
        rows = data["response"]["data"]
        df = pd.DataFrame(rows)
        df = df[["period", "value"]].copy()
        df.columns = ["date", "price_usd_mmbtu"]
        df["date"] = pd.to_datetime(df["date"])
        df["price_usd_mmbtu"] = pd.to_numeric(df["price_usd_mmbtu"], errors="coerce")
        df = df.dropna().sort_values("date").reset_index(drop=True)
        return df
    except (KeyError, TypeError) as e:
        print(f"EIA Henry Hub parse error: {e}")
        return pd.DataFrame()


def fetch_us_gas_storage(weeks: int = 52) -> pd.DataFrame:
    """
    Fetch U.S. weekly natural gas storage from EIA.

    Series: NG.NW2_EPG0_SWO_R48_BCF.W
    (Working Gas in Underground Storage, Lower 48 States, BCF)

    Published every Thursday covering the week ending the prior Friday.
    The storage surplus/deficit vs. the 5-year average is a key
    short-term price driver — traders watch this number closely.

    Args:
        weeks : Number of weeks of history to fetch

    Returns:
        DataFrame with columns [date, storage_bcf], sorted ascending.
        Returns empty DataFrame on failure.
    """
    start_date = (datetime.today() - timedelta(weeks=weeks)).strftime("%Y-%m-%d")

    data = _get("natural-gas/stor/wkly/data/", {
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": "NW2_EPG0_SWO_R48_BCF",
        "start": start_date,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 200,
    })

    if not data:
        return pd.DataFrame()

    try:
        rows = data["response"]["data"]
        df = pd.DataFrame(rows)
        df = df[["period", "value"]].copy()
        df.columns = ["date", "storage_bcf"]
        df["date"] = pd.to_datetime(df["date"])
        df["storage_bcf"] = pd.to_numeric(df["storage_bcf"], errors="coerce")
        df = df.dropna().sort_values("date").reset_index(drop=True)
        return df
    except (KeyError, TypeError) as e:
        print(f"EIA storage parse error: {e}")
        return pd.DataFrame()


if __name__ == "__main__":
    print("Testing EIA client...")

    hh = fetch_henry_hub_spot(days=30)
    if not hh.empty:
        print(f"  Henry Hub spot: {len(hh)} rows fetched")
        print(f"  Latest: ${hh['price_usd_mmbtu'].iloc[-1]:.3f}/MMBtu on {hh['date'].iloc[-1].date()}")
    else:
        print("  Henry Hub: no data (check EIA_API_KEY in .env)")

    storage = fetch_us_gas_storage(weeks=8)
    if not storage.empty:
        print(f"  US Storage: {len(storage)} weeks fetched")
        print(f"  Latest: {storage['storage_bcf'].iloc[-1]:,.0f} BCF on {storage['date'].iloc[-1].date()}")
    else:
        print("  Storage: no data (check EIA_API_KEY in .env)")

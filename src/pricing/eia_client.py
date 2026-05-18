"""
src/pricing/eia_client.py - LNG Market Intelligence Terminal

Fetches U.S. natural gas data from the EIA Open Data API v2.

Market context:
    Henry Hub is the primary U.S. natural gas pricing hub and the
    reference point for most U.S. LNG export contracts.

    Storage data matters because the surplus/deficit vs. the 52-week
    rolling average is the most-watched short-term HH price signal.
    Released every Thursday at 10:30am ET.

    Regional storage matters for basis differentials — the South Central
    region (salt and nonsalt caverns) is the most flexible and fills/draws
    fastest, making it the most market-moving regional reporter.

Requires:
    EIA_API_KEY set in .env or Streamlit secrets.
    Register free at: https://www.eia.gov/opendata/
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
from config import EIA_API_KEY, EIA_BASE_URL


# EIA region codes matching the original storage tracker
US_STORAGE_REGIONS = {
    "Lower 48 States":    "R48",
    "East Region":        "R31",
    "Midwest Region":     "R32",
    "South Central":      "R33",
    "Mountain Region":    "R34",
    "Pacific Region":     "R35",
}


def _get(endpoint: str, params: dict) -> dict | None:
    """Internal GET helper for EIA API v2."""
    if not EIA_API_KEY:
        print("Warning: EIA_API_KEY not set.")
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

    Returns:
        DataFrame with columns [date, price_usd_mmbtu], sorted ascending.
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
        df = pd.DataFrame(rows)[["period", "value"]].copy()
        df.columns = ["date", "price_usd_mmbtu"]
        df["date"] = pd.to_datetime(df["date"])
        df["price_usd_mmbtu"] = pd.to_numeric(df["price_usd_mmbtu"], errors="coerce")
        return df.dropna().sort_values("date").reset_index(drop=True)
    except (KeyError, TypeError) as e:
        print(f"EIA Henry Hub parse error: {e}")
        return pd.DataFrame()


def fetch_us_gas_storage(weeks: int = 52, region_code: str = "R48") -> pd.DataFrame:
    """
    Fetch U.S. weekly natural gas storage for a specific region.

    Uses the duoarea facet to filter by region, matching the original
    LNG Storage Tracker exactly.

    Region codes:
        R48 = Lower 48 States (national aggregate)
        R31 = East Region
        R32 = Midwest Region
        R33 = South Central Region
        R34 = Mountain Region
        R35 = Pacific Region

    Args:
        weeks       : Number of weeks of history to fetch (default 52)
        region_code : EIA duoarea code (default 'R48' = national)

    Returns:
        DataFrame with columns [date, storage_bcf, region],
        sorted ascending. Returns empty DataFrame on failure.
    """
    start_date = (datetime.today() - timedelta(weeks=weeks)).strftime("%Y-%m-%d")

    data = _get("natural-gas/stor/wkly/data/", {
        "frequency": "weekly",
        "data[0]": "value",
        "facets[duoarea][]": region_code,
        "facets[process][]": "SWO",
        "start": start_date,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 200,
    })

    if not data:
        return pd.DataFrame()

    try:
        rows = data["response"]["data"]
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df = df[["period", "value"]].copy()
        df.columns = ["date", "storage_bcf"]
        df["date"] = pd.to_datetime(df["date"])
        df["storage_bcf"] = pd.to_numeric(df["storage_bcf"], errors="coerce")
        df["region"] = region_code
        return df.dropna().sort_values("date").reset_index(drop=True)
    except (KeyError, TypeError) as e:
        print(f"EIA storage parse error for {region_code}: {e}")
        return pd.DataFrame()


def fetch_all_regions(weeks: int = 52) -> dict:
    """
    Fetch storage data for all six EIA regions.

    Args:
        weeks : Number of weeks of history per region

    Returns:
        Dict mapping region label -> DataFrame.
        Regions that fail to fetch are excluded with a warning.
    """
    results = {}
    for label, code in US_STORAGE_REGIONS.items():
        df = fetch_us_gas_storage(weeks=weeks, region_code=code)
        if not df.empty:
            results[label] = df
        else:
            print(f"  Warning: no data for {label} ({code})")
    return results


if __name__ == "__main__":
    print("Testing EIA client...")

    hh = fetch_henry_hub_spot(days=30)
    if not hh.empty:
        print(f"  Henry Hub: ${hh['price_usd_mmbtu'].iloc[-1]:.3f}/MMBtu on {hh['date'].iloc[-1].date()}")
    else:
        print("  Henry Hub: no data (check EIA_API_KEY in .env)")

    for label, code in US_STORAGE_REGIONS.items():
        df = fetch_us_gas_storage(weeks=4, region_code=code)
        if not df.empty:
            print(f"  {label}: {df['storage_bcf'].iloc[-1]:,.0f} Bcf on {df['date'].iloc[-1].date()}")
        else:
            print(f"  {label}: no data")

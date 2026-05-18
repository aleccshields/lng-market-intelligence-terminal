"""
src/storage/agsi_client.py - LNG Market Intelligence Terminal

Fetches European natural gas storage data from the AGSI+ API.

Market context:
    European gas storage is one of the most closely watched LNG demand
    signals. If storage enters winter below the 5-year average, Europe
    needs more LNG imports to compensate, tightening Atlantic Basin
    balances and pushing TTF higher.

    The EU mandated 80% storage fill by November 1 starting in 2022
    (regulation EU 2022/1032), creating a structural seasonal buying
    pattern that LNG exporters now price into summer cargoes.

    Note on field differences between EU aggregate and country level:
        EU aggregate : uses 'full' field directly for fill percentage
        Country level: fill pct = gasInStorage / workingGasVolume * 100
                       Country endpoints also paginate (1 row per page)

    AGSI+ is operated by GIE (Gas Infrastructure Europe).
    Free API key required: https://agsi.gie.eu
    Updated daily with approximately 1-2 day lag.
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
from config import AGSI_BASE_URL, AGSI_COUNTRY_CODES, AGSI_API_KEY


def _get_headers() -> dict:
    """Return request headers with AGSI+ API key (passed as x-key)."""
    return {"x-key": AGSI_API_KEY}


def fetch_eu_storage(days: int = 365) -> pd.DataFrame:
    """
    Fetch EU aggregate gas storage levels from AGSI+.

    Args:
        days : Number of calendar days of history to fetch

    Returns:
        DataFrame with columns: date, full_pct, gas_in_storage, country
    """
    if not AGSI_API_KEY:
        print("Warning: AGSI_API_KEY not set in .env")
        return pd.DataFrame()

    end_date = datetime.today()
    start_date = end_date - timedelta(days=days)

    params = {
        "type": "EU",
        "from": start_date.strftime("%Y-%m-%d"),
        "to":   end_date.strftime("%Y-%m-%d"),
        "size": 500,
    }

    try:
        response = requests.get(
            AGSI_BASE_URL + "/data",
            params=params,
            headers=_get_headers(),
            timeout=15
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"AGSI+ EU aggregate fetch failed: {e}")
        return pd.DataFrame()

    return _parse_eu_response(data)


def fetch_country_storage(country_code: str, days: int = 365) -> pd.DataFrame:
    """
    Fetch gas storage data for a single European country.

    Country endpoints paginate (AGSI+ returns ~1 record per page by
    default for country queries). This function paginates automatically.

    Args:
        country_code : Two-letter code e.g. 'de', 'fr', 'it'
        days         : Number of calendar days of history to fetch

    Returns:
        DataFrame with columns: date, full_pct, gas_in_storage, country
    """
    if not AGSI_API_KEY:
        print("Warning: AGSI_API_KEY not set in .env")
        return pd.DataFrame()

    end_date = datetime.today()
    start_date = end_date - timedelta(days=days)

    all_records = []
    page = 1
    max_pages = 15

    while page <= max_pages:
        params = {
            "country": country_code.upper(),
            "from":    start_date.strftime("%Y-%m-%d"),
            "to":      end_date.strftime("%Y-%m-%d"),
            "size":    30,
            "page":    page,
        }

        try:
            response = requests.get(
                AGSI_BASE_URL + "/data",
                params=params,
                headers=_get_headers(),
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"AGSI+ fetch failed for {country_code} page {page}: {e}")
            break

        if data.get("error"):
            print(f"AGSI+ API error: {data.get('message')}")
            break

        records = data.get("data", [])
        if not records:
            break

        all_records.extend(records)

        last_page = int(data.get("last_page", 1))
        if page >= last_page:
            break
        page += 1

    if not all_records:
        print(f"AGSI+ returned empty data for {country_code}")
        return pd.DataFrame()

    return _parse_country_records(all_records, country_code=country_code.lower())


def fetch_all_countries(days: int = 180) -> pd.DataFrame:
    """
    Fetch and combine storage data for all tracked countries.
    Used for the multi-country comparison chart.
    """
    frames = []

    eu_df = fetch_eu_storage(days=days)
    if not eu_df.empty:
        eu_df["country_name"] = "EU Aggregate"
        frames.append(eu_df)

    for country_name, code in AGSI_COUNTRY_CODES.items():
        if code == "eu":
            continue
        df = fetch_country_storage(code, days=days)
        if not df.empty:
            df["country_name"] = country_name
            frames.append(df)
        else:
            print(f"  Skipping {country_name} - no data returned")

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    return combined.sort_values(["country", "date"]).reset_index(drop=True)


def _parse_eu_response(data: dict) -> pd.DataFrame:
    """
    Parse EU aggregate AGSI+ response.
    EU aggregate uses the 'full' field directly for fill percentage.
    """
    if data.get("error"):
        print(f"AGSI+ API error: {data.get('message')}")
        return pd.DataFrame()

    records = data.get("data", [])
    if not records:
        print("AGSI+ returned empty EU aggregate data")
        return pd.DataFrame()

    rows = []
    for item in records:
        try:
            rows.append({
                "date":           pd.to_datetime(item.get("gasDayStart")),
                "full_pct":       float(item.get("full", 0) or 0),
                "gas_in_storage": float(item.get("gasInStorage", 0) or 0),
                "country":        "eu",
            })
        except (ValueError, TypeError):
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["date", "full_pct"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _parse_country_records(records: list, country_code: str) -> pd.DataFrame:
    """
    Parse country-level AGSI+ records.

    Country responses do not include a 'full' percentage directly.
    Fill percentage is computed as: gasInStorage / workingGasVolume * 100
    where workingGasVolume is total working gas capacity in TWh.
    """
    rows = []
    for item in records:
        try:
            gas_in   = float(item.get("gasInStorage", 0) or 0)
            capacity = float(item.get("workingGasVolume", 0) or 0)

            if capacity > 0:
                full_pct = (gas_in / capacity) * 100
            else:
                full_pct = float(item.get("full", 0) or 0)

            rows.append({
                "date":           pd.to_datetime(item.get("gasDayStart")),
                "full_pct":       full_pct,
                "gas_in_storage": gas_in,
                "country":        country_code,
            })
        except (ValueError, TypeError):
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["date", "full_pct"])
    df = df.drop_duplicates(subset=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def get_storage_summary(df: pd.DataFrame) -> dict:
    """
    Compute summary statistics from a storage DataFrame.
    Used to populate dashboard header metric cards.

    Returns:
        Dict with keys: latest_pct, latest_date, trend_7d, yoy_change
    """
    if df.empty:
        return {}

    latest = df.iloc[-1]
    summary = {
        "latest_pct":  latest["full_pct"],
        "latest_date": latest["date"],
        "trend_7d":    None,
        "yoy_change":  None,
    }

    if len(df) >= 7:
        summary["trend_7d"] = latest["full_pct"] - df.iloc[-7]["full_pct"]

    if len(df) >= 30:
        target_date = latest["date"] - timedelta(days=365)
        df_copy = df.copy()
        df_copy["date_diff"] = (df_copy["date"] - target_date).abs()
        closest = df_copy.loc[df_copy["date_diff"].idxmin()]
        summary["yoy_change"] = latest["full_pct"] - closest["full_pct"]

    return summary


if __name__ == "__main__":
    print("Testing AGSI+ storage client...")

    print("\nFetching EU aggregate (90 days)...")
    eu_df = fetch_eu_storage(days=90)
    if not eu_df.empty:
        print(f"  Rows fetched : {len(eu_df)}")
        latest = eu_df.iloc[-1]
        print(f"  Latest date  : {latest['date'].date()}")
        print(f"  Storage fill : {latest['full_pct']:.1f}%")
        print(f"  Gas in store : {latest['gas_in_storage']:.1f} TWh")
        s = get_storage_summary(eu_df)
        if s.get("trend_7d") is not None:
            print(f"  7-day trend  : {s['trend_7d']:+.2f} pct points")
        if s.get("yoy_change") is not None:
            print(f"  YoY change   : {s['yoy_change']:+.2f} pct points")
    else:
        print("  No data - check AGSI_API_KEY in .env")

    print("\nFetching Germany (90 days)...")
    de_df = fetch_country_storage("de", days=90)
    if not de_df.empty:
        print(f"  Rows fetched  : {len(de_df)}")
        print(f"  Germany latest: {de_df.iloc[-1]['full_pct']:.1f}% full on {de_df.iloc[-1]['date'].date()}")
    else:
        print("  Germany: no data")

    print("\nagsi_client.py OK")

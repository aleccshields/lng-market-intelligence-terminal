"""
src/pricing/price_utils.py - LNG Market Intelligence Terminal

Price calculation utilities: spreads, rolling metrics, JKM proxy, volatility.

Market context:
    Raw prices are useful but traders work with derived metrics:

    Spreads:
        The TTF-HH spread is the most-watched LNG arbitrage signal.
        When TTF >> HH (after accounting for shipping/liquefaction),
        U.S. LNG exports are economically attractive to Europe.
        The JKM-HH spread drives Pacific Basin flows.

    Rolling averages:
        7-day and 30-day rolling means smooth out daily noise and
        reveal the underlying trend direction.

    Volatility:
        Realized volatility (annualized standard deviation of daily
        log returns) is used in options pricing and risk management.
        High HH volatility increases uncertainty in netback calculations.

    JKM proxy:
        We estimate JKM as: Brent_price * JKM_OIL_FACTOR + JKM_ASIA_PREMIUM
        This reflects the historical oil-indexation of Asian LNG contracts.
        All JKM-derived outputs must be labeled as estimated.
"""

import pandas as pd
import numpy as np
from config import (
    JKM_OIL_FACTOR,
    JKM_ASIA_PREMIUM,
    JKM_LABEL,
    MWH_TO_MMBTU,
)


def estimate_jkm(brent_price: float, asia_premium: float = JKM_ASIA_PREMIUM) -> float:
    """
    Estimate JKM spot price from Brent crude using the oil-indexation proxy.

    Formula:
        JKM_est = (Brent_usd_bbl * JKM_OIL_FACTOR) + asia_premium

    The 0.172 factor converts USD/bbl to USD/MMBtu using the approximate
    energy content ratio of crude oil to LNG, adjusted for historical
    contract pricing patterns in Asia.

    Args:
        brent_price  : Brent crude price in USD/bbl
        asia_premium : Structural Asia premium in USD/MMBtu (default 2.50)

    Returns:
        Estimated JKM price in USD/MMBtu. Label as estimated in all UI.
    """
    return (brent_price * JKM_OIL_FACTOR) + asia_premium


def estimate_jkm_series(brent_series: pd.Series,
                         asia_premium: float = JKM_ASIA_PREMIUM) -> pd.Series:
    """
    Apply JKM proxy formula to a full Brent price series.

    Args:
        brent_series : Pandas Series of Brent prices (USD/bbl)
        asia_premium : Structural Asia premium in USD/MMBtu

    Returns:
        Pandas Series of estimated JKM prices (USD/MMBtu)
    """
    return (brent_series * JKM_OIL_FACTOR) + asia_premium


def convert_ttf_to_usd_mmbtu(ttf_eur_mwh: float, eur_usd: float) -> float:
    """
    Convert TTF price from native EUR/MWh to USD/MMBtu.

    TTF (Title Transfer Facility) is the primary European gas hub,
    analogous to Henry Hub for the U.S. It trades in EUR/MWh on ICE.

    Conversion:
        USD/MMBtu = (EUR/MWh) * (USD/EUR) / (MWh/MMBtu)
        where 1 MWh = 3.412 MMBtu

    Args:
        ttf_eur_mwh : TTF price in EUR/MWh
        eur_usd     : EUR/USD exchange rate

    Returns:
        TTF price in USD/MMBtu
    """
    return ttf_eur_mwh * eur_usd / MWH_TO_MMBTU


def compute_spread(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    """
    Compute the price spread between two series (A minus B).

    Args:
        series_a : First price series
        series_b : Second price series (subtracted from A)

    Returns:
        Spread series aligned on the intersection of both indexes.
    """
    return series_a.subtract(series_b).dropna()


def compute_rolling_average(series: pd.Series, window: int) -> pd.Series:
    """
    Compute a rolling simple moving average.

    Args:
        series : Price series
        window : Rolling window in periods (days)

    Returns:
        Rolling average series with NaN for initial periods < window
    """
    return series.rolling(window=window, min_periods=1).mean()


def compute_realized_volatility(series: pd.Series,
                                 window: int = 30,
                                 annualize: bool = True) -> pd.Series:
    """
    Compute realized volatility as the rolling standard deviation of
    daily log returns, optionally annualized.

    Annualization uses 252 trading days per year (market convention).

    Args:
        series    : Price series (daily closing prices)
        window    : Rolling window in trading days (default 30)
        annualize : If True, multiply by sqrt(252) for annualized vol

    Returns:
        Rolling realized volatility series (as decimal, e.g. 0.45 = 45%)
    """
    log_returns = np.log(series / series.shift(1))
    vol = log_returns.rolling(window=window, min_periods=5).std()
    if annualize:
        vol = vol * np.sqrt(252)
    return vol


def compute_zscore(series: pd.Series, window: int = 60) -> pd.Series:
    """
    Compute a rolling z-score to identify when prices are statistically
    extreme relative to recent history.

    A z-score > 2 suggests the price is more than 2 standard deviations
    above its recent mean — a signal traders use to assess overextension.

    Args:
        series : Price series
        window : Lookback window for mean and std calculation

    Returns:
        Rolling z-score series
    """
    rolling_mean = series.rolling(window=window, min_periods=10).mean()
    rolling_std = series.rolling(window=window, min_periods=10).std()
    return (series - rolling_mean) / rolling_std


def build_price_summary(prices: dict) -> dict:
    """
    Build a summary dict of key metrics from the fetched prices dict.
    Used to populate the dashboard header cards.

    Args:
        prices : Dict returned by yfinance_client.fetch_all_prices()

    Returns:
        Dict with formatted display strings and raw values for each metric.
        JKM values are labeled with the estimated marker.
    """
    summary = {}

    hh = prices.get("hh_price")
    ttf = prices.get("ttf_usd_mmbtu")
    brent = prices.get("brent_price")

    summary["henry_hub"] = {
        "label": "Henry Hub",
        "value": hh,
        "display": f"${hh:.3f}/MMBtu" if hh else "N/A",
        "unit": "USD/MMBtu",
        "estimated": False,
    }

    summary["ttf"] = {
        "label": "TTF (converted)",
        "value": ttf,
        "display": f"${ttf:.3f}/MMBtu" if ttf else "N/A",
        "unit": "USD/MMBtu",
        "estimated": False,
    }

    summary["brent"] = {
        "label": "Brent Crude",
        "value": brent,
        "display": f"${brent:.2f}/bbl" if brent else "N/A",
        "unit": "USD/bbl",
        "estimated": False,
    }

    if brent:
        jkm = estimate_jkm(brent)
        summary["jkm"] = {
            "label": f"JKM {JKM_LABEL}",
            "value": jkm,
            "display": f"${jkm:.3f}/MMBtu {JKM_LABEL}",
            "unit": "USD/MMBtu",
            "estimated": True,
        }

    if hh and ttf:
        spread = ttf - hh
        summary["ttf_hh_spread"] = {
            "label": "TTF-HH Spread",
            "value": spread,
            "display": f"${spread:+.3f}/MMBtu",
            "unit": "USD/MMBtu",
            "estimated": False,
        }

    if hh and brent:
        jkm = estimate_jkm(brent)
        jkm_spread = jkm - hh
        summary["jkm_hh_spread"] = {
            "label": f"JKM-HH Spread {JKM_LABEL}",
            "value": jkm_spread,
            "display": f"${jkm_spread:+.3f}/MMBtu {JKM_LABEL}",
            "unit": "USD/MMBtu",
            "estimated": True,
        }

    return summary


if __name__ == "__main__":
    # Quick test with synthetic prices
    test_brent = 82.50
    test_ttf_eur = 35.0
    test_eur_usd = 1.08

    jkm = estimate_jkm(test_brent)
    ttf_conv = convert_ttf_to_usd_mmbtu(test_ttf_eur, test_eur_usd)

    print(f"Brent: ${test_brent}/bbl")
    print(f"JKM proxy: ${jkm:.3f}/MMBtu {JKM_LABEL}")
    print(f"TTF: {test_ttf_eur} EUR/MWh -> ${ttf_conv:.3f}/MMBtu")
    print("price_utils.py OK")

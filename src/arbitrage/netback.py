"""
src/arbitrage/netback.py - LNG Market Intelligence Terminal

LNG netback calculations and arbitrage status for U.S. Gulf Coast exports.

Market context:
    LNG arbitrage is the primary mechanism allocating U.S. export cargoes
    between the Atlantic Basin (Europe) and Pacific Basin (Asia).

    A cargo's destination is determined by which route offers the highest
    netback to the seller. The netback is the destination price minus all
    costs required to deliver gas from the Henry Hub to that market.

    Netback formula (per MMBtu):
        Netback = Destination_Price - Liquefaction - Shipping - Regas

    Arbitrage margin:
        Margin = Netback - Henry_Hub_Price

    If Margin > threshold (typically $0.50/MMBtu to account for model
    uncertainty), the arbitrage is considered open and cargoes should
    flow to that destination.

    The marginal cargo destination is whichever route has the highest
    positive margin. When both are positive, Asia typically wins if
    JKM - HH spread exceeds TTF - HH spread by more than the shipping
    cost differential (~$1.00-1.50/MMBtu via Panama vs Atlantic).

    Routes modeled:
        Atlantic    : U.S. Gulf Coast -> NW Europe (TTF destination)
        Pacific (P) : U.S. Gulf Coast -> Japan/Korea via Panama Canal
        Pacific (C) : U.S. Gulf Coast -> Japan/Korea via Cape of Good Hope
                      Used when Panama Canal is congested or restricted.

    Key constraints not modeled here (acknowledged):
        - Cargo availability and terminal slot commitments
        - Force majeure clauses in long-term contracts
        - Panama Canal draft restrictions (drought-related)
        - Vessel availability and TFDE vs steam turbine efficiency differences
        - Seasonal shipping rate variation

    In production this analysis would be done using Platts or Argus
    netback calculators with live JKM, TTF, and shipping rate inputs.
"""

import pandas as pd
from datetime import datetime
from dataclasses import dataclass, field
from config import (
    LIQUEFACTION_COST_DEFAULT,
    SHIPPING_ATLANTIC_DEFAULT,
    SHIPPING_PACIFIC_PANAMA_DEFAULT,
    SHIPPING_PACIFIC_CAPE_DEFAULT,
    REGAS_COST_DEFAULT,
    ARB_OPEN_THRESHOLD,
    JKM_LABEL,
)


@dataclass
class CostAssumptions:
    """
    Container for all variable cost inputs to the netback calculation.
    Defaults are pulled from config.py but can be overridden by the user
    via Streamlit sliders in the arbitrage tab.

    All values in USD/MMBtu.
    """
    liquefaction:     float = LIQUEFACTION_COST_DEFAULT
    shipping_atlantic: float = SHIPPING_ATLANTIC_DEFAULT
    shipping_pacific_panama: float = SHIPPING_PACIFIC_PANAMA_DEFAULT
    shipping_pacific_cape: float = SHIPPING_PACIFIC_CAPE_DEFAULT
    regas:            float = REGAS_COST_DEFAULT
    arb_threshold:    float = ARB_OPEN_THRESHOLD


@dataclass
class NetbackResult:
    """
    Result of a single netback calculation for one route.

    Fields:
        route           : 'atlantic' | 'pacific_panama' | 'pacific_cape'
        hh_price        : Henry Hub input price (USD/MMBtu)
        destination_price: TTF or JKM price used (USD/MMBtu)
        destination_label: Human-readable price label (includes est. for JKM)
        total_cost      : Sum of all delivery costs (USD/MMBtu)
        netback         : destination_price - total_cost (USD/MMBtu)
        margin          : netback - hh_price (USD/MMBtu)
        arb_open        : True if margin > arb_threshold
        costs_breakdown : Dict of individual cost components
        calculated_at   : UTC timestamp
    """
    route:             str
    hh_price:          float
    destination_price: float
    destination_label: str
    total_cost:        float
    netback:           float
    margin:            float
    arb_open:          bool
    costs_breakdown:   dict = field(default_factory=dict)
    calculated_at:     str = field(default_factory=lambda: datetime.utcnow().isoformat())


def calculate_atlantic_netback(
    hh_price: float,
    ttf_usd_mmbtu: float,
    costs: CostAssumptions = None,
) -> NetbackResult:
    """
    Calculate netback for U.S. Gulf Coast -> NW Europe (TTF destination).

    Atlantic route economics:
        Typical voyage: ~7-9 days on a Q-Flex or Q-Max vessel
        Key terminals: Sabine Pass, Corpus Christi -> Gate (Rotterdam),
                       Grain (UK), Elengy (France), Adriatic LNG (Italy)

        The Atlantic route benefits from short voyage times and low
        shipping costs but competes with piped Russian/Norwegian gas
        and North African LNG (Algeria, Libya, Egypt).

    Args:
        hh_price      : Henry Hub spot price (USD/MMBtu)
        ttf_usd_mmbtu : TTF price converted to USD/MMBtu
        costs         : Cost assumptions (uses defaults if None)

    Returns:
        NetbackResult for the Atlantic route
    """
    if costs is None:
        costs = CostAssumptions()

    total_cost = costs.liquefaction + costs.shipping_atlantic + costs.regas
    netback = ttf_usd_mmbtu - total_cost
    margin = netback - hh_price

    return NetbackResult(
        route="atlantic",
        hh_price=hh_price,
        destination_price=ttf_usd_mmbtu,
        destination_label="TTF (USD/MMBtu)",
        total_cost=total_cost,
        netback=netback,
        margin=margin,
        arb_open=margin > costs.arb_threshold,
        costs_breakdown={
            "liquefaction":  costs.liquefaction,
            "shipping":      costs.shipping_atlantic,
            "regas":         costs.regas,
            "total":         total_cost,
        },
    )


def calculate_pacific_netback(
    hh_price: float,
    jkm_usd_mmbtu: float,
    via_panama: bool = True,
    costs: CostAssumptions = None,
) -> NetbackResult:
    """
    Calculate netback for U.S. Gulf Coast -> Japan/Korea (JKM destination).

    Pacific route economics:
        Via Panama Canal (~20 days): Faster but subject to draft
            restrictions during drought. Canal authority may limit
            vessel drafts, forcing rerouting via Cape of Good Hope.

        Via Cape of Good Hope (~35 days): Longer and more expensive
            but not subject to canal constraints. Becomes the default
            route when Panama Canal throughput is restricted.

        Key receiving terminals: Sodegaura (Tokyo Gas), Futtsu (TEPCO),
            Incheon (KOGAS), Yung-An (CPC Taiwan)

    Args:
        hh_price       : Henry Hub spot price (USD/MMBtu)
        jkm_usd_mmbtu  : JKM price in USD/MMBtu (estimated proxy)
        via_panama     : True for Panama route, False for Cape route
        costs          : Cost assumptions (uses defaults if None)

    Returns:
        NetbackResult for the Pacific route
    """
    if costs is None:
        costs = CostAssumptions()

    if via_panama:
        shipping = costs.shipping_pacific_panama
        route_name = "pacific_panama"
        route_label = "Pacific (via Panama)"
    else:
        shipping = costs.shipping_pacific_cape
        route_name = "pacific_cape"
        route_label = "Pacific (via Cape)"

    total_cost = costs.liquefaction + shipping + costs.regas
    netback = jkm_usd_mmbtu - total_cost
    margin = netback - hh_price

    return NetbackResult(
        route=route_name,
        hh_price=hh_price,
        destination_price=jkm_usd_mmbtu,
        destination_label=f"JKM {JKM_LABEL} (USD/MMBtu)",
        total_cost=total_cost,
        netback=netback,
        margin=margin,
        arb_open=margin > costs.arb_threshold,
        costs_breakdown={
            "liquefaction":  costs.liquefaction,
            "shipping":      shipping,
            "regas":         costs.regas,
            "total":         total_cost,
        },
    )


def calculate_all_routes(
    hh_price: float,
    ttf_usd_mmbtu: float,
    jkm_usd_mmbtu: float,
    costs: CostAssumptions = None,
) -> dict:
    """
    Calculate netbacks for all three routes simultaneously.

    Also determines the marginal cargo destination — the route with
    the highest positive margin. If no route is positive, returns
    'no arbitrage' status.

    Args:
        hh_price       : Henry Hub spot price (USD/MMBtu)
        ttf_usd_mmbtu  : TTF price in USD/MMBtu
        jkm_usd_mmbtu  : JKM proxy price in USD/MMBtu
        costs          : Cost assumptions (uses defaults if None)

    Returns:
        Dict with keys:
            atlantic        : NetbackResult
            pacific_panama  : NetbackResult
            pacific_cape    : NetbackResult
            marginal_dest   : 'europe' | 'asia' | 'none'
            marginal_label  : Human-readable destination string
            best_margin     : Highest margin across all routes (USD/MMBtu)
    """
    if costs is None:
        costs = CostAssumptions()

    atlantic      = calculate_atlantic_netback(hh_price, ttf_usd_mmbtu, costs)
    pac_panama    = calculate_pacific_netback(hh_price, jkm_usd_mmbtu, via_panama=True, costs=costs)
    pac_cape      = calculate_pacific_netback(hh_price, jkm_usd_mmbtu, via_panama=False, costs=costs)

    # Marginal destination: highest margin among open arbitrage routes
    open_routes = {
        "europe": atlantic.margin if atlantic.arb_open else float("-inf"),
        "asia":   max(pac_panama.margin, pac_cape.margin) if (pac_panama.arb_open or pac_cape.arb_open) else float("-inf"),
    }

    best_dest = max(open_routes, key=open_routes.get)
    best_margin = open_routes[best_dest]

    if best_margin == float("-inf"):
        marginal_dest = "none"
        marginal_label = "No arbitrage open"
    elif best_dest == "europe":
        marginal_dest = "europe"
        marginal_label = "Europe (Atlantic Basin)"
    else:
        marginal_dest = "asia"
        marginal_label = "Asia (Pacific Basin)"

    return {
        "atlantic":       atlantic,
        "pacific_panama": pac_panama,
        "pacific_cape":   pac_cape,
        "marginal_dest":  marginal_dest,
        "marginal_label": marginal_label,
        "best_margin":    max(atlantic.margin, pac_panama.margin, pac_cape.margin),
    }


def build_sensitivity_table(
    hh_price: float,
    ttf_usd_mmbtu: float,
    costs: CostAssumptions = None,
) -> pd.DataFrame:
    """
    Build a sensitivity table showing Atlantic arbitrage margin across a
    range of TTF prices and shipping cost scenarios.

    This is the kind of table a trading desk would use to quickly assess
    how much TTF needs to move before a cargo becomes economic.

    Args:
        hh_price      : Henry Hub spot price (USD/MMBtu)
        ttf_usd_mmbtu : Current TTF price in USD/MMBtu (used as midpoint)
        costs         : Cost assumptions (uses defaults if None)

    Returns:
        DataFrame with TTF prices as rows and shipping cost scenarios
        as columns. Values are Atlantic Basin margins (USD/MMBtu).
        Positive values indicate open arbitrage.
    """
    if costs is None:
        costs = CostAssumptions()

    # TTF range: current price +/- 30%
    ttf_range = [
        round(ttf_usd_mmbtu * mult, 2)
        for mult in [0.70, 0.80, 0.90, 1.00, 1.10, 1.20, 1.30]
    ]

    # Shipping scenarios
    shipping_scenarios = {
        "Low Shipping\n($1.00/MMBtu)":  1.00,
        "Base Shipping\n($1.25/MMBtu)": 1.25,
        "High Shipping\n($1.50/MMBtu)": 1.50,
    }

    rows = []
    for ttf in ttf_range:
        row = {"TTF (USD/MMBtu)": ttf}
        for scenario_label, shipping_cost in shipping_scenarios.items():
            scenario_costs = CostAssumptions(
                liquefaction=costs.liquefaction,
                shipping_atlantic=shipping_cost,
                regas=costs.regas,
            )
            result = calculate_atlantic_netback(hh_price, ttf, scenario_costs)
            row[scenario_label] = round(result.margin, 3)
        rows.append(row)

    return pd.DataFrame(rows).set_index("TTF (USD/MMBtu)")


def format_result_for_display(result: NetbackResult) -> dict:
    """
    Format a NetbackResult into display-ready strings for the Streamlit UI.

    Args:
        result : NetbackResult from any calculate_* function

    Returns:
        Dict with formatted string values for each field
    """
    status_emoji = "✅ OPEN" if result.arb_open else "❌ CLOSED"
    margin_sign = "+" if result.margin >= 0 else ""

    return {
        "route":             result.route.replace("_", " ").title(),
        "status":            status_emoji,
        "hh_price":          f"${result.hh_price:.3f}/MMBtu",
        "destination_price": f"${result.destination_price:.3f}/MMBtu",
        "destination_label": result.destination_label,
        "total_cost":        f"${result.total_cost:.3f}/MMBtu",
        "netback":           f"${result.netback:.3f}/MMBtu",
        "margin":            f"{margin_sign}${result.margin:.3f}/MMBtu",
        "liquefaction":      f"${result.costs_breakdown.get('liquefaction', 0):.2f}/MMBtu",
        "shipping":          f"${result.costs_breakdown.get('shipping', 0):.2f}/MMBtu",
        "regas":             f"${result.costs_breakdown.get('regas', 0):.2f}/MMBtu",
    }


if __name__ == "__main__":
    print("Testing arbitrage engine...")
    print()

    # Test with representative prices
    hh    = 3.50    # USD/MMBtu
    ttf   = 11.00   # USD/MMBtu (converted from EUR/MWh)
    jkm   = 13.50   # USD/MMBtu (proxy estimate)

    print(f"Input prices:")
    print(f"  Henry Hub : ${hh:.2f}/MMBtu")
    print(f"  TTF       : ${ttf:.2f}/MMBtu")
    print(f"  JKM {JKM_LABEL}  : ${jkm:.2f}/MMBtu")
    print()

    results = calculate_all_routes(hh, ttf, jkm)

    for route_key in ["atlantic", "pacific_panama", "pacific_cape"]:
        r = results[route_key]
        fmt = format_result_for_display(r)
        print(f"Route: {fmt['route']}")
        print(f"  Status  : {fmt['status']}")
        print(f"  Netback : {fmt['netback']}")
        print(f"  Margin  : {fmt['margin']}")
        print()

    print(f"Marginal destination: {results['marginal_label']}")
    print(f"Best margin        : ${results['best_margin']:+.3f}/MMBtu")
    print()

    print("Sensitivity table (Atlantic margin by TTF and shipping cost):")
    sens = build_sensitivity_table(hh, ttf)
    print(sens.to_string())
    print()
    print("netback.py OK")

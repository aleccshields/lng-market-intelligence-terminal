"""
src/arbitrage/netback.py - LNG Market Intelligence Terminal

LNG netback calculations and arbitrage status for U.S. Gulf Coast exports.

Market context:
    LNG arbitrage is the primary mechanism allocating U.S. export cargoes
    between the Atlantic Basin (Europe) and Pacific Basin (Asia).

    Netback formula (per MMBtu):
        Netback = Destination_Price - Liquefaction - Shipping - Regas

    Arbitrage margin:
        Margin = Netback - Henry_Hub_Price

    Breakeven Henry Hub price:
        Breakeven_HH = Destination_Price - Liquefaction - Shipping - Regas
        (i.e. the HH price at which margin = 0)

    This is the number traders actually use day-to-day: "HH needs to be
    below $X for this cargo to work." When current HH is below breakeven,
    the arb is open. When HH is above breakeven, the arb is closed.

    Routes modeled:
        Atlantic    : U.S. Gulf Coast -> NW Europe (TTF destination)
        Pacific (P) : U.S. Gulf Coast -> Japan/Korea via Panama Canal
        Pacific (C) : U.S. Gulf Coast -> Japan/Korea via Cape of Good Hope
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
    All values in USD/MMBtu.
    """
    liquefaction:            float = LIQUEFACTION_COST_DEFAULT
    shipping_atlantic:       float = SHIPPING_ATLANTIC_DEFAULT
    shipping_pacific_panama: float = SHIPPING_PACIFIC_PANAMA_DEFAULT
    shipping_pacific_cape:   float = SHIPPING_PACIFIC_CAPE_DEFAULT
    regas:                   float = REGAS_COST_DEFAULT
    arb_threshold:           float = ARB_OPEN_THRESHOLD


@dataclass
class NetbackResult:
    """
    Result of a single netback calculation for one route.

    Key fields:
        netback         : destination_price - total_cost (USD/MMBtu)
        margin          : netback - hh_price (USD/MMBtu)
        breakeven_hh    : HH price at which margin = 0 (USD/MMBtu)
                          = destination_price - total_cost
                          If current HH < breakeven_hh, arb is open.
        arb_open        : True if margin > arb_threshold
    """
    route:             str
    hh_price:          float
    destination_price: float
    destination_label: str
    total_cost:        float
    netback:           float
    margin:            float
    breakeven_hh:      float
    arb_open:          bool
    costs_breakdown:   dict = field(default_factory=dict)
    calculated_at:     str  = field(default_factory=lambda: datetime.now().isoformat())


def calculate_atlantic_netback(
    hh_price: float,
    ttf_usd_mmbtu: float,
    costs: CostAssumptions = None,
) -> NetbackResult:
    """
    Calculate netback for U.S. Gulf Coast -> NW Europe (TTF destination).

    Breakeven HH = TTF - liquefaction - shipping - regas
    This is the maximum Henry Hub price at which a cargo destined for
    Europe remains profitable. Traders watch this number daily.

    Args:
        hh_price      : Henry Hub spot price (USD/MMBtu)
        ttf_usd_mmbtu : TTF price converted to USD/MMBtu
        costs         : Cost assumptions (uses defaults if None)

    Returns:
        NetbackResult for the Atlantic route
    """
    if costs is None:
        costs = CostAssumptions()

    total_cost   = costs.liquefaction + costs.shipping_atlantic + costs.regas
    netback      = ttf_usd_mmbtu - total_cost
    margin       = netback - hh_price
    breakeven_hh = netback  # = TTF - total_cost; margin=0 when HH = breakeven

    return NetbackResult(
        route="atlantic",
        hh_price=hh_price,
        destination_price=ttf_usd_mmbtu,
        destination_label="TTF (USD/MMBtu)",
        total_cost=total_cost,
        netback=netback,
        margin=margin,
        breakeven_hh=breakeven_hh,
        arb_open=margin > costs.arb_threshold,
        costs_breakdown={
            "liquefaction": costs.liquefaction,
            "shipping":     costs.shipping_atlantic,
            "regas":        costs.regas,
            "total":        total_cost,
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

    Breakeven HH = JKM - liquefaction - shipping - regas
    When Panama Canal is restricted, the Cape route's higher shipping cost
    lowers the breakeven, making it harder to justify Pacific cargoes.

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
        shipping   = costs.shipping_pacific_panama
        route_name = "pacific_panama"
    else:
        shipping   = costs.shipping_pacific_cape
        route_name = "pacific_cape"

    total_cost   = costs.liquefaction + shipping + costs.regas
    netback      = jkm_usd_mmbtu - total_cost
    margin       = netback - hh_price
    breakeven_hh = netback  # margin=0 when HH = breakeven

    return NetbackResult(
        route=route_name,
        hh_price=hh_price,
        destination_price=jkm_usd_mmbtu,
        destination_label=f"JKM {JKM_LABEL} (USD/MMBtu)",
        total_cost=total_cost,
        netback=netback,
        margin=margin,
        breakeven_hh=breakeven_hh,
        arb_open=margin > costs.arb_threshold,
        costs_breakdown={
            "liquefaction": costs.liquefaction,
            "shipping":     shipping,
            "regas":        costs.regas,
            "total":        total_cost,
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

    atlantic   = calculate_atlantic_netback(hh_price, ttf_usd_mmbtu, costs)
    pac_panama = calculate_pacific_netback(hh_price, jkm_usd_mmbtu, via_panama=True,  costs=costs)
    pac_cape   = calculate_pacific_netback(hh_price, jkm_usd_mmbtu, via_panama=False, costs=costs)

    open_routes = {
        "europe": atlantic.margin if atlantic.arb_open else float("-inf"),
        "asia":   max(pac_panama.margin, pac_cape.margin) if (pac_panama.arb_open or pac_cape.arb_open) else float("-inf"),
    }

    best_dest   = max(open_routes, key=open_routes.get)
    best_margin = open_routes[best_dest]

    if best_margin == float("-inf"):
        marginal_dest  = "none"
        marginal_label = "No arbitrage open"
    elif best_dest == "europe":
        marginal_dest  = "europe"
        marginal_label = "Europe (Atlantic Basin)"
    else:
        marginal_dest  = "asia"
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
    Build sensitivity table: Atlantic margin across TTF prices and
    shipping cost scenarios.

    Returns:
        DataFrame with TTF prices as rows, shipping scenarios as columns.
        Values are Atlantic Basin margins (USD/MMBtu).
    """
    if costs is None:
        costs = CostAssumptions()

    ttf_range = [
        round(ttf_usd_mmbtu * mult, 2)
        for mult in [0.70, 0.80, 0.90, 1.00, 1.10, 1.20, 1.30]
    ]

    shipping_scenarios = {
        "Low Ship ($1.00)":  1.00,
        "Base Ship ($1.25)": 1.25,
        "High Ship ($1.50)": 1.50,
    }

    rows = []
    for ttf in ttf_range:
        row = {"TTF (USD/MMBtu)": ttf}
        for label, ship in shipping_scenarios.items():
            sc = CostAssumptions(
                liquefaction=costs.liquefaction,
                shipping_atlantic=ship,
                regas=costs.regas,
            )
            result = calculate_atlantic_netback(hh_price, ttf, sc)
            row[label] = round(result.margin, 3)
        rows.append(row)

    return pd.DataFrame(rows).set_index("TTF (USD/MMBtu)")


def format_result_for_display(result: NetbackResult) -> dict:
    """
    Format a NetbackResult into display-ready strings for the Streamlit UI.
    Includes breakeven_hh for dashboard card display.
    """
    status_emoji = "✅ OPEN" if result.arb_open else "❌ CLOSED"
    margin_sign  = "+" if result.margin >= 0 else ""
    hh_vs_be     = result.hh_price - result.breakeven_hh

    if result.arb_open:
        be_note = f"HH has ${abs(hh_vs_be):.2f}/MMBtu of headroom before arb closes"
    else:
        be_note = f"HH needs to fall ${abs(hh_vs_be):.2f}/MMBtu for arb to open"

    return {
        "route":             result.route.replace("_", " ").title(),
        "status":            status_emoji,
        "hh_price":          f"${result.hh_price:.3f}/MMBtu",
        "destination_price": f"${result.destination_price:.3f}/MMBtu",
        "destination_label": result.destination_label,
        "total_cost":        f"${result.total_cost:.3f}/MMBtu",
        "netback":           f"${result.netback:.3f}/MMBtu",
        "margin":            f"{margin_sign}${result.margin:.3f}/MMBtu",
        "breakeven_hh":      f"${result.breakeven_hh:.3f}/MMBtu",
        "breakeven_note":    be_note,
        "liquefaction":      f"${result.costs_breakdown.get('liquefaction', 0):.2f}/MMBtu",
        "shipping":          f"${result.costs_breakdown.get('shipping', 0):.2f}/MMBtu",
        "regas":             f"${result.costs_breakdown.get('regas', 0):.2f}/MMBtu",
    }


if __name__ == "__main__":
    print("Testing arbitrage engine with breakeven prices...")
    print()

    hh  = 3.50
    ttf = 11.00
    jkm = 13.50

    print(f"Input prices:")
    print(f"  Henry Hub : ${hh:.2f}/MMBtu")
    print(f"  TTF       : ${ttf:.2f}/MMBtu")
    print(f"  JKM {JKM_LABEL}  : ${jkm:.2f}/MMBtu")
    print()

    results = calculate_all_routes(hh, ttf, jkm)

    for route_key in ["atlantic", "pacific_panama", "pacific_cape"]:
        r   = results[route_key]
        fmt = format_result_for_display(r)
        print(f"Route: {fmt['route']}")
        print(f"  Status      : {fmt['status']}")
        print(f"  Margin      : {fmt['margin']}")
        print(f"  Breakeven HH: {fmt['breakeven_hh']}")
        print(f"  Note        : {fmt['breakeven_note']}")
        print()

    print(f"Marginal destination: {results['marginal_label']}")
    print()
    print("netback.py OK")

# LNG Market Intelligence Terminal

An AI-powered market intelligence platform for LNG and natural gas markets, built with Python and Streamlit. Integrates live pricing, European and US storage data, netback arbitrage calculations, and an LNG news feed into a unified analytical dashboard.

**[Live App →](https://lng-market-intelligence-terminal-frkpvkscg6q2n7gyj2auck.streamlit.app/)**

---

## What This Does

LNG is the most globally integrated energy commodity — a cargo loading in Louisiana competes for the same buyer in Tokyo or Rotterdam depending on where netback economics point. This terminal operationalizes that logic:

- **Market Dashboard** tracks Henry Hub, TTF (converted to USD/MMBtu), Brent, and an estimated JKM proxy in a single view alongside spread history, rolling averages, and realized volatility
- **Arbitrage Engine** computes netback margins and breakeven Henry Hub prices for the Atlantic Basin (U.S. Gulf → Europe) and Pacific Basin (via Panama and Cape routes)
- **Gas Storage Tracker** monitors European storage by country (AGSI+) and U.S. regional storage by EIA region with signal cards and confidence qualifiers
- **News Feed** ingests LNG and natural gas headlines with keyword-based topic classification (supply outages, geopolitical, shipping, weather, price moves, and more)

---

## Arbitrage Logic

The core of the arbitrage engine is the netback calculation. For each route:

```
Netback = Destination_Price − Liquefaction − Shipping − Regas
Margin  = Netback − Henry_Hub_Price
```

The **breakeven Henry Hub price** — the maximum HH level at which a cargo remains economic — is:

```
Breakeven_HH = Destination_Price − Liquefaction − Shipping − Regas
```

When `HH < Breakeven_HH`, the arbitrage is open. When `HH > Breakeven_HH`, cargoes to that destination are uneconomic at current prices.

### Default Cost Assumptions (USD/MMBtu)

| Component | Default | Range |
|---|---|---|
| Liquefaction (U.S. Gulf) | $2.75 | $2.50–$3.00 |
| Shipping — Atlantic | $1.25 | $1.00–$1.50 |
| Shipping — Pacific (Panama) | $2.25 | $2.00–$2.50 |
| Shipping — Pacific (Cape) | $2.75 | $2.50–$3.00 |
| Regasification | $0.40 | $0.30–$0.50 |

All assumptions are adjustable via sliders in the UI.

---

## Data Sources

| Data | Source | Notes |
|---|---|---|
| Henry Hub (futures) | yfinance `NG=F` | Front-month, ~15 min delay |
| TTF (futures) | yfinance `TTF=F` | EUR/MWh → USD/MMBtu converted using live EUR/USD |
| Brent Crude | EIA API `PET.RBRTE.D` | Daily spot price, 1-day lag |
| JKM | **Estimated proxy** | Brent × 0.172 + $2.50/MMBtu Asia premium |
| EU Gas Storage | AGSI+ / GIE API | Country-level and EU aggregate, daily |
| US Gas Storage | EIA Weekly Storage Report | 6 EIA regions, weekly (Thursdays) |
| News | EIA Today in Energy, NGI, Global LNG Hub | RSS, keyword-classified |

### A Note on JKM

JKM (Japan Korea Marker) is the primary Asian LNG spot benchmark, published by Platts/S&P Global. It is proprietary and not freely available via public APIs. The proxy used here — `Brent × 0.172 + Asia_Premium` — reflects the historical oil-indexation of Asian LNG contracts. Since 2021–2022, Asian spot LNG has partially decoupled from oil as European buyers competed aggressively for cargoes. The proxy carries meaningful uncertainty and all JKM-derived values are labeled as estimated throughout the terminal.

In a production environment, JKM would be sourced from Platts eWindow, CME direct data feed, or a vendor like ICIS or Argus Media.

---

## Storage Signal Methodology

### European Storage (AGSI+)
Signal is based on deviation from the **EU 80% mandate threshold** (Regulation EU 2022/1032, requiring 80% fill by November 1):

| Deviation from 80% | Signal |
|---|---|
| > +15pp | Strongly Bearish for TTF |
| +8 to +15pp | Bearish (Moderate conviction) |
| 0 to +8pp | Mildly Bearish |
| -8 to 0pp | Mildly Bullish |
| -15 to -8pp | Bullish (Moderate conviction) |
| < -15pp | Strongly Bullish for TTF |

### US Storage (EIA)
Signal is based on surplus/deficit vs. the **52-week rolling average**:

| Deviation from 52-wk avg | Signal |
|---|---|
| > +300 Bcf | Strongly Bearish HH |
| +150 to +300 Bcf | Bearish (Moderate) |
| 0 to +150 Bcf | Mildly Bearish |
| -150 to 0 Bcf | Mildly Bullish |
| -300 to -150 Bcf | Bullish (Moderate) |
| < -300 Bcf | Strongly Bullish HH |

Professional analysis uses the EIA 5-year average rather than the 52-week rolling average. The rolling average is used here as a freely computable proxy from the same data series.

---

## Local Setup

**Requirements:** Python 3.10+, free API keys from EIA and AGSI+

```bash
git clone https://github.com/aleccshields/lng-market-intelligence-terminal
cd lng-market-intelligence-terminal
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
EIA_API_KEY=your_eia_key_here
AGSI_API_KEY=your_agsi_key_here
```

- **EIA API key**: Free registration at [eia.gov/opendata](https://www.eia.gov/opendata/)
- **AGSI+ API key**: Free registration at [agsi.gie.eu](https://agsi.gie.eu)

```bash
streamlit run app.py
```

---

## Project Structure

```
lng-market-intelligence-terminal/
├── app.py                      # Streamlit entry point
├── config.py                   # All constants, API keys, cost assumptions
├── src/
│   ├── pricing/
│   │   ├── yfinance_client.py  # HH, TTF, EUR/USD via yfinance; Brent via EIA
│   │   ├── eia_client.py       # EIA API: HH spot, US storage, Brent spot
│   │   └── price_utils.py      # Spreads, rolling averages, JKM proxy, volatility
│   ├── arbitrage/
│   │   └── netback.py          # Netback calculations, breakeven HH, sensitivity table
│   ├── storage/
│   │   └── agsi_client.py      # AGSI+ EU storage by country
│   ├── news/
│   │   └── rss_ingestor.py     # RSS ingestion, deduplication, keyword classification
│   ├── database/
│   │   └── db.py               # SQLite schema: prices, news, arb log
│   └── dashboard/
│       ├── market_tab.py       # Prices, spreads, volatility
│       ├── arbitrage_tab.py    # Netback, breakeven, sensitivity
│       ├── storage_tab.py      # EU + US storage tracker
│       ├── news_tab.py         # Classified news feed
│       └── ui_utils.py         # Shared HTML metric cards
```

---

## Tech Stack

| Component | Tool |
|---|---|
| Backend | Python 3.14 |
| Dashboard | Streamlit |
| Charts | Plotly |
| Data | pandas, yfinance, requests |
| Database | SQLite via SQLAlchemy |
| News | feedparser, BeautifulSoup |
| Hosting | Streamlit Community Cloud |

---

## Known Limitations

- **JKM is estimated**, not live. Platts JKM is proprietary. See note above.
- **yfinance TTF** is front-month futures with ~15 min delay, not spot.
- **Shipping costs** are fixed assumptions, not live freight rates (which would require Baltic LNG Index or Clarksons data).
- **News classification** is keyword-based, not ML-based. False positives occur on ambiguous headlines.
- **No vessel tracking** — AIS data at scale requires a paid provider (Kpler, Vortexa, MarineTraffic).

---

## Roadmap

- [ ] 5-year average overlay on US storage chart (EIA historical series)
- [ ] TTF-HH spread breakeven calculator
- [ ] Scenario simulator (pipeline cutoff, Panama congestion, cold winter)
- [ ] LNG terminal utilization tracker (EIA export data)
- [ ] Research paper intelligence layer (PDF ingestion, vector search)

---

## Author

**Alec Shields** — MPA Candidate, Columbia SIPA (Energy, Environment & Climate)

Substack: [Blackstart](https://blackstart.substack.com) — Energy markets, from first principles.

---

*Built for portfolio and educational purposes. Not for trading. All JKM values are model estimates.*

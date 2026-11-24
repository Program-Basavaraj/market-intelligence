# Architecture, data sources and spec coverage

## 1. Architecture (Option A — static site + scheduled job)

| Layer | Technology | Why |
|---|---|---|
| Compute | GitHub Actions (Ubuntu runner, Python 3.12) | Free for public repos; runs on a schedule; ~16 GB RAM |
| Analytics | pandas, NumPy, SciPy, scikit-learn | CPU-only and fits the 8 GB-RAM constraint; well-tested open-source libraries |
| Storage | JSON files on a `data` branch + Actions cache (prices, fundamentals, models) | No database server needed for a static site. Writes are atomic. |
| Website | Plain HTML/CSS/JS + Plotly.js, hosted on Netlify | No build step. Can be swapped for another front end without touching the analytics. |
| Alerts | Telegram Bot API | Free; token kept in GitHub Secrets |
| Live quotes | Netlify Function (`netlify/functions/quotes.mjs`, JavaScript) → Yahoo chart endpoint | Netlify Functions support JS/TS/Go, not Python. Symbols are validated, at most 60 per call. Responses are CDN-cached for 30 s. Failures return per-symbol errors, never invented prices. |

**Why not FastAPI, PostgreSQL, Redis, Streamlit or Docker?** Netlify cannot run Python servers or databases (its functions are JavaScript/Go with 10–30 s limits). The analytics code is modular, so the full server version (Option B) can wrap the same `pipeline/` package later:
- a FastAPI service reading the same functions
- PostgreSQL in place of JSON files
- a broker adapter for intraday data

### Pipeline steps (`pipeline/run.py`)
1. **Instrument master.** Built from the NSE equity list and Nifty index constituents. BSE codes are joined by ISIN (never by symbol). New listings, removals and symbol changes are detected by ISIN.
2. **Prices.** The Yahoo adapter runs behind the `MarketDataProvider` interface. The cache is incremental; if the overlap check shows prices have been re-based (split or bonus), the full history is downloaded again.
3. **Indicators.** About 45 indicators, all causal. A test proves values do not change when future bars are added.
4. **Fundamentals.** Refreshed incrementally (80 companies per run, at most 14 days old). The engine computes 20 ratios with their formulas, red flags and a multi-check scorecard.
5. **News.** RSS feeds, NSE announcements RSS and BSE announcements. Each item gets company matching, classification, sentiment, amounts, Order Size Ratio, de-duplication and a repeat check.
6. **Models.** See section 3.
7. **Assessments and backtests.** Then the JSON files for the site are written, followed by Telegram alerts.

## 2. Data sources and licensing

| Source | Used for | Status | Notes |
|---|---|---|---|
| Yahoo Finance via `yfinance` (Apache-2.0 library) | Daily OHLCV, indices, statements | Unofficial | End-of-day/delayed; personal research use under Yahoo's terms; field gaps for Indian companies are shown, not filled |
| NSE `EQUITY_L.csv` | Instrument master | Public file | Often blocks cloud IPs → falls back to the cached list |
| niftyindices.com constituent CSVs | Index membership, industry, size bucket | Public files | Size bucket approximates SEBI large/mid/small via Nifty 100 / Midcap 150 / Smallcap 250 |
| BSE scrip list & announcements (`api.bseindia.com`) | BSE codes, filings | Unofficial endpoint used by bseindia.com | Optional; failures reported |
| NSE announcements RSS | Filings (verified) | Public RSS | |
| Moneycontrol, ET, Business Standard, Mint, CNBC-TV18 RSS | Headlines + links | Public RSS | Only headline, source, time and link are stored/published; no article text; feed URLs may change — edit `config/settings.json` |
| Google Finance | — | Not used | No official API; scraping is against its terms |
| Broker APIs (Angel One SmartAPI, Upstox, Fyers, Dhan…) | Future intraday/live data | Not configured | Need a trading account; data licensed for personal use — do not publish on a public site |

## 3. Mathematical and machine-learning design

**Labels.** There are three mutually exclusive classes per horizon *h* ∈ {2, 5, 10} trading days. A move is **bullish** if the *h*-day return is greater than the band, where band = max(0.5·σ₂₀·√h, 0.4 %), and **bearish** if it is less than −band. Anything else is **neutral**. σ₂₀ uses past returns only.

**Features.** There are 19 causal features: returns, RSI, MACD/price, %B, ATR %, HV, relative volume, distance to the 50/200-day SMAs, ADX, DI spread, CMF, gap, relative strength vs Nifty, market return and volatility, and liquidity. If two features are more than 0.9 correlated, one is dropped.

**Models.** Logistic regression (the baseline), histogram gradient boosting, and their average (an ensemble). The model with the lowest out-of-sample log loss is selected.

**Validation.** Expanding walk-forward with 6-month test folds. Between training and test data there is a purge gap equal to the horizon. Probabilities are calibrated by **temperature scaling**, fitted on the last 15 % of each training window.

**Release gate.** The model is used only if all of these hold:
- at least 2,000 out-of-sample predictions
- Brier skill score of at least 0.005 versus fold-specific base rates
- log loss below the base-rate log loss
- the 5th percentile of the Brier skill score in a 21-day **moving-block bootstrap over dates** is above 0

The bootstrap guards against false skill from correlated stocks and overlapping labels. The test suite shows that random-walk data fails this gate and data with a planted signal passes.

**Thresholds.** The cut-off for a directional label is chosen on the first half of the out-of-sample period and checked on the second half. It counts as validated only with at least 100 signals, lift of at least 1.05, and a one-sided binomial p-value below 0.05 (using signal *dates* as a conservative n).

**Kept separate.** These four numbers are never merged:
- technical score (rule-based, −100…+100)
- news sentiment (−1…+1)
- model probabilities (sum to 100 %)
- model confidence (decisiveness and validated lift)

**Backtest.** Out-of-sample signals only. Each trade buys at the next open and sells at the close after *h* days. Trades are equal-weight and use non-overlapping periods. Costs cover STT, stamp duty, exchange, SEBI, GST, brokerage and slippage (~0.49 % round trip). The test is long-only. Known biases are shown on the page: survivorship (current constituents) and dividends ignored.

## 4. Spec coverage (honest)

| Spec section | Status in Option A |
|---|---|
| §4 Instrument master, NSE+BSE via ISIN, changes | ✅ (delisting vs suspension not distinguishable from free data) |
| §5 Provider interface, Yahoo adapter, timestamps, "Delayed data" label | ✅ ; delayed live quotes via Netlify Function (labelled, timestamped, with end-of-day fallback); broker adapter = interface only |
| §6 News engine, categories A–G, 15 processing fields, Order Size Ratio, Kannada/English notes | ✅ (rules + TF-IDF similarity, not a large NLP model; order book / payment terms not in free data — listed as unavailable) |
| §7 Fundamentals, 20 ratios with formulas, red flags, not-from-one-ratio rule | ✅ (auditor qualifications, related-party, pledges need annual reports — stated) |
| §8 Indicator library A–G | ✅ except chart-pattern recognition (head & shoulders etc.), delivery volume and OI/PCR (no free source) |
| §9 Quant engine | ✅ |
| §10 ML: swing horizons, baselines, walk-forward, calibration, metrics | ✅ for LR + gradient boosting; XGBoost/LightGBM/CatBoost/RF/SVM not included (sklearn HGB is the CPU-efficient equivalent) — **intraday horizons not built** (no authorised data) |
| §11 Recommendation engine with all listed fields | ✅ |
| §12 Dashboard (24 sections) | ✅ all sections; alert *configuration* is via `settings.json` (a static site cannot store settings) |
| §13 Telegram | ✅ |
| §14 13 bilingual PDF/DOCX documents | ⚠️ Not in this release. Replaced for now by the 83-topic bilingual Learning centre. The documents are a separate phase. |
| §16 Install guides for Ubuntu/Debian/RHEL/Windows, systemd, Nginx | ⚠️ Not applicable to Option A. Local run instructions are in the README. Server guides belong to Option B. |
| §17 Auth, RBAC, rate limiting, SQL injection | Not applicable (no server, no database, no user accounts). Secrets are environment-only; the site escapes all feed text and restricts links to http(s); Netlify sends security headers including a CSP. |
| §19 Tests | ✅ 70 pytest tests (indicators vs published values, reference implementations, causality, news parsing, calendar/holidays/time zones, splits, provider failures, duplicates, calibration, gate, backtest, alerts) |

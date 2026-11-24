# Market Intelligence — Indian stock research (Option A)

A free, open-source research platform for NSE/BSE stocks:

- **Python pipeline** (runs free on GitHub Actions every evening and 4× during market hours) — prices, 45+ technical indicators, fundamentals, news intelligence, calibrated swing-probability models, backtests, Telegram alerts.
- **Static dashboard** (hosted free on Netlify) — overview, scanners, stock pages, news & order-win scanner, model performance, backtests, and a **Kannada + English learning centre**.

> **Live quotes.** While the NSE market is open, pages refresh **delayed quotes every 60 s** through a Netlify Function (`netlify/functions/quotes.mjs`). These come from Yahoo Finance, are usually a few seconds to ~15 minutes behind, and are marked ● with their time. If the source fails, the page shows the end-of-day price instead.

> **Honest limits.** All analysis (indicators, models, scores) uses **end-of-day** data from Yahoo Finance (unofficial, research use). No source can promise "100 % accurate" data; every number carries its source and timestamp. Intraday predictions are **not** produced (they need a licensed intraday feed). Models are shown **only if they beat a naive forecast out of sample** — otherwise the site says *"Insufficient evidence — no recommendation."* This is a research tool, not investment advice.

> **ಕನ್ನಡ ಸಾರಾಂಶ:** ಇದು NSE/BSE ಷೇರುಗಳ ಸಂಶೋಧನೆಗಾಗಿ ಉಚಿತ ವೇದಿಕೆ. ಪ್ರತಿದಿನ ಸಂಜೆ GitHub ನಲ್ಲಿ Python ಪ್ರೋಗ್ರಾಂ ಓಡಿ, ದತ್ತಾಂಶವನ್ನು ತಯಾರಿಸುತ್ತದೆ; Netlify ತಾಣ ಅದನ್ನು ತೋರಿಸುತ್ತದೆ. ಬೆಲೆಗಳು ದಿನದ ಅಂತ್ಯದ (ತಡವಾದ) ದತ್ತಾಂಶ. ಮಾದರಿ ಪರೀಕ್ಷೆಯಲ್ಲಿ ಉತ್ತೀರ್ಣವಾಗದಿದ್ದರೆ ಯಾವುದೇ ಶಿಫಾರಸು ತೋರಿಸುವುದಿಲ್ಲ. ಇದು ಹೂಡಿಕೆ ಸಲಹೆ ಅಲ್ಲ.

## Quick start

**Deploy (no coding):** follow [`docs/SETUP.md`](docs/SETUP.md) — about 20 minutes: GitHub repo → run the workflow → point `site/js/config.js` at your data branch → connect Netlify.

**Run locally (Linux / macOS / Windows):**
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q                                     # 70 tests, ~30 s, no internet needed
node --test tests/js/quotes.test.mjs                    # 6 tests for the live-quotes function
python -m pipeline.run --universe nifty50               # needs internet; writes site/data/
python -m http.server 8000 -d site                      # open http://localhost:8000
```
(For local viewing keep `dataBase: "./data/"` in `site/js/config.js`. Live quotes need the function: run `npx netlify-cli dev` instead of `http.server`.)

## How it works
```
GitHub Actions (cron) ──► python -m pipeline.run ──► JSON ──► `data` branch ──► dashboard (Netlify) reads it
        │                          │
        │      instruments · prices (Yahoo) · indicators · fundamentals · news (RSS + NSE/BSE filings)
        │      walk-forward ML + calibration + release gate · backtest · recommendations
        └──► Telegram alerts (optional, de-duplicated)
```
Details, data-source licensing and the full spec-coverage table: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Project layout
```
pipeline/            Python research engine
  providers/         MarketDataProvider interface + Yahoo adapter (add a broker adapter here)
  instruments.py     NSE/BSE instrument master, ISIN joins, listing/symbol-change detection
  indicators.py      technical indicator library (custom, tested)
  fundamentals.py    ratios, multi-year trends, red flags, scorecard
  quant.py           VaR/CVaR, Sharpe/Sortino, drawdown, confidence intervals
  news.py            feeds, company matching, classification, order-size ratio, de-dup, Kannada notes
  ml.py              swing models, walk-forward, calibration, release gate, thresholds
  backtest.py        out-of-sample backtest with Indian delivery costs
  recommend.py       bullish / bearish / neutral / insufficient assessments
  telegram.py        alerts with de-duplication
  run.py             orchestrator (writes the website's JSON)
site/                static dashboard (index.html, css, js, learn.json)
netlify/functions/   quotes.mjs — delayed live quotes + today's 1-minute line (Yahoo)
config/              settings.json (tunable, no secrets), holidays.json, fallback list
tests/               pytest suite (synthetic data only)
.github/workflows/   daily pipeline + tests
```

## Configuration
- Research parameters: `config/settings.json` (universe, horizons, costs, alert thresholds, news feeds).
- Secrets: **only** environment variables / GitHub Secrets — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- NSE holidays: add each year's list to `config/holidays.json` (affects the "stale data" warning only).

## Licence
MIT. Third-party: pandas, NumPy, SciPy (BSD-3), scikit-learn (BSD-3), requests (Apache-2.0), yfinance (Apache-2.0), Plotly.js (MIT, via CDN). Yahoo Finance data is subject to Yahoo's terms — personal, non-commercial research use.

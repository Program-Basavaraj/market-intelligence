# Changelog

## 1.1.0 — 2026-11-24
- Delayed live quotes: Netlify Function `/api/quotes` (Yahoo chart endpoint, symbol validation, 30 s CDN cache, per-symbol errors).
- Overview index tiles, movers, scanner prices and the stock header refresh every 60 s during NSE hours (09:15–15:30 IST, visible tab only); each value is marked ● with its quote time and falls back to end-of-day if the source fails.
- Stock page: "Today (delayed, 1-minute)" intraday line versus previous close.
- Live-quotes status badge; 6 Node tests for the function (mocked upstream).

## 1.0.0 — 2026-11-24
- First release of Option A: Python pipeline on GitHub Actions + static Netlify dashboard.
- Instrument master (NSE equity list, Nifty index membership, BSE codes joined by ISIN, change detection).
- Yahoo Finance adapter behind a provider-independent interface; incremental price cache with split detection.
- 45+ technical indicators with tests against published examples (RSI matches StockCharts exactly) and slow reference implementations (ATR, ADX); causality (no look-ahead) test.
- Fundamental engine: 20 ratios with formulas, multi-year statements, red-flag detection, multi-check scorecard.
- News intelligence: RSS + NSE/BSE filings, company matching, rule + similarity classification, amounts, Order Size Ratio, de-duplication, Kannada/English explanations.
- Swing models (2/5/10 days): walk-forward with purge gap, temperature calibration, block-bootstrap release gate, hold-out-validated thresholds; out-of-sample backtest with Indian delivery costs.
- Telegram alerts with de-duplication; bilingual learning centre (83 topics).

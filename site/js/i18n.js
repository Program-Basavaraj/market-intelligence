/* Language switch: English ⇄ ಕನ್ನಡ for the whole dashboard.
 *
 * How it works:
 *   1. Elements with class "t-en" / "t-kn" are shown only in that language (pure CSS, see style.css).
 *      Used for headings (bi()) and long paragraphs written separately in each language.
 *   2. Every other visible text node and placeholder/title attribute is looked up in KN (exact match)
 *      or matched against PATTERNS (text with numbers). A MutationObserver translates content as it
 *      is drawn, including table re-sorts and live-quote updates.
 *   3. Anything not in the tables stays in English (company names, symbols, news headlines, numbers).
 * Inside <code>, <pre>, .notranslate, .t-en and .t-kn nothing is touched.
 */
(() => {
  "use strict";
  let lang = "en";
  try { lang = localStorage.getItem("mi-lang") === "kn" ? "kn" : "en"; } catch (e) { /* storage unavailable */ }
  document.documentElement.lang = lang;

  // ---------------------------------------------------------------- exact phrases
  const KN = {
    // top bar, common
    "Search symbol or company…": "ಷೇರು ಚಿಹ್ನೆ ಅಥವಾ ಕಂಪನಿ ಹುಡುಕಿ…",
    "Toggle dark mode": "ಕಪ್ಪು/ಬಿಳಿ ಹಿನ್ನೆಲೆ ಬದಲಿಸಿ",
    "Loading…": "ಲೋಡ್ ಆಗುತ್ತಿದೆ…", "Loading data…": "ದತ್ತಾಂಶ ಲೋಡ್ ಆಗುತ್ತಿದೆ…",
    "No data yet": "ಇನ್ನೂ ದತ್ತಾಂಶ ಇಲ್ಲ",
    "Analysis: end-of-day": "ವಿಶ್ಲೇಷಣೆ: ದಿನದ ಅಂತ್ಯದ ದತ್ತಾಂಶ",
    "Delayed live quotes": "ತಡವಾದ ನೇರ ದರಗಳು", "Market closed": "ಮಾರುಕಟ್ಟೆ ಮುಚ್ಚಿದೆ",
    "Live quotes unavailable — showing end-of-day prices": "ನೇರ ದರಗಳು ಲಭ್ಯವಿಲ್ಲ — ದಿನದ ಅಂತ್ಯದ ಬೆಲೆ ತೋರಿಸಲಾಗಿದೆ",
    "Show more": "ಇನ್ನಷ್ಟು ತೋರಿಸಿ", "No rows match these filters.": "ಈ ಆಯ್ಕೆಗಳಿಗೆ ಹೊಂದುವ ಸಾಲುಗಳಿಲ್ಲ.",
    "Could not load this page.": "ಈ ಪುಟವನ್ನು ತೆರೆಯಲು ಆಗಲಿಲ್ಲ.", "Nothing found.": "ಏನೂ ಸಿಗಲಿಲ್ಲ.",
    "None": "ಯಾವುದೂ ಇಲ್ಲ", "All": "ಎಲ್ಲಾ", "Other": "ಇತರೆ", "n/a": "ಲಭ್ಯವಿಲ್ಲ", "unmatched": "ಹೊಂದಿಕೆ ಇಲ್ಲ",
    "Overview": "ಅವಲೋಕನ", "Scanners": "ಶೋಧಕಗಳು", "News": "ಸುದ್ದಿ", "Analysis": "ವಿಶ್ಲೇಷಣೆ", "More": "ಇನ್ನಷ್ಟು",

    // labels / pills
    "▲ Bullish": "▲ ಏರುಮುಖ", "▼ Bearish": "▼ ಇಳಿಮುಖ", "◆ Neutral": "◆ ತಟಸ್ಥ", "○ Insufficient evidence": "○ ಸಾಕಷ್ಟು ಆಧಾರವಿಲ್ಲ",
    "Bullish": "ಏರುಮುಖ", "Bearish": "ಇಳಿಮುಖ", "Neutral": "ತಟಸ್ಥ", "Insufficient": "ಆಧಾರ ಸಾಲದು",
    "Insufficient evidence — no recommendation.": "ಸಾಕಷ್ಟು ಆಧಾರವಿಲ್ಲ — ಯಾವುದೇ ಶಿಫಾರಸು ಇಲ್ಲ.",
    "Exchange filing": "ವಿನಿಮಯ ಕೇಂದ್ರದ ಅಧಿಕೃತ ಪ್ರಕಟಣೆ", "Media report": "ಮಾಧ್ಯಮ ವರದಿ",
    "low": "ಕಡಿಮೆ", "medium": "ಮಧ್ಯಮ", "high": "ಹೆಚ್ಚು", "normal": "ಸಾಮಾನ್ಯ", "unknown": "ತಿಳಿದಿಲ್ಲ",
    "Large": "ದೊಡ್ಡ", "Mid": "ಮಧ್ಯಮ", "Small": "ಸಣ್ಣ", "Unclassified": "ವರ್ಗೀಕರಿಸಿಲ್ಲ",
    "Positive": "ಧನಾತ್ಮಕ", "Negative": "ಋಣಾತ್ಮಕ",

    // overview
    "Market context:": "ಮಾರುಕಟ್ಟೆ ಸ್ಥಿತಿ:",
    "Nifty 50 is below its 200-day average — a weaker backdrop for bullish setups.": "Nifty 50 ತನ್ನ 200-ದಿನದ ಸರಾಸರಿಗಿಂತ ಕೆಳಗಿದೆ — ಏರುಮುಖ ಅವಕಾಶಗಳಿಗೆ ದುರ್ಬಲ ಹಿನ್ನೆಲೆ.",
    "Above 200-day average": "200-ದಿನದ ಸರಾಸರಿಗಿಂತ ಮೇಲೆ", "of tracked stocks": "ಗಮನಿಸುತ್ತಿರುವ ಷೇರುಗಳಲ್ಲಿ",
    "Breakouts / Breakdowns": "ಬ್ರೇಕ್‌ಔಟ್ / ಬ್ರೇಕ್‌ಡೌನ್", "20-day range, volume ≥ 1.5×": "20-ದಿನದ ವ್ಯಾಪ್ತಿ, ವಹಿವಾಟು ≥ 1.5×",
    "validated thresholds only": "ಪರಿಶೀಲಿತ ಮಿತಿಗಳು ಮಾತ್ರ", "Models not validated — no recommendations": "ಮಾದರಿಗಳು ಪರೀಕ್ಷೆಯಲ್ಲಿ ಉತ್ತೀರ್ಣವಾಗಿಲ್ಲ — ಶಿಫಾರಸುಗಳಿಲ್ಲ",
    "Average 20-day change of tracked stocks per sector (equal-weighted).": "ಪ್ರತಿ ವಲಯದ ಷೇರುಗಳ ಸರಾಸರಿ 20-ದಿನದ ಬದಲಾವಣೆ (ಸಮಾನ ತೂಕ).",
    "All news →": "ಎಲ್ಲಾ ಸುದ್ದಿ →", "No matched news yet.": "ಇನ್ನೂ ಹೊಂದಿಕೆಯಾದ ಸುದ್ದಿ ಇಲ್ಲ.",
    "Top gainers": "ಹೆಚ್ಚು ಏರಿದವು", "Top losers": "ಹೆಚ್ಚು ಇಳಿದವು", "Unusual volume": "ಅಸಾಮಾನ್ಯ ವಹಿವಾಟು",
    "Symbol": "ಚಿಹ್ನೆ", "Price": "ಬೆಲೆ", "1D": "1 ದಿನ", "1M": "1 ತಿಂಗಳು", "Rel. vol": "ಸಾಪೇಕ್ಷ ವಹಿವಾಟು",
    "Index data unavailable — see System status.": "ಸೂಚ್ಯಂಕ ದತ್ತಾಂಶ ಲಭ್ಯವಿಲ್ಲ — ವ್ಯವಸ್ಥೆಯ ಸ್ಥಿತಿ ನೋಡಿ.",
    "· 6-month trend": "· 6-ತಿಂಗಳ ಪ್ರವೃತ್ತಿ",

    // news row
    "Explain · ವಿವರಣೆ": "ವಿವರಣೆ", "· similar to an earlier item": "· ಹಿಂದಿನ ಸುದ್ದಿಯಂತೆಯೇ ಇದೆ", "· order =": "· ಆರ್ಡರ್ =",

    // scanner
    "Stock scanner": "ಷೇರು ಶೋಧಕ", "Bullish scanner": "ಏರುಮುಖ ಶೋಧಕ", "Bearish scanner": "ಇಳಿಮುಖ ಶೋಧಕ",
    "Neutral stocks": "ತಟಸ್ಥ ಷೇರುಗಳು", "Small-cap scanner": "ಸಣ್ಣ ಕಂಪನಿಗಳ ಶೋಧಕ", "Mid-cap scanner": "ಮಧ್ಯಮ ಕಂಪನಿಗಳ ಶೋಧಕ",
    "Filter symbol / name": "ಚಿಹ್ನೆ / ಹೆಸರು ಹುಡುಕಿ", "Horizon": "ಅವಧಿ", "Sector": "ವಲಯ", "Size": "ಗಾತ್ರ",
    "Exchange": "ವಿನಿಮಯ ಕೇಂದ್ರ", "NSE (all)": "NSE (ಎಲ್ಲಾ)", "Also on BSE": "BSE ಯಲ್ಲೂ ಇರುವವು",
    "Min. probability": "ಕನಿಷ್ಠ ಸಂಭವನೀಯತೆ", "Min. rel. volume": "ಕನಿಷ್ಠ ಸಾಪೇಕ್ಷ ವಹಿವಾಟು", "Liquid only": "ದ್ರವ್ಯತೆ ಇರುವವು ಮಾತ್ರ",
    "Stock": "ಷೇರು", "RSI": "RSI", "Tech score": "ತಾಂತ್ರಿಕ ಅಂಕ", "Fundamentals": "ಮೂಲಭೂತ ಅಂಶಗಳು",
    "Probabilities": "ಸಂಭವನೀಯತೆಗಳು", "Strong": "ಬಲಿಷ್ಠ", "Moderate": "ಮಧ್ಯಮ", "Weak": "ದುರ್ಬಲ",
    "Insufficient data": "ಸಾಕಷ್ಟು ದತ್ತಾಂಶವಿಲ್ಲ",

    // stock page
    "Research assessment": "ಸಂಶೋಧನಾ ಮೌಲ್ಯಮಾಪನ", "Intraday": "ದಿನದೊಳಗಿನ",
    "intraday models need an authorised intraday data feed (not configured)": "ದಿನದೊಳಗಿನ ಮಾದರಿಗಳಿಗೆ ಅಧಿಕೃತ ನೇರ ದತ್ತಾಂಶ ಬೇಕು (ಸಂರಚಿಸಿಲ್ಲ)",
    "Technical justification": "ತಾಂತ್ರಿಕ ಆಧಾರ", "Fundamental justification": "ಮೂಲಭೂತ ಆಧಾರ", "News justification": "ಸುದ್ದಿ ಆಧಾರ",
    "Rule-based summary of indicators; not a probability.": "ಸೂಚಕಗಳ ನಿಯಮಾಧಾರಿತ ಸಾರಾಂಶ; ಇದು ಸಂಭವನೀಯತೆ ಅಲ್ಲ.",
    "Scenarios (not instructions)": "ಸನ್ನಿವೇಶಗಳು (ಸೂಚನೆಗಳಲ್ಲ)", "Reference price": "ಉಲ್ಲೇಖ ಬೆಲೆ",
    "Entry scenario": "ಪ್ರವೇಶ ಸನ್ನಿವೇಶ", "Stop-loss scenario": "ಸ್ಟಾಪ್-ಲಾಸ್ ಸನ್ನಿವೇಶ", "Target scenario": "ಗುರಿ ಸನ್ನಿವೇಶ",
    "Risk / reward": "ಅಪಾಯ / ಪ್ರತಿಫಲ", "Support": "ಬೆಂಬಲ", "Resistance": "ಪ್ರತಿರೋಧ", "Not enough data.": "ಸಾಕಷ್ಟು ದತ್ತಾಂಶವಿಲ್ಲ.",
    "Research estimate only — not investment advice, not a guarantee. Not a buy/sell instruction.": "ಸಂಶೋಧನಾ ಅಂದಾಜು ಮಾತ್ರ — ಹೂಡಿಕೆ ಸಲಹೆ ಅಲ್ಲ, ಖಾತರಿ ಅಲ್ಲ. ಖರೀದಿ/ಮಾರಾಟದ ಸೂಚನೆ ಅಲ್ಲ.",
    "stop below nearest support (≥1 ATR, ≤3 ATR away); target at next resistance ≥1 ATR away, else 2.5 ATR": "ಸ್ಟಾಪ್: ಹತ್ತಿರದ ಬೆಂಬಲದ ಕೆಳಗೆ (1–3 ATR ಅಂತರ); ಗುರಿ: ಕನಿಷ್ಠ 1 ATR ದೂರದ ಮುಂದಿನ ಪ್ರತಿರೋಧ, ಇಲ್ಲದಿದ್ದರೆ 2.5 ATR",
    "Price chart": "ಬೆಲೆ ಚಾರ್ಟ್", "Bollinger": "ಬೊಲಿಂಜರ್", "Support/Resistance": "ಬೆಂಬಲ/ಪ್ರತಿರೋಧ",
    "RSI (14)": "RSI (14)", "MACD (12, 26, 9)": "MACD (12, 26, 9)",
    "Today (delayed, 1-minute)": "ಇಂದಿನ ಬೆಲೆ ಚಲನೆ (ತಡವಾದ, 1-ನಿಮಿಷ)",
    "Delayed quotes from Yahoo Finance (unofficial). For viewing only — the assessments below use end-of-day data.": "Yahoo Finance ನಿಂದ ತಡವಾದ ದರಗಳು (ಅನಧಿಕೃತ). ನೋಡಲು ಮಾತ್ರ — ಕೆಳಗಿನ ಮೌಲ್ಯಮಾಪನಗಳು ದಿನದ ಅಂತ್ಯದ ದತ್ತಾಂಶ ಬಳಸುತ್ತವೆ.",
    "Indicator readings": "ಸೂಚಕಗಳ ಮೌಲ್ಯಗಳು", "What do these mean? →": "ಇವುಗಳ ಅರ್ಥವೇನು? →", "Price structure": "ಬೆಲೆ ರಚನೆ",
    "Market structure": "ಮಾರುಕಟ್ಟೆ ರಚನೆ", "Pivot (classic)": "ಪಿವೋಟ್ (ಸಾಂಪ್ರದಾಯಿಕ)", "Fib extensions": "ಫಿಬೊನಾಚಿ ವಿಸ್ತರಣೆ",
    "Beta / correlation (1y vs Nifty)": "ಬೀಟಾ / ಸಹಸಂಬಂಧ (1 ವರ್ಷ, Nifty ಗೆ ಹೋಲಿಸಿ)", "Volatility regime": "ಚಂಚಲತೆಯ ಸ್ಥಿತಿ",
    "Candles, last 5 sessions": "ಕ್ಯಾಂಡಲ್ ಮಾದರಿಗಳು, ಕೊನೆಯ 5 ದಿನ", "No standard pattern": "ಪ್ರಮಾಣಿತ ಮಾದರಿ ಇಲ್ಲ",
    "uptrend (higher highs and higher lows)": "ಏರುಪ್ರವೃತ್ತಿ (ಎತ್ತರದ ಶಿಖರಗಳು ಮತ್ತು ತಳಗಳು)",
    "downtrend (lower highs and lower lows)": "ಇಳಿಪ್ರವೃತ್ತಿ (ತಗ್ಗಿನ ಶಿಖರಗಳು ಮತ್ತು ತಳಗಳು)",
    "mixed / range-bound": "ಮಿಶ್ರ / ವ್ಯಾಪ್ತಿಯೊಳಗೆ", "insufficient swings": "ಸಾಕಷ್ಟು ಏರಿಳಿತಗಳಿಲ್ಲ",
    "Fundamental analysis": "ಮೂಲಭೂತ ವಿಶ್ಲೇಷಣೆ", "Red flags": "ಎಚ್ಚರಿಕೆ ಸೂಚನೆಗಳು", "None detected from available data.": "ಲಭ್ಯ ದತ್ತಾಂಶದಲ್ಲಿ ಯಾವುದೂ ಕಂಡುಬಂದಿಲ್ಲ.",
    "Ratios": "ಅನುಪಾತಗಳು", "Ratio": "ಅನುಪಾತ", "Value": "ಮೌಲ್ಯ", "Formula": "ಸೂತ್ರ", "Period": "ಅವಧಿ",
    "Multi-year statements (₹ crore)": "ಬಹುವರ್ಷದ ಹಣಕಾಸು ವಿವರ (₹ ಕೋಟಿ)",
    "Revenue": "ಆದಾಯ", "EBITDA": "EBITDA", "Net profit": "ನಿವ್ವಳ ಲಾಭ", "Op. cash flow": "ಕಾರ್ಯಾಚರಣೆ ನಗದು ಹರಿವು",
    "Free cash flow": "ಮುಕ್ತ ನಗದು ಹರಿವು", "Total debt": "ಒಟ್ಟು ಸಾಲ", "Equity": "ಷೇರುಬಂಡವಾಳ", "Receivables": "ಬರಬೇಕಾದ ಬಾಕಿ", "Inventory": "ದಾಸ್ತಾನು",
    "✔ pass": "✔ ಉತ್ತೀರ್ಣ", "✖ fail": "✖ ಅನುತ್ತೀರ್ಣ",
    "ROE ≥ 12%": "ROE ≥ 12%", "ROCE ≥ 12%": "ROCE ≥ 12%", "Debt/Equity ≤ 1": "ಸಾಲ/ಷೇರುಬಂಡವಾಳ ≤ 1", "Current ratio ≥ 1.2": "ಚಾಲ್ತಿ ಅನುಪಾತ ≥ 1.2",
    "Interest coverage ≥ 3": "ಬಡ್ಡಿ ವ್ಯಾಪ್ತಿ ≥ 3", "Net margin > 5%": "ನಿವ್ವಳ ಲಾಭಾಂಶ > 5%", "OCF / Net profit ≥ 0.8": "ಕಾರ್ಯಾಚರಣೆ ನಗದು / ನಿವ್ವಳ ಲಾಭ ≥ 0.8",
    "Revenue growth > 0": "ಆದಾಯ ಬೆಳವಣಿಗೆ > 0", "Profit growth > 0": "ಲಾಭ ಬೆಳವಣಿಗೆ > 0", "2-yr revenue CAGR > 8%": "2-ವರ್ಷದ ಆದಾಯ CAGR > 8%",
    "Revenue growth without cash-flow growth": "ನಗದು ಹರಿವು ಹೆಚ್ಚದೆ ಆದಾಯ ಬೆಳವಣಿಗೆ", "Rising debt": "ಹೆಚ್ಚುತ್ತಿರುವ ಸಾಲ",
    "Falling margins": "ಕುಸಿಯುತ್ತಿರುವ ಲಾಭಾಂಶ", "Weak interest coverage": "ದುರ್ಬಲ ಬಡ್ಡಿ ವ್ಯಾಪ್ತಿ",
    "Receivables growing faster than revenue": "ಆದಾಯಕ್ಕಿಂತ ವೇಗವಾಗಿ ಹೆಚ್ಚುತ್ತಿರುವ ಬಾಕಿ", "Inventory accumulation": "ದಾಸ್ತಾನು ಶೇಖರಣೆ",
    "Net loss in latest year": "ಇತ್ತೀಚಿನ ವರ್ಷದಲ್ಲಿ ನಿವ್ವಳ ನಷ್ಟ",
    "Bank/NBFC/insurer: leverage & liquidity checks not applicable": "ಬ್ಯಾಂಕ್/NBFC/ವಿಮೆ: ಸಾಲ ಮತ್ತು ದ್ರವ್ಯತೆ ಪರೀಕ್ಷೆಗಳು ಅನ್ವಯಿಸುವುದಿಲ್ಲ",
    "Auditor qualifications, related-party transactions and pledges are not in this data source; check the annual report and exchange filings.": "ಲೆಕ್ಕಪರಿಶೋಧಕರ ಅಭಿಪ್ರಾಯ, ಸಂಬಂಧಿತ ಪಕ್ಷಗಳ ವ್ಯವಹಾರ ಮತ್ತು ಷೇರು ಅಡಮಾನ ಮಾಹಿತಿ ಈ ಮೂಲದಲ್ಲಿಲ್ಲ; ವಾರ್ಷಿಕ ವರದಿ ಮತ್ತು ವಿನಿಮಯ ಕೇಂದ್ರದ ಪ್ರಕಟಣೆಗಳನ್ನು ನೋಡಿ.",
    "Risk & return statistics": "ಅಪಾಯ ಮತ್ತು ಪ್ರತಿಫಲ ಅಂಕಿಅಂಶ",
    "Annualised return (3y)": "ವಾರ್ಷಿಕ ಪ್ರತಿಫಲ (3 ವರ್ಷ)", "Annualised volatility": "ವಾರ್ಷಿಕ ಚಂಚಲತೆ", "Sharpe / Sortino": "ಶಾರ್ಪ್ / ಸೊರ್ಟಿನೊ",
    "Max drawdown": "ಗರಿಷ್ಠ ಕುಸಿತ", "Current drawdown": "ಪ್ರಸ್ತುತ ಕುಸಿತ", "1-day VaR 95% (hist / normal / Cornish-Fisher)": "1-ದಿನದ VaR 95% (ಐತಿಹಾಸಿಕ / ಸಾಮಾನ್ಯ / Cornish-Fisher)",
    "1-day CVaR 95%": "1-ದಿನದ CVaR 95%", "Beta / correlation (1y)": "ಬೀಟಾ / ಸಹಸಂಬಂಧ (1 ವರ್ಷ)", "Normality (Jarque–Bera p)": "ಸಾಮಾನ್ಯ ವಿತರಣೆ ಪರೀಕ್ಷೆ (Jarque–Bera p)",
    "Mean daily return significant?": "ಸರಾಸರಿ ದೈನಂದಿನ ಪ್ರತಿಫಲ ಮಹತ್ವದ್ದೇ?", "Mean (95% CI)": "ಸರಾಸರಿ (95% ವಿಶ್ವಾಸಾರ್ಹ ಅಂತರ)",
    "P(positive) (95% CI)": "ಏರಿಕೆಯ ಸಂಭವನೀಯತೆ (95% ಅಂತರ)", "10th / 90th pct": "10ನೇ / 90ನೇ ಶೇಕಡಾಂಶ",
    "Historical statistics of non-overlapping past periods — descriptive, not a forecast, and separate from model probabilities.": "ಹಿಂದಿನ ಅವಧಿಗಳ ಐತಿಹಾಸಿಕ ಅಂಕಿಅಂಶ — ವಿವರಣೆ ಮಾತ್ರ, ಮುನ್ಸೂಚನೆ ಅಲ್ಲ; ಮಾದರಿಯ ಸಂಭವನೀಯತೆಗಳಿಂದ ಬೇರೆ.",
    "Historical distribution of past h-day returns — not a forecast.": "ಹಿಂದಿನ ಪ್ರತಿಫಲಗಳ ಐತಿಹಾಸಿಕ ವಿತರಣೆ — ಮುನ್ಸೂಚನೆ ಅಲ್ಲ.",
    "normal not rejected": "ಸಾಮಾನ್ಯ ವಿತರಣೆ ತಿರಸ್ಕೃತವಾಗಿಲ್ಲ", "fat tails: prefer historical VaR": "ತೀವ್ರ ಘಟನೆಗಳು ಹೆಚ್ಚು: ಐತಿಹಾಸಿಕ VaR ಬಳಸಿ",
    "yes": "ಹೌದು", "no": "ಇಲ್ಲ", "Related news": "ಸಂಬಂಧಿತ ಸುದ್ದಿ", "No matched news in the stored history.": "ಸಂಗ್ರಹಿಸಿದ ಸುದ್ದಿಗಳಲ್ಲಿ ಹೊಂದಿಕೆ ಇಲ್ಲ.",
    "End-of-day (delayed) — not real-time": "ದಿನದ ಅಂತ್ಯದ (ತಡವಾದ) ದತ್ತಾಂಶ — ನೇರ ಅಲ್ಲ",

    // recommendation texts produced by the pipeline
    "Price above 50-day SMA": "ಬೆಲೆ 50-ದಿನದ SMA ಗಿಂತ ಮೇಲಿದೆ", "Price below 50-day SMA": "ಬೆಲೆ 50-ದಿನದ SMA ಗಿಂತ ಕೆಳಗಿದೆ",
    "Price above 200-day SMA": "ಬೆಲೆ 200-ದಿನದ SMA ಗಿಂತ ಮೇಲಿದೆ", "Price below 200-day SMA": "ಬೆಲೆ 200-ದಿನದ SMA ಗಿಂತ ಕೆಳಗಿದೆ",
    "50-day SMA above 200-day (long-term uptrend)": "50-ದಿನದ SMA 200-ದಿನದ SMA ಗಿಂತ ಮೇಲೆ (ದೀರ್ಘಾವಧಿ ಏರುಪ್ರವೃತ್ತಿ)",
    "50-day SMA below 200-day (long-term downtrend)": "50-ದಿನದ SMA 200-ದಿನದ SMA ಗಿಂತ ಕೆಳಗೆ (ದೀರ್ಘಾವಧಿ ಇಳಿಪ್ರವೃತ್ತಿ)",
    "MACD above signal line": "MACD ಸಿಗ್ನಲ್ ರೇಖೆಯ ಮೇಲಿದೆ", "MACD below signal line": "MACD ಸಿಗ್ನಲ್ ರೇಖೆಯ ಕೆಳಗಿದೆ",
    "Supertrend in buy mode": "ಸೂಪರ್‌ಟ್ರೆಂಡ್ ಖರೀದಿ ಸ್ಥಿತಿಯಲ್ಲಿದೆ", "Supertrend in sell mode": "ಸೂಪರ್‌ಟ್ರೆಂಡ್ ಮಾರಾಟ ಸ್ಥಿತಿಯಲ್ಲಿದೆ",
    "Chaikin Money Flow positive (accumulation)": "ಚೈಕಿನ್ ಹಣದ ಹರಿವು ಧನಾತ್ಮಕ (ಸಂಗ್ರಹಣೆ)",
    "Chaikin Money Flow negative (distribution)": "ಚೈಕಿನ್ ಹಣದ ಹರಿವು ಋಣಾತ್ಮಕ (ವಿತರಣೆ)",
    "20-day breakout on above-average volume": "ಸರಾಸರಿಗಿಂತ ಹೆಚ್ಚು ವಹಿವಾಟಿನೊಂದಿಗೆ 20-ದಿನದ ಬ್ರೇಕ್‌ಔಟ್",
    "20-day breakdown on above-average volume": "ಸರಾಸರಿಗಿಂತ ಹೆಚ್ಚು ವಹಿವಾಟಿನೊಂದಿಗೆ 20-ದಿನದ ಬ್ರೇಕ್‌ಡೌನ್",
    "Broad market (Nifty 50) is below its 200-day average": "ಒಟ್ಟು ಮಾರುಕಟ್ಟೆ (Nifty 50) 200-ದಿನದ ಸರಾಸರಿಗಿಂತ ಕೆಳಗಿದೆ",
    "Volatility is in its top 20 % of the past year — wider swings likely": "ಚಂಚಲತೆ ಕಳೆದ ವರ್ಷದ ಮೇಲಿನ 20% ನಲ್ಲಿದೆ — ದೊಡ್ಡ ಏರಿಳಿತ ಸಾಧ್ಯ",
    "Recent negative corporate news": "ಇತ್ತೀಚಿನ ನಕಾರಾತ್ಮಕ ಕಂಪನಿ ಸುದ್ದಿ",
    "Unexpected news, results or market-wide shocks after the data timestamp": "ದತ್ತಾಂಶದ ಸಮಯದ ನಂತರ ಬರುವ ಅನಿರೀಕ್ಷಿತ ಸುದ್ದಿ, ಫಲಿತಾಂಶ ಅಥವಾ ಮಾರುಕಟ್ಟೆ ಆಘಾತಗಳು",
    "No matched news in the last 7 days": "ಕಳೆದ 7 ದಿನಗಳಲ್ಲಿ ಹೊಂದಿಕೆಯಾದ ಸುದ್ದಿ ಇಲ್ಲ",
    "Probability crossed a threshold validated on held-out data": "ಸಂಭವನೀಯತೆ ಪರಿಶೀಲಿತ ಮಿತಿಯನ್ನು ದಾಟಿದೆ",
    "No class crossed its validated threshold — no directional edge detected": "ಯಾವುದೇ ವರ್ಗ ಪರಿಶೀಲಿತ ಮಿತಿ ದಾಟಿಲ್ಲ — ದಿಕ್ಕಿನ ಅನುಕೂಲ ಕಂಡುಬಂದಿಲ್ಲ",
    "less than one year of price history": "ಒಂದು ವರ್ಷಕ್ಕಿಂತ ಕಡಿಮೆ ಬೆಲೆ ಇತಿಹಾಸ",
    "No fundamentals fetched yet": "ಮೂಲಭೂತ ದತ್ತಾಂಶ ಇನ್ನೂ ಪಡೆದಿಲ್ಲ",
    "Not available yet — fundamentals are refreshed gradually (about 80 companies per run).": "ಇನ್ನೂ ಲಭ್ಯವಿಲ್ಲ — ಮೂಲಭೂತ ದತ್ತಾಂಶವನ್ನು ಹಂತ ಹಂತವಾಗಿ ನವೀಕರಿಸಲಾಗುತ್ತದೆ (ಪ್ರತಿ ಬಾರಿ ಸುಮಾರು 80 ಕಂಪನಿಗಳು).",

    // news pages
    "Market news": "ಮಾರುಕಟ್ಟೆ ಸುದ್ದಿ", "Order-win scanner": "ಆರ್ಡರ್ ಗೆಲುವು ಶೋಧಕ", "Corporate announcement scanner": "ಕಾರ್ಪೊರೇಟ್ ಪ್ರಕಟಣೆಗಳು",
    "Search headline / symbol": "ಶೀರ್ಷಿಕೆ / ಚಿಹ್ನೆ ಹುಡುಕಿ", "Category": "ವರ್ಗ", "Sentiment": "ಭಾವನೆ", "Last": "ಕೊನೆಯ",
    "1 day": "1 ದಿನ", "3 days": "3 ದಿನ", "7 days": "7 ದಿನ", "30 days": "30 ದಿನ", "all stored": "ಸಂಗ್ರಹಿಸಿದ ಎಲ್ಲವೂ",
    "Matched to a stock": "ಷೇರಿಗೆ ಹೊಂದಿಕೆಯಾದವು", "Exchange filings only": "ಅಧಿಕೃತ ಪ್ರಕಟಣೆಗಳು ಮಾತ್ರ",
    "No news matches these filters.": "ಈ ಆಯ್ಕೆಗಳಿಗೆ ಸುದ್ದಿ ಇಲ್ಲ.", "Date": "ದಿನಾಂಕ", "Company": "ಕಂಪನಿ", "Headline": "ಶೀರ್ಷಿಕೆ",
    "Order (₹ cr)": "ಆರ್ಡರ್ (₹ ಕೋಟಿ)", "Revenue (₹ cr)": "ಆದಾಯ (₹ ಕೋಟಿ)", "Order size ratio": "ಆರ್ಡರ್ ಗಾತ್ರ ಅನುಪಾತ",
    "Materiality": "ಮಹತ್ವ", "Note": "ಟಿಪ್ಪಣಿ", "May be a repeat of an earlier disclosure": "ಹಿಂದಿನ ಪ್ರಕಟಣೆಯ ಪುನರಾವರ್ತನೆ ಇರಬಹುದು",
    "unknown (order value or revenue missing)": "ತಿಳಿದಿಲ್ಲ (ಆರ್ಡರ್ ಮೊತ್ತ ಅಥವಾ ಆದಾಯ ಲಭ್ಯವಿಲ್ಲ)",
    "Order win": "ಆರ್ಡರ್ ಗೆಲುವು", "Strong results / growth": "ಬಲವಾದ ಫಲಿತಾಂಶ / ಬೆಳವಣಿಗೆ", "Weak results": "ದುರ್ಬಲ ಫಲಿತಾಂಶ",
    "Results announced / board meeting": "ಫಲಿತಾಂಶ ಪ್ರಕಟಣೆ / ಮಂಡಳಿ ಸಭೆ", "Government / regulatory approval": "ಸರ್ಕಾರ / ನಿಯಂತ್ರಕ ಅನುಮೋದನೆ",
    "Business development": "ವ್ಯವಹಾರ ವಿಸ್ತರಣೆ", "Positive corporate action": "ಧನಾತ್ಮಕ ಕಾರ್ಪೊರೇಟ್ ಕ್ರಮ",
    "Negative development": "ನಕಾರಾತ್ಮಕ ಬೆಳವಣಿಗೆ", "Market trigger": "ಮಾರುಕಟ್ಟೆ ಪ್ರಚೋದಕ",

    // model / backtest / compare / swing / alerts / learn / status
    "Model performance": "ಮಾದರಿ ಕಾರ್ಯಕ್ಷಮತೆ", "Validated — in use": "ಪರಿಶೀಲಿತ — ಬಳಕೆಯಲ್ಲಿದೆ",
    "Not validated — no recommendations": "ಪರೀಕ್ಷೆಯಲ್ಲಿ ಉತ್ತೀರ್ಣವಾಗಿಲ್ಲ — ಶಿಫಾರಸುಗಳಿಲ್ಲ", "Why not released:": "ಏಕೆ ಬಳಸುತ್ತಿಲ್ಲ:",
    "Model": "ಮಾದರಿ", "Brier": "Brier", "Brier (base rate)": "Brier (ಮೂಲ ಆವರ್ತನ)", "Brier skill": "Brier ಕೌಶಲ",
    "Log loss": "ಲಾಗ್ ನಷ್ಟ", "Log loss (base)": "ಲಾಗ್ ನಷ್ಟ (ಮೂಲ)", "AUC bull / bear": "AUC ಏರು / ಇಳಿ",
    "Calibration — bullish class": "ಹೊಂದಾಣಿಕೆ — ಏರುಮುಖ ವರ್ಗ",
    "Points near the diagonal = well calibrated. Bins with fewer than 20 predictions are hidden.": "ಕರ್ಣರೇಖೆಯ ಹತ್ತಿರದ ಬಿಂದುಗಳು = ಉತ್ತಮ ಹೊಂದಾಣಿಕೆ. 20 ಕ್ಕಿಂತ ಕಡಿಮೆ ಮುನ್ಸೂಚನೆಗಳ ಗುಂಪುಗಳನ್ನು ತೋರಿಸಿಲ್ಲ.",
    "Thresholds (chosen on 1st half, tested on 2nd half)": "ಮಿತಿಗಳು (ಮೊದಲಾರ್ಧದಲ್ಲಿ ಆಯ್ಕೆ, ಎರಡನೇ ಅರ್ಧದಲ್ಲಿ ಪರೀಕ್ಷೆ)",
    "Class": "ವರ್ಗ", "Threshold": "ಮಿತಿ", "Hold-out precision": "ಪರೀಕ್ಷಾ ನಿಖರತೆ", "Base rate": "ಮೂಲ ಆವರ್ತನ", "Lift": "ಏರಿಕೆ ಪ್ರಮಾಣ",
    "Signals": "ಸಂಕೇತಗಳು", "p-value": "p-ಮೌಲ್ಯ", "Valid?": "ಮಾನ್ಯವೇ?", "✔ yes": "✔ ಹೌದು", "✖ no": "✖ ಇಲ್ಲ",
    "Per-class precision / recall / F1": "ವರ್ಗವಾರು ನಿಖರತೆ / ಮರುಸ್ಮರಣೆ / F1", "actual ↓ / predicted →": "ನಿಜ ↓ / ಮುನ್ಸೂಚನೆ →",
    "bullish": "ಏರುಮುಖ", "bearish": "ಇಳಿಮುಖ", "neutral": "ತಟಸ್ಥ",
    "No model reports yet.": "ಇನ್ನೂ ಮಾದರಿ ವರದಿಗಳಿಲ್ಲ.", "No backtests yet.": "ಇನ್ನೂ ಹಿಂಪರೀಕ್ಷೆಗಳಿಲ್ಲ.",
    "Strategy total return": "ತಂತ್ರದ ಒಟ್ಟು ಪ್ರತಿಫಲ", "Benchmark (all stocks)": "ಮಾನದಂಡ (ಎಲ್ಲಾ ಷೇರುಗಳು)", "Strategy max drawdown": "ತಂತ್ರದ ಗರಿಷ್ಠ ಕುಸಿತ",
    "Strategy Sharpe": "ತಂತ್ರದ ಶಾರ್ಪ್", "Trades": "ವಹಿವಾಟುಗಳು", "Win rate (net)": "ಯಶಸ್ಸಿನ ದರ (ನಿವ್ವಳ)", "Avg trade (net)": "ಸರಾಸರಿ ವಹಿವಾಟು (ನಿವ್ವಳ)",
    "Round-trip cost": "ಖರೀದಿ+ಮಾರಾಟ ವೆಚ್ಚ", "Strategy": "ತಂತ್ರ", "All tracked stocks (equal weight)": "ಎಲ್ಲಾ ಷೇರುಗಳು (ಸಮಾನ ತೂಕ)",
    "Growth of ₹1": "₹1 ರ ಬೆಳವಣಿಗೆ", "Indexed (start = 100)": "ಸೂಚ್ಯಂಕೀಕೃತ (ಆರಂಭ = 100)", "Predicted P(bullish)": "ಮುನ್ಸೂಚಿತ ಏರಿಕೆ ಸಂಭವನೀಯತೆ",
    "Observed frequency": "ಕಂಡ ಆವರ್ತನ", "Perfect calibration": "ಪರಿಪೂರ್ಣ ಹೊಂದಾಣಿಕೆ",
    "Compare": "ಹೋಲಿಸಿ", "Enter valid NSE symbols.": "ಸರಿಯಾದ NSE ಚಿಹ್ನೆಗಳನ್ನು ನಮೂದಿಸಿ.", 
    "Technical score": "ತಾಂತ್ರಿಕ ಅಂಕ", "Fundamental label": "ಮೂಲಭೂತ ಮೌಲ್ಯಮಾಪನ", "ROE %": "ROE %", "Debt / equity": "ಸಾಲ / ಷೇರುಬಂಡವಾಳ",
    "P/E": "P/E", "Volatility (ann.)": "ಚಂಚಲತೆ (ವಾರ್ಷಿಕ)", "Max drawdown (3y)": "ಗರಿಷ್ಠ ಕುಸಿತ (3 ವರ್ಷ)", "Beta": "ಬೀಟಾ", "Sharpe": "ಶಾರ್ಪ್",
    "No validated directional signals.": "ಪರಿಶೀಲಿತ ದಿಕ್ಕಿನ ಸಂಕೇತಗಳಿಲ್ಲ.", "Assessment": "ಮೌಲ್ಯಮಾಪನ",
    "How to enable later": "ಮುಂದೆ ಸಕ್ರಿಯಗೊಳಿಸುವುದು ಹೇಗೆ",
    "Current status": "ಪ್ರಸ್ತುತ ಸ್ಥಿತಿ", "Telegram configured": "Telegram ಸಂರಚನೆ", "Last run": "ಕೊನೆಯ ಓಟ", "Errors": "ದೋಷಗಳು",
    "Thresholds in use": "ಬಳಕೆಯಲ್ಲಿರುವ ಮಿತಿಗಳು", "Run the pipeline first": "ಮೊದಲು ಪೈಪ್‌ಲೈನ್ ಓಡಿಸಿ", "Set up Telegram (5 minutes)": "Telegram ಸಿದ್ಧಪಡಿಸಿ (5 ನಿಮಿಷ)",
    
    "Topic": "ವಿಷಯ", "All topics": "ಎಲ್ಲಾ ವಿಷಯಗಳು", "Language": "ಭಾಷೆ", "Search: RSI, ROE, VaR, ಬೆಂಬಲ…": "ಹುಡುಕಿ: RSI, ROE, VaR, ಬೆಂಬಲ…",
    "Formula · ಸೂತ್ರ": "ಸೂತ್ರ", "Example (hypothetical) · ಉದಾಹರಣೆ": "ಉದಾಹರಣೆ (ಕಾಲ್ಪನಿಕ)",
    "Bullish reading": "ಏರುಮುಖ ಅರ್ಥ", "Bearish reading": "ಇಳಿಮುಖ ಅರ್ಥ", "Sideways market": "ಪಕ್ಕಮುಖ ಮಾರುಕಟ್ಟೆ",
    "Warnings": "ಎಚ್ಚರಿಕೆಗಳು", "Prices": "ಬೆಲೆಗಳು", "Instruments": "ಷೇರುಗಳ ಪಟ್ಟಿ", "Sources": "ಮೂಲಗಳು",
    "Changes since last run": "ಕೊನೆಯ ಓಟದ ನಂತರದ ಬದಲಾವಣೆಗಳು", "News feeds": "ಸುದ್ದಿ ಮೂಲಗಳು", "Per feed": "ಪ್ರತಿ ಮೂಲ",
    "Fundamentals, models & alerts": "ಮೂಲಭೂತ ಅಂಶ, ಮಾದರಿಗಳು ಮತ್ತು ಎಚ್ಚರಿಕೆಗಳು", "Models": "ಮಾದರಿಗಳು", "Telegram": "Telegram",
    "State": "ಸ್ಥಿತಿ", "Market date": "ಮಾರುಕಟ್ಟೆ ದಿನಾಂಕ", "Run finished": "ಓಟ ಮುಗಿದದ್ದು", "Duration": "ಅವಧಿ",
    "Finish setup": "ಸಿದ್ಧತೆ ಪೂರ್ಣಗೊಳಿಸಿ", "Meanwhile, open the Learning centre →": "ಅಲ್ಲಿಯವರೆಗೆ ಕಲಿಕಾ ಕೇಂದ್ರ ತೆರೆಯಿರಿ →",
    "Welcome — no data has been generated yet": "ಸ್ವಾಗತ — ಇನ್ನೂ ದತ್ತಾಂಶ ತಯಾರಾಗಿಲ್ಲ",

    // sectors (Nifty industry names)
    "Financial Services": "ಹಣಕಾಸು ಸೇವೆಗಳು", "Information Technology": "ಮಾಹಿತಿ ತಂತ್ರಜ್ಞಾನ", "Capital Goods": "ಬಂಡವಾಳ ಸರಕುಗಳು",
    "Healthcare": "ಆರೋಗ್ಯ ರಕ್ಷಣೆ", "Fast Moving Consumer Goods": "ದೈನಂದಿನ ಗ್ರಾಹಕ ವಸ್ತುಗಳು (FMCG)",
    "Automobile and Auto Components": "ವಾಹನ ಮತ್ತು ಬಿಡಿಭಾಗಗಳು", "Oil Gas & Consumable Fuels": "ತೈಲ, ಅನಿಲ ಮತ್ತು ಇಂಧನ",
    "Metals & Mining": "ಲೋಹ ಮತ್ತು ಗಣಿಗಾರಿಕೆ", "Power": "ವಿದ್ಯುತ್", "Construction": "ನಿರ್ಮಾಣ",
    "Construction Materials": "ನಿರ್ಮಾಣ ಸಾಮಗ್ರಿ", "Consumer Durables": "ಬಾಳಿಕೆ ಬರುವ ಗ್ರಾಹಕ ವಸ್ತುಗಳು", "Consumer Services": "ಗ್ರಾಹಕ ಸೇವೆಗಳು",
    "Chemicals": "ರಾಸಾಯನಿಕಗಳು", "Telecommunication": "ದೂರಸಂಪರ್ಕ", "Services": "ಸೇವೆಗಳು", "Realty": "ರಿಯಲ್ ಎಸ್ಟೇಟ್",
    "Textiles": "ಜವಳಿ", "Media Entertainment & Publication": "ಮಾಧ್ಯಮ ಮತ್ತು ಮನರಂಜನೆ", "Diversified": "ವೈವಿಧ್ಯಮಯ",
    "Forest Materials": "ಅರಣ್ಯ ಉತ್ಪನ್ನಗಳು", "Utilities": "ಸಾರ್ವಜನಿಕ ಸೇವೆಗಳು",
  };

  const pct = "([−\\-+]?[\\d.,]+)";
  const tr = (s) => (KN[s] !== undefined ? KN[s] : translateDynamic(s) ?? s);
  // ---------------------------------------------------------------- patterns (text with numbers)
  const PATTERNS = [
    [/^(\d+) rows$/, (m) => `${m[1]} ಸಾಲುಗಳು`],
    [/^(\d+) items$/, (m) => `${m[1]} ಸುದ್ದಿಗಳು`],
    [/^Showing (\d+) of (\d+)\.$/, (m) => `${m[2]} ರಲ್ಲಿ ${m[1]} ತೋರಿಸಲಾಗಿದೆ.`],
    [/^(\d+) trading days$/, (m) => `${m[1]} ವಹಿವಾಟು ದಿನಗಳು`],
    [/^(\d+)-day swing$/, (m) => `${m[1]}-ದಿನದ ಸ್ವಿಂಗ್`],
    [/^(\d+)-day assessment$/, (m) => `${m[1]}-ದಿನದ ಮೌಲ್ಯಮಾಪನ`],
    [/^(\d+)-day swing model$/, (m) => `${m[1]}-ದಿನದ ಸ್ವಿಂಗ್ ಮಾದರಿ`],
    [/^Strongest (\d+)-day signals$/, (m) => `ಅತ್ಯಂತ ಬಲವಾದ ${m[1]}-ದಿನದ ಸಂಕೇತಗಳು`],
    [/^Open scanner \(choose (\d+)-day horizon\) →$/, (m) => `ಶೋಧಕ ತೆರೆಯಿರಿ (${m[1]}-ದಿನದ ಅವಧಿ ಆಯ್ಕೆಮಾಡಿ) →`],
    [/^(\d+) days$/, (m) => `${m[1]} ದಿನಗಳು`],
    [/^confidence: (\w+)$/, (m) => `ವಿಶ್ವಾಸ: ${tr(m[1])}`],
    [/^close of (.+)$/, (m) => `${m[1]} ರ ಮುಕ್ತಾಯ ಬೆಲೆ`],
    [/^close (.+)$/, (m) => `${m[1]} ರ ಮುಕ್ತಾಯ`],
    [/^EOD (.+)$/, (m) => `ದಿನಾಂತ್ಯ ${m[1]}`],
    [/^delayed quote · (.+)$/, (m) => `ತಡವಾದ ದರ · ${m[1]}`],
    [/^End-of-day close: (.+)$/, (m) => `ದಿನದ ಅಂತ್ಯದ ಮುಕ್ತಾಯ: ${m[1]}`],
    [/^A\/D ratio (.+)$/, (m) => `ಏರಿಕೆ/ಇಳಿಕೆ ಅನುಪಾತ ${m[1]}`],
    [/^· last quote (.+?)( · refresh (\d+)s)?$/, (m) => `· ಕೊನೆಯ ದರ ${m[1]}${m[3] ? ` · ಪ್ರತಿ ${m[3]} ಸೆಕೆಂಡಿಗೆ ನವೀಕರಣ` : ""}`],
    [/^· impact (\d+)\/100$/, (m) => `· ಪರಿಣಾಮ ${m[1]}/100`],
    [/^· sentiment (.+)$/, (m) => `· ಭಾವನೆ ${m[1]}`],
    [/^of revenue \((.+)\)$/, (m) => `ಆದಾಯದ (${tr(m[1])})`],
    [/^over (\d+) months$/, (m) => `${m[1]} ತಿಂಗಳಲ್ಲಿ`],
    [/^Model: (.+) · Brier skill (.+)$/, (m) => `ಮಾದರಿ: ${m[1]} · Brier ಕೌಶಲ ${m[2]}`],
    [/^\(score (.+) \/ ±100\)$/, (m) => `(ಅಂಕ ${m[1]} / ±100)`],
    [/^\(risk-free (.+)\)$/, (m) => `(ಅಪಾಯರಹಿತ ದರ ${m[1]})`],
    [/^Scorecard: (\w[\w ]*?)( \((\d+)\/(\d+) checks\))?$/, (m) => `ಅಂಕಪಟ್ಟಿ: ${tr(m[1])}${m[2] ? ` (${m[4]} ರಲ್ಲಿ ${m[3]} ಪರೀಕ್ಷೆ ಉತ್ತೀರ್ಣ)` : ""}`],
    [/^Fundamental scorecard: (\w[\w ]*?)( \((\d+)\/(\d+) checks passed\))?$/, (m) => `ಮೂಲಭೂತ ಅಂಕಪಟ್ಟಿ: ${tr(m[1])}${m[2] ? ` (${m[4]} ರಲ್ಲಿ ${m[3]} ಉತ್ತೀರ್ಣ)` : ""}`],
    [/^Fundamentals unavailable: (.+)$/, (m) => `ಮೂಲಭೂತ ದತ್ತಾಂಶ ಲಭ್ಯವಿಲ್ಲ: ${tr(m[1])}`],
    [/^Fundamental red flags: (.+)$/, (m) => `ಮೂಲಭೂತ ಎಚ್ಚರಿಕೆಗಳು: ${m[1].split(", ").map(tr).join(", ")}`],
    [/^⚠ (.+?): (.+)$/, (m) => `⚠ ${tr(m[1])}: ${m[2]}`],
    [/^(\d+) news item\(s\) in 7 days, weighted sentiment (.+)$/, (m) => `7 ದಿನಗಳಲ್ಲಿ ${m[1]} ಸುದ್ದಿ, ತೂಕದ ಭಾವನೆ ${m[2]}`],
    [/^(\d+) order-win report\(s\)$/, (m) => `${m[1]} ಆರ್ಡರ್ ಗೆಲುವಿನ ವರದಿ(ಗಳು)`],
    [/^(\d+) negative event\(s\)$/, (m) => `${m[1]} ನಕಾರಾತ್ಮಕ ಘಟನೆ(ಗಳು)`],
    [/^RSI (\d+): positive momentum$/, (m) => `RSI ${m[1]}: ಧನಾತ್ಮಕ ಆವೇಗ`],
    [/^RSI (\d+): weak momentum$/, (m) => `RSI ${m[1]}: ದುರ್ಬಲ ಆವೇಗ`],
    [/^RSI (\d+): strong momentum but overbought — not an automatic sell$/, (m) => `RSI ${m[1]}: ಬಲವಾದ ಆವೇಗ, ಆದರೆ ಅತಿಖರೀದಿ — ತಕ್ಷಣ ಮಾರಾಟದ ಸಂಕೇತವಲ್ಲ`],
    [/^RSI (\d+): oversold — not an automatic buy$/, (m) => `RSI ${m[1]}: ಅತಿಮಾರಾಟ — ತಕ್ಷಣ ಖರೀದಿಯ ಸಂಕೇತವಲ್ಲ`],
    [/^ADX (\d+): strong trend, \+DI leading$/, (m) => `ADX ${m[1]}: ಬಲವಾದ ಪ್ರವೃತ್ತಿ, +DI ಮುಂದಿದೆ`],
    [/^ADX (\d+): strong trend, −DI leading$/, (m) => `ADX ${m[1]}: ಬಲವಾದ ಪ್ರವೃತ್ತಿ, −DI ಮುಂದಿದೆ`],
    [/^price data is stale \(last bar (.+)\)$/, (m) => `ಬೆಲೆ ದತ್ತಾಂಶ ಹಳೆಯದು (ಕೊನೆಯ ದಿನ ${m[1]})`],
    [/^illiquid: median traded value (.+)$/, (m) => `ದ್ರವ್ಯತೆ ಕಡಿಮೆ: ಸರಾಸರಿ ವಹಿವಾಟು ಮೌಲ್ಯ ${m[1]}`],
    [/^model did not pass out-of-sample validation: (.+)$/, (m) => `ಮಾದರಿ ಹೊರಗಿನ ಪರೀಕ್ಷೆಯಲ್ಲಿ ಉತ್ತೀರ್ಣವಾಗಿಲ್ಲ: ${m[1]}`],
    [/^no model prediction for this stock.*$/, () => "ಈ ಷೇರಿಗೆ ಮಾದರಿಯ ಮುನ್ಸೂಚನೆ ಇಲ್ಲ"],
    [/^Only if price holds above (.+) \(nearest support\) after the next session opens; avoid chasing a gap-up\.$/,
      (m) => `ಮುಂದಿನ ದಿನ ಬೆಲೆ ${m[1]} (ಹತ್ತಿರದ ಬೆಂಬಲ) ಕ್ಕಿಂತ ಮೇಲೆ ಉಳಿದರೆ ಮಾತ್ರ; ಅಂತರದ ಏರಿಕೆಯನ್ನು (gap-up) ಹಿಂಬಾಲಿಸಬೇಡಿ.`],
    [/^Past (\d+)-day returns of this stock \(not a forecast\): 10th pct (.+)%, median (.+)%, 90th pct (.+)%; positive (.+)% of the time\.$/,
      (m) => `ಈ ಷೇರಿನ ಹಿಂದಿನ ${m[1]}-ದಿನದ ಪ್ರತಿಫಲಗಳು (ಮುನ್ಸೂಚನೆ ಅಲ್ಲ): 10ನೇ ಶೇಕಡಾಂಶ ${m[2]}%, ಮಧ್ಯಮ ${m[3]}%, 90ನೇ ಶೇಕಡಾಂಶ ${m[4]}%; ${m[5]}% ಬಾರಿ ಏರಿಕೆ.`],
    [/^(.+)\. Thresholds: bullish ≥ (\S+), bearish ≥ (\S+)\. Model: (.+)\.$/,
      (m) => `${tr(m[1])}. ಮಿತಿಗಳು: ಏರುಮುಖ ≥ ${m[2]}, ಇಳಿಮುಖ ≥ ${m[3]}. ಮಾದರಿ: ${m[4]}.`],
    [/^(Large|Mid|Small|Unclassified)-cap$/, (m) => `${tr(m[1])} ಕಂಪನಿ`],
    [/^(\d+) candidates, (\d+) new, (\d+) sent, (\d+) failed$/, (m) => `${m[1]} ಅಭ್ಯರ್ಥಿ, ${m[2]} ಹೊಸ, ${m[3]} ಕಳುಹಿಸಲಾಗಿದೆ, ${m[4]} ವಿಫಲ`],
    [/^Model signals \((.+)\)$/, (m) => `ಮಾದರಿ ಸಂಕೇತಗಳು (${m[1].replace(/d/g, " ದಿನ")})`],
    [/^Confusion matrix \((.+)\)$/, (m) => `ಗೊಂದಲ ಮ್ಯಾಟ್ರಿಕ್ಸ್ (${m[1]})`],
    [/^Fibonacci \((up|down) swing\)$/, (m) => `ಫಿಬೊನಾಚಿ (${m[1] === "up" ? "ಏರು" : "ಇಳಿ"} ಚಲನೆ)`],
    [/^(\d+)-day$/, (m) => `${m[1]}-ದಿನ`],
    [/^(.+) ([↑↓])$/, (m) => `${tr(m[1])} ${m[2]}`],
    [/^1D ·$/, () => "1 ದಿನ ·"],
    [/^· source: (.+?) · fetched (.+)$/, (m) => `· ಮೂಲ: ${m[1]} · ಪಡೆದದ್ದು ${m[2]}`],
    [/^last (.+) · prev close (.+)$/, (m) => `ಕೊನೆಯ ದರ ${m[1]} · ಹಿಂದಿನ ಮುಕ್ತಾಯ ${m[2]}`],
    [/^· ISIN (\S+) · (.+?) · (Large|Mid|Small|Unclassified)-cap$/, (m) => `· ISIN ${m[1]} · ${tr(m[2])} · ${tr(m[3])} ಕಂಪನಿ`],
    [/^Data-quality notes: (.+)$/, (m) => `ದತ್ತಾಂಶ ಗುಣಮಟ್ಟದ ಟಿಪ್ಪಣಿ: ${m[1]}`],
    [/^(\d+) day(s)? assessment$/, (m) => `${m[1]}-ದಿನದ ಮೌಲ್ಯಮಾಪನ`],
  ];
  function translateDynamic(s) {
    for (const [re, f] of PATTERNS) {
      const m = s.match(re);
      if (m) return f(m);
    }
    const bi = s.match(BI_LABEL);
    if (bi) return bi[2];
    return null;
  }
  // a short "English label · ಕನ್ನಡ ಲೇಬಲ್" heading (no numbers, no extra separators)
  const BI_LABEL = /^([A-Za-z][A-Za-z ()\-]*) · ([\u0C80-\u0CFF][\u0C80-\u0CFF ()\-]*)$/;
  function translateText(s) {
    const k = s.trim();
    if (!k || !/[A-Za-z]/.test(k)) return null;
    const out = KN[k] !== undefined ? KN[k] : translateDynamic(k);
    return out == null || out === k ? null : s.replace(k, out);
  }
  function englishOnly(s) {   // in English mode, "English · ಕನ್ನಡ" labels keep the English side
    const k = s.trim();
    const bi = k.match(BI_LABEL);
    return bi ? s.replace(k, bi[1]) : null;
  }

  const SKIP = "code, pre, script, style, textarea, .notranslate, .t-en, .t-kn, .formula";
  function walk(root) {
    if (!root) return;
    const fn = lang === "kn" ? translateText : englishOnly;
    if (root.nodeType === 3) {
      if (root.parentElement && !root.parentElement.closest(SKIP)) {
        const t = fn(root.nodeValue);
        if (t != null) root.nodeValue = t;
      }
      return;
    }
    if (root.nodeType !== 1 || root.closest?.(SKIP)) return;
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (n.parentElement && n.parentElement.closest(SKIP) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
    });
    const nodes = [];
    while (tw.nextNode()) nodes.push(tw.currentNode);
    nodes.forEach((n) => { const t = fn(n.nodeValue); if (t != null) n.nodeValue = t; });
    if (lang === "kn") {
      [root, ...root.querySelectorAll("[placeholder],[title],[aria-label]")].forEach((el) => {
        for (const a of ["placeholder", "title", "aria-label"]) {
          const v = el.getAttribute?.(a);
          if (v && KN[v.trim()]) el.setAttribute(a, KN[v.trim()]);
        }
      });
      root.querySelectorAll("option").forEach((o) => { const t = translateText(o.textContent); if (t) o.textContent = t; });
    }
  }
  const observer = new MutationObserver((muts) => {
    for (const m of muts) {
      if (m.type === "characterData") walk(m.target);
      else m.addedNodes.forEach(walk);
    }
  });

  window.I18N = {
    get lang() { return lang; },
    t: (s) => (lang === "kn" ? (KN[s] ?? translateDynamic(s) ?? s) : s),
    locale: () => (lang === "kn" ? "kn-IN" : "en-IN"),
    start() {
      walk(document.body);
      observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    },
    set(next) {
      lang = next === "kn" ? "kn" : "en";
      try { localStorage.setItem("mi-lang", lang); } catch (e) { /* storage unavailable */ }
      document.documentElement.lang = lang;
    },
    _KN: KN, _translate: translateText,
  };
})();

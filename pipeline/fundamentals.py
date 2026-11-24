"""Fundamental analysis engine (CA-style research checks, not an audit or attestation).

Input: the raw dict from a provider's fundamentals() — statements keyed by period.
Output: ratios (with formula + inputs), multi-year trends, red flags and a multi-check score.
Every number records whether it is reported, derived or missing. A company is never called
"healthy" from one ratio: the overall label needs at least MIN_CHECKS evaluated checks.
"""
from __future__ import annotations

import math

MIN_CHECKS = 6

ALIASES = {
    "revenue": ["Total Revenue", "Operating Revenue", "Revenue"],
    "gross_profit": ["Gross Profit"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "ebit": ["EBIT", "Operating Income"],
    "operating_income": ["Operating Income", "EBIT"],
    "net_income": ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operation Net Minority Interest"],
    "interest_expense": ["Interest Expense", "Interest Expense Non Operating"],
    "eps": ["Diluted EPS", "Basic EPS"],
    "total_assets": ["Total Assets"],
    "current_assets": ["Current Assets"],
    "current_liabilities": ["Current Liabilities"],
    "inventory": ["Inventory"],
    "receivables": ["Accounts Receivable", "Receivables", "Gross Accounts Receivable"],
    "cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
    "total_debt": ["Total Debt"],
    "long_term_debt": ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"],
    "short_term_debt": ["Current Debt", "Current Debt And Capital Lease Obligation"],
    "equity": ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"],
    "reserves": ["Retained Earnings"],
    "ocf": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "icf": ["Investing Cash Flow", "Cash Flow From Continuing Investing Activities"],
    "fcf_fin": ["Financing Cash Flow", "Cash Flow From Continuing Financing Activities"],
    "capex": ["Capital Expenditure"],
    "fcf": ["Free Cash Flow"],
}


def _pick(stmt: dict, key: str):
    for name in ALIASES[key]:
        v = stmt.get(name)
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            return float(v)
    return None


def _div(a, b, scale: float = 1.0):
    if a is None or b is None or b == 0:
        return None
    return a / b * scale


def extract_years(raw: dict) -> list[dict]:
    """Merge income, balance and cash-flow statements per fiscal period (latest first)."""
    periods = sorted(set(raw.get("income", {})) | set(raw.get("balance", {})) | set(raw.get("cashflow", {})),
                     reverse=True)
    years = []
    for p in periods:
        merged = {**raw.get("income", {}).get(p, {}), **raw.get("balance", {}).get(p, {}),
                  **raw.get("cashflow", {}).get(p, {})}
        row = {"period": p}
        for key in ALIASES:
            row[key] = _pick(merged, key)
        if row["fcf"] is None and row["ocf"] is not None and row["capex"] is not None:
            row["fcf"] = row["ocf"] + row["capex"]  # capex is reported negative
        if row["total_debt"] is None and (row["long_term_debt"] or row["short_term_debt"]):
            row["total_debt"] = (row["long_term_debt"] or 0) + (row["short_term_debt"] or 0)
        years.append(row)
    return [y for y in years if y.get("revenue") is not None or y.get("total_assets") is not None]


def ratios(latest: dict, info: dict, price: float | None) -> dict:
    """Return {ratio: {value, formula, inputs}}; value None when inputs are missing."""
    mcap = info.get("marketCap")
    shares = info.get("sharesOutstanding")
    if mcap is None and price and shares:
        mcap = price * shares
    eps = latest.get("eps") or info.get("trailingEps")
    book_ps = info.get("bookValue")
    rev, ni, eq = latest.get("revenue"), latest.get("net_income"), latest.get("equity")
    ebitda, ebit = latest.get("ebitda"), latest.get("ebit")
    debt, cash = latest.get("total_debt"), latest.get("cash")
    ca, cl, inv = latest.get("current_assets"), latest.get("current_liabilities"), latest.get("inventory")
    capital_employed = (latest["total_assets"] - cl) if latest.get("total_assets") is not None and cl is not None else None
    ev = (mcap + (debt or 0) - (cash or 0)) if mcap is not None else None
    interest = abs(latest["interest_expense"]) if latest.get("interest_expense") else None
    growth = info.get("earningsGrowth")
    pe = _div(price, eps) if eps and eps > 0 else None
    dy = info.get("dividendYield")
    if dy is not None and dy > 1:   # yfinance sometimes returns percent, sometimes fraction
        dy = dy / 100

    def r(value, formula, **inputs):
        return {"value": None if value is None else round(float(value), 4), "formula": formula,
                "inputs": {k: v for k, v in inputs.items()}}

    return {
        "pe": r(pe, "Price / EPS", price=price, eps=eps),
        "pb": r(_div(price, book_ps), "Price / Book value per share", price=price, book_value_ps=book_ps),
        "eps": r(eps, "Net profit / Weighted shares", eps=eps),
        "roe": r(_div(ni, eq, 100), "Net profit / Shareholders' equity × 100", net_profit=ni, equity=eq),
        "roce": r(_div(ebit, capital_employed, 100), "EBIT / (Total assets − Current liabilities) × 100",
                  ebit=ebit, capital_employed=capital_employed),
        "roa": r(_div(ni, latest.get("total_assets"), 100), "Net profit / Total assets × 100",
                 net_profit=ni, total_assets=latest.get("total_assets")),
        "debt_to_equity": r(_div(debt, eq), "Total debt / Shareholders' equity", total_debt=debt, equity=eq),
        "current_ratio": r(_div(ca, cl), "Current assets / Current liabilities", current_assets=ca, current_liabilities=cl),
        "quick_ratio": r(_div((ca - (inv or 0)) if ca is not None else None, cl),
                         "(Current assets − Inventory) / Current liabilities", current_assets=ca, inventory=inv,
                         current_liabilities=cl),
        "interest_coverage": r(_div(ebit, interest), "EBIT / Interest expense", ebit=ebit, interest=interest),
        "ebitda_margin": r(_div(ebitda, rev, 100), "EBITDA / Revenue × 100", ebitda=ebitda, revenue=rev),
        "net_margin": r(_div(ni, rev, 100), "Net profit / Revenue × 100", net_profit=ni, revenue=rev),
        "operating_margin": r(_div(latest.get("operating_income"), rev, 100), "Operating profit / Revenue × 100",
                              operating_profit=latest.get("operating_income"), revenue=rev),
        "ocf_to_net_profit": r(_div(latest.get("ocf"), ni), "Operating cash flow / Net profit",
                               ocf=latest.get("ocf"), net_profit=ni),
        "ps": r(_div(mcap, rev), "Market cap / Revenue", market_cap=mcap, revenue=rev),
        "ev_ebitda": r(_div(ev, ebitda) if ebitda and ebitda > 0 else None,
                       "(Market cap + Debt − Cash) / EBITDA", ev=ev, ebitda=ebitda),
        "dividend_yield": r(dy * 100 if dy is not None else None, "Dividend per share / Price × 100", dividend_yield=dy),
        "peg": r(_div(pe, growth * 100) if pe and growth and growth > 0 else None,
                 "P/E / EPS growth rate (%)", pe=pe, eps_growth=growth),
        "working_capital_ratio": r(_div(ca, cl), "Current assets / Current liabilities (same as current ratio)",
                                   current_assets=ca, current_liabilities=cl),
        "working_capital": r((ca - cl) if ca is not None and cl is not None else None,
                             "Current assets − Current liabilities", current_assets=ca, current_liabilities=cl),
    }


def _growth(new, old):
    if new is None or old is None or old == 0:
        return None
    return (new / old - 1) * 100 if old > 0 else None


def red_flags(years: list[dict]) -> list[dict]:
    flags = []
    if len(years) < 2:
        return flags
    a, b = years[0], years[1]
    rg = _growth(a.get("revenue"), b.get("revenue"))
    og = _growth(a.get("ocf"), b.get("ocf"))
    if rg is not None and rg > 10 and (a.get("ocf") is not None and (a["ocf"] <= 0 or (og is not None and og < 0))):
        flags.append({"flag": "Revenue growth without cash-flow growth", "severity": "high",
                      "detail": f"Revenue +{rg:.1f}% but operating cash flow fell or is negative"})
    if a.get("total_debt") and b.get("total_debt") and a["total_debt"] > b["total_debt"] * 1.25:
        flags.append({"flag": "Rising debt", "severity": "medium",
                      "detail": f"Total debt up {_growth(a['total_debt'], b['total_debt']):.1f}% year-on-year"})
    ma = _div(a.get("ebitda"), a.get("revenue"), 100)
    mb = _div(b.get("ebitda"), b.get("revenue"), 100)
    if ma is not None and mb is not None and ma < mb - 2:
        flags.append({"flag": "Falling margins", "severity": "medium",
                      "detail": f"EBITDA margin {mb:.1f}% → {ma:.1f}%"})
    ic = _div(a.get("ebit"), abs(a["interest_expense"]) if a.get("interest_expense") else None)
    if ic is not None and ic < 2:
        flags.append({"flag": "Weak interest coverage", "severity": "high", "detail": f"EBIT covers interest only {ic:.1f}×"})
    recg = _growth(a.get("receivables"), b.get("receivables"))
    if recg is not None and rg is not None and recg > rg + 15:
        flags.append({"flag": "Receivables growing faster than revenue", "severity": "medium",
                      "detail": f"Receivables +{recg:.1f}% vs revenue +{rg:.1f}%"})
    invg = _growth(a.get("inventory"), b.get("inventory"))
    if invg is not None and rg is not None and invg > rg + 15:
        flags.append({"flag": "Inventory accumulation", "severity": "medium",
                      "detail": f"Inventory +{invg:.1f}% vs revenue +{rg:.1f}%"})
    if a.get("net_income") is not None and a["net_income"] < 0:
        flags.append({"flag": "Net loss in latest year", "severity": "high", "detail": "Reported net profit is negative"})
    return flags


def score(rat: dict, years: list[dict], sector: str = "") -> dict:
    """Multi-check scorecard. Banks/NBFCs/insurers skip checks that don't apply to them."""
    financial = any(w in (sector or "").lower() for w in ("financial", "bank", "insurance"))
    checks = []

    def add(name, value, ok, applies=True):
        if not applies or value is None:
            checks.append({"check": name, "result": "n/a"})
        else:
            checks.append({"check": name, "result": "pass" if ok else "fail", "value": round(value, 2)})

    v = lambda k: rat[k]["value"]  # noqa: E731
    add("ROE ≥ 12%", v("roe"), (v("roe") or 0) >= 12)
    add("ROCE ≥ 12%", v("roce"), (v("roce") or 0) >= 12, not financial)
    add("Debt/Equity ≤ 1", v("debt_to_equity"), (v("debt_to_equity") or 0) <= 1, not financial)
    add("Current ratio ≥ 1.2", v("current_ratio"), (v("current_ratio") or 0) >= 1.2, not financial)
    add("Interest coverage ≥ 3", v("interest_coverage"), (v("interest_coverage") or 0) >= 3, not financial)
    add("Net margin > 5%", v("net_margin"), (v("net_margin") or 0) > 5)
    add("OCF / Net profit ≥ 0.8", v("ocf_to_net_profit"), (v("ocf_to_net_profit") or 0) >= 0.8, not financial)
    if len(years) >= 2:
        g = _growth(years[0].get("revenue"), years[1].get("revenue"))
        add("Revenue growth > 0", g, (g or 0) > 0)
        ng = _growth(years[0].get("net_income"), years[1].get("net_income"))
        add("Profit growth > 0", ng, (ng or 0) > 0)
    if len(years) >= 3 and all(y.get("revenue") for y in years[:3]):
        cagr = ((years[0]["revenue"] / years[2]["revenue"]) ** 0.5 - 1) * 100 if years[2]["revenue"] > 0 else None
        add("2-yr revenue CAGR > 8%", cagr, (cagr or 0) > 8)
    evaluated = [c for c in checks if c["result"] != "n/a"]
    passed = sum(c["result"] == "pass" for c in evaluated)
    if len(evaluated) < MIN_CHECKS:
        label, value = "Insufficient data", None
    else:
        value = round(100 * passed / len(evaluated), 1)
        label = "Strong" if value >= 75 else "Moderate" if value >= 50 else "Weak"
    return {"score": value, "label": label, "passed": passed, "evaluated": len(evaluated), "checks": checks,
            "note": "Bank/NBFC/insurer: leverage & liquidity checks not applicable" if financial else ""}


def analyse(raw: dict, price: float | None, sector: str = "") -> dict:
    if not raw:
        return {"available": False, "reason": "No fundamentals fetched yet"}
    years = extract_years(raw)
    info = raw.get("info", {})
    if not years:
        return {"available": False, "reason": "Provider returned no financial statements",
                "fetched_at": raw.get("fetched_at")}
    rat = ratios(years[0], info, price)
    return {
        "available": True, "provider": raw.get("provider"), "fetched_at": raw.get("fetched_at"),
        "data_status": raw.get("data_status"), "currency": info.get("financialCurrency", "INR"),
        "latest_period": years[0]["period"], "ratios": rat, "years": years[:4],
        "red_flags": red_flags(years), "scorecard": score(rat, years, sector),
        "annual_revenue": years[0].get("revenue"),
        "governance_note": "Auditor qualifications, related-party transactions and pledges are not in this "
                           "data source; check the annual report and exchange filings.",
    }

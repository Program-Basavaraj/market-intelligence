"""News & corporate-announcement intelligence.

Copyright / terms: only the headline, source name, timestamp and original link are stored and
published. Article bodies are never republished. Paywalls, logins and rate limits are not bypassed.
Exchange filings (NSE/BSE) are marked "verified"; media reports are "unverified" until matched.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pandas as pd

from . import http
from .config import IST

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ categories
CATEGORIES = {
    "order_win": {
        "label": "Order win", "sentiment_prior": 0.5, "weight": 0.65,
        "patterns": [r"\b(bag|bags|bagged|win|wins|won|secure|secures|secured|receive|receives|received|"
                     r"bags?|gets?|got|clinch(es|ed)?|land(s|ed)?)\b.{0,40}\b(order|orders|contract|contracts|"
                     r"work order|loi|letter of (award|intent))\b",
                     r"\b(order|contract)s?\b.{0,25}\b(worth|valued|of rs|of ₹|of inr)\b",
                     r"\b(defence|railway|government|international|export|epc)\b.{0,20}\b(order|contract)\b",
                     r"\bcontract award(ed)?\b", r"\border inflow\b", r"\blowest bidder\b|\bl-?1 bidder\b"],
        "prototypes": ["company secures new order worth crore", "receives work order from government",
                       "wins major contract from railways", "bags defence order", "emerges lowest bidder for project"],
    },
    "results_positive": {
        "label": "Strong results / growth", "sentiment_prior": 0.6, "weight": 0.6,
        "patterns": [r"\b(net )?profit\b.{0,30}\b(rises|rose|jumps|jumped|surges|surged|up|grows|grew|soars|doubles)\b",
                     r"\b(revenue|sales|ebitda|income)\b.{0,30}\b(rises|jumps|surges|up|grows|grew|growth)\b",
                     r"\bmargin(s)? expan", r"\bearnings upgrade\b", r"\b(strong|robust|record) (q[1-4]|quarter|results|earnings)\b",
                     r"\bbeats? (estimates|expectations)\b"],
        "prototypes": ["net profit rises year on year", "revenue growth strong quarterly results",
                       "ebitda improvement margin expansion", "beats street estimates"],
    },
    "results_negative": {
        "label": "Weak results", "sentiment_prior": -0.6, "weight": 0.6,
        "patterns": [r"\b(net )?profit\b.{0,30}\b(falls|fell|declines|declined|drops|dropped|slumps|plunges|down)\b",
                     r"\b(revenue|sales|ebitda)\b.{0,30}\b(falls|declines|drops|slumps|down)\b",
                     r"\bmargin(s)? (contract|shrink|compress)", r"\b(net )?loss\b.{0,20}\b(widens|reports|posts)\b",
                     r"\bmisses? (estimates|expectations)\b", r"\bearnings downgrade\b"],
        "prototypes": ["net profit falls year on year", "reports net loss", "misses estimates weak quarter"],
    },
    "results_announcement": {
        "label": "Results announced / board meeting", "sentiment_prior": 0.0, "weight": 0.4,
        "patterns": [r"\b(financial )?results?\b.{0,30}\b(q[1-4]|quarter|fy\d{2}|half year|annual)\b",
                     r"\bboard meeting\b.{0,40}\bresults\b", r"\bq[1-4] results\b"],
        "prototypes": ["announces financial results for the quarter", "board meeting to consider results"],
    },
    "govt_regulatory": {
        "label": "Government / regulatory approval", "sentiment_prior": 0.4, "weight": 0.55,
        "patterns": [r"\b(government|govt|ministry|cabinet|sebi|rbi|usfda|cdsco|nclt|cci)\b.{0,30}\b(approv|clear|nod|sanction|grant)",
                     r"\bpli\b", r"\btender (award|won)\b", r"\bregulatory (clearance|approval)\b",
                     r"\b(eir|establishment inspection report)\b", r"\bdefence procurement\b"],
        "prototypes": ["receives regulatory approval", "government approves project", "pli scheme approval",
                       "usfda approval for drug"],
    },
    "business_development": {
        "label": "Business development", "sentiment_prior": 0.3, "weight": 0.5,
        "patterns": [r"\b(acquire|acquires|acquired|acquisition|merger|merge|amalgamation|demerger)\b",
                     r"\b(strategic )?(partnership|tie-?up|joint venture|jv|mou|collaboration)\b",
                     r"\b(capacity expansion|new (plant|facility|manufacturing)|commissions?|capex plan)\b",
                     r"\bexport(s)? (growth|order|surge)\b"],
        "prototypes": ["acquires stake in company", "announces joint venture", "commissions new manufacturing plant",
                       "capacity expansion plan"],
    },
    "corporate_action_positive": {
        "label": "Positive corporate action", "sentiment_prior": 0.45, "weight": 0.5,
        "patterns": [r"\bbuy-?back\b", r"\b(interim |final |special )?dividend\b", r"\bbonus (issue|shares)\b",
                     r"\bdebt (reduction|free|repay)", r"\bpromoter(s)?\b.{0,30}\b(buy|bought|raise|increase|hike)",
                     r"\bstock split\b|\bsplit of shares\b"],
        "prototypes": ["board approves share buyback", "declares interim dividend", "promoter increases stake",
                       "becomes debt free"],
    },
    "negative_event": {
        "label": "Negative development", "sentiment_prior": -0.75, "weight": 0.85,
        "patterns": [r"\b(fraud|forensic|probe|raid|investigation|show cause|scam)\b",
                     r"\b(sebi|rbi|ed|cbi|income tax)\b.{0,25}\b(penalty|fine|order|notice|ban)\b",
                     r"\b(default|defaults|defaulted|insolvency|ibc|nclt admits|bankruptcy|downgrade)\b",
                     r"\b(auditor|ceo|cfo|md|managing director|director)\b.{0,20}\b(resign|resigns|resigned|quits|steps down)\b",
                     r"\bpledge(d)?\b.{0,20}\b(increase|rise|hike)", r"\bplant (shutdown|fire)\b|\bfire at\b",
                     r"\bwarning letter\b|\bimport alert\b"],
        "prototypes": ["sebi imposes penalty", "auditor resigns citing concerns", "loan default insolvency proceedings",
                       "fraud investigation ordered", "promoter pledge increases"],
    },
    "market_trigger": {
        "label": "Market trigger", "sentiment_prior": 0.0, "weight": 0.35,
        "patterns": [r"\b(breakout|breaks out|breakdown|52-week (high|low)|all-time high|record high)\b",
                     r"\b(upper|lower) circuit\b", r"\b(volume spike|unusual volume|heavy volume|block deal|bulk deal)\b",
                     r"\bgap(s)? (up|down)\b", r"\b(shares?|stock) (zoom|soar|surge|jump|rally|tank|crash|plunge|slump)"],
        "prototypes": ["stock hits upper circuit", "shares surge on heavy volume", "stock hits 52 week high",
                       "shares plunge lower circuit", "block deal"],
    },
}

POSITIVE_WORDS = set("""gain gains rise rises rose jump jumps jumped surge surges surged soar soars rally rallies up upgrade
upgraded beat beats strong robust record growth grow grows grew profit profits approval approved wins won secures secured
bags bagged expansion expands higher boost boosts positive buyback dividend outperform bullish""".split())
NEGATIVE_WORDS = set("""fall falls fell drop drops dropped decline declines declined slump slumps plunge plunges plunged
crash crashes tank tanks loss losses weak down downgrade downgraded miss misses cut cuts penalty fine fraud probe default
resign resigns resigned lower negative bearish concern concerns warning risk delay delayed slowdown shutdown""".split())
NEGATORS = {"not", "no", "never", "without", "despite", "fails", "failed"}

KANNADA = {
    "order_win": "ಕಂಪನಿಗೆ ಹೊಸ ಆರ್ಡರ್ ಅಥವಾ ಒಪ್ಪಂದ (order/contract) ದೊರೆತಿದೆ ಎಂಬ ಸುದ್ದಿ. ಆರ್ಡರ್ ಮೊತ್ತವನ್ನು ಕಂಪನಿಯ ವಾರ್ಷಿಕ "
                 "ಆದಾಯಕ್ಕೆ ಹೋಲಿಸಿ ನೋಡಿ (Order Size Ratio). ದೊಡ್ಡ ಆರ್ಡರ್ ಬಂದ ಮಾತ್ರಕ್ಕೆ ಷೇರು ಬೆಲೆ ಏರುತ್ತದೆ ಎಂದು ಖಚಿತವಿಲ್ಲ.",
    "results_positive": "ಹಣಕಾಸು ಫಲಿತಾಂಶದಲ್ಲಿ ಬೆಳವಣಿಗೆ ಕಂಡುಬಂದಿದೆ ಎಂಬ ಸುದ್ದಿ. ಆದಾಯ (revenue), ಲಾಭ (profit) ಮತ್ತು ನಗದು ಹರಿವು "
                        "(cash flow) — ಮೂರನ್ನೂ ಒಟ್ಟಿಗೆ ಪರಿಶೀಲಿಸಿ.",
    "results_negative": "ಹಣಕಾಸು ಫಲಿತಾಂಶ ದುರ್ಬಲವಾಗಿದೆ ಎಂಬ ಸುದ್ದಿ (ಲಾಭ ಅಥವಾ ಆದಾಯ ಇಳಿಕೆ). ಇದು ತಾತ್ಕಾಲಿಕವೇ ಅಥವಾ "
                        "ಮುಂದುವರಿಯುವ ಸಮಸ್ಯೆಯೇ ಎಂಬುದನ್ನು ಗಮನಿಸಿ.",
    "results_announcement": "ಕಂಪನಿಯ ಹಣಕಾಸು ಫಲಿತಾಂಶ ಅಥವಾ ಮಂಡಳಿ ಸಭೆ (board meeting) ಕುರಿತ ಪ್ರಕಟಣೆ. ಫಲಿತಾಂಶದ ವಿವರಗಳು ಬಂದ "
                            "ನಂತರವೇ ಪರಿಣಾಮವನ್ನು ಅಂದಾಜಿಸಬಹುದು.",
    "govt_regulatory": "ಸರ್ಕಾರ ಅಥವಾ ನಿಯಂತ್ರಕ ಸಂಸ್ಥೆಯಿಂದ (SEBI, RBI, USFDA ಇತ್ಯಾದಿ) ಅನುಮೋದನೆ ಅಥವಾ ಟೆಂಡರ್‌ಗೆ ಸಂಬಂಧಿಸಿದ ಸುದ್ದಿ.",
    "business_development": "ಸ್ವಾಧೀನ (acquisition), ವಿಲೀನ (merger), ಪಾಲುದಾರಿಕೆ ಅಥವಾ ಸಾಮರ್ಥ್ಯ ವಿಸ್ತರಣೆಯ ಸುದ್ದಿ. ಇದಕ್ಕೆ "
                            "ಬೇಕಾಗುವ ಹೂಡಿಕೆ ಮತ್ತು ಸಾಲವನ್ನು ಗಮನಿಸಿ.",
    "corporate_action_positive": "ಷೇರು ಮರುಖರೀದಿ (buyback), ಲಾಭಾಂಶ (dividend), ಬೋನಸ್ ಅಥವಾ ಸಾಲ ಕಡಿತದಂತಹ ಕಾರ್ಪೊರೇಟ್ ಕ್ರಮ.",
    "negative_event": "ತನಿಖೆ, ದಂಡ, ಸಾಲ ಮರುಪಾವತಿ ವೈಫಲ್ಯ ಅಥವಾ ಹಿರಿಯ ಅಧಿಕಾರಿಗಳ ರಾಜೀನಾಮೆಯಂತಹ ನಕಾರಾತ್ಮಕ ಸುದ್ದಿ. ಅಪಾಯ "
                      "ಹೆಚ್ಚಿರಬಹುದು; ಅಧಿಕೃತ ಪ್ರಕಟಣೆಯನ್ನು ಓದಿ.",
    "market_trigger": "ಷೇರು ಬೆಲೆ ಅಥವಾ ವಹಿವಾಟು ಪ್ರಮಾಣದಲ್ಲಿ ಅಸಾಮಾನ್ಯ ಚಲನೆ (breakout, circuit, volume spike) ಕುರಿತ ಸುದ್ದಿ.",
    "other": "ಸಾಮಾನ್ಯ ಮಾರುಕಟ್ಟೆ ಸುದ್ದಿ; ನಿರ್ದಿಷ್ಟ ಘಟನೆ ಗುರುತಿಸಲಾಗಿಲ್ಲ.",
}
KANNADA_VERIFIED = {True: "ಇದು ವಿನಿಮಯ ಕೇಂದ್ರದ (NSE/BSE) ಅಧಿಕೃತ ಪ್ರಕಟಣೆ.",
                    False: "ಇದು ಮಾಧ್ಯಮ ವರದಿ; ಅಧಿಕೃತ ಪ್ರಕಟಣೆಯೊಂದಿಗೆ ದೃಢೀಕರಿಸಿ."}

COMMON_WORDS = set("""india indian bank power steel oil gas motors energy finance capital global national general united
the and for new star life first tech infra industries international limited company group market markets stock stocks
shares share sensex nifty bse nse rbi sebi govt""".split())


# ------------------------------------------------------------------ fetching
def _text(el, *names):
    for n in names:
        found = el.find(n)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    for fn in (parsedate_to_datetime, lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))):
        try:
            d = fn(s)
            return d if d.tzinfo else d.replace(tzinfo=IST)
        except Exception:  # noqa: BLE001
            continue
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s.strip(), fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def parse_rss(xml_text: str, source: str, official: bool) -> list[dict]:
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    out = []
    for it in items:
        title = _text(it, "title", "{http://www.w3.org/2005/Atom}title")
        link = _text(it, "link")
        if not link:
            l = it.find("{http://www.w3.org/2005/Atom}link")
            link = l.get("href", "") if l is not None else ""
        desc = re.sub(r"<[^>]+>", " ", _text(it, "description", "{http://www.w3.org/2005/Atom}summary"))
        pub = _parse_date(_text(it, "pubDate", "{http://www.w3.org/2005/Atom}updated", "{http://purl.org/dc/elements/1.1/}date"))
        if title and link:
            out.append({"headline": re.sub(r"\s+", " ", title), "url": link.strip(), "source": source,
                        "official": official, "published": pub.isoformat() if pub else None,
                        "_desc": re.sub(r"\s+", " ", desc)[:400]})   # used for classification only, never published
    return out


def fetch_feeds(feeds: list[dict]) -> tuple[list[dict], dict]:
    items, status = [], {}
    for f in feeds:
        try:
            resp = http.get(f["url"], headers={"Referer": "https://www.nseindia.com/"} if "nse" in f["url"] else None)
            got = parse_rss(resp.content.decode(resp.encoding or "utf-8", errors="replace"), f["name"], f.get("official", False))
            items.extend(got)
            status[f["name"]] = f"ok ({len(got)})"
        except Exception as exc:  # noqa: BLE001 - every failure is reported on the status page
            status[f["name"]] = f"failed: {str(exc)[:160]}"
    return items, status


def fetch_bse_announcements(day: datetime) -> list[dict]:
    """Unofficial JSON endpoint used by bseindia.com. Optional; failures are reported, not hidden."""
    d = day.strftime("%Y%m%d")
    url = ("https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno=1&strCat=-1"
           f"&strPrevDate={d}&strScrip=&strSearch=P&strToDate={d}&strType=C&subcategory=-1")
    resp = http.get(url, headers={"Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com"})
    rows = resp.json().get("Table", [])
    out = []
    for r in rows:
        att = r.get("ATTACHMENTNAME") or ""
        link = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{att}" if att else \
            "https://www.bseindia.com/corporates/ann.html"
        pub = _parse_date(r.get("NEWS_DT") or r.get("DT_TM") or "")
        out.append({"headline": f"{r.get('SLONGNAME', '').strip()}: {r.get('NEWSSUB') or r.get('HEADLINE', '')}".strip(),
                    "url": link, "source": "BSE Corporate Announcements", "official": True,
                    "published": pub.isoformat() if pub else None, "bse_code": str(r.get("SCRIP_CD", "")),
                    "_desc": (r.get("HEADLINE") or "")[:400]})
    return out


# ------------------------------------------------------------------ company matching
def _norm(s: str) -> str:
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _name_aliases(name: str) -> list[str]:
    n = _norm(name)
    n = re.sub(r"\b(limited|ltd|private|pvt|corporation|corp|company|co|inc)\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    aliases = {n}
    parts = n.split()
    if len(parts) >= 3 and parts[-1] in ("india", "industries", "enterprises", "and"):
        aliases.add(" ".join(parts[:-1]))
    return [a for a in aliases if a]


class CompanyMatcher:
    def __init__(self, master: pd.DataFrame):
        self.by_symbol = {}
        self.by_bse = {}
        self.alias_index: dict[str, list[tuple[str, str]]] = {}
        for row in master.to_dict("records"):
            sym = row["symbol"]
            self.by_symbol[sym] = row
            if row.get("bse_code"):
                self.by_bse[str(row["bse_code"])] = row
            for alias in _name_aliases(row.get("name", "")):
                toks = alias.split()
                if len(toks) == 1 and (len(alias) < 5 or alias in COMMON_WORDS):
                    continue  # too ambiguous on its own
                self.alias_index.setdefault(toks[0], []).append((alias, sym))

    def match(self, headline: str, bse_code: str = "") -> list[dict]:
        if bse_code and bse_code in self.by_bse:
            return [self._out(self.by_bse[bse_code], "bse_code", 1.0)]
        found: dict[str, tuple[float, str]] = {}
        text = _norm(headline)
        toks = text.split()
        for i, t in enumerate(toks):
            for alias, sym in self.alias_index.get(t, []):
                a_toks = alias.split()
                if toks[i:i + len(a_toks)] == a_toks:
                    conf = min(1.0, 0.6 + 0.15 * len(a_toks))
                    if sym not in found or found[sym][0] < conf:
                        found[sym] = (conf, "name")
        # upper-case NSE symbols written in the headline, e.g. "RVNL shares jump"
        for tok in re.findall(r"\b[A-Z][A-Z0-9&\-]{2,14}\b", headline):
            if tok in self.by_symbol and tok.lower() not in COMMON_WORDS and tok not in ("NSE", "BSE", "IPO", "CEO", "Q1", "Q2", "Q3", "Q4"):
                found.setdefault(tok, (0.75, "symbol"))
        # keep the longest/most confident matches, drop names contained in a longer match
        ranked = sorted(found.items(), key=lambda kv: -kv[1][0])[:3]
        return [self._out(self.by_symbol[s], how, conf) for s, (conf, how) in ranked]

    @staticmethod
    def _out(row: dict, how: str, conf: float) -> dict:
        return {"symbol": row["symbol"], "name": row.get("name"), "isin": row.get("isin"),
                "bse_code": row.get("bse_code"), "sector": row.get("sector"), "match": how,
                "match_confidence": round(conf, 2)}


# ------------------------------------------------------------------ classification
_COMPILED = {k: [re.compile(p, re.I) for p in v["patterns"]] for k, v in CATEGORIES.items()}
_PROTO = None


def _prototype_model():
    global _PROTO
    if _PROTO is None:
        from sklearn.feature_extraction.text import TfidfVectorizer
        labels, docs = [], []
        for k, v in CATEGORIES.items():
            for p in v["prototypes"]:
                labels.append(k)
                docs.append(p)
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True).fit(docs)
        _PROTO = (vec, vec.transform(docs), labels)
    return _PROTO


def classify(text: str) -> tuple[str, float, str]:
    """Return (category, confidence, method). Regex rules first, then TF-IDF prototype similarity."""
    hits = [(k, CATEGORIES[k]["weight"]) for k, pats in _COMPILED.items() if any(p.search(text) for p in pats)]
    if hits:
        # negative events dominate; otherwise the most specific (highest weight) rule wins
        if any(k == "negative_event" for k, _ in hits):
            return "negative_event", 0.9, "rule"
        k = max(hits, key=lambda kv: kv[1])[0]
        return k, 0.85, "rule"
    vec, mat, labels = _prototype_model()
    sims = (vec.transform([text.lower()]) @ mat.T).toarray()[0]
    best = int(sims.argmax())
    if sims[best] >= 0.30:
        return labels[best], round(float(sims[best]), 2), "similarity"
    return "other", 0.0, "none"


def sentiment(text: str, category: str) -> float:
    toks = _norm(text).split()
    score = 0.0
    for i, t in enumerate(toks):
        s = 1 if t in POSITIVE_WORDS else -1 if t in NEGATIVE_WORDS else 0
        if s and any(w in NEGATORS for w in toks[max(0, i - 3):i]):
            s = -s
        score += s
    lex = max(-1.0, min(1.0, score / 3))
    prior = CATEGORIES.get(category, {}).get("sentiment_prior", 0.0)
    return round(0.5 * lex + 0.5 * prior if category != "other" else lex, 3)


# ------------------------------------------------------------------ numbers
AMOUNT_RE = re.compile(
    r"(?P<cur>rs\.?|inr|₹|\$|usd|us\$)?\s*(?P<num>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>lakh crore|crore|crores|cr|lakh|lakhs|million|mn|billion|bn)\b", re.I)
DURATION_RE = re.compile(r"\b(?:within|over|in|across|during)\s+(?:a\s+period\s+of\s+)?(\d{1,3})\s*(months?|years?|days?)\b", re.I)


def extract_amounts(text: str, usd_inr: float) -> list[dict]:
    out = []
    for m in AMOUNT_RE.finditer(text):
        num = float(m.group("num").replace(",", ""))
        unit = m.group("unit").lower()
        cur = (m.group("cur") or "").lower()
        is_usd = cur in ("$", "usd", "us$")
        if not cur and unit in ("million", "mn", "billion", "bn"):
            continue  # ambiguous currency, skip rather than guess
        if unit == "lakh crore":
            cr = num * 1e5
        elif unit.startswith("cr"):
            cr = num
        elif unit.startswith("lakh"):
            cr = num / 100
        elif unit in ("million", "mn"):
            cr = num * 1e6 / 1e7
        else:
            cr = num * 1e9 / 1e7
        if is_usd:
            cr *= usd_inr
        out.append({"text": m.group(0).strip(), "inr_crore": round(cr, 2), "converted_from_usd": is_usd})
    return out


def extract_duration_months(text: str) -> float | None:
    m = DURATION_RE.search(text)
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2).lower()
    return n * 12 if unit.startswith("year") else n / 30 if unit.startswith("day") else n


def order_analysis(order_cr: float | None, annual_revenue_inr: float | None, duration_m: float | None) -> dict:
    """Order Size Ratio = New Order Value / Annual Revenue × 100 (with what is NOT known stated)."""
    res = {"order_value_cr": order_cr, "annual_revenue_cr": round(annual_revenue_inr / 1e7, 2) if annual_revenue_inr else None,
           "execution_months": duration_m}
    if order_cr and annual_revenue_inr:
        ratio = order_cr * 1e7 / annual_revenue_inr * 100
        res["order_size_ratio_pct"] = round(ratio, 2)
        if duration_m:
            res["annualised_ratio_pct"] = round(ratio * 12 / max(duration_m, 1), 2)
        res["materiality"] = "high" if ratio >= 20 else "moderate" if ratio >= 5 else "low"
    else:
        res["order_size_ratio_pct"] = None
        res["materiality"] = "unknown (order value or revenue missing)"
    res["not_available_from_source"] = ["order book size", "customer concentration", "payment terms",
                                        "project margin", "working-capital and debt needs"]
    res["caution"] = "A large order is not automatically bullish: margin, execution risk and funding matter."
    return res


# ------------------------------------------------------------------ de-duplication & history
def canonical_url(url: str) -> str:
    p = urlsplit(url.strip())
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", ""))


def _tokens(s: str) -> set:
    return {t for t in _norm(s).split() if len(t) > 2}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def process(items: list[dict], matcher: CompanyMatcher, history: list[dict], revenue_lookup: dict,
            usd_inr: float, now: datetime | None = None) -> list[dict]:
    """Enrich, classify, de-duplicate. Returns the merged history (newest first)."""
    now = now or datetime.now(timezone.utc)
    known = {h["id"]: h for h in history}
    recent = [h for h in history if h.get("published") and
              datetime.fromisoformat(h["published"]) > now - timedelta(days=3)]
    for it in items:
        nid = hashlib.sha1(canonical_url(it["url"]).encode()).hexdigest()[:16]
        if nid in known:
            continue
        text = f"{it['headline']} {it.get('_desc', '')}"
        toks = _tokens(it["headline"])
        dup = next((h for h in recent if jaccard(toks, _tokens(h["headline"])) >= 0.75), None)
        if dup:
            dup.setdefault("also_reported_by", [])
            if it["source"] not in dup["also_reported_by"] and it["source"] != dup["source"]:
                dup["also_reported_by"].append(it["source"])
            if it["official"] and not dup.get("verified"):
                dup["verified"] = True
            continue
        cat, conf, method = classify(text)
        companies = matcher.match(it["headline"], it.get("bse_code", ""))
        amounts = extract_amounts(text, usd_inr)
        sent = sentiment(it["headline"], cat)
        primary = companies[0] if companies else None
        order = None
        if cat == "order_win":
            order_cr = max((a["inr_crore"] for a in amounts), default=None)
            order = order_analysis(order_cr, revenue_lookup.get(primary["symbol"]) if primary else None,
                                   extract_duration_months(text))
        importance = CATEGORIES.get(cat, {}).get("weight", 0.2) * (1.0 if it["official"] else 0.8)
        if order and order.get("order_size_ratio_pct"):
            importance = min(1.0, importance + min(order["order_size_ratio_pct"], 50) / 100)
        repeat_of = None
        if primary:
            for h in history:
                if h.get("symbol") == primary["symbol"] and h.get("category") == cat and \
                        jaccard(toks, _tokens(h["headline"])) >= 0.5:
                    repeat_of = h["id"]
                    break
        rec = {
            "id": nid, "headline": it["headline"], "url": it["url"], "source": it["source"],
            "published": it.get("published") or now.isoformat(), "published_estimated": not it.get("published"),
            "collected_at": now.isoformat(), "verified": bool(it["official"]),
            "symbol": primary["symbol"] if primary else None, "companies": companies,
            "sector": primary.get("sector") if primary else None,
            "category": cat, "category_label": CATEGORIES.get(cat, {}).get("label", "Other"),
            "classification": {"confidence": conf, "method": method},
            "sentiment": sent, "importance": round(importance * 100, 1), "amounts": amounts,
            "order_analysis": order, "repeat_of": repeat_of,
            "explain_en": f"{CATEGORIES.get(cat, {}).get('label', 'General news')}; sentiment "
                          f"{'positive' if sent > 0.15 else 'negative' if sent < -0.15 else 'neutral'}; "
                          f"{'exchange filing (verified)' if it['official'] else 'media report (unverified)'}."
                          + (" Similar to an earlier item — may already be disclosed." if repeat_of else ""),
            "explain_kn": KANNADA.get(cat, KANNADA["other"]) + " " + KANNADA_VERIFIED[bool(it["official"])],
        }
        known[nid] = rec
        recent.append(rec)
    merged = sorted(known.values(), key=lambda r: r.get("published") or "", reverse=True)
    cutoff = (now - timedelta(days=45)).isoformat()
    return [m for m in merged if (m.get("published") or "") >= cutoff][:6000]


def load_history(path: Path) -> list[dict]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("news history corrupt; starting fresh")
    return []


def news_sentiment_by_symbol(history: list[dict], days: int = 7, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    out: dict[str, dict] = {}
    for h in history:
        sym = h.get("symbol")
        if not sym or not h.get("published"):
            continue
        age = (now - datetime.fromisoformat(h["published"])).total_seconds() / 86400
        if age > days or age < -1:
            continue
        w = (h["importance"] / 100) * (0.5 ** (max(age, 0) / 2))  # 2-day half-life
        d = out.setdefault(sym, {"score": 0.0, "weight": 0.0, "count": 0, "negative_events": 0, "order_wins": 0})
        d["score"] += w * h["sentiment"]
        d["weight"] += w
        d["count"] += 1
        d["negative_events"] += h["category"] == "negative_event"
        d["order_wins"] += h["category"] == "order_win"
    for d in out.values():
        d["score"] = round(d["score"] / d["weight"], 3) if d["weight"] else 0.0
        del d["weight"]
    return out

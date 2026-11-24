"""Dynamic instrument master for NSE (and BSE where the scrip list is reachable).

Sources, in order of preference:
  1. NSE equity list (EQUITY_L.csv)            -> symbol, name, ISIN, listing date
  2. Nifty Indices constituent CSVs            -> index membership, industry, size category
  3. BSE scrip list (unofficial JSON endpoint) -> BSE security code, joined on ISIN
  4. Previously saved master (cache)           -> used when downloads fail
  5. Bundled fallback list (config/fallback_instruments.csv) -> last resort, flagged

NSE and BSE symbols are never assumed to be the same: the two are joined on ISIN only.
"""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import http
from .config import ROOT, Settings

log = logging.getLogger(__name__)

NSE_EQUITY_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
INDEX_URLS = {
    "nifty50": "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv",
    "niftynext50": "https://niftyindices.com/IndexConstituent/ind_niftynext50list.csv",
    "nifty100": "https://niftyindices.com/IndexConstituent/ind_nifty100list.csv",
    "nifty200": "https://niftyindices.com/IndexConstituent/ind_nifty200list.csv",
    "nifty500": "https://niftyindices.com/IndexConstituent/ind_nifty500list.csv",
    "midcap150": "https://niftyindices.com/IndexConstituent/ind_niftymidcap150list.csv",
    "smallcap250": "https://niftyindices.com/IndexConstituent/ind_niftysmallcap250list.csv",
}
BSE_SCRIP_URL = ("https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode="
                 "&industry=&segment=Equity&status=Active")
FALLBACK_FILE = ROOT / "config" / "fallback_instruments.csv"

COLUMNS = ["symbol", "name", "isin", "bse_code", "series", "sector", "industry", "listing_date",
           "listing_status", "instrument_type", "exchanges", "cap_category", "cap_source",
           "indices", "yahoo_nse", "yahoo_bse"]


def _csv(url: str) -> pd.DataFrame:
    resp = http.get(url, headers={"Referer": "https://www.nseindia.com/"})
    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = [c.strip() for c in df.columns]
    return df


def fetch_nse_equity() -> pd.DataFrame:
    df = _csv(NSE_EQUITY_URL)
    df = df.rename(columns={"SYMBOL": "symbol", "NAME OF COMPANY": "name", "SERIES": "series",
                            "DATE OF LISTING": "listing_date", "ISIN NUMBER": "isin"})
    df = df[df["series"].astype(str).str.strip().isin(["EQ", "BE", "BZ", "SM", "ST"])]
    return df[["symbol", "name", "series", "listing_date", "isin"]].apply(
        lambda c: c.astype(str).str.strip())


def fetch_index(key: str) -> pd.DataFrame:
    df = _csv(INDEX_URLS[key])
    df = df.rename(columns={"Company Name": "name", "Industry": "industry", "Symbol": "symbol",
                            "Series": "series", "ISIN Code": "isin"})
    return df[["symbol", "name", "industry", "isin"]].apply(lambda c: c.astype(str).str.strip())


def fetch_bse_scrips() -> pd.DataFrame:
    resp = http.get(BSE_SCRIP_URL, headers={"Referer": "https://www.bseindia.com/",
                                            "Origin": "https://www.bseindia.com"})
    data = resp.json()
    rows = data if isinstance(data, list) else data.get("Table", [])
    df = pd.DataFrame(rows)
    if df.empty:
        raise http.FetchError("BSE scrip list empty")
    cols = {c.lower(): c for c in df.columns}
    out = pd.DataFrame({
        "bse_code": df[cols.get("scrip_cd", "SCRIP_CD")].astype(str),
        "isin": df[cols.get("isin_number", "ISIN_NUMBER")].astype(str).str.strip(),
        "bse_symbol": df[cols.get("scrip_id", "scrip_id")].astype(str).str.strip()
        if cols.get("scrip_id") else "",
        "bse_industry": df[cols["industry"]].astype(str) if "industry" in cols else "",
    })
    return out


def _cap_category(symbol: str, members: dict[str, set]) -> tuple[str, str]:
    """SEBI-style size buckets approximated from Nifty index membership."""
    if symbol in members.get("nifty100", set()):
        return "Large", "Nifty 100 membership"
    if symbol in members.get("midcap150", set()):
        return "Mid", "Nifty Midcap 150 membership"
    if symbol in members.get("smallcap250", set()):
        return "Small", "Nifty Smallcap 250 membership"
    return "Unclassified", "not in Nifty 100/Midcap 150/Smallcap 250"


def build_master(settings: Settings) -> tuple[pd.DataFrame, dict]:
    """Return (master dataframe, report). Never silently invents instruments."""
    report: dict = {"sources": {}, "warnings": []}
    cache_file = Path(settings.cache_dir) / "instrument_master.csv"

    members: dict[str, set] = {}
    industry: dict[str, str] = {}
    for key in INDEX_URLS:
        try:
            idx = fetch_index(key)
            members[key] = set(idx["symbol"])
            for s, ind in zip(idx["symbol"], idx["industry"]):
                industry.setdefault(s, ind)
            report["sources"][key] = f"ok ({len(idx)})"
        except Exception as exc:  # noqa: BLE001 - every failure is reported
            report["sources"][key] = f"failed: {exc}"

    try:
        nse = fetch_nse_equity()
        report["sources"]["nse_equity_list"] = f"ok ({len(nse)})"
    except Exception as exc:  # noqa: BLE001
        report["sources"]["nse_equity_list"] = f"failed: {exc}"
        nse = None

    if nse is None:
        # Build from index lists if those worked
        frames = []
        for key in ("nifty500", "nifty200", "nifty100", "nifty50"):
            if key in members:
                try:
                    frames.append(fetch_index(key))
                except Exception:  # noqa: BLE001
                    pass
                break
        if frames:
            nse = frames[0].assign(series="EQ", listing_date="")
            report["warnings"].append("NSE equity list unavailable; universe built from Nifty index list.")
        elif cache_file.exists():
            cached = pd.read_csv(cache_file, dtype=str).fillna("")
            report["warnings"].append("All downloads failed; using previously saved instrument master.")
            report["mode"] = "cache"
            return cached, report
        else:
            fb = pd.read_csv(FALLBACK_FILE, dtype=str).fillna("")
            report["warnings"].append(
                "All downloads failed and no cache exists; using the bundled fallback list "
                "(not an official index list - verify).")
            report["mode"] = "fallback"
            fb["cap_source"] = "fallback list (unverified)"
            fb["indices"] = ""
            for col in COLUMNS:
                if col not in fb:
                    fb[col] = ""
            fb["yahoo_nse"] = fb["symbol"] + ".NS"
            fb["exchanges"] = "NSE"
            fb["listing_status"] = "Listed (unverified)"
            fb["instrument_type"] = "Equity"
            return fb[COLUMNS], report

    df = nse.copy()
    df["industry"] = df["symbol"].map(industry).fillna("")
    df["sector"] = df["industry"]  # Nifty "Industry" is the closest free sector label
    cats = df["symbol"].apply(lambda s: _cap_category(s, members))
    df["cap_category"] = [c[0] for c in cats]
    df["cap_source"] = [c[1] if members else "unverified" for c in cats]
    df["indices"] = df["symbol"].apply(
        lambda s: ",".join(k for k in ("nifty50", "niftynext50", "nifty100", "nifty200", "nifty500")
                           if s in members.get(k, set())))
    df["listing_status"] = "Listed"
    df["instrument_type"] = "Equity"
    df["exchanges"] = "NSE"
    df["bse_code"] = ""
    df["yahoo_nse"] = df["symbol"] + ".NS"
    df["yahoo_bse"] = ""

    try:
        bse = fetch_bse_scrips()
        joined = df.merge(bse[["isin", "bse_code"]].drop_duplicates("isin"), on="isin", how="left",
                          suffixes=("", "_b"))
        df["bse_code"] = joined["bse_code_b"].fillna("").values
        has_bse = df["bse_code"] != ""
        df.loc[has_bse, "exchanges"] = "NSE,BSE"
        df.loc[has_bse, "yahoo_bse"] = df.loc[has_bse, "bse_code"] + ".BO"
        report["sources"]["bse_scrip_list"] = f"ok ({len(bse)}), matched {int(has_bse.sum())} by ISIN"
    except Exception as exc:  # noqa: BLE001
        report["sources"]["bse_scrip_list"] = f"failed: {exc} (BSE codes left blank)"

    for col in COLUMNS:
        if col not in df:
            df[col] = ""
    df = df[COLUMNS].drop_duplicates("symbol").reset_index(drop=True)

    report["changes"] = detect_changes(cache_file, df)
    df.to_csv(cache_file, index=False)
    report["mode"] = "live"
    return df, report


def detect_changes(previous_file: Path, current: pd.DataFrame) -> dict:
    """New listings, removals (delisted/suspended/moved series) and symbol changes via ISIN."""
    if not previous_file.exists():
        return {"new": [], "removed": [], "symbol_changes": []}
    prev = pd.read_csv(previous_file, dtype=str).fillna("")
    prev_isin = dict(zip(prev["isin"], prev["symbol"]))
    cur_isin = dict(zip(current["isin"], current["symbol"]))
    changes = [{"isin": i, "old": prev_isin[i], "new": s} for i, s in cur_isin.items()
               if i in prev_isin and prev_isin[i] != s and i]
    new = sorted(set(current["symbol"]) - set(prev["symbol"]) - {c["new"] for c in changes})
    removed = sorted(set(prev["symbol"]) - set(current["symbol"]) - {c["old"] for c in changes})
    return {"new": new[:200], "removed": removed[:200], "symbol_changes": changes[:200],
            "checked_at": datetime.now(timezone.utc).isoformat()}


def select_universe(master: pd.DataFrame, universe: str) -> pd.DataFrame:
    if universe == "all_nse":
        return master[master["series"].isin(["EQ", "BE", ""])]
    key = universe.lower()
    if master["indices"].str.len().sum() == 0:
        return master  # fallback/cached list without membership info
    sel = master[master["indices"].str.split(",").apply(lambda xs: key in xs)]
    return sel if len(sel) else master


def save_public(master: pd.DataFrame, report: dict, out_dir: Path) -> None:
    pub = master[["symbol", "name", "isin", "bse_code", "sector", "industry", "cap_category",
                  "cap_source", "indices", "exchanges", "listing_status"]]
    with open(Path(out_dir) / "instruments.json", "w", encoding="utf-8") as fh:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "report": report,
                   "count": len(pub), "instruments": pub.to_dict("records")}, fh, ensure_ascii=False)

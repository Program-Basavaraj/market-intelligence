"""Telegram alerts with de-duplication. Token & chat id come only from environment variables."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

log = logging.getLogger(__name__)
RISK = "⚠️ Research estimate, not advice. No guaranteed outcome. ಸಂಶೋಧನಾ ಅಂದಾಜು ಮಾತ್ರ — ಹೂಡಿಕೆ ಸಲಹೆ ಅಲ್ಲ."


class AlertLog:
    def __init__(self, path: Path, keep_days: int = 10):
        self.path = Path(path)
        self.keep = keep_days
        self.sent: dict[str, str] = {}
        if self.path.exists():
            try:
                self.sent = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.sent = {}

    @staticmethod
    def key(*parts) -> str:
        return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:16]

    def seen(self, k: str) -> bool:
        return k in self.sent

    def mark(self, k: str):
        self.sent[k] = datetime.now(timezone.utc).isoformat()

    def save(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.keep)).isoformat()
        self.sent = {k: v for k, v in self.sent.items() if v >= cutoff}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.sent), encoding="utf-8")


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_news_alert(n: dict) -> str:
    oa = n.get("order_analysis") or {}
    lines = [f"<b>{_esc(n['category_label'])}</b> — {_esc(n.get('symbol') or 'unmatched')}",
             _esc(n["headline"]),
             f"Source: {_esc(n['source'])} ({'verified filing' if n['verified'] else 'media report'})",
             f"Impact score: {n['importance']}/100 · sentiment {n['sentiment']:+.2f}"]
    if oa.get("order_size_ratio_pct") is not None:
        lines.append(f"Order ₹{oa['order_value_cr']:,} cr = {oa['order_size_ratio_pct']}% of annual revenue ({oa['materiality']})")
    lines += [f"<a href=\"{_esc(n['url'])}\">Original link</a>", f"Time: {_esc(n['published'])}", RISK]
    return "\n".join(lines)


def format_signal_alert(rec: dict, h: dict, kind: str) -> str:
    p = h["probabilities"]
    return "\n".join([
        f"<b>{kind}</b> — {_esc(rec['symbol'])} ({_esc(rec['name'])})",
        f"Price ₹{rec['latest_price']} (data: {_esc(rec['data_timestamp'])}, end-of-day)",
        f"{h['horizon_days']}-day swing: bullish {p['bullish']}% · neutral {p['neutral']}% · bearish {p['bearish']}%",
        f"Model confidence: {h['model_confidence']} · Intraday: not available",
        "Evidence: " + _esc("; ".join(rec["technical_justification"][:3])),
        RISK])


def send(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=15)
        if r.status_code == 200 and r.json().get("ok"):
            return True, "sent"
        return False, f"HTTP {r.status_code}: {r.text[:120]}"
    except requests.RequestException as exc:
        return False, str(exc)[:160]


def dispatch(settings, news: list[dict], recs: list[dict], new_news_ids: set, state_dir: Path) -> dict:
    """Build candidate alerts, skip duplicates, send (if configured). Returns a status report."""
    log_ = AlertLog(Path(state_dir) / "alerts_sent.json")
    cfg = settings.alerts
    candidates: list[tuple[str, str]] = []
    for n in news:
        if n["id"] not in new_news_ids:
            continue
        oa = n.get("order_analysis") or {}
        major_order = n["category"] == "order_win" and (oa.get("order_size_ratio_pct") or 0) >= cfg["min_order_size_ratio_pct"]
        if major_order or n["category"] == "negative_event" and n.get("symbol") or (n["verified"] and n["importance"] >= 60):
            candidates.append((AlertLog.key("news", n["id"]), format_news_alert(n)))
    for rec in recs:
        for h in rec["horizons"]:
            if h.get("label") in ("bullish", "bearish"):
                prob = h["probabilities"][h["label"]] / 100
                if prob >= cfg["min_probability"]:
                    kind = "Strong bullish signal" if h["label"] == "bullish" else "Strong bearish signal"
                    candidates.append((AlertLog.key("sig", rec["symbol"], h["horizon_days"], h["label"], rec["data_timestamp"]),
                                       format_signal_alert(rec, h, kind)))
        dq = rec["data_quality"]
        if dq.get("breakout") or dq.get("breakdown") or (dq.get("rel_volume") or 0) >= cfg["volume_spike_x"]:
            what = "Breakout" if dq.get("breakout") else "Breakdown" if dq.get("breakdown") else "Unusual volume"
            text = (f"<b>{what}</b> — {_esc(rec['symbol'])}\nClose ₹{rec['latest_price']} · relative volume "
                    f"{dq.get('rel_volume')}× · data {rec['data_timestamp']}\n{RISK}")
            candidates.append((AlertLog.key("trig", rec["symbol"], what, rec["data_timestamp"]), text))
    fresh = [(k, t) for k, t in candidates if not log_.seen(k)][: cfg["max_per_run"]]
    report = {"configured": bool(settings.telegram_token and settings.telegram_chat_id),
              "candidates": len(candidates), "new": len(fresh), "sent": 0, "failed": 0, "errors": []}
    if not report["configured"]:
        report["note"] = "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — alerts not sent"
        return report
    for k, text in fresh:
        ok, msg = send(settings.telegram_token, settings.telegram_chat_id, text)
        if ok:
            log_.mark(k)
            report["sent"] += 1
        else:
            report["failed"] += 1
            report["errors"].append(msg)
    log_.save()
    return report

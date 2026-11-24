"""End-to-end offline pipeline test with synthetic data, plus cache, provider-failure and alert tests."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from pipeline import telegram
from pipeline.config import Settings
from pipeline.providers.base import validate_ohlcv
from pipeline.run import PriceCache, run
from tests.fakes import FakeProvider, fake_master

NOW = datetime(2026, 11, 24, 14, 0, tzinfo=timezone.utc)
NEWS = [{"headline": "Testcompany B Industries bags order worth Rs 1,200 crore from Railways", "url": "https://example.com/a",
         "source": "NSE Corporate Announcements", "official": True, "published": "2026-11-24T10:00:00+05:30", "_desc": ""},
        {"headline": "SEBI imposes penalty on Testcompany C Industries", "url": "https://example.com/b", "source": "Mint",
         "official": False, "published": "2026-11-24T11:00:00+05:30", "_desc": ""}]


def _no_nan(o):
    if isinstance(o, dict):
        return all(_no_nan(v) for v in o.values())
    if isinstance(o, list):
        return all(_no_nan(v) for v in o)
    return not (isinstance(o, float) and (math.isnan(o) or math.isinf(o)))


@pytest.fixture(scope="module")
def pipeline_out(tmp_path_factory):
    root = tmp_path_factory.mktemp("run")
    s = Settings.load()
    s.output_dir, s.cache_dir, s.state_dir = root / "data", root / "cache", root / "data" / "state"
    for d in (s.output_dir, s.cache_dir, s.state_dir):
        Path(d).mkdir(parents=True, exist_ok=True)
    s.gate_min_samples = 500
    s.telegram_token = s.telegram_chat_id = None
    master = fake_master(12)
    prov = FakeProvider(list(master.yahoo_nse) + ["^NSEI", "^BSESN"], n=800, end="2026-11-24")
    status = run(s, provider=prov, master_override=master, news_items_override=NEWS, now=NOW)
    return s, status, master, prov


def test_all_output_files_exist_and_are_valid_json(pipeline_out):
    s, status, master, _ = pipeline_out
    out = Path(s.output_dir)
    for f in ("status.json", "overview.json", "scanner.json", "news.json", "model.json", "backtest.json", "instruments.json"):
        data = json.loads((out / f).read_text(encoding="utf-8"))
        assert _no_nan(data), f
    assert len(list((out / "stocks").glob("*.json"))) == len(master)
    assert status["state"] == "ok"
    assert status["market_date"] == "2026-11-24"


def test_failed_tickers_are_reported_not_hidden(pipeline_out):
    _, status, _, _ = pipeline_out
    p = status["steps"]["prices"]
    assert p["failed"] > 0                       # sector indices unknown to the fake provider
    assert "^CNXIT" in p["failed_examples"]
    ov = json.loads((Path(pipeline_out[0].output_dir) / "overview.json").read_text())
    assert any(not i["available"] for i in ov["indices"])


def test_probabilities_sum_to_100_and_labels_valid(pipeline_out):
    s = pipeline_out[0]
    sc = json.loads((Path(s.output_dir) / "scanner.json").read_text())
    for row in sc["rows"]:
        for h, v in row["horizons"].items():
            assert v["label"] in ("bullish", "bearish", "neutral", "insufficient")
            if v["p"]:
                assert sum(v["p"].values()) == pytest.approx(100.0, abs=1e-6)
            else:
                assert v["label"] == "insufficient"


def test_data_type_is_never_live(pipeline_out):
    s = pipeline_out[0]
    d = json.loads(next((Path(s.output_dir) / "stocks").glob("*.json")).read_text())
    assert "not real-time" in d["quality"]["data_type"]
    assert d["recommendation"]["intraday"]["label"] == "insufficient"


def test_news_processed_and_rerun_does_not_duplicate(pipeline_out):
    s, _, master, prov = pipeline_out
    news = json.loads((Path(s.output_dir) / "news.json").read_text())["items"]
    assert len(news) == 2
    order = next(n for n in news if n["category"] == "order_win")
    assert order["symbol"] == "TEST01" and order["verified"]
    status2 = run(s, provider=prov, master_override=master, news_items_override=NEWS, now=NOW)
    assert status2["steps"]["news"]["new"] == 0
    assert status2["steps"]["news"]["stored"] == 2


def test_telegram_not_configured_is_reported(pipeline_out):
    assert pipeline_out[1]["steps"]["telegram"]["configured"] is False


def test_price_cache_detects_split_and_refetches(tmp_path):
    prov = FakeProvider(["A.NS"], n=300, end="2026-11-24")
    cache = PriceCache(tmp_path)
    first, _ = cache.update(prov, ["A.NS"], 5)
    assert len(first["A.NS"]) == 300
    # simulate a 1:2 split: provider history is now re-based
    prov.data["A.NS"][["open", "high", "low", "close", "adj_close"]] /= 2
    second, _ = cache.update(prov, ["A.NS"], 5)
    assert second["A.NS"]["close"].iloc[0] == pytest.approx(first["A.NS"]["close"].iloc[0] / 2)


def test_provider_failure_falls_back_to_cache(tmp_path):
    prov = FakeProvider(["A.NS"], n=300, end="2026-11-24")
    cache = PriceCache(tmp_path)
    cache.update(prov, ["A.NS"], 5)
    prov.data = {}  # provider now returns nothing
    out, meta = cache.update(prov, ["A.NS"], 5)
    assert len(out["A.NS"]) == 300
    assert "cached" in meta["A.NS"]["provider_issue"]


def test_validate_ohlcv_removes_impossible_rows_and_reports():
    df = pd.DataFrame({"open": [10, 10, None], "high": [11, 9, 11], "low": [9, 9.5, 9], "close": [10.5, 10, 10],
                       "adj_close": [10.5, 10, 10], "volume": [100, 100, 100]}, index=pd.bdate_range("2026-01-01", periods=3))
    clean, issues = validate_ohlcv(df)
    assert len(clean) == 1
    assert any("inconsistent" in i for i in issues)


def test_alert_dedup(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(telegram, "send", lambda tok, chat, text: (sent.append(text) or True, "sent"))
    s = Settings.load()
    s.telegram_token, s.telegram_chat_id = "x", "y"
    news = [{"id": "n1", "category": "negative_event", "category_label": "Negative development", "symbol": "X",
             "headline": "SEBI penalty <b>", "source": "Mint", "verified": False, "importance": 85, "sentiment": -0.8,
             "url": "https://e.com", "published": "2026-11-24T10:00:00+05:30", "order_analysis": None}]
    r1 = telegram.dispatch(s, news, [], {"n1"}, tmp_path)
    r2 = telegram.dispatch(s, news, [], {"n1"}, tmp_path)
    assert r1["sent"] == 1 and r2["sent"] == 0
    assert "&lt;b&gt;" in sent[0] and "not advice" in sent[0]


def test_alert_send_failure_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(telegram, "send", lambda *a: (False, "HTTP 401"))
    s = Settings.load()
    s.telegram_token, s.telegram_chat_id = "x", "y"
    news = [{"id": "n2", "category": "negative_event", "category_label": "Neg", "symbol": "X", "headline": "h",
             "source": "s", "verified": True, "importance": 90, "sentiment": -1, "url": "https://e.com",
             "published": "2026-11-24", "order_analysis": None}]
    r = telegram.dispatch(s, news, [], {"n2"}, tmp_path)
    assert r["failed"] == 1 and r["errors"] == ["HTTP 401"]
    # failed alerts are NOT marked as sent, so they are retried next run
    assert telegram.AlertLog(Path(tmp_path) / "alerts_sent.json").sent == {}

from datetime import datetime, timezone

import pytest

from pipeline import news
from tests.fakes import fake_master

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Testcompany B Industries bags order worth Rs 1,200 crore</title><link>https://example.com/a?utm=x</link>
<pubDate>Mon, 24 Nov 2026 10:00:00 +0530</pubDate><description>&lt;p&gt;Order from Railways to be executed within 24 months&lt;/p&gt;</description></item>
<item><title>Markets end flat</title><link>https://example.com/b</link><pubDate>bad date</pubDate></item>
<item><title></title><link>https://example.com/c</link></item>
</channel></rss>"""


def test_parse_rss_handles_bad_dates_and_empty_titles():
    items = news.parse_rss(RSS, "Test", False)
    assert len(items) == 2
    assert items[0]["published"].startswith("2026-11-24T10:00")
    assert items[1]["published"] is None
    assert "Railways" in items[0]["_desc"]


@pytest.mark.parametrize("text,cat", [
    ("BEL secures defence order worth Rs 500 crore", "order_win"),
    ("RVNL emerges lowest bidder for railway project", "order_win"),
    ("Q2 net profit jumps 35% YoY", "results_positive"),
    ("Net profit falls 20% on weak demand", "results_negative"),
    ("SEBI imposes penalty on promoters", "negative_event"),
    ("Statutory auditor resigns citing concerns", "negative_event"),
    ("Board approves share buyback at Rs 1,500", "corporate_action_positive"),
    ("Company to acquire 51% stake in startup", "business_development"),
    ("USFDA approval for generic drug", "govt_regulatory"),
    ("Shares hit upper circuit on heavy volume", "market_trigger"),
])
def test_classification(text, cat):
    assert news.classify(text)[0] == cat


def test_negative_event_wins_over_positive_words():
    assert news.classify("Profit jumps but SEBI orders forensic probe")[0] == "negative_event"


@pytest.mark.parametrize("text,crore", [
    ("order worth Rs 1,200 crore", 1200), ("₹500 cr contract", 500), ("Rs. 75 lakh", 0.75),
    ("INR 2 lakh crore plan", 200000), ("$50 million deal", 50e6 * 84 / 1e7), ("Rs 300 million", 30),
])
def test_amount_extraction(text, crore):
    a = news.extract_amounts(text, 84.0)
    assert a and a[0]["inr_crore"] == pytest.approx(crore, rel=1e-6)


def test_ambiguous_currency_is_skipped():
    assert news.extract_amounts("sold 5 million units", 84.0) == []


def test_duration_and_order_ratio():
    assert news.extract_duration_months("to be executed within 24 months") == 24
    assert news.extract_duration_months("over 2 years") == 24
    oa = news.order_analysis(1200, 4000e7, 24)
    assert oa["order_size_ratio_pct"] == pytest.approx(30)
    assert oa["annualised_ratio_pct"] == pytest.approx(15)
    assert oa["materiality"] == "high"
    assert news.order_analysis(1200, None, None)["order_size_ratio_pct"] is None


def test_company_matching_and_no_false_match_on_common_words():
    m = news.CompanyMatcher(fake_master(5))
    hit = m.match("Testcompany B Industries bags order")
    assert hit[0]["symbol"] == "TEST01"
    assert m.match("Indian markets rally; Nifty at record")  == []
    assert m.match("anything", bse_code="500003")[0]["symbol"] == "TEST03"
    assert m.match("TEST04 shares surge")[0]["symbol"] == "TEST04"


def test_sentiment_negation():
    assert news.sentiment("profit rises", "other") > 0
    assert news.sentiment("profit does not rise, no growth", "other") < 0.34


def test_process_dedupes_and_flags_repeats():
    m = news.CompanyMatcher(fake_master(5))
    now = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
    items = [
        {"headline": "Testcompany B Industries bags order worth Rs 1,200 crore from Railways", "url": "https://a.com/1",
         "source": "A", "official": False, "published": "2026-11-24T10:00:00+05:30", "_desc": ""},
        {"headline": "Testcompany B Industries bags order worth Rs 1,200 crore from Railways!", "url": "https://b.com/2",
         "source": "NSE", "official": True, "published": "2026-11-24T10:05:00+05:30", "_desc": ""},
        {"headline": "Testcompany B Industries bags order worth Rs 1,200 crore from Railways", "url": "https://a.com/1/",
         "source": "A", "official": False, "published": "2026-11-24T10:00:00+05:30", "_desc": ""},
    ]
    hist = news.process(items, m, [], {"TEST01": 4000e7}, 84.0, now)
    assert len(hist) == 1
    rec = hist[0]
    assert rec["verified"] is True and rec["also_reported_by"] == ["NSE"]
    assert rec["order_analysis"]["order_size_ratio_pct"] == pytest.approx(30)
    assert "explain_kn" in rec and rec["explain_kn"]
    again = news.process([{**items[0], "url": "https://c.com/3", "published": "2026-11-20T10:00:00+05:30",
                           "headline": "Testcompany B Industries bags another order from Railways"}], m, hist, {}, 84.0, now)
    newer = [h for h in again if h["url"] == "https://c.com/3"]
    assert newer and newer[0]["repeat_of"] == rec["id"]


def test_sentiment_by_symbol_counts_events():
    now = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
    hist = [{"symbol": "X", "published": "2026-11-24T10:00:00+05:30", "importance": 80, "sentiment": -0.8, "category": "negative_event"},
            {"symbol": "X", "published": "2026-10-01T10:00:00+05:30", "importance": 80, "sentiment": 0.8, "category": "order_win"}]
    s = news.news_sentiment_by_symbol(hist, 7, now)
    assert s["X"]["count"] == 1 and s["X"]["negative_events"] == 1 and s["X"]["score"] < 0

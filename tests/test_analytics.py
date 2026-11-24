"""Quant, fundamentals, calendar, backtest, ML and recommendation tests."""
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import backtest, fundamentals, indicators, marketcal, ml, quant, recommend
from pipeline.config import IST, Settings
from tests.fakes import FakeProvider, synthetic_ohlcv


# ------------------------------------------------------------------ quant
def test_wilson_interval_known_value():
    lo, hi = quant.wilson_interval(50, 100)
    assert lo == pytest.approx(0.4038, abs=1e-3) and hi == pytest.approx(0.5962, abs=1e-3)


def test_max_drawdown_simple():
    s = pd.Series([100, 120, 90, 130, 117], index=pd.bdate_range("2026-01-01", periods=5), dtype=float)
    dd = quant.max_drawdown(s)
    assert dd["max_drawdown_pct"] == pytest.approx(-25.0)
    assert dd["current_drawdown_pct"] == pytest.approx(-10.0)


def test_var_cvar_ordering():
    r = pd.Series(np.random.default_rng(0).standard_t(3, 3000) * 0.01)
    v = quant.var_cvar(r)
    assert v["historical_cvar_pct"] >= v["historical_var_pct"] > 0


def test_quant_analyse_outputs_are_descriptive():
    df = synthetic_ohlcv(800)
    q = quant.analyse(df["close"], synthetic_ohlcv(800, seed=50)["close"], 0.065, [2, 5])
    assert q["available"] and len(q["horizons"]) == 2
    h = q["horizons"][0]
    assert 0 <= h["p_positive_ci95"][0] <= h["p_positive"] <= h["p_positive_ci95"][1] <= 1
    assert "not a forecast" in h["note"]


# ------------------------------------------------------------------ fundamentals
def test_fundamental_ratios_and_score():
    raw = FakeProvider(["X.NS"]).fundamentals("X.NS")
    f = fundamentals.analyse(raw, price=500.0, sector="Capital Goods")
    r = f["ratios"]
    assert r["pe"]["value"] == pytest.approx(20.0)
    assert r["roe"]["value"] == pytest.approx(3.5e10 / 2.8e11 * 100, rel=1e-4)
    assert r["debt_to_equity"]["value"] == pytest.approx(1e11 / 2.8e11, abs=1e-4)
    assert r["interest_coverage"]["value"] == pytest.approx(12.0)
    assert r["quick_ratio"]["value"] == pytest.approx((2.5e11 - 5e10) / 1.5e11, abs=1e-4)
    assert f["years"][0]["fcf"] == pytest.approx(4e10 - 1.5e10)
    assert f["scorecard"]["evaluated"] >= fundamentals.MIN_CHECKS
    assert f["scorecard"]["label"] in ("Strong", "Moderate", "Weak")


def test_red_flags_detected():
    years = [{"revenue": 130, "ocf": -5, "total_debt": 200, "ebitda": 10, "ebit": 8, "interest_expense": 6,
              "receivables": 80, "inventory": 70, "net_income": -1},
             {"revenue": 100, "ocf": 10, "total_debt": 100, "ebitda": 15, "ebit": 12, "interest_expense": 4,
              "receivables": 40, "inventory": 35, "net_income": 5}]
    flags = {f["flag"] for f in fundamentals.red_flags(years)}
    assert {"Revenue growth without cash-flow growth", "Rising debt", "Falling margins", "Weak interest coverage",
            "Receivables growing faster than revenue", "Inventory accumulation", "Net loss in latest year"} <= flags


def test_never_healthy_from_one_ratio():
    raw = {"info": {}, "income": {"2025-03-31": {"Total Revenue": 100.0, "Net Income": 20.0}}, "balance": {}, "cashflow": {}}
    f = fundamentals.analyse(raw, 10.0)
    assert f["scorecard"]["label"] == "Insufficient data"


def test_missing_fundamentals_reported():
    assert fundamentals.analyse({}, 10.0)["available"] is False


# ------------------------------------------------------------------ market calendar
def test_calendar_weekend_holiday_timezone():
    hol = {date(2026, 11, 24)}
    # Tuesday 24 Nov is a holiday -> expected session is Monday 23 Nov
    assert marketcal.expected_last_session(datetime(2026, 11, 24, 18, 0, tzinfo=IST), hol) == date(2026, 11, 23)
    # Monday before data is ready (10:00 IST) -> previous Friday
    assert marketcal.expected_last_session(datetime(2026, 11, 23, 10, 0, tzinfo=IST), set()) == date(2026, 11, 20)
    # 12:00 UTC is 17:30 IST -> today's session data should exist
    assert marketcal.expected_last_session(datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc), set()) == date(2026, 11, 23)
    assert marketcal.sessions_between(date(2026, 11, 20), date(2026, 11, 23), set()) == 1
    assert not marketcal.is_stale(date(2026, 11, 20), datetime(2026, 11, 23, 18, 0, tzinfo=IST), set())
    assert marketcal.is_stale(date(2026, 11, 17), datetime(2026, 11, 23, 18, 0, tzinfo=IST), set())


# ------------------------------------------------------------------ ML
def _panel(ar, n_stocks=24, n=800, horizons=(2,)):
    bench = synthetic_ohlcv(n, seed=999)["close"]
    stocks = {}
    for i in range(n_stocks):
        df = synthetic_ohlcv(n, seed=i, ar=ar)
        stocks[f"S{i}"] = (df, indicators.compute_all(df, bench))
    return ml.build_panel(stocks, bench, list(horizons), 0.5, 0.004)


def test_labels_are_three_exclusive_classes_and_future_is_masked():
    c = synthetic_ohlcv(100)["close"]
    y, fwd = ml.make_labels(c, 5, 0.5, 0.004)
    assert set(y.dropna().unique()) <= {0.0, 1.0, 2.0}
    assert y.iloc[-5:].isna().all()          # unknown future -> no label


def test_temperature_scaling_and_probability_sum():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 3, 5000)
    over = np.full((5000, 3), 0.05)
    over[np.arange(5000), rng.integers(0, 3, 5000)] = 0.9   # overconfident noise
    T = ml.fit_temperature(over, y)
    cal = ml.apply_temperature(over, T)
    assert T > 1
    np.testing.assert_allclose(cal.sum(axis=1), 1.0)
    assert ml.log_loss(cal, y) < ml.log_loss(over, y)


@pytest.fixture(scope="module")
def settings_small(tmp_path_factory):
    s = Settings.load()
    s.gate_min_samples = 500
    s.cache_dir = tmp_path_factory.mktemp("cache")
    return s


def test_gate_rejects_random_walk(settings_small):
    res = ml.run(_panel(0.0), [2], Path(settings_small.cache_dir) / "rw", settings_small, force=True)
    rep = res[2]["report"]
    assert rep["gate"]["passed"] is False
    assert not any(t.get("validated") for t in rep.get("thresholds", {}).values())


def test_gate_accepts_real_signal(settings_small):
    res = ml.run(_panel(-0.25), [2], Path(settings_small.cache_dir) / "sig", settings_small, force=True)
    rep = res[2]["report"]
    assert rep["gate"]["passed"] is True
    assert rep["gate"]["bootstrap"]["lower_5pct"] > 0
    assert res[2]["bundle"] is not None
    assert pd.Timestamp(res[2]["oos"]["date"].min()) > pd.Timestamp(_panel(-0.25)["date"].min())


def test_walk_forward_has_purge_gap():
    panel = _panel(0.0, n_stocks=6, horizons=(5,))
    oos, metrics = ml.walk_forward(panel, 5, ml.FEATURES[:6], min_train_days=400, test_days=100, min_train_rows=500)
    assert "error" not in metrics and metrics["_folds"] >= 2
    dates = sorted(panel["date"].unique())
    pos = {d: i for i, d in enumerate(dates)}
    for (_, fold) in oos.groupby("train_end"):
        gap = pos[fold["date"].min()] - pos[fold["train_end"].iloc[0]]
        assert gap > 5, "training data must end more than h sessions before the test period"


# ------------------------------------------------------------------ backtest
def test_round_trip_cost_reasonable():
    c = Settings.load().costs
    cost = backtest.round_trip_cost(c)
    assert 0.0035 < cost < 0.006   # ~0.4-0.5 % for delivery trades incl. slippage


def test_backtest_on_toy_predictions():
    dates = pd.bdate_range("2025-01-01", periods=40)
    rows = []
    for d in dates:
        rows.append({"symbol": "A", "date": d, "y_2": 2, "trade_2": 0.02, "fwd_2": 0.02, "m_bear": 0.1, "m_neu": 0.2, "m_bull": 0.7})
        rows.append({"symbol": "B", "date": d, "y_2": 0, "trade_2": -0.01, "fwd_2": -0.01, "m_bear": 0.7, "m_neu": 0.2, "m_bull": 0.1})
    r = backtest.run(pd.DataFrame(rows), 2, "m", 0.6, Settings.load().costs)
    assert r["available"] and r["trades"] == 40
    assert r["win_rate_pct"] == 100.0
    assert r["strategy"]["total_return_pct"] > r["benchmark_equal_weight_universe"]["total_return_pct"]
    assert r["bearish_signal_check"]["avg_forward_return_pct"] == pytest.approx(-1.0)


def test_backtest_without_threshold_is_unavailable():
    assert backtest.run(pd.DataFrame(), 2, "m", None, {})["available"] is False


# ------------------------------------------------------------------ recommendation
def test_recommendation_probabilities_sum_to_100_and_insufficient_paths():
    df = synthetic_ohlcv(400)
    ind = indicators.compute_all(df)
    row = {"symbol": "S", "name": "S Ltd", "exchanges": "NSE"}
    quality = {"last_date": "2026-11-24", "stale": False, "liquid": True, "bars": 400, "data_type": "EOD"}
    rep_ok = {"gate": {"passed": True}, "selected_model": "m",
              "thresholds": {"bullish": {"threshold": 0.45, "validated": True, "holdout_lift": 1.3},
                             "bearish": {"threshold": 0.45, "validated": True, "holdout_lift": 1.3}}}
    out = recommend.assess(row, df, ind, quality, {"available": False}, {"horizons": []}, None,
                           {5: {"report": rep_ok, "probs": {"S": [0.1234, 0.3333, 0.5433]}}}, {}, {"support": [], "resistance": []})
    h = out["horizons"][0]
    assert h["label"] == "bullish"
    assert sum(h["probabilities"].values()) == pytest.approx(100.0, abs=1e-9)
    # failed gate -> insufficient
    bad = recommend.assess(row, df, ind, quality, {"available": False}, {"horizons": []}, None,
                           {5: {"report": {"gate": {"passed": False, "reasons": ["x"]}}, "probs": {}}}, {}, {})
    assert bad["horizons"][0]["label"] == "insufficient"
    assert bad["horizons"][0]["message"] == recommend.INSUFFICIENT
    # stale data -> insufficient even with a validated model
    stale = recommend.assess(row, df, ind, {**quality, "stale": True}, {"available": False}, {"horizons": []}, None,
                             {5: {"report": rep_ok, "probs": {"S": [0.1, 0.2, 0.7]}}}, {}, {})
    assert stale["horizons"][0]["label"] == "insufficient"
    assert out["intraday"]["label"] == "insufficient"

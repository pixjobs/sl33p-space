"""Unit tests for the multi-night experiment engine (pure logic, no DB)."""

from db import experiments as ex


def test_finalize_reports_improvement():
    exp = {"label": "caffeine", "factor": "caffeine", "target_nights": 3,
           "baseline": {"avg_with": 2.5}}
    nights = [
        {"adhered": True, "rating": 4},
        {"adhered": True, "rating": 5},
        {"adhered": True, "rating": 4},
        {"adhered": False, "rating": 2},
    ]
    res = ex._finalize(exp, nights)
    assert res["adhered_avg"] > res["control_avg"]
    assert res["delta"] >= 0.5
    assert "helped" in res["conclusion"].lower()


def test_finalize_uses_historical_baseline_when_no_control():
    exp = {"label": "stress", "factor": "stress", "target_nights": 2,
           "baseline": {"avg_with": 4.0}}
    nights = [{"adhered": True, "rating": 4}, {"adhered": True, "rating": 4}]
    res = ex._finalize(exp, nights)
    # adhered avg 4.0 vs historical with-factor 4.0 -> little difference
    assert res["control_avg"] == 4.0
    assert abs(res["delta"]) < 0.5
    assert "little difference" in res["conclusion"].lower()


def test_propose_returns_none_without_data(monkeypatch):
    monkeypatch.setattr(ex, "get_active_experiment", lambda uid: None)
    insights = {"stats": {"avg_rating": None, "reviewed_sessions": 0},
                "factor_correlations": []}
    assert ex.propose_experiment("u", insights) is None


def test_propose_picks_dragging_factor(monkeypatch):
    monkeypatch.setattr(ex, "get_active_experiment", lambda uid: None)
    monkeypatch.setattr(ex, "_recently_declined_factors", lambda uid: set())
    monkeypatch.setattr(ex, "_factor_baseline",
                        lambda uid, f: {"avg_with": 2.5, "avg_without": 4.0,
                                        "n_with": 3, "n_without": 5})
    insights = {
        "stats": {"avg_rating": 3.6, "reviewed_sessions": 8},
        "factor_correlations": [
            {"factor": "exercise", "sessions": 4, "avg_rating": 4.2},
            {"factor": "caffeine", "sessions": 3, "avg_rating": 2.5},
        ],
    }
    prop = ex.propose_experiment("u", insights)
    assert prop is not None
    assert prop["factor"] == "caffeine"
    assert prop["direction"] == "avoid"
    assert prop["target_nights"] == 3

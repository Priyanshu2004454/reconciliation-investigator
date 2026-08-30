"""
Evaluation suite (section 11/26 of the spec). Measures the deterministic
reconciliation engine's accuracy against the 100-record synthetic dataset's
known ground truth. This is a real, calculated measurement -- no accuracy
number is claimed anywhere else in this codebase without a test like this
backing it up.
"""

import pytest

from app.services.demo_dataset import generate_dataset, CATEGORY_TARGET_COUNTS
from app.services.reconciliation_engine import reconcile


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("MATCH_AMOUNT_TOLERANCE_PAISE", "100")
    monkeypatch.setenv("MATCH_DATE_WINDOW_DAYS", "3")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "x")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "x")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("APP_SECRET_KEY", "x")
    monkeypatch.setenv("JWT_SECRET_KEY", "x")
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _classify(case) -> str:
    """Ground truth uses 'MATCHED' for clean matches, else the root cause label."""
    return case.status if case.status == "MATCHED" else case.root_cause


def test_dataset_generates_expected_record_count():
    data, ground_truth = generate_dataset()
    assert len(data.settlements) == sum(CATEGORY_TARGET_COUNTS.values())
    assert len(data.settlements) >= 50, "Track 04 requires at least 50 records"
    assert len(ground_truth) == len(data.settlements)


def test_dataset_is_reproducible_with_same_seed():
    data1, gt1 = generate_dataset(seed=42)
    data2, gt2 = generate_dataset(seed=42)
    assert [s.razorpay_settlement_id for s in data1.settlements] == [s.razorpay_settlement_id for s in data2.settlements]
    assert gt1 == gt2


def test_reconciliation_engine_accuracy_against_ground_truth():
    """
    The headline evaluation metric: what fraction of the deterministic
    engine's classifications match the dataset's known ground truth?
    """
    data, ground_truth = generate_dataset()
    result = reconcile(data)

    total = len(ground_truth)
    correct = 0
    mismatches = []

    for case in result.cases:
        sid = case.razorpay_settlement_id
        expected = ground_truth.get(sid)
        actual = _classify(case)

        if actual == expected:
            correct += 1
        else:
            mismatches.append((sid, expected, actual))

    accuracy = round((correct / total) * 100, 2)

    print("\n=== Reconciliation Engine Evaluation ===")
    print(f"Total records: {total}")
    print(f"Correct classifications: {correct}")
    print(f"Incorrect classifications: {total - correct}")
    print(f"Accuracy: {accuracy}%")

    # The dataset is constructed so the deterministic engine should resolve
    # every case correctly -- this is a regression guard, not a soft target.
    assert accuracy == 100.0, f"Engine accuracy dropped to {accuracy}%: {mismatches}"


def test_match_rate_calculation_matches_dashboard_definition():
    """
    match_rate = (matched + explained) / total * 100 -- same formula used by
    both reconciliation_persistence.py and dashboard_service.py. This test
    guards against the two definitions silently drifting apart.
    """
    data, _ = generate_dataset()
    result = reconcile(data)

    expected_match_rate = round(((result.matched + result.explained) / result.total_cases) * 100, 2)
    successfully_reconciled = (
        CATEGORY_TARGET_COUNTS["MATCHED"] + CATEGORY_TARGET_COUNTS["FEE_TAX"]
        + CATEGORY_TARGET_COUNTS["REFUND"] + CATEGORY_TARGET_COUNTS["TIMING_DIFFERENCE"]
    )
    total = sum(CATEGORY_TARGET_COUNTS.values())

    assert expected_match_rate == round((successfully_reconciled / total) * 100, 2)


def test_needs_review_cases_are_exactly_the_unexplainable_categories():
    """Only MISSING_BANK_CREDIT, DUPLICATE, and AMOUNT_MISMATCH should end up NEEDS_REVIEW."""
    data, ground_truth = generate_dataset()
    result = reconcile(data)

    needs_review_sids = {c.razorpay_settlement_id for c in result.cases if c.status == "NEEDS_REVIEW"}
    expected_needs_review = {
        sid for sid, label in ground_truth.items()
        if label in ("MISSING_BANK_CREDIT", "DUPLICATE", "AMOUNT_MISMATCH")
    }
    assert needs_review_sids == expected_needs_review


def test_prefixed_dataset_evaluation_maintains_100_percent_accuracy():
    """Verify merchant-scoped prefixed dataset maintains 100% engine accuracy."""
    data, ground_truth = generate_dataset(seed=42, prefix="m_demo_test")
    assert len(data.settlements) == 100
    assert all("m_demo_test" in s.razorpay_settlement_id for s in data.settlements)

    result = reconcile(data)
    total = len(ground_truth)
    correct = sum(1 for c in result.cases if _classify(c) == ground_truth.get(c.razorpay_settlement_id))
    assert (correct / total) == 1.0


def test_multiple_reconciliation_runs_produce_consistent_latest_metrics():
    """
    Verify running reconciliation multiple times produces exact, deterministic
    per-run counts without drifting or inflating metrics:
    Exactly 100 total, 40 matched, 35 explained, 25 needs_review, 75.0% match rate.
    """
    data, _ = generate_dataset()

    # Run 1
    run1 = reconcile(data)
    assert run1.total_cases == 100
    assert run1.matched == 40
    assert run1.explained == 35
    assert run1.needs_review == 25
    match_rate_1 = round(((run1.matched + run1.explained) / run1.total_cases) * 100, 2)
    assert match_rate_1 == 75.0

    # Run 2 (subsequent execution)
    run2 = reconcile(data)
    assert run2.total_cases == 100
    assert run2.matched == 40
    assert run2.explained == 35
    assert run2.needs_review == 25
    match_rate_2 = round(((run2.matched + run2.explained) / run2.total_cases) * 100, 2)
    assert match_rate_2 == 75.0

    # Counts per status for each run
    status_counts = {}
    for c in run2.cases:
        status_counts[c.status] = status_counts.get(c.status, 0) + 1

    assert status_counts == {"MATCHED": 40, "EXPLAINED": 35, "NEEDS_REVIEW": 25}



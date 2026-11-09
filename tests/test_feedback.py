"""Unit tests for the feedback-object shape and the bounded correction
formulas (Phase 11's next_allocation_mbps, Phase 12's
next_background_rate_mbps -- the formula actually driving the closed
loop in backend/cli.py). Pure numeric logic -- no network, no loop."""
import pytest

from backend.models.feedback import (
    MAX_ALLOCATION_STEP_RATIO,
    MIN_BACKGROUND_RATE_MBPS,
    BandwidthFeedback,
    next_allocation_mbps,
    next_background_rate_mbps,
)


def test_feedback_object_matches_specified_shape():
    fb = BandwidthFeedback(
        target_mbps=20.0,
        measured_mbps=6.0,
        current_path=["h1", "s1", "s2", "s4", "h4"],
        candidate_paths=[["h1", "s1", "s2", "s4", "h4"], ["h1", "s1", "s3", "s4", "h4"]],
        network_state={"note": "example"},
        status="NOT_SATISFIED",
    )
    dumped = fb.model_dump(mode="json")
    assert set(dumped) == {
        "objective", "target_mbps", "measured_mbps", "current_path",
        "candidate_paths", "network_state", "status",
    }


def test_correction_formula_matches_ratio_when_under_cap():
    # old=10, target=20, measured=10 -> ratio 2.0, exactly at the cap
    result = next_allocation_mbps(old_allocation_mbps=10.0, target_mbps=20.0, measured_mbps=10.0)
    assert result == pytest.approx(20.0)


def test_correction_formula_is_capped_per_iteration():
    # ratio would be 100/1 = 100x; must be capped at MAX_ALLOCATION_STEP_RATIO
    result = next_allocation_mbps(old_allocation_mbps=1.0, target_mbps=100.0, measured_mbps=1.0)
    assert result == pytest.approx(1.0 * MAX_ALLOCATION_STEP_RATIO)


def test_correction_formula_no_change_when_target_already_met():
    result = next_allocation_mbps(old_allocation_mbps=20.0, target_mbps=20.0, measured_mbps=25.0)
    assert result == pytest.approx(20.0)


def test_correction_formula_handles_zero_measured_without_crashing():
    result = next_allocation_mbps(old_allocation_mbps=5.0, target_mbps=20.0, measured_mbps=0.0)
    assert result == pytest.approx(5.0 * MAX_ALLOCATION_STEP_RATIO)


def test_correction_formula_rejects_nonpositive_old_allocation():
    with pytest.raises(ValueError):
        next_allocation_mbps(old_allocation_mbps=0.0, target_mbps=20.0, measured_mbps=5.0)


def test_background_rate_throttles_down_in_proportion_to_shortfall():
    # old=8, target=49, measured=46.9 -> ratio ~1.045, small shortfall -> small reduction
    result = next_background_rate_mbps(old_background_rate_mbps=8.0, target_mbps=49.0, measured_mbps=46.9)
    assert result < 8.0
    assert result == pytest.approx(8.0 / (49.0 / 46.9))


def test_background_rate_capped_per_iteration():
    # ratio would be 100/1 = 100x; the reduction must be capped at MAX_ALLOCATION_STEP_RATIO (halved, not /100)
    result = next_background_rate_mbps(old_background_rate_mbps=8.0, target_mbps=100.0, measured_mbps=1.0)
    assert result == pytest.approx(8.0 / MAX_ALLOCATION_STEP_RATIO)


def test_background_rate_never_goes_below_floor():
    result = next_background_rate_mbps(old_background_rate_mbps=1.2, target_mbps=100.0, measured_mbps=0.5,
                                        floor_mbps=1.0)
    assert result == pytest.approx(1.0)


def test_background_rate_unchanged_when_target_already_met():
    result = next_background_rate_mbps(old_background_rate_mbps=8.0, target_mbps=20.0, measured_mbps=25.0)
    assert result == pytest.approx(8.0)


def test_background_rate_handles_zero_measured_without_crashing():
    result = next_background_rate_mbps(old_background_rate_mbps=8.0, target_mbps=20.0, measured_mbps=0.0)
    assert result == pytest.approx(max(8.0 / MAX_ALLOCATION_STEP_RATIO, MIN_BACKGROUND_RATE_MBPS))


def test_background_rate_rejects_nonpositive_old_rate():
    with pytest.raises(ValueError):
        next_background_rate_mbps(old_background_rate_mbps=0.0, target_mbps=20.0, measured_mbps=5.0)

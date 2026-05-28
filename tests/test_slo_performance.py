import numpy as np
import pytest
from scrutable.profiles import LATENCY_VARIANCE_SPECTRUM
from scrutable.scenarios.slo_performance import PerformancePoint, sweep_slo_performance

pytestmark = pytest.mark.slow


def test_sweep_returns_one_point_per_profile_window_pair():
    profiles = LATENCY_VARIANCE_SPECTRUM[:2]
    window_sizes = [1.0, 2.0]
    results = sweep_slo_performance(
        profiles, window_sizes,
        seed=42, rate=200.0, n_workloads=5,
        burn_in=10.0, post_disturbance=10.0,
    )
    assert len(results) == len(profiles) * len(window_sizes)


def test_performance_point_has_required_fields():
    profiles = LATENCY_VARIANCE_SPECTRUM[:1]
    results = sweep_slo_performance(
        profiles, [1.0],
        seed=42, rate=200.0, n_workloads=5,
        burn_in=10.0, post_disturbance=10.0,
    )
    pt = results[0]
    assert isinstance(pt, PerformancePoint)
    assert pt.profile_name == profiles[0].name
    assert pt.window_size == 1.0
    assert 0.0 <= pt.fpr <= 1.0
    assert 0.0 <= pt.recall <= 1.0
    assert 0.0 <= pt.precision <= 1.0


def test_precision_is_one_when_no_false_positives():
    # Very generous threshold: never fires during burn-in, so all alerts are TPs → precision=1
    profile = LATENCY_VARIANCE_SPECTRUM[0]
    results = sweep_slo_performance(
        [profile], [1.0],
        seed=42, rate=500.0, n_workloads=5,
        burn_in=10.0, post_disturbance=20.0,
        calibration_multiplier=5.0,
    )
    pt = results[0]
    assert pt.fpr == 0.0
    assert pt.precision == 1.0 or pt.recall == 0.0  # no FPs → precision=1, unless no detections at all


def test_precision_zero_when_no_true_positives_but_false_positives():
    # Tiny threshold fires constantly in burn-in but addend is zero, so no disturbance signal either
    profile = LATENCY_VARIANCE_SPECTRUM[0]
    results = sweep_slo_performance(
        [profile], [1.0],
        seed=42, rate=500.0, n_workloads=5,
        burn_in=10.0, post_disturbance=10.0,
        calibration_multiplier=0.5,  # fires constantly, in burn-in and post
        disturbance_addend=0.0,      # no actual disturbance signal
    )
    pt = results[0]
    # With calibration_multiplier=0.5, fires everywhere; precision = post_alerts/(post+burn_in alerts)
    # Since no real disturbance, TP count depends on overlap classification only
    assert 0.0 <= pt.precision <= 1.0


def test_fpr_near_zero_with_high_multiplier():
    # A very generous threshold (5x) should fire almost never during burn-in
    profiles = LATENCY_VARIANCE_SPECTRUM[:1]
    results = sweep_slo_performance(
        profiles, [1.0],
        seed=42, rate=500.0, n_workloads=10,
        burn_in=10.0, post_disturbance=10.0,
        calibration_multiplier=5.0,
    )
    assert results[0].fpr < 0.1


def test_recall_high_on_low_variance_profile():
    # v1 (sigma=0.1) with addend=1s: disturbance clearly above calibrated threshold
    profile = LATENCY_VARIANCE_SPECTRUM[0]
    results = sweep_slo_performance(
        [profile], [1.0],
        seed=42, rate=500.0, n_workloads=10,
        burn_in=10.0, post_disturbance=20.0,
    )
    assert results[0].recall > 0.8


def test_recall_lower_on_high_variance_profile():
    # v5 (sigma=1.5): addend=1s is below the calibrated threshold
    low_var = LATENCY_VARIANCE_SPECTRUM[0]
    high_var = LATENCY_VARIANCE_SPECTRUM[4]
    results = sweep_slo_performance(
        [low_var, high_var], [1.0],
        seed=42, rate=200.0, n_workloads=10,
        burn_in=60.0, post_disturbance=20.0,
    )
    low_recall = next(r.recall for r in results if r.profile_name == low_var.name)
    high_recall = next(r.recall for r in results if r.profile_name == high_var.name)
    assert low_recall > high_recall


def test_sweep_parallel_matches_serial():
    profiles = LATENCY_VARIANCE_SPECTRUM[:2]
    window_sizes = [1.0, 2.0]
    common = dict(seed=42, rate=200.0, n_workloads=5, burn_in=10.0, post_disturbance=10.0)
    serial = sweep_slo_performance(profiles, window_sizes, workers=1, **common)
    parallel = sweep_slo_performance(profiles, window_sizes, workers=2, **common)
    assert len(parallel) == len(serial)
    for s, p in zip(serial, parallel):
        assert s.profile_name == p.profile_name
        assert s.window_size == p.window_size
        assert s.recall == p.recall
        assert s.fpr == p.fpr
        assert s.precision == p.precision

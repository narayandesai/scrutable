import numpy as np
import pytest
from scrutable.profiles import LATENCY_VARIANCE_SPECTRUM
from scrutable.scenarios.slo_performance import PerformancePoint, sweep_slo_performance


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

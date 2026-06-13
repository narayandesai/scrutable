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
        seed=42, total_rate=200.0, n_calibration_windows=5, post_disturbance=10.0,
    )
    assert len(results) == len(profiles) * len(window_sizes)


def test_performance_point_has_required_fields():
    profiles = LATENCY_VARIANCE_SPECTRUM[:1]
    results = sweep_slo_performance(
        profiles, [1.0],
        seed=42, total_rate=200.0, n_calibration_windows=10, post_disturbance=10.0,
    )
    pt = results[0]
    assert isinstance(pt, PerformancePoint)
    assert pt.profile_name == profiles[0].name
    assert pt.window_size == 1.0
    assert 0.0 <= pt.fpr <= 1.0
    assert 0.0 <= pt.recall <= 1.0
    assert 0.0 <= pt.precision <= 1.0


def test_performance_point_noise_and_signal_present():
    profiles = LATENCY_VARIANCE_SPECTRUM[:1]
    results = sweep_slo_performance(
        profiles, [1.0],
        seed=42, total_rate=200.0, n_calibration_windows=10, post_disturbance=10.0,
    )
    pt = results[0]
    assert hasattr(pt, "noise")
    assert hasattr(pt, "signal")
    assert 99.9 in pt.noise
    assert 99.9 in pt.signal
    assert pt.noise[99.9] is not None
    assert pt.signal[99.9] is not None


def test_noise_decreases_with_larger_window_for_stable_profile():
    # For a single-workload always-on profile, noise(P99.9) should fall as window grows
    # because it's purely estimator variance (1/sqrt(N events))
    profile = LATENCY_VARIANCE_SPECTRUM[0]  # v1: sigma=0.1, very stable
    results = sweep_slo_performance(
        [profile, profile], [1.0, 5.0],
        seed=42, total_rate=200.0, n_calibration_windows=30, post_disturbance=10.0,
    )
    noise_1s = results[0].noise[99.9]
    noise_5s = results[1].noise[99.9]
    assert noise_5s < noise_1s


def test_time_to_first_detection_near_window_size_for_strong_signal():
    # v1 (sigma=0.1): strong signal, first window after disturbance should fire
    profile = LATENCY_VARIANCE_SPECTRUM[0]
    window_size = 2.0
    results = sweep_slo_performance(
        [profile], [window_size],
        seed=42, total_rate=500.0, n_calibration_windows=5, post_disturbance=20.0,
    )
    pt = results[0]
    assert pt.time_to_first_detection is not None
    assert pt.time_to_first_detection <= window_size


def test_time_to_first_detection_none_iff_recall_zero():
    # Structural invariant: no detections ↔ time_to_first_detection is None.
    # Use tiny addend on high-variance profile; calibration anchored conservatively.
    profile = LATENCY_VARIANCE_SPECTRUM[4]  # sigma=1.5
    results = sweep_slo_performance(
        [profile], [1.0],
        seed=42, total_rate=200.0, n_calibration_windows=50, post_disturbance=20.0,
        disturbance_addend=0.001,
    )
    pt = results[0]
    if pt.recall == 0.0:
        assert pt.time_to_first_detection is None
    else:
        assert pt.time_to_first_detection is not None


def test_precision_high_when_signal_dominates_noise():
    # v1 with addend=0.3 and enough calibration: most fires are TPs, so precision is high.
    # With 100 calibration windows at target_fpr=0.001, at most ~1 FP per 100 burn-in windows.
    profile = LATENCY_VARIANCE_SPECTRUM[0]
    results = sweep_slo_performance(
        [profile], [1.0],
        seed=42, total_rate=500.0, n_calibration_windows=100, post_disturbance=20.0,
    )
    pt = results[0]
    assert pt.precision >= 0.9 or pt.recall == 0.0


def test_precision_in_bounds_when_threshold_fires_everywhere():
    # target_fpr=0.9 → threshold at 10th percentile of burn-in estimates → fires frequently
    profile = LATENCY_VARIANCE_SPECTRUM[0]
    results = sweep_slo_performance(
        [profile], [1.0],
        seed=42, total_rate=500.0, n_calibration_windows=10, post_disturbance=10.0,
        target_fpr=0.9, disturbance_addend=0.0,
    )
    pt = results[0]
    assert 0.0 <= pt.precision <= 1.0


def test_fpr_matches_target_fpr():
    # With enough calibration windows, in-sample FPR should be ≤ target_fpr by construction.
    profile = LATENCY_VARIANCE_SPECTRUM[0]
    results = sweep_slo_performance(
        [profile], [1.0],
        seed=42, total_rate=500.0, n_calibration_windows=100, post_disturbance=10.0,
        target_fpr=0.05,
    )
    assert results[0].fpr <= 0.05 + 1e-9


def test_recall_high_on_low_variance_profile():
    # v1 (sigma=0.1) with addend=0.3s: disturbance clearly above calibrated threshold
    profile = LATENCY_VARIANCE_SPECTRUM[0]
    results = sweep_slo_performance(
        [profile], [1.0],
        seed=42, total_rate=500.0, n_calibration_windows=10, post_disturbance=20.0,
    )
    assert results[0].recall > 0.8


def test_recall_lower_on_high_variance_profile():
    # v5 (sigma=1.5): addend=0.3s buried in estimator noise → lower recall than v1
    low_var = LATENCY_VARIANCE_SPECTRUM[0]
    high_var = LATENCY_VARIANCE_SPECTRUM[4]
    results = sweep_slo_performance(
        [low_var, high_var], [1.0],
        seed=42, total_rate=200.0, n_calibration_windows=60, post_disturbance=20.0,
    )
    low_recall = next(r.recall for r in results if r.profile_name == low_var.name)
    high_recall = next(r.recall for r in results if r.profile_name == high_var.name)
    assert low_recall > high_recall


def test_snr_is_dict_keyed_by_percentile():
    results = sweep_slo_performance(
        LATENCY_VARIANCE_SPECTRUM[:1], [1.0],
        seed=42, total_rate=200.0, n_calibration_windows=10, post_disturbance=10.0,
    )
    snr = results[0].snr
    assert isinstance(snr, dict)
    assert set(snr.keys()) == {50.0, 75.0, 90.0, 99.0, 99.9}


def test_snr_positive_at_p999_for_detectable_disturbance():
    results = sweep_slo_performance(
        LATENCY_VARIANCE_SPECTRUM[:1], [1.0],
        seed=42, total_rate=500.0, n_calibration_windows=20, post_disturbance=20.0,
        disturbance_addend=0.8,
    )
    assert results[0].snr[99.9] is not None
    assert results[0].snr[99.9] > 1.0


def test_snr_p999_lower_for_high_variance_profile():
    low_var = LATENCY_VARIANCE_SPECTRUM[0]
    high_var = LATENCY_VARIANCE_SPECTRUM[4]
    results = sweep_slo_performance(
        [low_var, high_var], [1.0],
        seed=42, total_rate=500.0, n_calibration_windows=30, post_disturbance=30.0,
        disturbance_addend=0.8,
    )
    snr_low = next(r.snr[99.9] for r in results if r.profile_name == low_var.name)
    snr_high = next(r.snr[99.9] for r in results if r.profile_name == high_var.name)
    assert snr_low is not None and snr_high is not None
    assert snr_low > snr_high


def test_snr_p50_exceeds_p999_for_additive_disturbance_on_high_variance_service():
    # Additive disturbance shifts all percentiles equally in absolute terms.
    # P50 has much less natural variance than P99.9, so SNR(P50) > SNR(P99.9).
    # This is the core claim: a P50 sensor detects what a P99.9 sensor misses.
    high_var = LATENCY_VARIANCE_SPECTRUM[4]   # sigma=1.5
    results = sweep_slo_performance(
        [high_var], [1.0],
        seed=42, total_rate=500.0, n_calibration_windows=30, post_disturbance=30.0,
        disturbance_addend=0.8,
    )
    snr = results[0].snr
    assert snr[50.0] is not None and snr[99.9] is not None
    assert snr[50.0] > snr[99.9]


def test_sweep_parallel_matches_serial():
    profiles = LATENCY_VARIANCE_SPECTRUM[:2]
    window_sizes = [1.0, 2.0]
    common = dict(seed=42, total_rate=200.0, n_calibration_windows=5, post_disturbance=10.0)
    serial = sweep_slo_performance(profiles, window_sizes, workers=1, **common)
    parallel = sweep_slo_performance(profiles, window_sizes, workers=2, **common)
    assert len(parallel) == len(serial)
    for s, p in zip(serial, parallel):
        assert s.profile_name == p.profile_name
        assert s.window_size == p.window_size
        assert s.recall == p.recall
        assert s.fpr == p.fpr
        assert s.precision == p.precision

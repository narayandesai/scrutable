import numpy as np
import pytest
from scrutable.traffic import FlatCurve, SinusoidalCurve, DoublePeakCurve, MarkovActivity, WorkloadEntry, WorkloadMix
from scrutable.models import WorkloadModel


def test_flat_curve_returns_one():
    curve = FlatCurve()
    for phase in [0.0, 0.25, 0.5, 0.75, 0.999]:
        assert curve(phase) == 1.0


def test_sinusoidal_curve_peak_at_phase():
    curve = SinusoidalCurve(peak_phase=0.25, trough_depth=0.5)
    assert curve(0.25) == pytest.approx(1.5)
    assert curve(0.75) == pytest.approx(0.5)


def test_sinusoidal_curve_non_negative():
    curve = SinusoidalCurve(peak_phase=0.0, trough_depth=1.0)
    phases = np.linspace(0.0, 1.0, 1000, endpoint=False)
    assert all(curve(p) >= 0.0 for p in phases)


def test_sinusoidal_curve_mean_is_one():
    curve = SinusoidalCurve(peak_phase=0.3, trough_depth=0.7)
    phases = np.linspace(0.0, 1.0, 10_000, endpoint=False)
    assert np.mean([curve(p) for p in phases]) == pytest.approx(1.0, abs=1e-3)


def test_double_peak_curve_mean_is_one():
    curve = DoublePeakCurve(peak1_phase=0.25, peak2_phase=0.75, trough_depth=0.6)
    phases = np.linspace(0.0, 1.0, 10_000, endpoint=False)
    assert np.mean([curve(p) for p in phases]) == pytest.approx(1.0, abs=1e-3)


def test_double_peak_curve_has_two_local_maxima():
    curve = DoublePeakCurve(peak1_phase=0.2, peak2_phase=0.7, trough_depth=0.8)
    phases = np.linspace(0.0, 1.0, 1000, endpoint=False)
    values = [curve(p) for p in phases]
    peak1_idx = int(0.2 * 1000)
    peak2_idx = int(0.7 * 1000)
    midpoint_idx = int(0.45 * 1000)
    assert values[peak1_idx] > values[midpoint_idx]
    assert values[peak2_idx] > values[midpoint_idx]


def _model(wid: str) -> WorkloadModel:
    return WorkloadModel(
        workload_id=wid,
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=1000.0,
        error_shape=1.5,
        noise_sigma=0.001,
    )


def test_workload_mix_valid_shares_no_error():
    m1, m2 = _model("w1"), _model("w2")
    WorkloadMix(
        total_rate=100.0,
        period=3600.0,
        entries=[WorkloadEntry(model=m1, share=0.7), WorkloadEntry(model=m2, share=0.3)],
    )  # should not raise


def test_workload_mix_invalid_shares_raises():
    m1 = _model("w1")
    with pytest.raises(ValueError, match="sum to 1.0"):
        WorkloadMix(total_rate=100.0, period=3600.0, entries=[WorkloadEntry(model=m1, share=0.7)])


def test_workload_mix_rate_at_flat():
    m1, m2 = _model("w1"), _model("w2")
    mix = WorkloadMix(
        total_rate=100.0,
        period=3600.0,
        entries=[WorkloadEntry(model=m1, share=0.7), WorkloadEntry(model=m2, share=0.3)],
    )
    assert mix.rate_at("w1", 0.0) == pytest.approx(70.0)
    assert mix.rate_at("w2", 0.0) == pytest.approx(30.0)


def test_workload_mix_rate_at_sinusoidal():
    model = _model("w1")
    curve = SinusoidalCurve(peak_phase=0.0, trough_depth=0.5)
    mix = WorkloadMix(
        total_rate=100.0,
        period=1000.0,
        entries=[WorkloadEntry(model=model, share=1.0, diurnal=curve)],
    )
    # At t=0, phase=0.0: multiplier=1+0.5*cos(0)=1.5
    assert mix.rate_at("w1", 0.0) == pytest.approx(150.0)
    # At t=500, phase=0.5: multiplier=1+0.5*cos(π)=0.5
    assert mix.rate_at("w1", 500.0) == pytest.approx(50.0)


def test_workload_entry_default_diurnal_is_flat():
    model = _model("w1")
    mix = WorkloadMix(
        total_rate=200.0,
        period=3600.0,
        entries=[WorkloadEntry(model=model, share=1.0)],
    )
    assert mix.rate_at("w1", 0.0) == pytest.approx(200.0)
    assert mix.rate_at("w1", 1800.0) == pytest.approx(200.0)


def test_markov_activity_defaults():
    act = MarkovActivity(onset_rate=2.0, recovery_rate=0.5)
    assert act.initial_active is True


def test_workload_mix_duplicate_id_raises():
    m1 = _model("w1")
    m2 = _model("w1")  # same id
    with pytest.raises(ValueError, match="duplicate workload_id"):
        WorkloadMix(
            total_rate=100.0,
            period=3600.0,
            entries=[WorkloadEntry(model=m1, share=0.5), WorkloadEntry(model=m2, share=0.5)],
        )

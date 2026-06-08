import math
import numpy as np
import pytest
from scrutable.traffic import FlatCurve, SinusoidalCurve, DoublePeakCurve


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

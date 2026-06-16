import numpy as np
import pytest
from scrutable.models import Response, Signal, Alarm
from scrutable.sensor import Sensor
from scrutable.detector import Detector
from scrutable.observations import NumpyObservationBuffer
from scrutable.detectors.slo import (
    SloTarget,
    LatencySloCalibrator,
    LatencySloSensor,
    LatencySloDetector,
    ErrorRateSloTarget,
    ErrorRateSloCalibrator,
    ErrorRateSloSensor,
    ErrorRateSloDetector,
)


def make_responses(n: int, latency: float, issued_at_start: float = 0.0) -> list[Response]:
    return [
        Response(
            request_id=f"req-{i}", workload_id="wl1", node_id="r1c1n1",
            cluster_id="r1c1", region_id="r1",
            issued_at=issued_at_start + i * 0.001,
            latency=latency, error_code=0,
        )
        for i in range(n)
    ]


def make_responses_with_errors(n: int, error_rate: float, issued_at_start: float = 0.0) -> list[Response]:
    return [
        Response(
            request_id=f"req-{i}", workload_id="wl1", node_id="r1c1n1",
            cluster_id="r1c1", region_id="r1",
            issued_at=issued_at_start + i * 0.001,
            latency=0.05, error_code=1 if i / n < error_rate else 0,
        )
        for i in range(n)
    ]


def build_window_result(responses: list) -> "WindowResult":
    """Wrap a list of Response objects in a WindowResult (test helper)."""
    import numpy as np
    from scrutable.window_result import WindowResult
    if not responses:
        return WindowResult(t_start=0.0, t_end=0.0, count=0, error_rate=0.0,
                            _latencies=np.empty(0, dtype=np.float64))
    latencies = np.array([r.latency for r in responses], dtype=np.float64)
    errors    = sum(1 for r in responses if r.error_code != 0)
    t_start   = min(r.issued_at for r in responses)
    t_end     = max(r.issued_at + r.latency for r in responses)
    return WindowResult(
        t_start=t_start, t_end=t_end,
        count=len(responses), error_rate=errors / len(responses),
        _latencies=latencies,
    )


# --- LatencySloCalibrator ---

def _make_buf_lognormal(n_windows: int, window_size: float, n_per_window: int,
                        mu: float, sigma: float, rng: np.random.Generator) -> NumpyObservationBuffer:
    buf = NumpyObservationBuffer()
    for w in range(n_windows):
        latencies = rng.lognormal(mu, sigma, n_per_window)
        for i, lat in enumerate(latencies):
            buf.append(Response(
                request_id=f"r{w}-{i}", workload_id="wl", node_id="n", cluster_id="c", region_id="r",
                issued_at=w * window_size + i * (window_size / n_per_window),
                latency=float(lat), error_code=0,
            ))
    return buf


def test_empirical_calibrator_returns_slo_target():
    rng = np.random.default_rng(0)
    buf = _make_buf_lognormal(100, 1.0, 1000, -2.3, 0.3, rng)
    target = LatencySloCalibrator(target_fpr=0.01).calibrate(buf, calibration_end=100.0, percentile=99.9, window_size=1.0)
    assert isinstance(target, SloTarget)
    assert target.percentile == 99.9
    assert target.window_size == 1.0


def test_empirical_calibrator_threshold_above_zero():
    rng = np.random.default_rng(0)
    buf = _make_buf_lognormal(100, 1.0, 1000, -2.3, 0.3, rng)
    target = LatencySloCalibrator(target_fpr=0.01).calibrate(buf, calibration_end=100.0, percentile=99.9, window_size=1.0)
    assert target.threshold > 0.0


def test_empirical_calibrator_threshold_is_high_quantile_of_per_window_estimates():
    # With target_fpr=0.01 (99th percentile of burn-in window estimates), at most ~1% of
    # burn-in windows should exceed the threshold in-sample.
    rng = np.random.default_rng(42)
    n_windows = 200
    buf = _make_buf_lognormal(n_windows, 1.0, 500, -2.3, 0.3, rng)
    target = LatencySloCalibrator(target_fpr=0.01).calibrate(buf, calibration_end=float(n_windows), percentile=99.9, window_size=1.0)
    # count how many burn-in windows exceed the threshold
    exceed = 0
    for w in range(n_windows):
        window = buf.window(float(w), float(w + 1))
        if window.percentile(99.9) > target.threshold:
            exceed += 1
    assert exceed / n_windows <= 0.01 + 1e-9


def test_empirical_calibrator_higher_variance_yields_higher_threshold():
    rng_lo = np.random.default_rng(0)
    rng_hi = np.random.default_rng(0)
    buf_lo = _make_buf_lognormal(100, 1.0, 1000, -2.3, 0.3, rng_lo)
    buf_hi = _make_buf_lognormal(100, 1.0, 1000, -2.3, 1.5, rng_hi)
    t_lo = LatencySloCalibrator(target_fpr=0.01).calibrate(buf_lo, calibration_end=100.0, percentile=99.9, window_size=1.0)
    t_hi = LatencySloCalibrator(target_fpr=0.01).calibrate(buf_hi, calibration_end=100.0, percentile=99.9, window_size=1.0)
    assert t_hi.threshold > t_lo.threshold


def test_empirical_calibrator_respects_percentile():
    rng = np.random.default_rng(0)
    buf = _make_buf_lognormal(100, 1.0, 1000, -2.3, 0.5, rng)
    t90 = LatencySloCalibrator(target_fpr=0.01).calibrate(buf, calibration_end=100.0, percentile=90.0, window_size=1.0)
    t999 = LatencySloCalibrator(target_fpr=0.01).calibrate(buf, calibration_end=100.0, percentile=99.9, window_size=1.0)
    assert t999.threshold > t90.threshold


def test_empirical_calibrator_raises_with_fewer_than_two_windows():
    rng = np.random.default_rng(0)
    buf = _make_buf_lognormal(1, 1.0, 1000, -2.3, 0.3, rng)
    with pytest.raises(ValueError, match="calibration"):
        LatencySloCalibrator(target_fpr=0.01).calibrate(buf, calibration_end=1.0, percentile=99.9, window_size=1.0)


def test_effective_fpr_uses_target_fpr_when_stricter():
    # window_size=3600 (1 hour), max_daily_alerts=4 → fpr_from_daily = 4/24 ≈ 0.167
    # target_fpr=0.001 is stricter → effective = 0.001
    cal = LatencySloCalibrator(target_fpr=0.001, max_daily_alerts=4.0)
    assert cal._effective_fpr(window_size=3600.0) == pytest.approx(0.001)


def test_effective_fpr_uses_daily_limit_when_stricter():
    # window_size=3600 (1 hour), max_daily_alerts=1 → fpr_from_daily = 1/24 ≈ 0.042
    # target_fpr=0.1 is looser → effective = 1/24
    cal = LatencySloCalibrator(target_fpr=0.1, max_daily_alerts=1.0)
    assert cal._effective_fpr(window_size=3600.0) == pytest.approx(1.0 / 24.0)


def test_effective_fpr_scales_with_window_size():
    # max_daily_alerts=4: with 1-min windows → fpr_from_daily = 4/1440
    # with 1-hour windows → fpr_from_daily = 4/24
    cal = LatencySloCalibrator(target_fpr=1.0, max_daily_alerts=4.0)
    assert cal._effective_fpr(60.0) == pytest.approx(4.0 / 1440.0)
    assert cal._effective_fpr(3600.0) == pytest.approx(4.0 / 24.0)


def test_calibrator_daily_limit_raises_threshold_vs_looser_fpr():
    # With a tighter effective FPR the threshold should be higher (more conservative).
    rng = np.random.default_rng(0)
    buf = _make_buf_lognormal(200, 1.0, 500, -2.3, 0.3, rng)
    # Loose: target_fpr=0.1, daily limit so loose it won't bind (1000 alerts/day)
    t_loose = LatencySloCalibrator(target_fpr=0.1, max_daily_alerts=1000.0).calibrate(
        buf, calibration_end=200.0, percentile=99.9, window_size=1.0
    )
    # Tight: daily limit of 4 with 1-second windows → fpr_from_daily = 4/86400 ≈ 4.6e-5
    t_tight = LatencySloCalibrator(target_fpr=0.1, max_daily_alerts=4.0).calibrate(
        buf, calibration_end=200.0, percentile=99.9, window_size=1.0
    )
    assert t_tight.threshold >= t_loose.threshold


def test_effective_fpr_bake_constraint_binds_when_strictest():
    # bake_duration=172800s (2d), max_alerts_per_bake=0.5, window_size=300s
    # fpr_from_bake = 0.5 * 300 / 172800 ≈ 8.68e-4 — stricter than target_fpr=0.01
    cal = LatencySloCalibrator(
        target_fpr=0.01,
        max_daily_alerts=4.0,
        max_alerts_per_bake=0.5,
        bake_duration=172800.0,
    )
    expected = 0.5 * 300.0 / 172800.0
    assert cal._effective_fpr(window_size=300.0) == pytest.approx(expected)


def test_effective_fpr_bake_constraint_ignored_without_bake_duration():
    cal = LatencySloCalibrator(target_fpr=0.01, max_alerts_per_bake=0.5, bake_duration=None)
    assert cal._effective_fpr(window_size=300.0) == pytest.approx(0.01)


def test_effective_fpr_all_three_constraints_take_minimum():
    # target_fpr=0.1, daily=0.05 (fpr_from_daily=0.05*60/86400≈3.5e-5), bake not binding
    cal = LatencySloCalibrator(
        target_fpr=0.1,
        max_daily_alerts=0.05,
        max_alerts_per_bake=0.5,
        bake_duration=60.0,  # 1-minute bake: fpr_from_bake=0.5*60/60=0.5 → not binding
    )
    expected = 0.05 * 60.0 / 86400.0  # daily constraint wins
    assert cal._effective_fpr(window_size=60.0) == pytest.approx(expected)


def test_bake_constraint_raises_threshold_vs_no_bake_constraint():
    rng = np.random.default_rng(0)
    buf = _make_buf_lognormal(200, 1.0, 500, -2.3, 0.3, rng)
    t_no_bake = LatencySloCalibrator(target_fpr=0.1).calibrate(
        buf, calibration_end=200.0, percentile=99.9, window_size=1.0
    )
    # bake constraint with short bake and tight budget → very low per-window FPR
    t_bake = LatencySloCalibrator(
        target_fpr=0.1, max_alerts_per_bake=0.5, bake_duration=10.0
    ).calibrate(buf, calibration_end=200.0, percentile=99.9, window_size=1.0)
    assert t_bake.threshold >= t_no_bake.threshold


# --- LatencySloSensor ---

def test_latency_sensor_satisfies_sensor_protocol():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    assert isinstance(sensor, Sensor)


def test_latency_sensor_produces_signal_from_window():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    window = build_window_result(make_responses(2000, latency=0.05))
    signals = sensor.measure(window)
    assert len(signals) == 1
    assert signals[0].metric == "latency_p99.9"
    assert signals[0].sensor_id == "lat"
    assert signals[0].sample_count == 2000
    assert signals[0].value > 0.0


def test_latency_sensor_empty_window_returns_no_signals():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    assert sensor.measure(build_window_result([])) == []


def test_latency_sensor_window_size_from_target():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=30.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=30.0)
    assert sensor.window_size == 30.0


def test_latency_sensor_value_reflects_percentile():
    target_p50 = SloTarget(percentile=50.0, threshold=0.1, window_size=1.0)
    target_p99 = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    rng = np.random.default_rng(0)
    window = [
        Response(request_id=f"r{i}", workload_id="w", node_id="n", cluster_id="c", region_id="r",
                 issued_at=i * 0.001, latency=float(rng.lognormal(-2.3, 0.5)), error_code=0)
        for i in range(2000)
    ]
    sig_p50 = LatencySloSensor(sensor_id="s", target=target_p50, sampling_period=1.0).measure(build_window_result(window))[0]
    sig_p99 = LatencySloSensor(sensor_id="s", target=target_p99, sampling_period=1.0).measure(build_window_result(window))[0]
    assert sig_p99.value > sig_p50.value


# --- LatencySloDetector ---

def test_latency_detector_satisfies_detector_protocol():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    detector = LatencySloDetector(detector_id="slo", target=target)
    assert isinstance(detector, Detector)


def test_latency_detector_fires_alarm_above_threshold():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target)
    signals = sensor.measure(build_window_result(make_responses(2000, latency=1.0)))
    alarms = detector.detect(signals)
    assert len(alarms) == 1
    assert alarms[0].detector_id == "slo-test"
    assert alarms[0].fault_type == "latency_degradation"
    assert alarms[0].severity > 0.0


def test_latency_detector_silent_below_threshold():
    target = SloTarget(percentile=99.9, threshold=1.0, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target)
    signals = sensor.measure(build_window_result(make_responses(2000, latency=0.05)))
    assert detector.detect(signals) == []


def test_latency_detector_silent_on_empty_signals():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target)
    assert detector.detect([]) == []


def test_latency_detector_severity_higher_further_above_threshold():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target)
    sev_slight = detector.detect(sensor.measure(build_window_result(make_responses(2000, latency=0.12))))[0].severity
    sev_large = detector.detect(sensor.measure(build_window_result(make_responses(2000, latency=2.0))))[0].severity
    assert sev_large > sev_slight


def test_latency_detector_ignores_unrelated_metric():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target)
    unrelated = [Signal(sensor_id="s", metric="error_rate", value=999.0,
                        window_start=0.0, window_end=1.0, sample_count=100)]
    assert detector.detect(unrelated) == []


# --- ErrorRateSloTarget / Calibrator / Sensor / Detector ---

def test_error_rate_slo_target_fields():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    assert target.threshold == 0.001
    assert target.window_size == 300.0


def test_error_rate_calibrator_returns_target():
    buf = NumpyObservationBuffer()
    for r in make_responses_with_errors(2000, error_rate=0.01):
        buf.append(r)
    target = ErrorRateSloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, window_size=2.0)
    assert isinstance(target, ErrorRateSloTarget)
    assert target.threshold > 0.01
    assert target.window_size == 2.0


def test_error_rate_calibrator_scales_with_multiplier():
    buf = NumpyObservationBuffer()
    for r in make_responses_with_errors(2000, error_rate=0.01):
        buf.append(r)
    t2 = ErrorRateSloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, window_size=2.0)
    t3 = ErrorRateSloCalibrator(multiplier=3.0).calibrate(buf, calibration_end=2.0, window_size=2.0)
    assert t3.threshold > t2.threshold


def test_error_rate_calibrator_raises_on_empty_window():
    buf = NumpyObservationBuffer()
    with pytest.raises(ValueError):
        ErrorRateSloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, window_size=2.0)


def test_error_rate_sensor_satisfies_sensor_protocol():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    assert isinstance(sensor, Sensor)


def test_error_rate_sensor_produces_signal():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    window = build_window_result(make_responses_with_errors(1000, error_rate=0.05))
    signals = sensor.measure(window)
    assert len(signals) == 1
    assert signals[0].metric == "error_rate"
    assert abs(signals[0].value - 0.05) < 0.01


def test_error_rate_sensor_empty_window_returns_no_signals():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    assert sensor.measure(build_window_result([])) == []


def test_error_rate_detector_satisfies_detector_protocol():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    detector = ErrorRateSloDetector(detector_id="err-det", target=target)
    assert isinstance(detector, Detector)


def test_error_rate_detector_fires_when_rate_exceeds_threshold():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target)
    signals = sensor.measure(build_window_result(make_responses_with_errors(1000, error_rate=0.05)))
    alarms = detector.detect(signals)
    assert len(alarms) == 1
    assert alarms[0].detector_id == "err-test"
    assert alarms[0].fault_type == "error_rate_degradation"
    assert alarms[0].severity > 0.0


def test_error_rate_detector_silent_below_threshold():
    target = ErrorRateSloTarget(threshold=0.05, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target)
    signals = sensor.measure(build_window_result(make_responses_with_errors(1000, error_rate=0.01)))
    assert detector.detect(signals) == []


def test_error_rate_detector_silent_on_empty_signals():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target)
    assert detector.detect([]) == []


def test_error_rate_detector_zero_errors_silent_above_zero_threshold():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target)
    signals = sensor.measure(build_window_result(make_responses_with_errors(1000, error_rate=0.0)))
    assert detector.detect(signals) == []


def test_error_rate_detector_ignores_latency_metric():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target)
    latency_signals = [Signal(sensor_id="s", metric="latency_p99.9", value=999.0,
                              window_start=0.0, window_end=1.0, sample_count=100)]
    assert detector.detect(latency_signals) == []

import numpy as np
import pytest
from scrutable.models import Response, Signal, Alarm
from scrutable.sensor import Sensor
from scrutable.detector import Detector
from scrutable.observations import ObservationBuffer
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


# --- LatencySloCalibrator (unchanged) ---

def test_burn_in_calibrator_returns_slo_target():
    buf = ObservationBuffer()
    for r in make_responses(2000, latency=0.05):
        buf.append(r)
    calibrator = LatencySloCalibrator(multiplier=2.0)
    target = calibrator.calibrate(buf, calibration_end=2.0, percentile=99.9, window_size=2.0)
    assert isinstance(target, SloTarget)
    assert target.percentile == 99.9
    assert target.window_size == 2.0


def test_burn_in_calibrator_threshold_above_baseline():
    buf = ObservationBuffer()
    for r in make_responses(2000, latency=0.05):
        buf.append(r)
    target = LatencySloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, percentile=99.9, window_size=2.0)
    assert target.threshold > 0.05


def test_burn_in_calibrator_threshold_scales_with_multiplier():
    buf = ObservationBuffer()
    for r in make_responses(2000, latency=0.05):
        buf.append(r)
    t2 = LatencySloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, percentile=99.9, window_size=2.0)
    t3 = LatencySloCalibrator(multiplier=3.0).calibrate(buf, calibration_end=2.0, percentile=99.9, window_size=2.0)
    assert t3.threshold > t2.threshold


def test_burn_in_calibrator_respects_percentile():
    buf = ObservationBuffer()
    rng = np.random.default_rng(0)
    for i in range(5000):
        r = Response(
            request_id=f"r{i}", workload_id="w", node_id="n", cluster_id="c", region_id="r",
            issued_at=i * 0.001, latency=float(rng.lognormal(-2.3, 0.5)), error_code=0,
        )
        buf.append(r)
    t90 = LatencySloCalibrator(multiplier=1.0).calibrate(buf, calibration_end=5.0, percentile=90.0, window_size=5.0)
    t999 = LatencySloCalibrator(multiplier=1.0).calibrate(buf, calibration_end=5.0, percentile=99.9, window_size=5.0)
    assert t999.threshold > t90.threshold


def test_burn_in_calibrator_raises_on_empty_window():
    buf = ObservationBuffer()
    with pytest.raises(ValueError):
        LatencySloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, percentile=99.9, window_size=2.0)


# --- LatencySloSensor ---

def test_latency_sensor_satisfies_sensor_protocol():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    assert isinstance(sensor, Sensor)


def test_latency_sensor_produces_signal_from_window():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    window = make_responses(2000, latency=0.05)
    signals = sensor.measure(window)
    assert len(signals) == 1
    assert signals[0].metric == "latency_p99.9"
    assert signals[0].sensor_id == "lat"
    assert signals[0].sample_count == 2000
    assert signals[0].value > 0.0


def test_latency_sensor_empty_window_returns_no_signals():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    assert sensor.measure([]) == []


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
    sig_p50 = LatencySloSensor(sensor_id="s", target=target_p50, sampling_period=1.0).measure(window)[0]
    sig_p99 = LatencySloSensor(sensor_id="s", target=target_p99, sampling_period=1.0).measure(window)[0]
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
    signals = sensor.measure(make_responses(2000, latency=1.0))
    alarms = detector.detect(signals)
    assert len(alarms) == 1
    assert alarms[0].detector_id == "slo-test"
    assert alarms[0].fault_type == "latency_degradation"
    assert alarms[0].severity > 0.0


def test_latency_detector_silent_below_threshold():
    target = SloTarget(percentile=99.9, threshold=1.0, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target)
    signals = sensor.measure(make_responses(2000, latency=0.05))
    assert detector.detect(signals) == []


def test_latency_detector_silent_on_empty_signals():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target)
    assert detector.detect([]) == []


def test_latency_detector_severity_higher_further_above_threshold():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target)
    sev_slight = detector.detect(sensor.measure(make_responses(2000, latency=0.12)))[0].severity
    sev_large = detector.detect(sensor.measure(make_responses(2000, latency=2.0)))[0].severity
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
    buf = ObservationBuffer()
    for r in make_responses_with_errors(2000, error_rate=0.01):
        buf.append(r)
    target = ErrorRateSloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, window_size=2.0)
    assert isinstance(target, ErrorRateSloTarget)
    assert target.threshold > 0.01
    assert target.window_size == 2.0


def test_error_rate_calibrator_scales_with_multiplier():
    buf = ObservationBuffer()
    for r in make_responses_with_errors(2000, error_rate=0.01):
        buf.append(r)
    t2 = ErrorRateSloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, window_size=2.0)
    t3 = ErrorRateSloCalibrator(multiplier=3.0).calibrate(buf, calibration_end=2.0, window_size=2.0)
    assert t3.threshold > t2.threshold


def test_error_rate_calibrator_raises_on_empty_window():
    buf = ObservationBuffer()
    with pytest.raises(ValueError):
        ErrorRateSloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, window_size=2.0)


def test_error_rate_sensor_satisfies_sensor_protocol():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    assert isinstance(sensor, Sensor)


def test_error_rate_sensor_produces_signal():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    window = make_responses_with_errors(1000, error_rate=0.05)
    signals = sensor.measure(window)
    assert len(signals) == 1
    assert signals[0].metric == "error_rate"
    assert abs(signals[0].value - 0.05) < 0.01


def test_error_rate_sensor_empty_window_returns_no_signals():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    assert sensor.measure([]) == []


def test_error_rate_detector_satisfies_detector_protocol():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    detector = ErrorRateSloDetector(detector_id="err-det", target=target)
    assert isinstance(detector, Detector)


def test_error_rate_detector_fires_when_rate_exceeds_threshold():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target)
    signals = sensor.measure(make_responses_with_errors(1000, error_rate=0.05))
    alarms = detector.detect(signals)
    assert len(alarms) == 1
    assert alarms[0].detector_id == "err-test"
    assert alarms[0].fault_type == "error_rate_degradation"
    assert alarms[0].severity > 0.0


def test_error_rate_detector_silent_below_threshold():
    target = ErrorRateSloTarget(threshold=0.05, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target)
    signals = sensor.measure(make_responses_with_errors(1000, error_rate=0.01))
    assert detector.detect(signals) == []


def test_error_rate_detector_silent_on_empty_signals():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target)
    assert detector.detect([]) == []


def test_error_rate_detector_zero_errors_silent_above_zero_threshold():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target)
    signals = sensor.measure(make_responses_with_errors(1000, error_rate=0.0))
    assert detector.detect(signals) == []


def test_error_rate_detector_ignores_latency_metric():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target)
    latency_signals = [Signal(sensor_id="s", metric="latency_p99.9", value=999.0,
                              window_start=0.0, window_end=1.0, sample_count=100)]
    assert detector.detect(latency_signals) == []

import numpy as np
import pytest
from scrutable.plant import PlantConfig, Plant
from scrutable.workload import WorkloadRegistry
from scrutable.models import WorkloadModel, WorkloadState, Response
from scrutable.observations import ObservationBuffer
from scrutable.detectors.slo import LatencySloCalibrator, SloTarget, LatencySloDetector


# --- helpers ---

def make_plant():
    config = PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1"]},
        nodes={"r1c1": ["r1c1n1", "r1c1n2", "r1c1n3"]},
    )
    return Plant(config)


def make_responses(n: int, latency: float, issued_at_start: float = 0.0) -> list[Response]:
    return [
        Response(
            request_id=f"req-{i}",
            workload_id="wl1",
            node_id="r1c1n1",
            cluster_id="r1c1",
            region_id="r1",
            issued_at=issued_at_start + i * 0.001,
            latency=latency,
            error_code=0,
        )
        for i in range(n)
    ]


# --- LatencySloCalibrator ---

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
    calibrator = LatencySloCalibrator(multiplier=2.0)
    target = calibrator.calibrate(buf, calibration_end=2.0, percentile=99.9, window_size=2.0)
    assert target.threshold > 0.05


def test_burn_in_calibrator_threshold_scales_with_multiplier():
    buf = ObservationBuffer()
    for r in make_responses(2000, latency=0.05):
        buf.append(r)
    cal_2x = LatencySloCalibrator(multiplier=2.0)
    cal_3x = LatencySloCalibrator(multiplier=3.0)
    t2 = cal_2x.calibrate(buf, calibration_end=2.0, percentile=99.9, window_size=2.0)
    t3 = cal_3x.calibrate(buf, calibration_end=2.0, percentile=99.9, window_size=2.0)
    assert t3.threshold > t2.threshold


def test_burn_in_calibrator_respects_percentile():
    buf = ObservationBuffer()
    rng = np.random.default_rng(0)
    for i in range(5000):
        r = Response(
            request_id=f"r{i}", workload_id="w", node_id="n",
            cluster_id="c", region_id="r",
            issued_at=i * 0.001, latency=float(rng.lognormal(-2.3, 0.5)),
            error_code=0,
        )
        buf.append(r)
    calibrator = LatencySloCalibrator(multiplier=1.0)
    t90 = calibrator.calibrate(buf, calibration_end=5.0, percentile=90.0, window_size=5.0)
    t999 = calibrator.calibrate(buf, calibration_end=5.0, percentile=99.9, window_size=5.0)
    assert t999.threshold > t90.threshold


def test_burn_in_calibrator_raises_on_empty_window():
    buf = ObservationBuffer()
    calibrator = LatencySloCalibrator(multiplier=2.0)
    with pytest.raises(ValueError):
        calibrator.calibrate(buf, calibration_end=2.0, percentile=99.9, window_size=2.0)


# --- LatencySloDetector ---

def test_slo_detector_fires_inference_when_percentile_exceeds_threshold():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target, tick_interval=1.0)
    window = make_responses(2000, latency=1.0)
    inferences = detector.detect(window)
    assert len(inferences) == 1
    assert inferences[0].detector_id == "slo-test"
    assert inferences[0].confidence > 0.0


def test_slo_detector_silent_below_threshold():
    target = SloTarget(percentile=99.9, threshold=1.0, window_size=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target, tick_interval=1.0)
    window = make_responses(2000, latency=0.05)
    assert detector.detect(window) == []


def test_slo_detector_silent_on_empty_window():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target, tick_interval=1.0)
    assert detector.detect([]) == []


def test_slo_detector_confidence_higher_further_above_threshold():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target, tick_interval=1.0)
    conf_slight = detector.detect(make_responses(2000, latency=0.12))[0].confidence
    conf_large = detector.detect(make_responses(2000, latency=2.0))[0].confidence
    assert conf_large > conf_slight


def test_slo_detector_uses_target_percentile():
    # P50 threshold: should fire when median is above threshold
    target = SloTarget(percentile=50.0, threshold=0.1, window_size=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target, tick_interval=1.0)
    # P50=0.15 > threshold 0.1 — must detect
    window = make_responses(2000, latency=0.15)
    assert len(detector.detect(window)) == 1
    # P50=0.05 < threshold 0.1 — must be silent
    window_ok = make_responses(2000, latency=0.05)
    assert detector.detect(window_ok) == []


def test_slo_detector_satisfies_detector_protocol():
    from scrutable.detector import Detector
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target, tick_interval=1.0)
    assert isinstance(detector, Detector)


# --- ErrorRateSloTarget / ErrorRateSloCalibrator / ErrorRateSloDetector ---

def make_responses_with_errors(n: int, error_rate: float, issued_at_start: float = 0.0) -> list[Response]:
    return [
        Response(
            request_id=f"req-{i}",
            workload_id="wl1",
            node_id="r1c1n1",
            cluster_id="r1c1",
            region_id="r1",
            issued_at=issued_at_start + i * 0.001,
            latency=0.05,
            error_code=1 if i / n < error_rate else 0,
        )
        for i in range(n)
    ]


def test_error_rate_slo_target_is_dataclass():
    from scrutable.detectors.slo import ErrorRateSloTarget
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    assert target.threshold == 0.001
    assert target.window_size == 300.0


def test_error_rate_calibrator_returns_target():
    from scrutable.detectors.slo import ErrorRateSloCalibrator, ErrorRateSloTarget
    buf = ObservationBuffer()
    for r in make_responses_with_errors(2000, error_rate=0.01):
        buf.append(r)
    calibrator = ErrorRateSloCalibrator(multiplier=2.0)
    target = calibrator.calibrate(buf, calibration_end=2.0, window_size=2.0)
    assert isinstance(target, ErrorRateSloTarget)
    assert target.threshold > 0.01
    assert target.window_size == 2.0


def test_error_rate_calibrator_scales_with_multiplier():
    from scrutable.detectors.slo import ErrorRateSloCalibrator
    buf = ObservationBuffer()
    for r in make_responses_with_errors(2000, error_rate=0.01):
        buf.append(r)
    t2 = ErrorRateSloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, window_size=2.0)
    t3 = ErrorRateSloCalibrator(multiplier=3.0).calibrate(buf, calibration_end=2.0, window_size=2.0)
    assert t3.threshold > t2.threshold


def test_error_rate_calibrator_raises_on_empty_window():
    from scrutable.detectors.slo import ErrorRateSloCalibrator
    buf = ObservationBuffer()
    with pytest.raises(ValueError):
        ErrorRateSloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, window_size=2.0)


def test_error_rate_detector_fires_when_rate_exceeds_threshold():
    from scrutable.detectors.slo import ErrorRateSloDetector, ErrorRateSloTarget
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target, tick_interval=300.0)
    window = make_responses_with_errors(1000, error_rate=0.05)
    inferences = detector.detect(window)
    assert len(inferences) == 1
    assert inferences[0].detector_id == "err-test"
    assert inferences[0].confidence > 0.0


def test_error_rate_detector_silent_below_threshold():
    from scrutable.detectors.slo import ErrorRateSloDetector, ErrorRateSloTarget
    target = ErrorRateSloTarget(threshold=0.05, window_size=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target, tick_interval=300.0)
    window = make_responses_with_errors(1000, error_rate=0.01)
    assert detector.detect(window) == []


def test_error_rate_detector_silent_on_empty_window():
    from scrutable.detectors.slo import ErrorRateSloDetector, ErrorRateSloTarget
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target, tick_interval=300.0)
    assert detector.detect([]) == []


def test_error_rate_detector_zero_errors_silent_above_zero_threshold():
    from scrutable.detectors.slo import ErrorRateSloDetector, ErrorRateSloTarget
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target, tick_interval=300.0)
    window = make_responses_with_errors(1000, error_rate=0.0)
    assert detector.detect(window) == []

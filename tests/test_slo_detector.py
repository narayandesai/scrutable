import numpy as np
import pytest
from scrutable.plant import PlantConfig, Plant
from scrutable.workload import WorkloadRegistry
from scrutable.models import WorkloadModel, WorkloadState, Response
from scrutable.observations import ObservationBuffer
from scrutable.detectors.slo import BurnInCalibrator, SloTarget, LatencySloDetector


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


# --- BurnInCalibrator ---

def test_burn_in_calibrator_returns_slo_target():
    buf = ObservationBuffer()
    for r in make_responses(2000, latency=0.05):
        buf.append(r)
    calibrator = BurnInCalibrator(multiplier=2.0)
    target = calibrator.calibrate(buf, burn_in_end=2.0, percentile=99.9, window_size=2.0)
    assert isinstance(target, SloTarget)
    assert target.percentile == 99.9
    assert target.window_size == 2.0


def test_burn_in_calibrator_threshold_above_baseline():
    buf = ObservationBuffer()
    for r in make_responses(2000, latency=0.05):
        buf.append(r)
    calibrator = BurnInCalibrator(multiplier=2.0)
    target = calibrator.calibrate(buf, burn_in_end=2.0, percentile=99.9, window_size=2.0)
    assert target.threshold > 0.05


def test_burn_in_calibrator_threshold_scales_with_multiplier():
    buf = ObservationBuffer()
    for r in make_responses(2000, latency=0.05):
        buf.append(r)
    cal_2x = BurnInCalibrator(multiplier=2.0)
    cal_3x = BurnInCalibrator(multiplier=3.0)
    t2 = cal_2x.calibrate(buf, burn_in_end=2.0, percentile=99.9, window_size=2.0)
    t3 = cal_3x.calibrate(buf, burn_in_end=2.0, percentile=99.9, window_size=2.0)
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
    calibrator = BurnInCalibrator(multiplier=1.0)
    t90 = calibrator.calibrate(buf, burn_in_end=5.0, percentile=90.0, window_size=5.0)
    t999 = calibrator.calibrate(buf, burn_in_end=5.0, percentile=99.9, window_size=5.0)
    assert t999.threshold > t90.threshold


def test_burn_in_calibrator_raises_on_empty_window():
    buf = ObservationBuffer()
    calibrator = BurnInCalibrator(multiplier=2.0)
    with pytest.raises(ValueError):
        calibrator.calibrate(buf, burn_in_end=2.0, percentile=99.9, window_size=2.0)


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

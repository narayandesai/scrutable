import numpy as np
import pytest
from scrutable.plant import PlantConfig, Plant
from scrutable.workload import WorkloadRegistry
from scrutable.models import WorkloadModel, WorkloadState, Response
from scrutable.observations import ObservationBuffer
from scrutable.detectors.slo import BurnInCalibrator, SloThresholds, LatencySloDetector


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

def test_burn_in_calibrator_returns_thresholds():
    buf = ObservationBuffer()
    for r in make_responses(2000, latency=0.05):
        buf.append(r)
    calibrator = BurnInCalibrator(window_size=2.0, multiplier=2.0)
    thresholds = calibrator.calibrate(buf, burn_in_end=2.0)
    assert isinstance(thresholds, SloThresholds)


def test_burn_in_calibrator_p999_threshold_above_baseline():
    buf = ObservationBuffer()
    for r in make_responses(2000, latency=0.05):
        buf.append(r)
    calibrator = BurnInCalibrator(window_size=2.0, multiplier=2.0)
    thresholds = calibrator.calibrate(buf, burn_in_end=2.0)
    assert thresholds.p999_latency > 0.05


def test_burn_in_calibrator_threshold_scales_with_multiplier():
    buf = ObservationBuffer()
    for r in make_responses(2000, latency=0.05):
        buf.append(r)
    cal_2x = BurnInCalibrator(window_size=2.0, multiplier=2.0)
    cal_3x = BurnInCalibrator(window_size=2.0, multiplier=3.0)
    t2 = cal_2x.calibrate(buf, burn_in_end=2.0)
    t3 = cal_3x.calibrate(buf, burn_in_end=2.0)
    assert t3.p999_latency > t2.p999_latency


def test_burn_in_calibrator_raises_on_empty_window():
    buf = ObservationBuffer()
    calibrator = BurnInCalibrator(window_size=2.0, multiplier=2.0)
    with pytest.raises(ValueError):
        calibrator.calibrate(buf, burn_in_end=2.0)


# --- LatencySloDetector ---

def test_slo_detector_fires_inference_when_p999_exceeds_threshold():
    thresholds = SloThresholds(p999_latency=0.1)
    detector = LatencySloDetector(
        detector_id="slo-test",
        thresholds=thresholds,
        window_size=1.0,
        tick_interval=1.0,
    )
    # responses with latency 1.0 — well above threshold of 0.1
    window = make_responses(2000, latency=1.0)
    inferences = detector.detect(window)
    assert len(inferences) == 1
    assert inferences[0].detector_id == "slo-test"
    assert inferences[0].confidence > 0.0


def test_slo_detector_silent_below_threshold():
    thresholds = SloThresholds(p999_latency=1.0)
    detector = LatencySloDetector(
        detector_id="slo-test",
        thresholds=thresholds,
        window_size=1.0,
        tick_interval=1.0,
    )
    window = make_responses(2000, latency=0.05)
    inferences = detector.detect(window)
    assert inferences == []


def test_slo_detector_silent_on_empty_window():
    thresholds = SloThresholds(p999_latency=0.1)
    detector = LatencySloDetector(
        detector_id="slo-test",
        thresholds=thresholds,
        window_size=1.0,
        tick_interval=1.0,
    )
    assert detector.detect([]) == []


def test_slo_detector_confidence_higher_further_above_threshold():
    thresholds = SloThresholds(p999_latency=0.1)
    detector = LatencySloDetector(
        detector_id="slo-test",
        thresholds=thresholds,
        window_size=1.0,
        tick_interval=1.0,
    )
    slight_breach = make_responses(2000, latency=0.12)
    large_breach = make_responses(2000, latency=2.0)
    conf_slight = detector.detect(slight_breach)[0].confidence
    conf_large = detector.detect(large_breach)[0].confidence
    assert conf_large > conf_slight


def test_slo_detector_satisfies_detector_protocol():
    from scrutable.detector import Detector
    thresholds = SloThresholds(p999_latency=0.1)
    detector = LatencySloDetector(
        detector_id="slo-test",
        thresholds=thresholds,
        window_size=1.0,
        tick_interval=1.0,
    )
    assert isinstance(detector, Detector)

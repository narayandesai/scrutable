from scrutable.models import Response, Inference
from scrutable.detector import Detector
from scrutable.actuator import Actuator
from scrutable.operations import RolloutSystem, OperationsSystem


class HighErrorRateDetector:
    detector_id = "high-error-rate"
    window_size = 60.0
    tick_interval = 10.0

    def detect(self, window: list[Response]) -> list[Inference]:
        if not window:
            return []
        error_rate = sum(1 for r in window if r.error_code != 0) / len(window)
        if error_rate > 0.1:
            return [
                Inference(
                    detector_id=self.detector_id,
                    pathology_type="high_error_rate",
                    target_id="unknown",
                    target_level="cluster",
                    confidence=min(1.0, error_rate),
                    detected_at=window[-1].issued_at,
                    window_start=window[0].issued_at,
                    window_end=window[-1].issued_at,
                )
            ]
        return []


class DrainActuator:
    def __init__(self):
        self.calls: list[tuple] = []

    def act(self, inference: Inference, sim_time: float, rollouts: RolloutSystem, ops: OperationsSystem) -> None:
        self.calls.append((inference.pathology_type, sim_time))


def test_detector_protocol_satisfied():
    d = HighErrorRateDetector()
    assert isinstance(d, Detector)


def test_actuator_protocol_satisfied():
    a = DrainActuator()
    assert isinstance(a, Actuator)


def test_detector_fires_on_high_error_rate(build_response):
    d = HighErrorRateDetector()
    window = [build_response(error_code=1) for _ in range(20)]
    inferences = d.detect(window)
    assert len(inferences) == 1
    assert inferences[0].pathology_type == "high_error_rate"


def test_detector_silent_on_low_error_rate(build_response):
    d = HighErrorRateDetector()
    window = [build_response(error_code=0) for _ in range(20)]
    inferences = d.detect(window)
    assert inferences == []


def test_detector_empty_window_returns_no_inferences():
    d = HighErrorRateDetector()
    assert d.detect([]) == []


def test_actuator_receives_inference(tiny_infra, build_response):
    detector = HighErrorRateDetector()
    actuator = DrainActuator()
    ops = OperationsSystem(tiny_infra)
    rollouts = RolloutSystem({}, tiny_infra, {})
    window = [build_response(error_code=1) for _ in range(20)]
    for inf in detector.detect(window):
        actuator.act(inf, 60.0, rollouts, ops)
    assert len(actuator.calls) == 1
    assert actuator.calls[0] == ("high_error_rate", 60.0)

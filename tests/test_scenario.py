import numpy as np
from scrutable.models import WorkloadModel, Pathology, PathologyScope, WorkloadState, Inference
from scrutable.workload import WorkloadRegistry
from scrutable.synthesizer import SynthesizerConfig
from scrutable.pathology import TimedPathology
from scrutable.operations import SoftwareVersion
from scrutable.engine import SimulationEngine
from scrutable.detector import Detector
from scrutable.actuator import Actuator
from scrutable.operations import RolloutSystem, OperationsSystem


def _make_registry():
    registry = WorkloadRegistry()
    registry.register(
        WorkloadModel(
            workload_id="wl1",
            latency_median=0.1,
            latency_sigma=0.3,
            error_scale=1000.0,
            error_shape=1.5,
            noise_sigma=0.001,
        )
    )
    return registry


def _make_engine(tiny_infra, seed=42):
    registry = _make_registry()
    config = SynthesizerConfig(workload_rates={"wl1": 50.0})
    return SimulationEngine(tiny_infra, registry, config, seed=seed)


def test_engine_produces_responses(tiny_infra):
    engine = _make_engine(tiny_infra)
    engine.run(1.0)
    responses = engine.buffer.window(0.0, 2.0)
    assert len(responses) > 0


def test_engine_responses_have_valid_fields(tiny_infra):
    engine = _make_engine(tiny_infra)
    engine.run(1.0)
    for resp in engine.buffer.window(0.0, 2.0):
        assert resp.workload_id == "wl1"
        assert resp.latency >= 0.0
        assert resp.error_code in (0, 1, 503)
        assert resp.node_id != "" or resp.error_code == 503


def test_engine_reproducible_with_same_seed(tiny_infra):
    from scrutable.infrastructure import InfrastructureConfig, InfrastructureModel
    config = InfrastructureConfig(
        regions=["r1", "r2"],
        clusters={"r1": ["r1c1", "r1c2"], "r2": ["r2c1", "r2c2"]},
        nodes={
            "r1c1": ["r1c1n1", "r1c1n2", "r1c1n3"],
            "r1c2": ["r1c2n1", "r1c2n2", "r1c2n3"],
            "r2c1": ["r2c1n1", "r2c1n2", "r2c1n3"],
            "r2c2": ["r2c2n1", "r2c2n2", "r2c2n3"],
        },
    )
    infra1 = InfrastructureModel(config)
    infra2 = InfrastructureModel(config)
    e1 = _make_engine(infra1, seed=99)
    e2 = _make_engine(infra2, seed=99)
    e1.run(2.0)
    e2.run(2.0)
    r1 = e1.buffer.window(0.0, 3.0)
    r2 = e2.buffer.window(0.0, 3.0)
    assert len(r1) == len(r2)
    for a, b in zip(r1, r2):
        assert a.request_id == b.request_id
        assert a.latency == b.latency
        assert a.error_code == b.error_code


def test_timed_pathology_elevates_latency(tiny_infra):
    engine = _make_engine(tiny_infra, seed=0)
    pathology = Pathology(
        pathology_id="slow-nodes",
        scope=PathologyScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 10.0},
    )
    engine.add_timed_pathology(TimedPathology(pathology=pathology, inject_at=5.0))
    engine.run(10.0)
    before = engine.buffer.window(0.0, 5.0)
    after = engine.buffer.window(5.0, 10.0)
    assert before and after
    avg_before = sum(r.latency for r in before) / len(before)
    avg_after = sum(r.latency for r in after) / len(after)
    assert avg_after > avg_before * 3


class RecordingActuator:
    def __init__(self):
        self.inferences: list[Inference] = []

    def act(self, inference: Inference, sim_time: float, rollouts: RolloutSystem, ops: OperationsSystem) -> None:
        self.inferences.append(inference)


class AlwaysFiresDetector:
    detector_id = "always"
    window_size = 5.0
    tick_interval = 5.0

    def detect(self, window):
        if not window:
            return []
        return [
            Inference(
                detector_id=self.detector_id,
                pathology_type="test",
                target_id="n1",
                target_level="node",
                confidence=1.0,
                detected_at=window[-1].issued_at + window[-1].latency,
                window_start=window[0].issued_at,
                window_end=window[-1].issued_at,
            )
        ]


def test_detector_and_actuator_wired_in_engine(tiny_infra):
    engine = _make_engine(tiny_infra, seed=7)
    detector = AlwaysFiresDetector()
    actuator = RecordingActuator()
    engine.add_detector(detector)
    engine.add_actuator(actuator)
    engine.run(10.0)
    assert len(actuator.inferences) > 0

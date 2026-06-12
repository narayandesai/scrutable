import numpy as np
from scrutable.models import WorkloadModel, Disturbance, DisturbanceScope, Signal, Alarm
from scrutable.disturbance import TimedDisturbance
from scrutable.engine import SimulationEngine
from scrutable.sensor import Sensor
from scrutable.detector import Detector
from scrutable.actuator import Actuator
from scrutable.operations import RolloutSystem, OperationsSystem
from scrutable.traffic import WorkloadEntry, WorkloadMix
from scrutable.plant import PlantConfig, Plant


def _make_engine(tiny_infra, seed=42):
    model = WorkloadModel(
        workload_id="wl1",
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=1000.0,
        error_shape=1.5,
        noise_sigma=0.001,
    )
    mix = WorkloadMix(
        total_rate=50.0,
        period=3600.0,
        entries=[WorkloadEntry(model=model, share=1.0)],
    )
    return SimulationEngine(tiny_infra, mix=mix, seed=seed)


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
    config = PlantConfig(
        regions=["r1", "r2"],
        clusters={"r1": ["r1c1", "r1c2"], "r2": ["r2c1", "r2c2"]},
        nodes={
            "r1c1": ["r1c1n1", "r1c1n2", "r1c1n3"],
            "r1c2": ["r1c2n1", "r1c2n2", "r1c2n3"],
            "r2c1": ["r2c1n1", "r2c1n2", "r2c1n3"],
            "r2c2": ["r2c2n1", "r2c2n2", "r2c2n3"],
        },
    )
    wl = WorkloadModel(workload_id="wl1", latency_median=0.1, latency_sigma=0.3,
                       error_scale=1000.0, error_shape=1.5, noise_sigma=0.001)
    mix = WorkloadMix(total_rate=50.0, period=3600.0, entries=[WorkloadEntry(model=wl, share=1.0)])
    e1 = SimulationEngine(Plant(config), mix=mix, seed=99)
    e2 = SimulationEngine(Plant(config), mix=mix, seed=99)
    e1.run(2.0)
    e2.run(2.0)
    r1 = e1.buffer.window(0.0, 3.0)
    r2 = e2.buffer.window(0.0, 3.0)
    assert len(r1) == len(r2)
    for a, b in zip(r1, r2):
        assert a.request_id == b.request_id
        assert a.latency == b.latency


def test_timed_disturbance_elevates_latency(tiny_infra):
    engine = _make_engine(tiny_infra, seed=0)
    disturbance = Disturbance(
        disturbance_id="slow-nodes",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 10.0},
    )
    engine.add_timed_disturbance(TimedDisturbance(disturbance=disturbance, inject_at=5.0))
    engine.run(10.0)
    before = engine.buffer.window(0.0, 5.0)
    after = engine.buffer.window(5.0, 10.0)
    avg_before = sum(r.latency for r in before) / len(before)
    avg_after = sum(r.latency for r in after) / len(after)
    assert avg_after > avg_before * 3


class RecordingActuator:
    def __init__(self):
        self.alarms: list[Alarm] = []

    def act(self, alarm: Alarm, sim_time: float, rollouts: RolloutSystem, ops: OperationsSystem) -> None:
        self.alarms.append(alarm)


class AlwaysFiresSensor:
    sensor_id = "always"
    window_size = 5.0
    sampling_period = 5.0

    def measure(self, window):
        if not window:
            return []
        t_start = min(r.issued_at for r in window)
        t_end = max(r.issued_at + r.latency for r in window)
        return [Signal(
            sensor_id=self.sensor_id,
            metric="always",
            value=1.0,
            window_start=t_start,
            window_end=t_end,
            sample_count=len(window),
        )]


class AlwaysFiresDetector:
    detector_id = "always"

    def detect(self, signals: list[Signal]) -> list[Alarm]:
        for sig in signals:
            if sig.metric == "always":
                return [Alarm(
                    detector_id=self.detector_id,
                    fault_type="test",
                    target_id="n1",
                    target_level="node",
                    severity=1.0,
                    detected_at=sig.window_end,
                    window_start=sig.window_start,
                    window_end=sig.window_end,
                )]
        return []


def test_sensor_and_actuator_wired_in_engine(tiny_infra):
    engine = _make_engine(tiny_infra, seed=7)
    engine.add_sensor(AlwaysFiresSensor())
    engine.add_detector(AlwaysFiresDetector())
    actuator = RecordingActuator()
    engine.add_actuator(actuator)
    engine.run(10.0)
    assert len(actuator.alarms) > 0


def test_engine_run_raises_on_second_call(tiny_infra):
    import pytest
    engine = _make_engine(tiny_infra)
    engine.run(0.1)
    with pytest.raises(RuntimeError):
        engine.run(0.1)


def test_add_sensor_raises_on_zero_sampling_period(tiny_infra):
    import pytest
    engine = _make_engine(tiny_infra)

    class BadSensor:
        sensor_id = "bad"
        window_size = 5.0
        sampling_period = 0.0
        def measure(self, window): return []

    with pytest.raises(ValueError):
        engine.add_sensor(BadSensor())

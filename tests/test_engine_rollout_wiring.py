import pytest
from scrutable.models import Release, ReleaseChange, RolloutState
from scrutable.rollout import Rollout
from scrutable.plant import PlantConfig, Plant
from scrutable.workload import WorkloadRegistry
from scrutable.models import WorkloadModel
from scrutable.synthesizer import InputConfig
from scrutable.engine import SimulationEngine


@pytest.fixture
def simple_engine():
    plant = Plant(PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1", "r1c2"]},
        nodes={"r1c1": ["r1c1n1"], "r1c2": ["r1c2n1"]},
    ))
    registry = WorkloadRegistry()
    registry.register(WorkloadModel(
        workload_id="wl1",
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=1000.0,
        error_shape=1.5,
        noise_sigma=0.001,
    ))
    return SimulationEngine(
        infra=plant,
        registry=registry,
        synth_config=InputConfig(workload_rates={"wl1": 5.0}),
        seed=42,
    )


def test_add_rollout_completes_all_stages(simple_engine):
    release = Release(release_id="v1", changes=[ReleaseChange(change_id="ch1")])
    rollout = Rollout(release, ["r1c1", "r1c2"], stage_interval=5.0, start_at=0.0)
    simple_engine.add_rollout(rollout)
    simple_engine.run(until=20.0)
    s = rollout.status
    assert s.state == RolloutState.COMPLETED
    assert s.stages_completed == 2


def test_add_rollout_gate_false_halts(simple_engine):
    release = Release(release_id="v2", changes=[ReleaseChange(change_id="ch1")])
    gates = [[], [lambda *_: False]]
    rollout = Rollout(release, ["r1c1", "r1c2"], stage_interval=5.0, start_at=0.0, gates=gates)
    simple_engine.add_rollout(rollout)
    simple_engine.run(until=20.0)
    s = rollout.status
    assert s.state == RolloutState.HALTED
    assert s.stages_completed == 1

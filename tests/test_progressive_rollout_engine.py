import pytest
from scrutable.models import (
    Release, ReleaseChange, RolloutState, Disturbance, DisturbanceScope, WorkloadModel,
)
from scrutable.rollout import Rollout
from scrutable.plant import PlantConfig, Plant
from scrutable.workload import WorkloadRegistry
from scrutable.synthesizer import InputConfig
from scrutable.engine import SimulationEngine


@pytest.fixture
def two_cluster_engine():
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
    engine = SimulationEngine(
        infra=plant,
        registry=registry,
        synth_config=InputConfig(workload_rates={"wl1": 5.0}),
        seed=42,
    )
    return engine


@pytest.fixture
def latency_release():
    d = Disturbance(
        disturbance_id="latency-bug",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_addend": 1.0},
    )
    return Release(release_id="v2", changes=[ReleaseChange(change_id="ch1", disturbance=d)])


def test_stages_fire_at_correct_sim_times(two_cluster_engine, latency_release):
    plant = two_cluster_engine._infra
    rollout = Rollout(
        latency_release,
        cluster_order=["r1c1", "r1c2"],
        stage_interval=10.0,
        start_at=5.0,
    )
    two_cluster_engine.add_rollout(rollout)
    two_cluster_engine.run(until=20.0)

    s = rollout.status
    assert s.state == RolloutState.COMPLETED
    assert s.stages_completed == 2
    assert plant.get_node("r1c1n1").latency_addend == pytest.approx(1.0)
    assert plant.get_node("r1c2n1").latency_addend == pytest.approx(1.0)


def test_gate_false_halts_rollout_at_stage(two_cluster_engine, latency_release):
    plant = two_cluster_engine._infra
    gates = [[], [lambda *_: False]]
    rollout = Rollout(
        latency_release,
        cluster_order=["r1c1", "r1c2"],
        stage_interval=5.0,
        start_at=1.0,
        gates=gates,
    )
    two_cluster_engine.add_rollout(rollout)
    two_cluster_engine.run(until=20.0)

    s = rollout.status
    assert s.state == RolloutState.HALTED
    assert s.stages_completed == 1
    assert "r1c1" in s.deployed_clusters
    assert "r1c2" not in s.deployed_clusters
    assert plant.get_node("r1c1n1").latency_addend == pytest.approx(1.0)
    assert plant.get_node("r1c2n1").latency_addend == pytest.approx(0.0)


def test_rollback_all_removes_all_effects(two_cluster_engine, latency_release):
    plant = two_cluster_engine._infra
    rollout = Rollout(
        latency_release,
        cluster_order=["r1c1", "r1c2"],
        stage_interval=5.0,
        start_at=0.0,
    )
    two_cluster_engine.add_rollout(rollout)
    two_cluster_engine.run(until=20.0)

    assert rollout.status.state == RolloutState.COMPLETED
    rollout.rollback_all(sim_time=20.0)

    assert plant.get_node("r1c1n1").latency_addend == pytest.approx(0.0)
    assert plant.get_node("r1c2n1").latency_addend == pytest.approx(0.0)
    assert rollout.status.state == RolloutState.ROLLED_BACK


def test_capacity_fraction_reflects_weights():
    plant = Plant(PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1", "r1c2"]},
        nodes={"r1c1": ["r1c1n1"], "r1c2": ["r1c2n1"]},
        capacity_weights={"r1c1": 1.0, "r1c2": 3.0},
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
    engine = SimulationEngine(
        infra=plant,
        registry=registry,
        synth_config=InputConfig(workload_rates={"wl1": 5.0}),
        seed=42,
    )
    release = Release(release_id="v1", changes=[ReleaseChange(change_id="ch1")])
    rollout = Rollout(release, ["r1c1", "r1c2"], stage_interval=10.0, start_at=0.0)
    engine.add_rollout(rollout)
    engine.run(until=3.0)  # only stage 0 fires at t=0; stage 1 at t=10 is beyond

    s = rollout.status
    assert s.stages_completed == 1
    assert s.capacity_fraction == pytest.approx(0.25)  # 1/(1+3)


def test_benign_release_completes_without_node_changes(two_cluster_engine):
    plant = two_cluster_engine._infra
    release = Release(release_id="v1", changes=[ReleaseChange(change_id="ch1")])
    rollout = Rollout(release, ["r1c1", "r1c2"], stage_interval=5.0, start_at=0.0)
    two_cluster_engine.add_rollout(rollout)
    two_cluster_engine.run(until=20.0)

    assert rollout.status.state == RolloutState.COMPLETED
    for node in plant.all_nodes():
        assert node.latency_addend == pytest.approx(0.0)
        assert node.latency_multiplier == pytest.approx(1.0)

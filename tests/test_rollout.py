import pytest
from scrutable.models import (
    Release, ReleaseChange, RolloutState, Disturbance, DisturbanceScope,
)
from scrutable.rollout import Rollout
from scrutable.plant import PlantConfig, Plant


@pytest.fixture
def two_cluster_plant():
    config = PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1", "r1c2"]},
        nodes={"r1c1": ["r1c1n1", "r1c1n2"], "r1c2": ["r1c2n1", "r1c2n2"]},
    )
    return Plant(config)


@pytest.fixture
def benign_release():
    return Release(release_id="v1", changes=[ReleaseChange(change_id="ch1")])


@pytest.fixture
def latency_release():
    d = Disturbance(
        disturbance_id="latency-bug",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_addend": 0.5},
    )
    return Release(release_id="v2", changes=[ReleaseChange(change_id="ch1", disturbance=d)])


def test_rollout_initial_status_is_pending(two_cluster_plant, benign_release):
    rollout = Rollout(benign_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    s = rollout.status
    assert s.state == RolloutState.PENDING
    assert s.stages_completed == 0
    assert s.stages_total == 2
    assert s.deployed_clusters == []
    assert s.pending_clusters == ["r1c1", "r1c2"]
    assert s.started_at is None
    assert s.state_entered_at is None
    assert s.state_history == []


def test_rollout_fractions_zero_before_any_deploy(two_cluster_plant, benign_release):
    rollout = Rollout(benign_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    s = rollout.status
    assert s.rollout_fraction == 0.0
    assert s.capacity_fraction == 0.0


def test_rollout_activate_twice_raises(two_cluster_plant, benign_release):
    rollout = Rollout(benign_release, ["r1c1"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    with pytest.raises(RuntimeError, match="_activate called more than once"):
        rollout._activate(two_cluster_plant, {})


def test_deploy_stage_affects_only_target_cluster(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=1.0)

    for node_id in two_cluster_plant.nodes_in_cluster("r1c1"):
        assert two_cluster_plant.get_node(node_id).latency_addend == pytest.approx(0.5)
    for node_id in two_cluster_plant.nodes_in_cluster("r1c2"):
        assert two_cluster_plant.get_node(node_id).latency_addend == pytest.approx(0.0)


def test_deploy_first_stage_transitions_to_in_progress(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=5.0)
    s = rollout.status
    assert s.state == RolloutState.IN_PROGRESS
    assert s.started_at == pytest.approx(5.0)
    assert s.state_entered_at == pytest.approx(5.0)
    assert s.stages_completed == 1
    assert s.deployed_clusters == ["r1c1"]
    assert s.pending_clusters == ["r1c2"]


def test_deploy_last_stage_transitions_to_completed(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=5.0)
    assert rollout.status.state == RolloutState.COMPLETED


def test_deploy_all_stages_updates_fractions(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=1.0)
    s = rollout.status
    assert s.rollout_fraction == pytest.approx(0.5)
    assert s.capacity_fraction == pytest.approx(0.5)


def test_state_history_recorded_on_transition(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=2.0)
    rollout._deploy_stage(1, sim_time=12.0)
    s = rollout.status
    assert len(s.state_history) == 1
    assert s.state_history[0].state == RolloutState.IN_PROGRESS
    assert s.state_history[0].entered_at == pytest.approx(2.0)
    assert s.state_history[0].exited_at == pytest.approx(12.0)


def test_benign_change_does_not_modify_nodes(two_cluster_plant, benign_release):
    rollout = Rollout(benign_release, ["r1c1"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=1.0)
    for node in two_cluster_plant.all_nodes():
        assert node.latency_addend == pytest.approx(0.0)
        assert node.latency_multiplier == pytest.approx(1.0)


def test_halt_transitions_to_halted(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=1.0)
    rollout.halt(sim_time=3.0)
    s = rollout.status
    assert s.state == RolloutState.HALTED
    assert s.deployed_clusters == ["r1c1"]


def test_halt_is_noop_if_already_completed(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=1.0)
    assert rollout.status.state == RolloutState.COMPLETED
    rollout.halt(sim_time=2.0)
    assert rollout.status.state == RolloutState.COMPLETED


def test_rollback_cluster_removes_effects(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=1.0)
    rollout.halt(sim_time=2.0)
    rollout.rollback_cluster("r1c1", sim_time=3.0)

    for node_id in two_cluster_plant.nodes_in_cluster("r1c1"):
        assert two_cluster_plant.get_node(node_id).latency_addend == pytest.approx(0.0)
    s = rollout.status
    assert "r1c1" not in s.deployed_clusters
    assert "r1c1" in s.pending_clusters
    assert s.state == RolloutState.HALTED


def test_rollback_cluster_noop_if_not_deployed(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout.halt(sim_time=1.0)
    rollout.rollback_cluster("r1c1", sim_time=2.0)
    assert rollout.status.deployed_clusters == []


def test_rollback_all_removes_all_effects_and_transitions(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=1.0)
    rollout._deploy_stage(1, sim_time=11.0)
    rollout.halt(sim_time=12.0)
    rollout.rollback_all(sim_time=13.0)

    for node in two_cluster_plant.all_nodes():
        assert node.latency_addend == pytest.approx(0.0)
    s = rollout.status
    assert s.state == RolloutState.ROLLED_BACK
    assert s.deployed_clusters == []


def test_check_gates_true_when_no_gates(two_cluster_plant, benign_release):
    rollout = Rollout(benign_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    assert rollout._check_gates(0, sim_time=1.0) is True
    assert rollout._check_gates(5, sim_time=1.0) is True


def test_check_gates_true_when_all_pass(two_cluster_plant, benign_release):
    gates = [[lambda status, t: True, lambda status, t: True]]
    rollout = Rollout(benign_release, ["r1c1", "r1c2"], stage_interval=10.0, gates=gates)
    rollout._activate(two_cluster_plant, {})
    assert rollout._check_gates(0, sim_time=1.0) is True


def test_check_gates_false_when_one_fails(two_cluster_plant, benign_release):
    gates = [[lambda status, t: True, lambda status, t: False]]
    rollout = Rollout(benign_release, ["r1c1", "r1c2"], stage_interval=10.0, gates=gates)
    rollout._activate(two_cluster_plant, {})
    assert rollout._check_gates(0, sim_time=1.0) is False


def test_check_gates_per_stage_independent(two_cluster_plant, benign_release):
    gates = [
        [lambda status, t: False],
        [lambda status, t: True],
    ]
    rollout = Rollout(benign_release, ["r1c1", "r1c2"], stage_interval=10.0, gates=gates)
    rollout._activate(two_cluster_plant, {})
    assert rollout._check_gates(0, sim_time=1.0) is False
    assert rollout._check_gates(1, sim_time=1.0) is True


def test_check_gates_receives_current_status(two_cluster_plant, latency_release):
    seen_stages = []

    def capture_gate(status, t):
        seen_stages.append(status.stages_completed)
        return True

    gates = [[capture_gate], [capture_gate]]
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0, gates=gates)
    rollout._activate(two_cluster_plant, {})
    rollout._check_gates(0, sim_time=1.0)
    rollout._deploy_stage(0, sim_time=1.0)
    rollout._check_gates(1, sim_time=11.0)
    assert seen_stages == [0, 1]

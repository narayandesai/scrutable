from scrutable.models import Disturbance, DisturbanceScope, WorkloadState
from scrutable.operations import SoftwareVersion, RolloutSystem, OperationsSystem


def test_drain_disables_cluster_traffic(tiny_infra):
    ops = OperationsSystem(tiny_infra)
    assert tiny_infra.get_cluster("r1c1").traffic_enabled is True
    ops.drain("r1c1")
    assert tiny_infra.get_cluster("r1c1").traffic_enabled is False


def test_restore_re_enables_cluster_traffic(tiny_infra):
    ops = OperationsSystem(tiny_infra)
    ops.drain("r1c1")
    ops.restore("r1c1")
    assert tiny_infra.get_cluster("r1c1").traffic_enabled is True


def test_rollout_deploy_applies_disturbances(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    disturbance = Disturbance(
        disturbance_id="bug-v2",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 3.0},
    )
    version = SoftwareVersion(version_id="v2", disturbances=[disturbance])
    rollouts = RolloutSystem({"v2": version}, tiny_infra, workload_states)
    rollouts.deploy("v2")
    for node in tiny_infra.all_nodes():
        assert node.latency_multiplier == 3.0


def test_rollout_deploy_idempotent(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    disturbance = Disturbance(
        disturbance_id="bug-v3",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 2.0},
    )
    version = SoftwareVersion(version_id="v3", disturbances=[disturbance])
    rollouts = RolloutSystem({"v3": version}, tiny_infra, workload_states)
    rollouts.deploy("v3")
    rollouts.deploy("v3")  # second deploy should be a no-op
    for node in tiny_infra.all_nodes():
        assert node.latency_multiplier == 2.0


def test_rollout_rollback_removes_disturbances(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    disturbance = Disturbance(
        disturbance_id="bug-v4",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 5.0},
    )
    version = SoftwareVersion(version_id="v4", disturbances=[disturbance])
    rollouts = RolloutSystem({"v4": version}, tiny_infra, workload_states)
    rollouts.deploy("v4")
    rollouts.rollback("v4")
    for node in tiny_infra.all_nodes():
        assert node.latency_multiplier == 1.0


def test_rollout_rollback_not_deployed_is_noop(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    version = SoftwareVersion(version_id="v5", disturbances=[])
    rollouts = RolloutSystem({"v5": version}, tiny_infra, workload_states)
    rollouts.rollback("v5")  # should not raise
    assert tiny_infra.get_node("r1c1n1").latency_multiplier == 1.0

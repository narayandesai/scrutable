from scrutable.models import (
    Release, ReleaseChange, RolloutState, RolloutStateTransition, ClusterState,
)


def test_release_defaults():
    r = Release(release_id="v1")
    assert r.changes == []
    assert r.description == ""


def test_release_with_description():
    r = Release(release_id="v2", description="hotfix")
    assert r.description == "hotfix"


def test_release_change_benign():
    c = ReleaseChange(change_id="ch1")
    assert c.disturbance is None


def test_release_change_with_disturbance():
    from scrutable.models import Disturbance, DisturbanceScope
    d = Disturbance(
        disturbance_id="d1",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_addend": 0.5},
    )
    c = ReleaseChange(change_id="ch2", disturbance=d)
    assert c.disturbance is d


def test_rollout_state_values():
    assert RolloutState.PENDING.value == "pending"
    assert RolloutState.IN_PROGRESS.value == "in_progress"
    assert RolloutState.HALTED.value == "halted"
    assert RolloutState.COMPLETED.value == "completed"
    assert RolloutState.ROLLED_BACK.value == "rolled_back"


def test_rollout_state_transition_fields():
    t = RolloutStateTransition(
        state=RolloutState.IN_PROGRESS,
        entered_at=1.0,
        exited_at=5.0,
    )
    assert t.state == RolloutState.IN_PROGRESS
    assert t.entered_at == 1.0
    assert t.exited_at == 5.0


def test_cluster_state_capacity_weight_defaults_to_one():
    cs = ClusterState(cluster_id="c1", region_id="r1")
    assert cs.capacity_weight == 1.0


def test_cluster_state_custom_capacity_weight():
    cs = ClusterState(cluster_id="c1", region_id="r1", capacity_weight=3.0)
    assert cs.capacity_weight == 3.0

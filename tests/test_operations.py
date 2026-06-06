import pytest
from scrutable.models import Release, ReleaseChange
from scrutable.rollout import Rollout
from scrutable.operations import RolloutSystem, OperationsSystem


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


def test_rollout_system_register_and_get():
    release = Release(release_id="v1")
    rollout = Rollout(release, ["r1c1"], stage_interval=10.0)
    system = RolloutSystem()
    system.register(rollout)
    assert system.get("v1") is rollout


def test_rollout_system_get_unknown_raises():
    system = RolloutSystem()
    with pytest.raises(ValueError, match="v99"):
        system.get("v99")


def test_rollout_system_all_rollouts():
    system = RolloutSystem()
    r1 = Rollout(Release(release_id="v1"), ["r1c1"], stage_interval=10.0)
    r2 = Rollout(Release(release_id="v2"), ["r1c2"], stage_interval=10.0)
    system.register(r1)
    system.register(r2)
    assert set(r.status.release_id for r in system.all_rollouts()) == {"v1", "v2"}

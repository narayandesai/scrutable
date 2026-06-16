import pytest
from scrutable.rollout import AlarmLog, RolloutActuator, Rollout
from scrutable.models import (
    Release, ReleaseChange, Disturbance, DisturbanceScope, RolloutState, Alarm,
)
from scrutable.plant import PlantConfig, Plant
from scrutable.operations import RolloutSystem, OperationsSystem
from scrutable.event_loop import EventLoop


def _plant() -> Plant:
    return Plant(PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1", "r1c2"]},
        nodes={"r1c1": ["r1c1n1"], "r1c2": ["r1c2n1"]},
    ))


def _latency_release() -> Release:
    d = Disturbance(
        disturbance_id="bug",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_addend": 0.5},
    )
    return Release(release_id="v1", changes=[ReleaseChange(change_id="ch1", disturbance=d)])


def _alarm() -> Alarm:
    return Alarm(
        detector_id="d1", fault_type="latency_degradation",
        target_id="cluster", target_level="cluster", severity=0.5,
        detected_at=5.0, window_start=4.0, window_end=5.0,
    )


def test_actuator_records_alarm_to_log():
    plant = _plant()
    loop = EventLoop()
    release = _latency_release()
    rollout = Rollout(release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(plant, {}, loop)
    rollout._deploy_stage(0, sim_time=1.0)

    log = AlarmLog()
    actuator = RolloutActuator(rollout, log, rollback_duration=100.0)
    actuator.act(_alarm(), 5.0, RolloutSystem(), OperationsSystem(plant))
    assert log.any_since(5.0)


def test_actuator_halts_and_begins_rollback_for_in_progress():
    plant = _plant()
    loop = EventLoop()
    release = _latency_release()
    rollout = Rollout(release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(plant, {}, loop)
    rollout._deploy_stage(0, sim_time=1.0)

    log = AlarmLog()
    actuator = RolloutActuator(rollout, log, rollback_duration=100.0)
    actuator.act(_alarm(), 5.0, RolloutSystem(), OperationsSystem(plant))
    assert rollout.status.state == RolloutState.ROLLING_BACK


def test_actuator_noop_for_completed_rollout():
    plant = _plant()
    release = _latency_release()
    rollout = Rollout(release, ["r1c1"], stage_interval=10.0)
    rollout._activate(plant, {})
    rollout._deploy_stage(0, sim_time=1.0)
    assert rollout.status.state == RolloutState.COMPLETED

    log = AlarmLog()
    actuator = RolloutActuator(rollout, log, rollback_duration=100.0)
    actuator.act(_alarm(), 5.0, RolloutSystem(), OperationsSystem(plant))
    assert rollout.status.state == RolloutState.COMPLETED


def test_actuator_calls_on_failure_with_release_and_time():
    plant = _plant()
    loop = EventLoop()
    release = _latency_release()
    rollout = Rollout(release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(plant, {}, loop)
    rollout._deploy_stage(0, sim_time=1.0)

    log = AlarmLog()
    fired: list[tuple[Release, float]] = []
    actuator = RolloutActuator(
        rollout, log, rollback_duration=100.0,
        on_failure=lambda r, t: fired.append((r, t)),
    )
    actuator.act(_alarm(), 5.0, RolloutSystem(), OperationsSystem(plant))
    assert len(fired) == 1
    assert fired[0][0] is release
    assert fired[0][1] == pytest.approx(5.0)


def test_actuator_does_not_call_on_failure_when_not_in_progress():
    plant = _plant()
    release = _latency_release()
    rollout = Rollout(release, ["r1c1"], stage_interval=10.0)
    rollout._activate(plant, {})
    rollout._deploy_stage(0, sim_time=1.0)  # COMPLETED

    log = AlarmLog()
    fired: list = []
    actuator = RolloutActuator(
        rollout, log, rollback_duration=100.0,
        on_failure=lambda r, t: fired.append((r, t)),
    )
    actuator.act(_alarm(), 5.0, RolloutSystem(), OperationsSystem(plant))
    assert len(fired) == 0

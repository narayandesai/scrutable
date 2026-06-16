import pytest
from scrutable.rollout import AlarmLog
from scrutable.models import Alarm


def _alarm(detected_at: float = 0.0) -> Alarm:
    return Alarm(
        detector_id="d1",
        fault_type="latency_degradation",
        target_id="cluster",
        target_level="cluster",
        severity=0.5,
        detected_at=detected_at,
        window_start=detected_at - 1.0,
        window_end=detected_at,
    )


def test_empty_log_any_since_returns_false():
    log = AlarmLog()
    assert not log.any_since(0.0)


def test_any_since_before_record_returns_true():
    log = AlarmLog()
    log.record(_alarm(), sim_time=5.0)
    assert log.any_since(4.0)


def test_any_since_at_exact_record_time_returns_true():
    log = AlarmLog()
    log.record(_alarm(), sim_time=5.0)
    assert log.any_since(5.0)


def test_any_since_after_record_returns_false():
    log = AlarmLog()
    log.record(_alarm(), sim_time=5.0)
    assert not log.any_since(6.0)


def test_any_since_with_multiple_records():
    log = AlarmLog()
    log.record(_alarm(), sim_time=3.0)
    log.record(_alarm(), sim_time=7.0)
    assert log.any_since(6.0)   # second alarm at 7.0 qualifies
    assert not log.any_since(8.0)

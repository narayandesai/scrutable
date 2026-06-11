from scrutable.models import Response, Signal, Alarm
from scrutable.sensor import Sensor
from scrutable.detector import Detector
from scrutable.actuator import Actuator
from scrutable.operations import RolloutSystem, OperationsSystem


class HighErrorRateSensor:
    sensor_id = "high-error-rate-sensor"
    window_size = 60.0
    sampling_period = 10.0

    def measure(self, window: list[Response]) -> list[Signal]:
        if not window:
            return []
        error_rate = sum(1 for r in window if r.error_code != 0) / len(window)
        t_start = min(r.issued_at for r in window)
        t_end = max(r.issued_at + r.latency for r in window)
        return [Signal(
            sensor_id=self.sensor_id,
            metric="error_rate",
            value=error_rate,
            window_start=t_start,
            window_end=t_end,
            sample_count=len(window),
        )]


class HighErrorRateDetector:
    detector_id = "high-error-rate"

    def detect(self, signals: list[Signal]) -> list[Alarm]:
        for sig in signals:
            if sig.metric == "error_rate" and sig.value > 0.1:
                return [Alarm(
                    detector_id=self.detector_id,
                    fault_type="high_error_rate",
                    target_id="unknown",
                    target_level="cluster",
                    severity=min(1.0, sig.value),
                    detected_at=sig.window_end,
                    window_start=sig.window_start,
                    window_end=sig.window_end,
                )]
        return []


class DrainActuator:
    def __init__(self):
        self.calls: list[tuple] = []

    def act(self, alarm: Alarm, sim_time: float, rollouts: RolloutSystem, ops: OperationsSystem) -> None:
        self.calls.append((alarm.fault_type, sim_time))


def test_sensor_protocol_satisfied():
    s = HighErrorRateSensor()
    assert isinstance(s, Sensor)


def test_detector_protocol_satisfied():
    d = HighErrorRateDetector()
    assert isinstance(d, Detector)


def test_actuator_protocol_satisfied():
    a = DrainActuator()
    assert isinstance(a, Actuator)


def test_sensor_produces_signal_on_errors():
    s = HighErrorRateSensor()
    window = [
        Response(request_id=f"r{i}", workload_id="w", node_id="n",
                 cluster_id="c", region_id="r",
                 issued_at=float(i), latency=0.01, error_code=1)
        for i in range(20)
    ]
    signals = s.measure(window)
    assert len(signals) == 1
    assert signals[0].metric == "error_rate"
    assert signals[0].value == 1.0


def test_sensor_produces_zero_error_rate_on_clean_window():
    s = HighErrorRateSensor()
    window = [
        Response(request_id=f"r{i}", workload_id="w", node_id="n",
                 cluster_id="c", region_id="r",
                 issued_at=float(i), latency=0.01, error_code=0)
        for i in range(20)
    ]
    signals = s.measure(window)
    assert signals[0].value == 0.0


def test_sensor_empty_window_returns_no_signals():
    s = HighErrorRateSensor()
    assert s.measure([]) == []


def test_detector_fires_on_high_error_signal():
    d = HighErrorRateDetector()
    signals = [Signal(sensor_id="s", metric="error_rate", value=0.5,
                      window_start=0.0, window_end=10.0, sample_count=100)]
    alarms = d.detect(signals)
    assert len(alarms) == 1
    assert alarms[0].fault_type == "high_error_rate"


def test_detector_silent_on_low_error_signal():
    d = HighErrorRateDetector()
    signals = [Signal(sensor_id="s", metric="error_rate", value=0.01,
                      window_start=0.0, window_end=10.0, sample_count=100)]
    assert d.detect(signals) == []


def test_detector_silent_on_empty_signals():
    d = HighErrorRateDetector()
    assert d.detect([]) == []


def test_detector_ignores_unrelated_metric():
    d = HighErrorRateDetector()
    signals = [Signal(sensor_id="s", metric="latency_p99", value=999.0,
                      window_start=0.0, window_end=10.0, sample_count=100)]
    assert d.detect(signals) == []


def test_actuator_receives_alarm():
    sensor = HighErrorRateSensor()
    detector = HighErrorRateDetector()
    actuator = DrainActuator()
    ops = OperationsSystem.__new__(OperationsSystem)
    rollouts = RolloutSystem()
    signals = sensor.measure([
        Response(request_id=f"r{i}", workload_id="w", node_id="n",
                 cluster_id="c", region_id="r",
                 issued_at=float(i), latency=0.01, error_code=1)
        for i in range(20)
    ])
    for alarm in detector.detect(signals):
        actuator.act(alarm, 60.0, rollouts, ops)
    assert len(actuator.calls) == 1
    assert actuator.calls[0] == ("high_error_rate", 60.0)

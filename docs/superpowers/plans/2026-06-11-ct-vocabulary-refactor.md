# Control Theory Vocabulary Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align implementation naming with control theory vocabulary: split the combined Sensor/Detector into two separate concepts; rename `Inference`→`Alarm` (+ field renames); rename `WorkloadProfile`→`PlantProfile`; rename `InputSynthesizer`→`InputProcess`.

**Architecture:** A `Sensor` measures the plant output from raw responses and produces a `Signal` (windowed metric). A `Detector` thresholds a list of `Signal`s and produces `Alarm`s. The engine drives ticks from sensors; on each tick it pipes sensor output to all detectors, then actuators. This cleanly separates measurement from decision.

**Tech Stack:** Python 3.13, dataclasses, typing.Protocol, pytest

---

## File Map

**Modified:**
- `src/scrutable/models.py` — add `Signal`; rename `Inference`→`Alarm`; `pathology_type`→`fault_type`; `confidence`→`severity`
- `src/scrutable/sensor.py` *(new)* — `Sensor` Protocol
- `src/scrutable/detector.py` — update: takes `list[Signal]` → `list[Alarm]`; remove `window_size`/`sampling_period` fields
- `src/scrutable/actuator.py` — update: takes `Alarm` instead of `Inference`
- `src/scrutable/detectors/slo.py` — add `LatencySloSensor`, `ErrorRateSloSensor`; rewrite detectors to take `Signal`→`Alarm`
- `src/scrutable/engine.py` — split `_detectors` into `_sensors`+`_detectors`; drive tick from sensors; `add_sensor()` validates `sampling_period`
- `src/scrutable/profiles.py` — `WorkloadProfile`→`PlantProfile`; `sample_workload` signature unchanged
- `src/scrutable/synthesizer.py` — `InputSynthesizer`→`InputProcess`
- `src/scrutable/__init__.py` — export `Signal`, `Alarm`, `Sensor`, `LatencySloSensor`, `ErrorRateSloSensor`, `PlantProfile`, `InputProcess`; remove old names
- `src/scrutable/scenarios/slo_performance.py` — `WorkloadProfile`→`PlantProfile`; split detector instantiation
- `src/scrutable/scenarios/slo_spectrum.py` — same; `tick_interval`→`sampling_period`

**Tests modified:**
- `tests/test_models.py` — `test_inference_fields`→`test_alarm_fields`; add `test_signal_fields`
- `tests/test_detector.py` — rewrite inline classes to new protocol; `Inference`→`Alarm`; field renames
- `tests/test_profiles.py` — `WorkloadProfile`→`PlantProfile`
- `tests/test_slo_detector.py` — major rewrite: add sensor tests; update detector tests for new protocol
- `tests/test_synthesizer.py` — `InputSynthesizer`→`InputProcess`
- `tests/test_scenario.py` — rewrite inline `AlwaysFiresDetector` into sensor+detector pair; `Inference`→`Alarm`

---

## Task 1: Add `Signal`, rename `Inference`→`Alarm`, field renames in models

**Files:**
- Modify: `src/scrutable/models.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write failing test for new model names**

In `tests/test_models.py`, replace `test_inference_fields` and add `test_signal_fields`:

```python
# replace test_inference_fields:
def test_alarm_fields():
    a = Alarm(
        detector_id="d1",
        fault_type="hardware_fault",
        target_id="n1",
        target_level="node",
        severity=0.9,
        detected_at=10.0,
        window_start=0.0,
        window_end=10.0,
    )
    assert a.severity == 0.9
    assert a.fault_type == "hardware_fault"

# add:
def test_signal_fields():
    s = Signal(
        sensor_id="s1",
        metric="latency_p99.9",
        value=0.42,
        window_start=0.0,
        window_end=1.0,
        sample_count=500,
    )
    assert s.value == 0.42
    assert s.sample_count == 500
```

Update imports at top of `tests/test_models.py`:
```python
from scrutable.models import (
    WorkloadModel,
    WorkloadState,
    NodeState,
    ClusterState,
    Request,
    Response,
    DisturbanceScope,
    Disturbance,
    Alarm,
    Signal,
)
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_models.py -v
```
Expected: `ImportError` or `AttributeError` on `Alarm`/`Signal`.

- [ ] **Step 3: Update `src/scrutable/models.py`**

Replace the `Inference` dataclass with `Alarm`, add `Signal`:

```python
@dataclass
class Signal:
    sensor_id: str
    metric: str
    value: float
    window_start: float
    window_end: float
    sample_count: int


@dataclass
class Alarm:
    detector_id: str
    fault_type: str
    target_id: str
    target_level: str
    severity: float
    detected_at: float
    window_start: float
    window_end: float
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_models.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/models.py tests/test_models.py
git commit -m "refactor: rename Inference→Alarm, add Signal, pathology_type→fault_type, confidence→severity"
```

---

## Task 2: Create `Sensor` protocol; update `Detector` and `Actuator` protocols

**Files:**
- Create: `src/scrutable/sensor.py`
- Modify: `src/scrutable/detector.py`
- Modify: `src/scrutable/actuator.py`

- [ ] **Step 1: Write failing tests for new protocols**

In `tests/test_detector.py`, replace the file's inline class definitions and imports with the new protocol shapes. The existing `HighErrorRateDetector` combined sensor+detector — split it and update all tests:

```python
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


def test_sensor_produces_signal_on_errors(build_response):
    s = HighErrorRateSensor()
    window = [build_response(error_code=1) for _ in range(20)]
    signals = s.measure(window)
    assert len(signals) == 1
    assert signals[0].metric == "error_rate"
    assert signals[0].value > 0.0


def test_sensor_produces_zero_error_rate_on_clean_window(build_response):
    s = HighErrorRateSensor()
    window = [build_response(error_code=0) for _ in range(20)]
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_detector.py -v
```
Expected: `ImportError` on `Sensor` / `Signal` / `Alarm` from new modules.

- [ ] **Step 3: Create `src/scrutable/sensor.py`**

```python
from __future__ import annotations
from typing import Protocol, runtime_checkable
from scrutable.models import Response, Signal


@runtime_checkable
class Sensor(Protocol):
    sensor_id: str
    window_size: float
    sampling_period: float

    def measure(self, window: list[Response]) -> list[Signal]: ...
```

- [ ] **Step 4: Update `src/scrutable/detector.py`**

```python
from __future__ import annotations
from typing import Protocol, runtime_checkable
from scrutable.models import Signal, Alarm


@runtime_checkable
class Detector(Protocol):
    detector_id: str

    def detect(self, signals: list[Signal]) -> list[Alarm]: ...
```

- [ ] **Step 5: Update `src/scrutable/actuator.py`**

Replace `Inference` with `Alarm` throughout:

```python
from __future__ import annotations
from typing import Protocol, runtime_checkable
from scrutable.models import Alarm
from scrutable.operations import RolloutSystem, OperationsSystem


@runtime_checkable
class Actuator(Protocol):
    def act(
        self,
        alarm: Alarm,
        sim_time: float,
        rollouts: RolloutSystem,
        ops: OperationsSystem,
    ) -> None: ...
```

- [ ] **Step 6: Run tests to confirm they pass**

```
pytest tests/test_detector.py -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/scrutable/sensor.py src/scrutable/detector.py src/scrutable/actuator.py tests/test_detector.py
git commit -m "refactor: create Sensor protocol, update Detector to Signal→Alarm, update Actuator"
```

---

## Task 3: Split SLO classes into sensors + detectors

**Files:**
- Modify: `src/scrutable/detectors/slo.py`
- Modify: `tests/test_slo_detector.py`

- [ ] **Step 1: Write failing tests for new SLO sensor and detector classes**

Replace `tests/test_slo_detector.py` entirely:

```python
import numpy as np
import pytest
from scrutable.models import Response, Signal, Alarm
from scrutable.sensor import Sensor
from scrutable.detector import Detector
from scrutable.observations import ObservationBuffer
from scrutable.detectors.slo import (
    SloTarget,
    LatencySloCalibrator,
    LatencySloSensor,
    LatencySloDetector,
    ErrorRateSloTarget,
    ErrorRateSloCalibrator,
    ErrorRateSloSensor,
    ErrorRateSloDetector,
)


def make_responses(n: int, latency: float, issued_at_start: float = 0.0) -> list[Response]:
    return [
        Response(
            request_id=f"req-{i}", workload_id="wl1", node_id="r1c1n1",
            cluster_id="r1c1", region_id="r1",
            issued_at=issued_at_start + i * 0.001,
            latency=latency, error_code=0,
        )
        for i in range(n)
    ]


def make_responses_with_errors(n: int, error_rate: float, issued_at_start: float = 0.0) -> list[Response]:
    return [
        Response(
            request_id=f"req-{i}", workload_id="wl1", node_id="r1c1n1",
            cluster_id="r1c1", region_id="r1",
            issued_at=issued_at_start + i * 0.001,
            latency=0.05, error_code=1 if i / n < error_rate else 0,
        )
        for i in range(n)
    ]


# --- LatencySloCalibrator (unchanged) ---

def test_burn_in_calibrator_returns_slo_target():
    buf = ObservationBuffer()
    for r in make_responses(2000, latency=0.05):
        buf.append(r)
    calibrator = LatencySloCalibrator(multiplier=2.0)
    target = calibrator.calibrate(buf, calibration_end=2.0, percentile=99.9, window_size=2.0)
    assert isinstance(target, SloTarget)
    assert target.percentile == 99.9
    assert target.window_size == 2.0


def test_burn_in_calibrator_threshold_above_baseline():
    buf = ObservationBuffer()
    for r in make_responses(2000, latency=0.05):
        buf.append(r)
    calibrator = LatencySloCalibrator(multiplier=2.0)
    target = calibrator.calibrate(buf, calibration_end=2.0, percentile=99.9, window_size=2.0)
    assert target.threshold > 0.05


def test_burn_in_calibrator_threshold_scales_with_multiplier():
    buf = ObservationBuffer()
    for r in make_responses(2000, latency=0.05):
        buf.append(r)
    t2 = LatencySloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, percentile=99.9, window_size=2.0)
    t3 = LatencySloCalibrator(multiplier=3.0).calibrate(buf, calibration_end=2.0, percentile=99.9, window_size=2.0)
    assert t3.threshold > t2.threshold


def test_burn_in_calibrator_respects_percentile():
    buf = ObservationBuffer()
    rng = np.random.default_rng(0)
    for i in range(5000):
        r = Response(
            request_id=f"r{i}", workload_id="w", node_id="n", cluster_id="c", region_id="r",
            issued_at=i * 0.001, latency=float(rng.lognormal(-2.3, 0.5)), error_code=0,
        )
        buf.append(r)
    t90 = LatencySloCalibrator(multiplier=1.0).calibrate(buf, calibration_end=5.0, percentile=90.0, window_size=5.0)
    t999 = LatencySloCalibrator(multiplier=1.0).calibrate(buf, calibration_end=5.0, percentile=99.9, window_size=5.0)
    assert t999.threshold > t90.threshold


def test_burn_in_calibrator_raises_on_empty_window():
    buf = ObservationBuffer()
    with pytest.raises(ValueError):
        LatencySloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, percentile=99.9, window_size=2.0)


# --- LatencySloSensor ---

def test_latency_sensor_satisfies_sensor_protocol():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    assert isinstance(sensor, Sensor)


def test_latency_sensor_produces_signal_from_window():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    window = make_responses(2000, latency=0.05)
    signals = sensor.measure(window)
    assert len(signals) == 1
    assert signals[0].metric == "latency_p99.9"
    assert signals[0].sensor_id == "lat"
    assert signals[0].sample_count == 2000
    assert signals[0].value > 0.0


def test_latency_sensor_empty_window_returns_no_signals():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    assert sensor.measure([]) == []


def test_latency_sensor_window_size_from_target():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=30.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=30.0)
    assert sensor.window_size == 30.0


def test_latency_sensor_value_reflects_percentile():
    target_p50 = SloTarget(percentile=50.0, threshold=0.1, window_size=1.0)
    target_p99 = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    rng = np.random.default_rng(0)
    window = [
        Response(request_id=f"r{i}", workload_id="w", node_id="n", cluster_id="c", region_id="r",
                 issued_at=i * 0.001, latency=float(rng.lognormal(-2.3, 0.5)), error_code=0)
        for i in range(2000)
    ]
    sig_p50 = LatencySloSensor(sensor_id="s", target=target_p50, sampling_period=1.0).measure(window)[0]
    sig_p99 = LatencySloSensor(sensor_id="s", target=target_p99, sampling_period=1.0).measure(window)[0]
    assert sig_p99.value > sig_p50.value


# --- LatencySloDetector ---

def test_latency_detector_satisfies_detector_protocol():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    detector = LatencySloDetector(detector_id="slo", target=target)
    assert isinstance(detector, Detector)


def test_latency_detector_fires_alarm_above_threshold():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target)
    signals = sensor.measure(make_responses(2000, latency=1.0))
    alarms = detector.detect(signals)
    assert len(alarms) == 1
    assert alarms[0].detector_id == "slo-test"
    assert alarms[0].fault_type == "latency_degradation"
    assert alarms[0].severity > 0.0


def test_latency_detector_silent_below_threshold():
    target = SloTarget(percentile=99.9, threshold=1.0, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target)
    signals = sensor.measure(make_responses(2000, latency=0.05))
    assert detector.detect(signals) == []


def test_latency_detector_silent_on_empty_signals():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target)
    assert detector.detect([]) == []


def test_latency_detector_severity_higher_further_above_threshold():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    sensor = LatencySloSensor(sensor_id="lat", target=target, sampling_period=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target)
    sev_slight = detector.detect(sensor.measure(make_responses(2000, latency=0.12)))[0].severity
    sev_large = detector.detect(sensor.measure(make_responses(2000, latency=2.0)))[0].severity
    assert sev_large > sev_slight


def test_latency_detector_ignores_unrelated_metric():
    target = SloTarget(percentile=99.9, threshold=0.1, window_size=1.0)
    detector = LatencySloDetector(detector_id="slo-test", target=target)
    unrelated = [Signal(sensor_id="s", metric="error_rate", value=999.0,
                        window_start=0.0, window_end=1.0, sample_count=100)]
    assert detector.detect(unrelated) == []


# --- ErrorRateSloTarget / Calibrator / Sensor / Detector ---

def test_error_rate_slo_target_fields():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    assert target.threshold == 0.001
    assert target.window_size == 300.0


def test_error_rate_calibrator_returns_target():
    buf = ObservationBuffer()
    for r in make_responses_with_errors(2000, error_rate=0.01):
        buf.append(r)
    target = ErrorRateSloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, window_size=2.0)
    assert isinstance(target, ErrorRateSloTarget)
    assert target.threshold > 0.01
    assert target.window_size == 2.0


def test_error_rate_calibrator_scales_with_multiplier():
    buf = ObservationBuffer()
    for r in make_responses_with_errors(2000, error_rate=0.01):
        buf.append(r)
    t2 = ErrorRateSloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, window_size=2.0)
    t3 = ErrorRateSloCalibrator(multiplier=3.0).calibrate(buf, calibration_end=2.0, window_size=2.0)
    assert t3.threshold > t2.threshold


def test_error_rate_calibrator_raises_on_empty_window():
    buf = ObservationBuffer()
    with pytest.raises(ValueError):
        ErrorRateSloCalibrator(multiplier=2.0).calibrate(buf, calibration_end=2.0, window_size=2.0)


def test_error_rate_sensor_satisfies_sensor_protocol():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    assert isinstance(sensor, Sensor)


def test_error_rate_sensor_produces_signal():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    window = make_responses_with_errors(1000, error_rate=0.05)
    signals = sensor.measure(window)
    assert len(signals) == 1
    assert signals[0].metric == "error_rate"
    assert abs(signals[0].value - 0.05) < 0.01


def test_error_rate_sensor_empty_window_returns_no_signals():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    assert sensor.measure([]) == []


def test_error_rate_detector_satisfies_detector_protocol():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    detector = ErrorRateSloDetector(detector_id="err-det", target=target)
    assert isinstance(detector, Detector)


def test_error_rate_detector_fires_when_rate_exceeds_threshold():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target)
    signals = sensor.measure(make_responses_with_errors(1000, error_rate=0.05))
    alarms = detector.detect(signals)
    assert len(alarms) == 1
    assert alarms[0].detector_id == "err-test"
    assert alarms[0].fault_type == "error_rate_degradation"
    assert alarms[0].severity > 0.0


def test_error_rate_detector_silent_below_threshold():
    target = ErrorRateSloTarget(threshold=0.05, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target)
    signals = sensor.measure(make_responses_with_errors(1000, error_rate=0.01))
    assert detector.detect(signals) == []


def test_error_rate_detector_silent_on_empty_signals():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target)
    assert detector.detect([]) == []


def test_error_rate_detector_zero_errors_silent_above_zero_threshold():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    sensor = ErrorRateSloSensor(sensor_id="err", target=target, sampling_period=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target)
    signals = sensor.measure(make_responses_with_errors(1000, error_rate=0.0))
    assert detector.detect(signals) == []


def test_error_rate_detector_ignores_latency_metric():
    target = ErrorRateSloTarget(threshold=0.001, window_size=300.0)
    detector = ErrorRateSloDetector(detector_id="err-test", target=target)
    latency_signals = [Signal(sensor_id="s", metric="latency_p99.9", value=999.0,
                              window_start=0.0, window_end=1.0, sample_count=100)]
    assert detector.detect(latency_signals) == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_slo_detector.py -v
```
Expected: `ImportError` on `LatencySloSensor`/`ErrorRateSloSensor`.

- [ ] **Step 3: Rewrite `src/scrutable/detectors/slo.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scrutable.models import Response, Signal, Alarm
from scrutable.observations import ObservationBuffer


@dataclass
class SloTarget:
    percentile: float
    threshold: float
    window_size: float


@dataclass
class LatencySloCalibrator:
    multiplier: float

    def calibrate(
        self,
        buf: ObservationBuffer,
        calibration_end: float,
        percentile: float,
        window_size: float,
    ) -> SloTarget:
        window = buf.window(0.0, calibration_end)
        if not window:
            raise ValueError("No responses in calibration window")
        latencies = np.array([r.latency for r in window])
        p = float(np.percentile(latencies, percentile))
        return SloTarget(percentile=percentile, threshold=p * self.multiplier, window_size=window_size)


@dataclass
class LatencySloSensor:
    sensor_id: str
    window_size: float
    sampling_period: float
    _percentile: float

    def __init__(self, sensor_id: str, target: SloTarget, sampling_period: float) -> None:
        self.sensor_id = sensor_id
        self.window_size = target.window_size
        self.sampling_period = sampling_period
        self._percentile = target.percentile

    def measure(self, window: list[Response]) -> list[Signal]:
        if not window:
            return []
        latencies = np.array([r.latency for r in window])
        value = float(np.percentile(latencies, self._percentile))
        t_start = min(r.issued_at for r in window)
        t_end = max(r.issued_at + r.latency for r in window)
        return [Signal(
            sensor_id=self.sensor_id,
            metric=f"latency_p{self._percentile}",
            value=value,
            window_start=t_start,
            window_end=t_end,
            sample_count=len(window),
        )]


@dataclass
class LatencySloDetector:
    detector_id: str
    _target: SloTarget
    _metric: str

    def __init__(self, detector_id: str, target: SloTarget) -> None:
        self.detector_id = detector_id
        self._target = target
        self._metric = f"latency_p{target.percentile}"

    def detect(self, signals: list[Signal]) -> list[Alarm]:
        for signal in signals:
            if signal.metric != self._metric:
                continue
            if signal.value <= self._target.threshold:
                continue
            ratio = signal.value / self._target.threshold
            severity = min(1.0, (ratio - 1.0) / 9.0)
            return [Alarm(
                detector_id=self.detector_id,
                fault_type="latency_degradation",
                target_id="cluster",
                target_level="cluster",
                severity=severity,
                detected_at=signal.window_end,
                window_start=signal.window_start,
                window_end=signal.window_end,
            )]
        return []


@dataclass
class ErrorRateSloTarget:
    threshold: float
    window_size: float


@dataclass
class ErrorRateSloCalibrator:
    multiplier: float

    def calibrate(
        self,
        buf: ObservationBuffer,
        calibration_end: float,
        window_size: float,
    ) -> ErrorRateSloTarget:
        window = buf.window(0.0, calibration_end)
        if not window:
            raise ValueError("No responses in calibration window")
        error_rate = sum(1 for r in window if r.error_code != 0) / len(window)
        return ErrorRateSloTarget(threshold=error_rate * self.multiplier, window_size=window_size)


@dataclass
class ErrorRateSloSensor:
    sensor_id: str
    window_size: float
    sampling_period: float

    def __init__(self, sensor_id: str, target: ErrorRateSloTarget, sampling_period: float) -> None:
        self.sensor_id = sensor_id
        self.window_size = target.window_size
        self.sampling_period = sampling_period

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


@dataclass
class ErrorRateSloDetector:
    detector_id: str
    _target: ErrorRateSloTarget

    def __init__(self, detector_id: str, target: ErrorRateSloTarget) -> None:
        self.detector_id = detector_id
        self._target = target

    def detect(self, signals: list[Signal]) -> list[Alarm]:
        for signal in signals:
            if signal.metric != "error_rate":
                continue
            if signal.value <= self._target.threshold:
                continue
            ratio = signal.value / self._target.threshold if self._target.threshold > 0 else float("inf")
            severity = min(1.0, (ratio - 1.0) / 9.0)
            return [Alarm(
                detector_id=self.detector_id,
                fault_type="error_rate_degradation",
                target_id="cluster",
                target_level="cluster",
                severity=severity,
                detected_at=signal.window_end,
                window_start=signal.window_start,
                window_end=signal.window_end,
            )]
        return []
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_slo_detector.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/detectors/slo.py tests/test_slo_detector.py
git commit -m "refactor: add LatencySloSensor, ErrorRateSloSensor; detectors now take Signal→Alarm"
```

---

## Task 4: Update engine for sensor/detector split

**Files:**
- Modify: `src/scrutable/engine.py`
- Modify: `tests/test_scenario.py`

- [ ] **Step 1: Write failing tests**

Update `tests/test_scenario.py` to use the new sensor+detector split and `Alarm`:

```python
import numpy as np
from scrutable.models import WorkloadModel, Disturbance, DisturbanceScope, WorkloadState, Signal, Alarm
from scrutable.disturbance import TimedDisturbance
from scrutable.engine import SimulationEngine
from scrutable.sensor import Sensor
from scrutable.detector import Detector
from scrutable.actuator import Actuator
from scrutable.operations import RolloutSystem, OperationsSystem
from scrutable.traffic import WorkloadEntry, WorkloadMix


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
    from scrutable.plant import PlantConfig, Plant
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
    e1 = SimulationEngine(Plant(config), mix=WorkloadMix(total_rate=50.0, period=3600.0, entries=[WorkloadEntry(model=WorkloadModel(workload_id="wl1", latency_median=0.1, latency_sigma=0.3, error_scale=1000.0, error_shape=1.5, noise_sigma=0.001), share=1.0)]), seed=99)
    e2 = SimulationEngine(Plant(config), mix=WorkloadMix(total_rate=50.0, period=3600.0, entries=[WorkloadEntry(model=WorkloadModel(workload_id="wl1", latency_median=0.1, latency_sigma=0.3, error_scale=1000.0, error_shape=1.5, noise_sigma=0.001), share=1.0)]), seed=99)
    e1.run(2.0); e2.run(2.0)
    r1 = e1.buffer.window(0.0, 3.0); r2 = e2.buffer.window(0.0, 3.0)
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
        from scrutable.models import Response
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
    sensor = AlwaysFiresSensor()
    detector = AlwaysFiresDetector()
    actuator = RecordingActuator()
    engine.add_sensor(sensor)
    engine.add_detector(detector)
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_scenario.py -v
```
Expected: failures on `add_sensor`, `AlwaysFiresSensor`, etc.

- [ ] **Step 3: Update `src/scrutable/engine.py`**

Replace `_detectors: list[Detector]` with `_sensors: list[Sensor]` and `_detectors: list[Detector]`; update imports; change `add_detector` to `add_sensor`; add `add_detector`; update tick scheduling:

```python
from scrutable.sensor import Sensor
from scrutable.detector import Detector
# remove: from scrutable.detector import Detector (old protocol)

# In __init__:
self._sensors: list[Sensor] = []
self._detectors: list[Detector] = []

# Replace add_detector:
def add_sensor(self, sensor: Sensor) -> None:
    if sensor.sampling_period <= 0:
        raise ValueError(
            f"sensor.sampling_period must be > 0, got {sensor.sampling_period!r}"
        )
    self._sensors.append(sensor)

def add_detector(self, detector: Detector) -> None:
    self._detectors.append(detector)

# Replace _schedule_detector_tick with _schedule_sensor_tick:
def _schedule_sensor_tick(self, sensor: Sensor, current_time: float) -> None:
    next_tick = current_time + sensor.sampling_period

    def tick(s=sensor, t=next_tick) -> None:
        window = self._buffer.window(t - s.window_size, t)
        signals = s.measure(window)
        for detector in self._detectors:
            alarms = detector.detect(signals)
            for alarm in alarms:
                for act in self._actuators:
                    act.act(alarm, t, self._rollouts, self._ops)
        self._schedule_sensor_tick(s, t)

    self._loop.schedule(next_tick, tick)

# In run(), replace detector scheduling:
for sensor in self._sensors:
    self._schedule_sensor_tick(sensor, 0.0)
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_scenario.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/engine.py tests/test_scenario.py
git commit -m "refactor: engine drives ticks from Sensor; Detector receives Signal list"
```

---

## Task 5: Rename `WorkloadProfile` → `PlantProfile`

**Files:**
- Modify: `src/scrutable/profiles.py`
- Modify: `tests/test_profiles.py`

- [ ] **Step 1: Update `tests/test_profiles.py`**

Replace all `WorkloadProfile` with `PlantProfile` in imports and test bodies:

```python
from scrutable.profiles import (
    FieldDist,
    PlantProfile,
    sample_workload,
    CONSISTENT_FAST,
    HIGH_VARIANCE_LATENCY,
    BURSTY_ERRORS,
    SLOW_RELIABLE,
    LATENCY_VARIANCE_SPECTRUM,
)
```

In `test_error_shape_clamped_to_minimum`:
```python
    profile = PlantProfile(
        name="test",
        ...
    )
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_profiles.py -v
```
Expected: `ImportError` on `PlantProfile`.

- [ ] **Step 3: Rename in `src/scrutable/profiles.py`**

Replace `WorkloadProfile` with `PlantProfile` everywhere in the file. The `sample_workload` signature becomes `sample_workload(profile: PlantProfile, ...)`. The `LATENCY_VARIANCE_SPECTRUM` type annotation becomes `list[PlantProfile]`.

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_profiles.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/profiles.py tests/test_profiles.py
git commit -m "refactor: rename WorkloadProfile→PlantProfile"
```

---

## Task 6: Rename `InputSynthesizer` → `InputProcess`

**Files:**
- Modify: `src/scrutable/synthesizer.py`
- Modify: `tests/test_synthesizer.py`

- [ ] **Step 1: Update `tests/test_synthesizer.py`**

Replace all `InputSynthesizer` with `InputProcess`:

```python
from scrutable.synthesizer import InputProcess

# In _make_synth:
synth = InputProcess(mix, loop, sim, rng)
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_synthesizer.py -v
```
Expected: `ImportError` on `InputProcess`.

- [ ] **Step 3: Rename in `src/scrutable/synthesizer.py`**

Replace `class InputSynthesizer:` with `class InputProcess:` everywhere. Update `engine.py` import: `from scrutable.synthesizer import InputProcess` and `self._synthesizer = InputProcess(...)`.

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_synthesizer.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/synthesizer.py src/scrutable/engine.py tests/test_synthesizer.py
git commit -m "refactor: rename InputSynthesizer→InputProcess"
```

---

## Task 7: Update exports, scenarios, and remaining references

**Files:**
- Modify: `src/scrutable/__init__.py`
- Modify: `src/scrutable/scenarios/slo_performance.py`
- Modify: `src/scrutable/scenarios/slo_spectrum.py`
- Modify: `examples/basic_simulation.py`
- Modify: `tests/test_slo_performance.py` (import `PlantProfile`)
- Modify: `tests/test_slo_scenario.py` (import `PlantProfile`)
- Modify: `tests/test_engine_mix.py` (import `sample_workload` with `PlantProfile`)

- [ ] **Step 1: Update `src/scrutable/__init__.py`**

Update imports and `__all__`:
- Replace `Inference` with `Alarm`, add `Signal`
- Replace `WorkloadProfile` with `PlantProfile`
- Add `Sensor` from `scrutable.sensor`
- Replace SLO detector imports to include sensor classes: `LatencySloSensor`, `ErrorRateSloSensor`
- Remove `InputSynthesizer` if exported; add `InputProcess`

```python
from scrutable.models import (
    WorkloadModel, WorkloadState, NodeState, ClusterState,
    Request, Response, Disturbance, DisturbanceScope,
    Signal, Alarm, RolloutState, RolloutStateTransition,
    ReleaseStatus, ReleaseChange, Release,
)
from scrutable.sensor import Sensor
from scrutable.detector import Detector
from scrutable.detectors.slo import (
    SloTarget, LatencySloCalibrator, LatencySloSensor, LatencySloDetector,
    ErrorRateSloTarget, ErrorRateSloCalibrator, ErrorRateSloSensor, ErrorRateSloDetector,
)
from scrutable.profiles import (
    FieldDist, PlantProfile, sample_workload,
    CONSISTENT_FAST, HIGH_VARIANCE_LATENCY, BURSTY_ERRORS, SLOW_RELIABLE, LATENCY_VARIANCE_SPECTRUM,
)
```

Update `__all__` to match (replace `Inference`→`Alarm`, `WorkloadProfile`→`PlantProfile`, add `Signal`, `Sensor`, `LatencySloSensor`, `ErrorRateSloSensor`).

- [ ] **Step 2: Update `src/scrutable/scenarios/slo_spectrum.py`**

- `from scrutable.profiles import WorkloadProfile` → `PlantProfile`
- Function signature: `profile: PlantProfile`
- Replace `LatencySloDetector(detector_id=..., target=..., tick_interval=window_size)` with:
  ```python
  sensor = LatencySloSensor(sensor_id=detector_id, target=target, sampling_period=window_size)
  detector = LatencySloDetector(detector_id=detector_id, target=target)
  ```
- In the detection loop, replace `detector.detect(responses)` with:
  ```python
  signals = sensor.measure(responses)
  alarms = detector.detect(signals)
  ```
- Rename local variable `inferences` → `alarms`, `inf` → `alarm`.

- [ ] **Step 3: Update `src/scrutable/scenarios/slo_performance.py`**

Same pattern as slo_spectrum.py:
- `WorkloadProfile` → `PlantProfile`
- Split `LatencySloDetector` instantiation into sensor + detector
- Update loop: `signals = sensor.measure(window)` then `alarms = detector.detect(signals)`
- Rename `inferences` → `alarms`

- [ ] **Step 4: Update `examples/basic_simulation.py`**

Change `from scrutable import sample_workload, CONSISTENT_FAST, ...` — `sample_workload` stays but `WorkloadProfile` if referenced becomes `PlantProfile`. No rename needed unless the example explicitly references `WorkloadProfile`.

- [ ] **Step 5: Run full test suite**

```
pytest tests/ -v --ignore=tests/test_slo_performance.py --ignore=tests/test_slo_scenario.py
```
Expected: all pass (the slow tests are excluded for speed; run them separately).

```
pytest tests/test_slo_performance.py tests/test_slo_scenario.py -v -m slow
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/scrutable/__init__.py src/scrutable/scenarios/ examples/
git commit -m "refactor: update exports and scenarios for CT vocabulary rename"
```

---

## Final verification

- [ ] **Run complete test suite**

```
pytest tests/ -v
```
Expected: all tests pass. Zero references to `Inference`, `WorkloadProfile`, `InputSynthesizer`, `pathology_type`, `confidence` (as a field), `tick_interval` should remain in source or test files.

- [ ] **Confirm no old names remain in source**

```bash
grep -rn "Inference\|WorkloadProfile\|InputSynthesizer\|pathology_type\b\|tick_interval\b" \
  src/ tests/ examples/ --include="*.py"
```
Expected: no output.

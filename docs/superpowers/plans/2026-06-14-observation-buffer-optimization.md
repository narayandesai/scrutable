# ObservationBuffer Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Python-list-backed `ObservationBuffer` with a numpy-array-backed `NumpyObservationBuffer` (~10x memory savings, exact) and add a pre-allocated histogram buffer (`HistogramBuffer`, ~1000x savings, approximate) for the parallel simulation pipeline.

**Architecture:** `WindowResult` is a new shared return type for `window()` that both buffers return; sensors and calibrators are updated to consume it. `NumpyObservationBuffer` stores four parallel numpy arrays and materializes lazily. `HistogramBuffer` pre-allocates a 2D count grid at construction and merges across workers by element-wise addition.

**Tech Stack:** Python, numpy, pytest, uv

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/scrutable/window_result.py` | `WindowResult` dataclass |
| Modify | `src/scrutable/observations.py` | `ObservationBuffer` ABC + `NumpyObservationBuffer` + `merge_observation_buffers` |
| Modify | `src/scrutable/engine.py` | instantiate `NumpyObservationBuffer` |
| Modify | `src/scrutable/sensor.py` | update `Sensor.measure` signature |
| Modify | `src/scrutable/detectors/slo.py` | update all four sensor/calibrator classes |
| Modify | `src/scrutable/scenarios/slo_performance.py` | update `_run_chunk`, `_analyze_buffer`, add histogram worker |
| Modify | `src/scrutable/scenarios/slo_spectrum.py` | update `_compute_window` |
| Create | `src/scrutable/histogram_buffer.py` | `HistogramBuffer` + `merge_histogram_buffers` |
| Modify | `tests/test_observations.py` | update to `NumpyObservationBuffer` + `WindowResult` assertions |
| Modify | `tests/test_slo_detector.py` | update `ObservationBuffer` refs + `measure()` call sites |
| Create | `tests/test_window_result.py` | `WindowResult` unit tests |
| Create | `tests/test_histogram_buffer.py` | `HistogramBuffer` unit + accuracy tests |
| Modify | `scrutable-talk/noise_vs_window_parallel.py` | workers return `HistogramBuffer`; lead sums |

---

## Task 1: WindowResult

**Files:**
- Create: `src/scrutable/window_result.py`
- Create: `tests/test_window_result.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_window_result.py
import numpy as np
import pytest
from scrutable.window_result import WindowResult


def _exact(latencies, error_rate=0.0, t_start=0.0, t_end=1.0):
    return WindowResult(
        t_start=t_start, t_end=t_end,
        count=len(latencies), error_rate=error_rate,
        _latencies=np.array(latencies, dtype=np.float64),
    )


def _precomputed(d, count=100):
    return WindowResult(t_start=0.0, t_end=1.0, count=count, error_rate=0.0,
                        _precomputed=d)


def test_percentile_exact_delegates_to_numpy():
    vals = [0.1, 0.2, 0.3, 0.4, 0.5]
    assert _exact(vals).percentile(50) == pytest.approx(np.percentile(vals, 50))


def test_percentile_precomputed_lookup():
    assert _precomputed({99.9: 0.42}).percentile(99.9) == pytest.approx(0.42)


def test_percentile_keyerror_for_undeclared():
    with pytest.raises(KeyError):
        _precomputed({99.0: 0.3}).percentile(99.9)


def test_len():
    assert len(_exact([0.1, 0.2, 0.3])) == 3


def test_bool_true_when_nonempty():
    assert bool(_exact([0.1]))


def test_bool_false_when_empty():
    assert not bool(WindowResult(t_start=0.0, t_end=1.0, count=0, error_rate=0.0))


def test_error_rate_stored():
    assert _exact([0.1, 0.2], error_rate=0.25).error_rate == pytest.approx(0.25)
```

- [ ] **Step 2: Run to confirm they fail**

```
LD_LIBRARY_PATH=$(nix-build '<nixpkgs>' -A stdenv.cc.cc.lib --no-build-output)/lib \
  uv run python -m pytest tests/test_window_result.py -v
```
Expected: `ModuleNotFoundError: No module named 'scrutable.window_result'`

- [ ] **Step 3: Implement `WindowResult`**

```python
# src/scrutable/window_result.py
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass
class WindowResult:
    t_start: float
    t_end: float
    count: int
    error_rate: float
    _latencies: np.ndarray | None = field(default=None, repr=False)
    _precomputed: dict[float, float] = field(default_factory=dict, repr=False)

    def percentile(self, p: float) -> float:
        if self._latencies is not None:
            return float(np.percentile(self._latencies, p))
        if p in self._precomputed:
            return self._precomputed[p]
        raise KeyError(
            f"percentile {p} not declared at HistogramBuffer construction; "
            f"available: {sorted(self._precomputed)}"
        )

    def __len__(self) -> int:
        return self.count

    def __bool__(self) -> bool:
        return self.count > 0
```

- [ ] **Step 4: Run tests**

```
LD_LIBRARY_PATH=$(nix-build '<nixpkgs>' -A stdenv.cc.cc.lib --no-build-output)/lib \
  uv run python -m pytest tests/test_window_result.py -v
```
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/window_result.py tests/test_window_result.py
git commit -m "feat: add WindowResult dataclass"
```

---

## Task 2: NumpyObservationBuffer

**Files:**
- Modify: `src/scrutable/observations.py` (full rewrite)
- Modify: `tests/test_observations.py` (update assertions + imports)

- [ ] **Step 1: Update `tests/test_observations.py`**

Replace the entire file:

```python
# tests/test_observations.py
import numpy as np
import pytest
from scrutable.observations import NumpyObservationBuffer, merge_observation_buffers
from scrutable.window_result import WindowResult


def test_window_returns_responses_in_range(build_response):
    buf = NumpyObservationBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))   # arrives 1.0
    buf.append(build_response(issued_at=1.0, latency=1.0))   # arrives 2.0
    buf.append(build_response(issued_at=4.0, latency=1.0))   # arrives 5.0
    assert len(buf.window(1.0, 3.0)) == 2


def test_window_is_inclusive_on_both_ends(build_response):
    buf = NumpyObservationBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))   # arrives 1.0
    buf.append(build_response(issued_at=4.0, latency=1.0))   # arrives 5.0
    assert len(buf.window(1.0, 5.0)) == 2


def test_window_empty_when_no_responses_in_range(build_response):
    buf = NumpyObservationBuffer()
    buf.append(build_response(issued_at=10.0, latency=1.0))
    assert not buf.window(0.0, 5.0)


def test_expire_removes_old_responses(build_response):
    buf = NumpyObservationBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))   # arrives 1.0
    buf.append(build_response(issued_at=1.0, latency=1.0))   # arrives 2.0
    buf.append(build_response(issued_at=9.0, latency=1.0))   # arrives 10.0
    buf.expire(before=5.0)
    assert not buf.window(0.0, 3.0)
    assert len(buf.window(9.0, 11.0)) == 1


def test_buffer_preserves_arrival_order(build_response):
    buf = NumpyObservationBuffer()
    r_early = build_response(issued_at=3.0, latency=1.0)   # arrives 4.0
    r_late  = build_response(issued_at=1.0, latency=5.0)   # arrives 6.0
    buf.append(r_early)
    buf.append(r_late)
    w1 = buf.window(3.5, 5.0)
    w2 = buf.window(5.5, 7.0)
    assert len(w1) == 1
    assert len(w2) == 1
    assert w1.percentile(50) == pytest.approx(r_early.latency)
    assert w2.percentile(50) == pytest.approx(r_late.latency)


def test_window_returns_window_result(build_response):
    buf = NumpyObservationBuffer()
    buf.append(build_response(issued_at=0.0, latency=0.5))
    assert isinstance(buf.window(0.0, 2.0), WindowResult)


def test_append_after_window_does_not_mutate_earlier_result(build_response):
    buf = NumpyObservationBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))
    result = buf.window(0.0, 2.0)
    assert len(result) == 1
    buf.append(build_response(issued_at=0.5, latency=1.0))
    assert len(result) == 1  # snapshot; not affected by subsequent appends


def test_window_result_percentile_matches_numpy(build_response):
    rng = np.random.default_rng(42)
    buf = NumpyObservationBuffer()
    latencies = rng.lognormal(-2, 0.3, 1000)
    for i, lat in enumerate(latencies):
        buf.append(build_response(issued_at=float(i) * 0.001, latency=float(lat)))
    result = buf.window(0.0, 2.0)
    assert result.percentile(99.9) == pytest.approx(np.percentile(latencies, 99.9))


def test_window_result_error_rate(build_response):
    buf = NumpyObservationBuffer()
    for i in range(10):
        buf.append(build_response(issued_at=float(i) * 0.1, latency=0.1,
                                  error_code=1 if i < 3 else 0))
    assert buf.window(0.0, 2.0).error_rate == pytest.approx(0.3)


def test_from_responses(build_response):
    responses = [build_response(issued_at=float(i), latency=0.1) for i in range(5)]
    buf = NumpyObservationBuffer.from_responses(responses)
    assert len(buf.window(0.0, 10.0)) == 5


def test_merge_observation_buffers(build_response):
    buf1 = NumpyObservationBuffer.from_responses([
        build_response(issued_at=0.0, latency=0.5),   # arrives 0.5
        build_response(issued_at=2.0, latency=0.5),   # arrives 2.5
    ])
    buf2 = NumpyObservationBuffer.from_responses([
        build_response(issued_at=1.0, latency=0.5),   # arrives 1.5
        build_response(issued_at=3.0, latency=0.5),   # arrives 3.5
    ])
    merged = merge_observation_buffers([buf1, buf2])
    assert len(merged.window(0.0, 4.0)) == 4
    assert len(merged.window(1.0, 2.0)) == 1   # only arrival at 1.5
```

- [ ] **Step 2: Run to confirm failures**

```
LD_LIBRARY_PATH=$(nix-build '<nixpkgs>' -A stdenv.cc.cc.lib --no-build-output)/lib \
  uv run python -m pytest tests/test_observations.py -v
```
Expected: `ImportError` — `NumpyObservationBuffer` not yet defined.

- [ ] **Step 3: Rewrite `src/scrutable/observations.py`**

```python
# src/scrutable/observations.py
from __future__ import annotations
from abc import ABC, abstractmethod
import numpy as np
from scrutable.models import Response
from scrutable.window_result import WindowResult


class ObservationBuffer(ABC):
    @abstractmethod
    def append(self, response: Response) -> None: ...

    @abstractmethod
    def window(self, start: float, end: float) -> WindowResult: ...

    @abstractmethod
    def expire(self, before: float) -> None: ...


class NumpyObservationBuffer(ObservationBuffer):
    def __init__(self) -> None:
        self._pending: list[tuple[float, float, float, int]] = []
        self._arrivals:    np.ndarray = np.empty(0, dtype=np.float64)
        self._latencies:   np.ndarray = np.empty(0, dtype=np.float64)
        self._issued_at:   np.ndarray = np.empty(0, dtype=np.float64)
        self._error_codes: np.ndarray = np.empty(0, dtype=np.int32)
        self._arrays_valid: bool = True  # empty arrays are already sorted

    def append(self, response: Response) -> None:
        arrival = response.issued_at + response.latency
        self._pending.append(
            (arrival, response.latency, response.issued_at, int(response.error_code))
        )
        self._arrays_valid = False

    def _materialize(self) -> None:
        if self._arrays_valid:
            return
        if not self._pending:
            self._arrays_valid = True
            return
        self._pending.sort(key=lambda t: t[0])
        new = np.array(self._pending, dtype=np.float64)
        new_arrivals    = new[:, 0]
        new_latencies   = new[:, 1]
        new_issued_at   = new[:, 2]
        new_error_codes = new[:, 3].astype(np.int32)
        if len(self._arrivals) == 0:
            self._arrivals    = new_arrivals
            self._latencies   = new_latencies
            self._issued_at   = new_issued_at
            self._error_codes = new_error_codes
        else:
            all_arrivals = np.concatenate([self._arrivals, new_arrivals])
            order = np.argsort(all_arrivals, kind='stable')
            self._arrivals    = all_arrivals[order]
            self._latencies   = np.concatenate([self._latencies,   new_latencies  ])[order]
            self._issued_at   = np.concatenate([self._issued_at,   new_issued_at  ])[order]
            self._error_codes = np.concatenate([self._error_codes, new_error_codes])[order]
        self._pending = []
        self._arrays_valid = True

    def window(self, start: float, end: float) -> WindowResult:
        self._materialize()
        lo = int(np.searchsorted(self._arrivals, start, side='left'))
        hi = int(np.searchsorted(self._arrivals, end,   side='right'))
        count = hi - lo
        if count == 0:
            return WindowResult(
                t_start=start, t_end=end, count=0, error_rate=0.0,
                _latencies=np.empty(0, dtype=np.float64),
            )
        lats = self._latencies[lo:hi]
        iss  = self._issued_at[lo:hi]
        errs = self._error_codes[lo:hi]
        return WindowResult(
            t_start=float(iss.min()),
            t_end=float((iss + lats).max()),
            count=count,
            error_rate=float((errs != 0).sum()) / count,
            _latencies=lats.copy(),
        )

    def expire(self, before: float) -> None:
        self._materialize()
        idx = int(np.searchsorted(self._arrivals, before, side='left'))
        if idx == 0:
            return
        self._arrivals    = self._arrivals[idx:]
        self._latencies   = self._latencies[idx:]
        self._issued_at   = self._issued_at[idx:]
        self._error_codes = self._error_codes[idx:]

    @classmethod
    def from_responses(cls, responses: list[Response]) -> "NumpyObservationBuffer":
        buf = cls()
        buf._pending = [
            (r.issued_at + r.latency, r.latency, r.issued_at, int(r.error_code))
            for r in responses
        ]
        if buf._pending:
            buf._arrays_valid = False
        return buf


def merge_observation_buffers(buffers: list[NumpyObservationBuffer]) -> NumpyObservationBuffer:
    for b in buffers:
        b._materialize()
    non_empty = [b for b in buffers if len(b._arrivals) > 0]
    merged = NumpyObservationBuffer()
    if not non_empty:
        return merged
    all_arrivals    = np.concatenate([b._arrivals    for b in non_empty])
    all_latencies   = np.concatenate([b._latencies   for b in non_empty])
    all_issued_at   = np.concatenate([b._issued_at   for b in non_empty])
    all_error_codes = np.concatenate([b._error_codes for b in non_empty])
    order = np.argsort(all_arrivals, kind='stable')
    merged._arrivals    = all_arrivals[order]
    merged._latencies   = all_latencies[order]
    merged._issued_at   = all_issued_at[order]
    merged._error_codes = all_error_codes[order]
    merged._arrays_valid = True
    return merged
```

- [ ] **Step 4: Run observations tests**

```
LD_LIBRARY_PATH=$(nix-build '<nixpkgs>' -A stdenv.cc.cc.lib --no-build-output)/lib \
  uv run python -m pytest tests/test_observations.py -v
```
Expected: 12 passed

- [ ] **Step 5: Run full suite to check for breakage**

```
LD_LIBRARY_PATH=$(nix-build '<nixpkgs>' -A stdenv.cc.cc.lib --no-build-output)/lib \
  uv run python -m pytest tests/ -x -q
```
Expected: many failures in `test_slo_detector.py` and engine/scenario tests (callers still expect the old class). Note them; don't fix yet — they're addressed in later tasks.

- [ ] **Step 6: Commit**

```bash
git add src/scrutable/observations.py tests/test_observations.py
git commit -m "feat: replace ObservationBuffer with NumpyObservationBuffer (ABC + numpy internals)"
```

---

## Task 3: Update engine.py

**Files:**
- Modify: `src/scrutable/engine.py` (lines 6, 36, 73)

- [ ] **Step 1: Update the import and instantiation**

In `src/scrutable/engine.py`:

Change line 6:
```python
# before
from scrutable.observations import ObservationBuffer
# after
from scrutable.observations import ObservationBuffer, NumpyObservationBuffer
```

Change line 36:
```python
# before
self._buffer = ObservationBuffer()
# after
self._buffer = NumpyObservationBuffer()
```

Leave the `buffer` property return type as `ObservationBuffer` (the ABC) — callers should depend on the interface, not the implementation.

- [ ] **Step 2: Run engine tests**

```
LD_LIBRARY_PATH=$(nix-build '<nixpkgs>' -A stdenv.cc.cc.lib --no-build-output)/lib \
  uv run python -m pytest tests/test_engine_mix.py tests/test_engine_rollout_wiring.py -v
```
Expected: these tests pass (they use the engine but don't inspect buffer internals).

- [ ] **Step 3: Commit**

```bash
git add src/scrutable/engine.py
git commit -m "feat: engine uses NumpyObservationBuffer"
```

---

## Task 4: Update sensors and calibrators in slo.py

Sensors currently receive `list[Response]` from `window()`. After this task they receive `WindowResult`.

**Files:**
- Modify: `src/scrutable/sensor.py`
- Modify: `src/scrutable/detectors/slo.py`
- Modify: `tests/test_slo_detector.py`

- [ ] **Step 1: Update `sensor.py` protocol**

Replace the entire file:

```python
# src/scrutable/sensor.py
from __future__ import annotations
from typing import Protocol, runtime_checkable
from scrutable.models import Signal
from scrutable.window_result import WindowResult


@runtime_checkable
class Sensor(Protocol):
    sensor_id: str
    window_size: float
    sampling_period: float

    def measure(self, window: WindowResult) -> list[Signal]: ...
```

- [ ] **Step 2: Update `src/scrutable/detectors/slo.py`**

Replace the entire file:

```python
# src/scrutable/detectors/slo.py
from __future__ import annotations
from dataclasses import dataclass
from scrutable.models import Signal, Alarm
from scrutable.observations import ObservationBuffer
from scrutable.window_result import WindowResult


@dataclass
class SloTarget:
    percentile: float
    threshold: float
    window_size: float


@dataclass
class LatencySloCalibrator:
    target_fpr: float = 0.001

    def calibrate(
        self,
        buf: ObservationBuffer,
        calibration_end: float,
        percentile: float,
        window_size: float,
    ) -> SloTarget:
        estimates: list[float] = []
        t = 0.0
        while t + window_size <= calibration_end:
            window = buf.window(t, t + window_size)
            if window:
                estimates.append(window.percentile(percentile))
            t += window_size
        if len(estimates) < 2:
            raise ValueError(
                f"Empirical calibration needs ≥2 windows but got {len(estimates)}. "
                f"Increase calibration_duration beyond {2 * window_size:.1f}s or reduce window_size."
            )
        import numpy as np
        threshold = float(np.percentile(estimates, (1.0 - self.target_fpr) * 100.0))
        return SloTarget(percentile=percentile, threshold=threshold, window_size=window_size)


class LatencySloSensor:
    def __init__(self, sensor_id: str, target: SloTarget, sampling_period: float) -> None:
        self.sensor_id = sensor_id
        self.window_size = target.window_size
        self.sampling_period = sampling_period
        self._percentile = target.percentile

    def measure(self, window: WindowResult) -> list[Signal]:
        if not window:
            return []
        return [Signal(
            sensor_id=self.sensor_id,
            metric=f"latency_p{self._percentile}",
            value=window.percentile(self._percentile),
            window_start=window.t_start,
            window_end=window.t_end,
            sample_count=len(window),
        )]


class LatencySloDetector:
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
        window = buf.window(calibration_end - window_size, calibration_end)
        if not window:
            raise ValueError(
                "No responses in calibration window — cannot calibrate error rate SLO target"
            )
        return ErrorRateSloTarget(
            threshold=min(1.0, window.error_rate * self.multiplier),
            window_size=window_size,
        )


class ErrorRateSloSensor:
    def __init__(self, sensor_id: str, target: ErrorRateSloTarget, sampling_period: float) -> None:
        self.sensor_id = sensor_id
        self.window_size = target.window_size
        self.sampling_period = sampling_period

    def measure(self, window: WindowResult) -> list[Signal]:
        if not window:
            return []
        return [Signal(
            sensor_id=self.sensor_id,
            metric="error_rate",
            value=window.error_rate,
            window_start=window.t_start,
            window_end=window.t_end,
            sample_count=len(window),
        )]


class ErrorRateSloDetector:
    def __init__(self, detector_id: str, target: ErrorRateSloTarget) -> None:
        self.detector_id = detector_id
        self._target = target

    def detect(self, signals: list[Signal]) -> list[Alarm]:
        for signal in signals:
            if signal.metric != "error_rate":
                continue
            if signal.value <= self._target.threshold:
                continue
            ratio = (signal.value / self._target.threshold
                     if self._target.threshold > 0 else float("inf"))
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

- [ ] **Step 3: Add `build_window_result` helper and update `tests/test_slo_detector.py`**

Add this helper after the existing `make_responses_with_errors` function:

```python
def build_window_result(responses: list) -> "WindowResult":
    """Wrap a list of Response objects in a WindowResult (test helper)."""
    import numpy as np
    from scrutable.window_result import WindowResult
    if not responses:
        return WindowResult(t_start=0.0, t_end=0.0, count=0, error_rate=0.0,
                            _latencies=np.empty(0, dtype=np.float64))
    latencies  = np.array([r.latency for r in responses], dtype=np.float64)
    errors     = sum(1 for r in responses if r.error_code != 0)
    t_start    = min(r.issued_at for r in responses)
    t_end      = max(r.issued_at + r.latency for r in responses)
    return WindowResult(
        t_start=t_start, t_end=t_end,
        count=len(responses), error_rate=errors / len(responses),
        _latencies=latencies,
    )
```

Change the import at the top of `tests/test_slo_detector.py`:
```python
# before
from scrutable.observations import ObservationBuffer
# after
from scrutable.observations import NumpyObservationBuffer
```

Replace every `ObservationBuffer()` instantiation with `NumpyObservationBuffer()` (lines 47, 223, 233, 241).

Replace every `_make_buf_lognormal` body to use `NumpyObservationBuffer`:
```python
def _make_buf_lognormal(n_windows, window_size, n_per_window, mu, sigma, rng):
    buf = NumpyObservationBuffer()
    for w in range(n_windows):
        latencies = rng.lognormal(mu, sigma, n_per_window)
        for i, lat in enumerate(latencies):
            buf.append(Response(
                request_id=f"r{w}-{i}", workload_id="wl", node_id="n",
                cluster_id="c", region_id="r",
                issued_at=w * window_size + i * (window_size / n_per_window),
                latency=float(lat), error_code=0,
            ))
    return buf
```

Replace every `sensor.measure(window)` or `sensor.measure(make_responses(...))` call that passes a raw list by wrapping it:
```python
# before
sensor.measure(make_responses(2000, latency=0.05))
# after
sensor.measure(build_window_result(make_responses(2000, latency=0.05)))
```

This affects lines 129, 140, 158–159, 175, 187, 201–202, 256, 266, 279, 291, 305.

Also update the inline check at line 86–88 (inside `test_empirical_calibrator_threshold_is_high_quantile_of_per_window_estimates`):
```python
# before
window = buf.window(float(w), float(w + 1))
latencies = np.array([r.latency for r in window])
if float(np.percentile(latencies, 99.9)) > target.threshold:
# after
window = buf.window(float(w), float(w + 1))
if window.percentile(99.9) > target.threshold:
```

- [ ] **Step 4: Run slo detector tests**

```
LD_LIBRARY_PATH=$(nix-build '<nixpkgs>' -A stdenv.cc.cc.lib --no-build-output)/lib \
  uv run python -m pytest tests/test_slo_detector.py -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/sensor.py src/scrutable/detectors/slo.py tests/test_slo_detector.py
git commit -m "feat: update sensors and calibrators to consume WindowResult"
```

---

## Task 5: Update slo_performance.py and slo_spectrum.py

**Files:**
- Modify: `src/scrutable/scenarios/slo_performance.py`
- Modify: `src/scrutable/scenarios/slo_spectrum.py`

- [ ] **Step 1: Update `slo_performance.py`**

Change the import block at the top to include `NumpyObservationBuffer`:
```python
# add to existing imports
from scrutable.observations import ObservationBuffer, NumpyObservationBuffer
```

Change `_run_chunk` to return `NumpyObservationBuffer` instead of `list`:

```python
# src/scrutable/scenarios/slo_performance.py

def _run_chunk(
    profile: PlantProfile,
    seed: int,
    total_rate: float,
    total_duration: float,
    disturbance_at: float,
    disturbance_addend: float,
    disturbance_coverage: float,
) -> NumpyObservationBuffer:
    total_share = sum(e.share for e in profile.entries)
    if abs(total_share - 1.0) > 1e-9:
        normalized = [
            PlantEntry(spec=e.spec, share=e.share / total_share,
                       activity=e.activity, diurnal=e.diurnal)
            for e in profile.entries
        ]
        profile = PlantProfile(name=profile.name, entries=normalized)
        total_rate = total_rate * total_share
    plant = _make_plant()
    mix = build_workload_mix(profile, total_rate=total_rate, period=3600.0)
    engine = SimulationEngine(infra=plant, mix=mix, seed=seed)
    disturbance = Disturbance(
        disturbance_id="perf-sweep",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=disturbance_coverage),
        node_effects={"latency_addend": disturbance_addend},
    )
    engine.add_timed_disturbance(TimedDisturbance(disturbance=disturbance, inject_at=disturbance_at))
    engine.run(total_duration)
    return engine.buffer  # NumpyObservationBuffer


def _run_chunk_kwargs(kwargs: dict) -> NumpyObservationBuffer:
    return _run_chunk(**kwargs)


def _run_chunk_by_index(
    profile_factory: str,
    chunk_index: int,
    n_chunks: int,
    profile_seed: int,
    sim_seed: int,
    total_rate: float,
    total_duration: float,
    disturbance_at: float,
    disturbance_addend: float,
    disturbance_coverage: float,
) -> NumpyObservationBuffer:
    from scrutable.profiles import SPHERICAL_COW, make_long_tail, split_profile
    if profile_factory == "spherical_cow":
        profile = SPHERICAL_COW
    elif profile_factory == "long_tail":
        profile = make_long_tail(rng=__import__("numpy").random.default_rng(profile_seed))
    else:
        raise ValueError(f"Unknown profile_factory: {profile_factory!r}")
    chunks = split_profile(profile, n_chunks)
    return _run_chunk(
        profile=chunks[chunk_index],
        seed=sim_seed,
        total_rate=total_rate,
        total_duration=total_duration,
        disturbance_at=disturbance_at,
        disturbance_addend=disturbance_addend,
        disturbance_coverage=disturbance_coverage,
    )


def _run_chunk_by_index_kwargs(kwargs: dict) -> NumpyObservationBuffer:
    return _run_chunk_by_index(**kwargs)
```

Add the new histogram worker after `_run_chunk_by_index_kwargs`:

```python
def _run_chunk_by_index_histogram_kwargs(kwargs: dict) -> "HistogramBuffer":
    """Worker that returns a HistogramBuffer for low-memory IPC."""
    from scrutable.histogram_buffer import HistogramBuffer
    h_keys = {'histogram_percentiles', 'histogram_dt',
               'histogram_latency_lo', 'histogram_latency_hi', 'histogram_n_bins'}
    sim_kwargs = {k: v for k, v in kwargs.items() if k not in h_keys}
    nbuf = _run_chunk_by_index(**sim_kwargs)
    return HistogramBuffer.from_numpy_buffer(
        nbuf,
        total_duration=kwargs['total_duration'],
        percentiles=kwargs['histogram_percentiles'],
        dt=kwargs.get('histogram_dt', 1.0),
        latency_lo=kwargs.get('histogram_latency_lo', 1e-3),
        latency_hi=kwargs.get('histogram_latency_hi', 10.0),
        n_bins=kwargs.get('histogram_n_bins', 200),
    )
```

Update `_run_profile_parallel` to use `merge_observation_buffers` instead of a list flatten:

```python
def _run_profile_parallel(...) -> list[PerformancePoint]:
    from scrutable.profiles import split_profile
    from scrutable.observations import merge_observation_buffers

    disturbance_at = max(window_sizes) * n_calibration_windows
    total_duration = disturbance_at + post_disturbance
    chunks = split_profile(profile, simulation_workers)
    chunk_kwargs = [
        dict(
            profile=chunk,
            seed=seed + i,
            total_rate=total_rate,
            total_duration=total_duration,
            disturbance_at=disturbance_at,
            disturbance_addend=disturbance_addend,
            disturbance_coverage=disturbance_coverage,
        )
        for i, chunk in enumerate(chunks)
    ]

    with ProcessPoolExecutor(max_workers=simulation_workers) as pool:
        chunk_bufs = list(pool.map(_run_chunk_kwargs, chunk_kwargs))

    buf = merge_observation_buffers(chunk_bufs)
    sigma = profile.entries[0].spec.latency_sigma
    return [
        _analyze_buffer(
            buf=buf,
            profile_name=profile.name,
            sigma=sigma,
            window_size=ws,
            calibration_duration=ws * n_calibration_windows,
            disturbance_at=disturbance_at,
            total_duration=total_duration,
            percentile=percentile,
            target_fpr=target_fpr,
        )
        for ws in window_sizes
    ]
```

Update `_analyze_buffer` — replace the `latencies` list comprehension with `WindowResult.percentile`:

```python
# inside the while loop, replace:
#   latencies = np.array([r.latency for r in responses])
#   ...
#   for p in _SNR_PERCENTILES:
#       bucket[p].append(float(np.percentile(latencies, p)))
# with:
            for p in _SNR_PERCENTILES:
                bucket[p].append(responses.percentile(p))
```

- [ ] **Step 2: Update `slo_spectrum.py`**

Add `WindowResult` import at the top:
```python
from scrutable.window_result import WindowResult
```

Replace `_compute_window`:
```python
def _compute_window(w: WindowResult, t_start: float, t_end: float) -> TimeWindow | None:
    if len(w) < 10:
        return None
    return TimeWindow(
        t_start=t_start,
        t_end=t_end,
        p50=w.percentile(50),
        p90=w.percentile(90),
        p99=w.percentile(99),
        p999=w.percentile(99.9),
        count=len(w),
    )
```

The `run_slo_scenario` call site `_compute_window(buf.window(t, t + window_size), t, t + window_size)` already passes the result of `buf.window()` which is now `WindowResult` — no other changes needed in the body.

- [ ] **Step 3: Run full test suite**

```
LD_LIBRARY_PATH=$(nix-build '<nixpkgs>' -A stdenv.cc.cc.lib --no-build-output)/lib \
  uv run python -m pytest tests/ -x -q
```
Expected: all 230+ tests pass

- [ ] **Step 4: Commit**

```bash
git add src/scrutable/scenarios/slo_performance.py src/scrutable/scenarios/slo_spectrum.py
git commit -m "feat: update analysis pipeline to consume WindowResult"
```

---

## Task 6: HistogramBuffer

**Files:**
- Create: `src/scrutable/histogram_buffer.py`
- Create: `tests/test_histogram_buffer.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_histogram_buffer.py
import numpy as np
import pytest
from scrutable.models import Response
from scrutable.histogram_buffer import HistogramBuffer, merge_histogram_buffers
from scrutable.observations import NumpyObservationBuffer


PERCENTILES = (50.0, 90.0, 99.0, 99.9)


def _r(issued_at: float, latency: float, error_code: int = 0) -> Response:
    return Response(
        request_id="r", workload_id="w", node_id="n",
        cluster_id="c", region_id="r",
        issued_at=issued_at, latency=latency, error_code=error_code,
    )


def test_window_count_matches_appended():
    hbuf = HistogramBuffer(total_duration=10.0, percentiles=PERCENTILES)
    for i in range(100):
        hbuf.append(_r(issued_at=float(i) * 0.05, latency=0.1))
    assert len(hbuf.window(0.0, 10.0)) == 100


def test_window_count_respects_time_range():
    hbuf = HistogramBuffer(total_duration=10.0, percentiles=PERCENTILES)
    for i in range(5):
        hbuf.append(_r(issued_at=float(i), latency=0.1))         # arrivals 0.1–4.1
    for i in range(5):
        hbuf.append(_r(issued_at=float(i) + 6.0, latency=0.1))  # arrivals 6.1–10.1
    assert len(hbuf.window(0.0, 5.0)) == 5
    assert len(hbuf.window(6.0, 11.0)) == 5


def test_percentile_accuracy_within_5_percent():
    rng = np.random.default_rng(42)
    n = 100_000
    latencies = rng.lognormal(-2.3, 0.3, n)
    total_duration = float(n) * 0.001 + 1.0
    hbuf = HistogramBuffer(total_duration=total_duration, percentiles=PERCENTILES)
    nbuf = NumpyObservationBuffer()
    for i, lat in enumerate(latencies):
        r = _r(issued_at=float(i) * 0.001, latency=float(lat))
        hbuf.append(r)
        nbuf.append(r)
    hw = hbuf.window(0.0, total_duration)
    nw = nbuf.window(0.0, total_duration)
    for p in PERCENTILES:
        exact = nw.percentile(p)
        approx = hw.percentile(p)
        assert abs(approx - exact) / exact < 0.05, \
            f"P{p}: exact={exact:.4f} approx={approx:.4f} rel_err={abs(approx-exact)/exact:.3f}"


def test_error_rate():
    hbuf = HistogramBuffer(total_duration=10.0, percentiles=PERCENTILES)
    for i in range(8):
        hbuf.append(_r(issued_at=float(i) * 0.1, latency=0.05, error_code=0))
    for i in range(2):
        hbuf.append(_r(issued_at=float(i + 8) * 0.1, latency=0.05, error_code=1))
    assert hbuf.window(0.0, 10.0).error_rate == pytest.approx(0.2)


def test_expire_zeros_old_cells():
    hbuf = HistogramBuffer(total_duration=10.0, percentiles=PERCENTILES)
    hbuf.append(_r(issued_at=0.0, latency=0.1))   # arrives 0.1 → cell 0
    hbuf.append(_r(issued_at=5.0, latency=0.1))   # arrives 5.1 → cell 5
    hbuf.expire(before=3.0)
    assert not hbuf.window(0.0, 2.0)
    assert len(hbuf.window(5.0, 6.0)) == 1


def test_from_numpy_buffer_matches_direct_append():
    rng = np.random.default_rng(0)
    n = 10_000
    latencies = rng.lognormal(-2, 0.4, n)
    responses = [_r(issued_at=float(i) * 0.001, latency=float(lat))
                 for i, lat in enumerate(latencies)]
    total_duration = float(n) * 0.001 + 1.0
    hbuf_direct = HistogramBuffer(total_duration=total_duration, percentiles=PERCENTILES)
    for r in responses:
        hbuf_direct.append(r)
    nbuf = NumpyObservationBuffer.from_responses(responses)
    hbuf_from = HistogramBuffer.from_numpy_buffer(
        nbuf, total_duration=total_duration, percentiles=PERCENTILES)
    for p in PERCENTILES:
        assert hbuf_direct.window(0.0, total_duration).percentile(p) == pytest.approx(
            hbuf_from.window(0.0, total_duration).percentile(p)
        )


def test_merge_histogram_buffers_count():
    total_duration = 10.0
    hbuf1 = HistogramBuffer(total_duration=total_duration, percentiles=PERCENTILES)
    hbuf2 = HistogramBuffer(total_duration=total_duration, percentiles=PERCENTILES)
    responses = [_r(issued_at=float(i) * 0.05, latency=0.1) for i in range(100)]
    for i, r in enumerate(responses):
        (hbuf1 if i % 2 == 0 else hbuf2).append(r)
    merged = merge_histogram_buffers([hbuf1, hbuf2])
    assert len(merged.window(0.0, 10.0)) == 100


def test_merge_percentiles_match_single_buffer():
    rng = np.random.default_rng(7)
    n = 10_000
    latencies = rng.lognormal(-2, 0.3, n)
    total_duration = float(n) * 0.001 + 1.0
    single = HistogramBuffer(total_duration=total_duration, percentiles=PERCENTILES)
    a      = HistogramBuffer(total_duration=total_duration, percentiles=PERCENTILES)
    b      = HistogramBuffer(total_duration=total_duration, percentiles=PERCENTILES)
    for i, lat in enumerate(latencies):
        r = _r(issued_at=float(i) * 0.001, latency=float(lat))
        single.append(r)
        (a if i % 2 == 0 else b).append(r)
    merged = merge_histogram_buffers([a, b])
    for p in PERCENTILES:
        assert merged.window(0.0, total_duration).percentile(p) == pytest.approx(
            single.window(0.0, total_duration).percentile(p)
        )
```

- [ ] **Step 2: Run to confirm they fail**

```
LD_LIBRARY_PATH=$(nix-build '<nixpkgs>' -A stdenv.cc.cc.lib --no-build-output)/lib \
  uv run python -m pytest tests/test_histogram_buffer.py -v
```
Expected: `ModuleNotFoundError: No module named 'scrutable.histogram_buffer'`

- [ ] **Step 3: Implement `src/scrutable/histogram_buffer.py`**

```python
# src/scrutable/histogram_buffer.py
from __future__ import annotations
from math import ceil
import numpy as np
from scrutable.models import Response
from scrutable.observations import ObservationBuffer, NumpyObservationBuffer
from scrutable.window_result import WindowResult


class HistogramBuffer(ObservationBuffer):
    def __init__(
        self,
        total_duration: float,
        percentiles: tuple[float, ...],
        dt: float = 1.0,
        latency_lo: float = 1e-3,
        latency_hi: float = 10.0,
        n_bins: int = 200,
    ) -> None:
        self._total_duration = total_duration
        self._percentiles    = percentiles
        self._dt             = dt
        self._n_bins         = n_bins
        self._n_cells        = ceil(total_duration / dt) + 1
        self._bin_edges      = np.logspace(
            np.log10(latency_lo), np.log10(latency_hi), n_bins + 1
        )
        self._counts = np.zeros((self._n_cells, n_bins), dtype=np.int32)
        self._errors = np.zeros(self._n_cells, dtype=np.int32)
        self._total  = np.zeros(self._n_cells, dtype=np.int32)

    def append(self, response: Response) -> None:
        arrival = response.issued_at + response.latency
        cell = min(int(arrival / self._dt), self._n_cells - 1)
        bin_idx = int(np.searchsorted(self._bin_edges, response.latency, side='right')) - 1
        bin_idx = max(0, min(bin_idx, self._n_bins - 1))
        self._counts[cell, bin_idx] += 1
        self._errors[cell] += int(response.error_code != 0)
        self._total[cell] += 1

    def window(self, start: float, end: float) -> WindowResult:
        lo = max(0, int(start / self._dt))
        hi = min(self._n_cells, int(end / self._dt) + 1)
        hist   = self._counts[lo:hi].sum(axis=0)
        total  = int(self._total[lo:hi].sum())
        errors = int(self._errors[lo:hi].sum())
        precomputed = _percentiles_from_hist(hist, self._bin_edges, self._percentiles, total)
        return WindowResult(
            t_start=start,
            t_end=end,
            count=total,
            error_rate=errors / total if total > 0 else 0.0,
            _precomputed=precomputed,
        )

    def expire(self, before: float) -> None:
        idx = max(0, int(before / self._dt))
        if idx == 0:
            return
        self._counts[:idx] = 0
        self._errors[:idx] = 0
        self._total[:idx]  = 0

    @classmethod
    def from_numpy_buffer(
        cls,
        buf: NumpyObservationBuffer,
        total_duration: float,
        percentiles: tuple[float, ...],
        dt: float = 1.0,
        latency_lo: float = 1e-3,
        latency_hi: float = 10.0,
        n_bins: int = 200,
    ) -> "HistogramBuffer":
        hbuf = cls(
            total_duration=total_duration,
            percentiles=percentiles,
            dt=dt,
            latency_lo=latency_lo,
            latency_hi=latency_hi,
            n_bins=n_bins,
        )
        buf._materialize()
        if len(buf._arrivals) == 0:
            return hbuf
        cells = np.clip(
            (buf._arrivals / dt).astype(np.int64), 0, hbuf._n_cells - 1
        )
        bins = np.clip(
            np.searchsorted(hbuf._bin_edges, buf._latencies, side='right') - 1,
            0, n_bins - 1,
        )
        np.add.at(hbuf._counts, (cells, bins), 1)
        np.add.at(hbuf._errors, cells, (buf._error_codes != 0).astype(np.int32))
        np.add.at(hbuf._total,  cells, 1)
        return hbuf


def _percentiles_from_hist(
    counts: np.ndarray,
    bin_edges: np.ndarray,
    percentiles: tuple[float, ...],
    total: int,
) -> dict[float, float]:
    if total == 0:
        return {p: 0.0 for p in percentiles}
    cdf = np.cumsum(counts)
    result: dict[float, float] = {}
    for p in percentiles:
        target = p / 100.0 * total
        idx = int(np.searchsorted(cdf, target, side='left'))
        idx = min(idx, len(counts) - 1)
        lo  = float(bin_edges[idx])
        hi  = float(bin_edges[idx + 1])
        prev = int(cdf[idx - 1]) if idx > 0 else 0
        span = int(cdf[idx]) - prev
        frac = (target - prev) / span if span > 0 else 0.5
        result[p] = lo + frac * (hi - lo)
    return result


def merge_histogram_buffers(buffers: list[HistogramBuffer]) -> HistogramBuffer:
    assert buffers, "merge_histogram_buffers requires at least one buffer"
    first = buffers[0]
    result = HistogramBuffer(
        total_duration=first._total_duration,
        percentiles=first._percentiles,
        dt=first._dt,
        latency_lo=float(first._bin_edges[0]),
        latency_hi=float(first._bin_edges[-1]),
        n_bins=first._n_bins,
    )
    for buf in buffers:
        result._counts += buf._counts
        result._errors += buf._errors
        result._total  += buf._total
    return result
```

- [ ] **Step 4: Run histogram tests**

```
LD_LIBRARY_PATH=$(nix-build '<nixpkgs>' -A stdenv.cc.cc.lib --no-build-output)/lib \
  uv run python -m pytest tests/test_histogram_buffer.py -v
```
Expected: 8 passed

- [ ] **Step 5: Run full suite**

```
LD_LIBRARY_PATH=$(nix-build '<nixpkgs>' -A stdenv.cc.cc.lib --no-build-output)/lib \
  uv run python -m pytest tests/ -q
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/scrutable/histogram_buffer.py tests/test_histogram_buffer.py
git commit -m "feat: add HistogramBuffer with merge_histogram_buffers"
```

---

## Task 7: Pipeline integration in talk script

**Files:**
- Modify: `scrutable-talk/noise_vs_window_parallel.py`

- [ ] **Step 1: Update `noise_vs_window_parallel.py`**

Replace the existing import block for observations/scenarios:
```python
# before
from scrutable.scenarios.slo_performance import _run_chunk_by_index_kwargs, _analyze_buffer
from scrutable.observations import ObservationBuffer, merge_observation_buffers
# after
from scrutable.scenarios.slo_performance import _run_chunk_by_index_histogram_kwargs, _analyze_buffer
from scrutable.histogram_buffer import HistogramBuffer, merge_histogram_buffers
```

Add a `PERCENTILES` constant below the existing scalar constants:
```python
PERCENTILES = (50.0, 75.0, 90.0, 99.0, 99.9)  # must cover _SNR_PERCENTILES + PERCENTILE
```

Update `sc_jobs` and `lt_jobs` to include `histogram_percentiles`:
```python
    sc_jobs = [dict(
        profile_factory="spherical_cow", chunk_index=0, n_chunks=1,
        profile_seed=PROFILE_SEED, sim_seed=SEED,
        **{**COMMON, "total_rate": 10_000.0},
        histogram_percentiles=PERCENTILES,
    )]
    lt_jobs = [dict(
        profile_factory="long_tail", chunk_index=i, n_chunks=14,
        profile_seed=PROFILE_SEED, sim_seed=SEED + i,
        **{**COMMON, "total_rate": 100_000.0},
        histogram_percentiles=PERCENTILES,
    ) for i in range(14)]
```

Replace the accumulation and merge section:
```python
    # before
    chunk_buffers: dict[str, list[ObservationBuffer]] = {"spherical_cow": [], "long_tail": []}

    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_run_chunk_by_index_kwargs, kw): name for name, kw in all_jobs}
        for fut in as_completed(futures):
            name = futures[fut]
            chunk_buffers[name].append(ObservationBuffer.from_responses(fut.result()))
            print(f"  chunk done for {name} ({time.time()-t0:.1f}s)", flush=True)

    # ... later:
    buf = merge_observation_buffers(chunk_buffers.pop(name))

    # after
    chunk_hbufs: dict[str, list[HistogramBuffer]] = {"spherical_cow": [], "long_tail": []}

    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_run_chunk_by_index_histogram_kwargs, kw): name for name, kw in all_jobs}
        for fut in as_completed(futures):
            name = futures[fut]
            chunk_hbufs[name].append(fut.result())
            print(f"  chunk done for {name} ({time.time()-t0:.1f}s)", flush=True)

    # ... later:
    buf = merge_histogram_buffers(chunk_hbufs.pop(name))
```

- [ ] **Step 2: Run the full test suite one final time**

```
LD_LIBRARY_PATH=$(nix-build '<nixpkgs>' -A stdenv.cc.cc.lib --no-build-output)/lib \
  uv run python -m pytest tests/ -q
```
Expected: all pass

- [ ] **Step 3: Smoke-test the talk script (optional but recommended)**

```
LD_LIBRARY_PATH=$(nix-build '<nixpkgs>' -A stdenv.cc.cc.lib --no-build-output)/lib \
  uv run python scrutable-talk/noise_vs_window_parallel.py
```
Expected: completes without error; prints window/noise table; memory usage is dramatically lower than before.

- [ ] **Step 4: Commit**

```bash
git add scrutable-talk/noise_vs_window_parallel.py
git commit -m "feat: parallel talk script uses HistogramBuffer workers for low-memory IPC"
```

---

## Self-Review

**Spec coverage:**
- ✅ `WindowResult` dataclass with `percentile()`, `error_rate`, `t_start`, `t_end`, `__len__`, `__bool__`
- ✅ `ObservationBuffer` ABC with `append`, `window`, `expire` (no `from_responses`)
- ✅ `NumpyObservationBuffer` — lazy materialization, four parallel arrays, `from_responses`, `merge_observation_buffers`
- ✅ `engine.py` updated to `NumpyObservationBuffer()`
- ✅ `sensor.py` Sensor protocol updated
- ✅ All sensor/calibrator call sites in `slo.py`, `slo_performance.py`, `slo_spectrum.py` updated
- ✅ `HistogramBuffer` with constructor params, `append`, `window`, `expire`, `from_numpy_buffer`
- ✅ `merge_histogram_buffers` (element-wise addition)
- ✅ `_run_chunk_by_index_histogram_kwargs` added to `slo_performance.py`
- ✅ Talk script uses histogram workers and `merge_histogram_buffers`
- ✅ Tests for `WindowResult`, `NumpyObservationBuffer`, `HistogramBuffer`

**Type consistency check:**
- `_run_chunk` → `NumpyObservationBuffer` (Task 5 matches Task 3 engine type)
- `_run_chunk_by_index_histogram_kwargs` returns `HistogramBuffer` (Task 5 matches Task 7 import)
- `merge_histogram_buffers` takes `list[HistogramBuffer]` (Task 6 matches Task 7 call)
- `HistogramBuffer.from_numpy_buffer` takes `NumpyObservationBuffer` (Task 6 matches Task 5 call)
- `Sensor.measure` takes `WindowResult` (Task 4 protocol matches Task 4 implementations)

# Workload Mix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat `InputConfig`/`WorkloadRegistry` pair with a `WorkloadMix` that gives each workload a traffic share, optional diurnal curve, and optional two-state Markov activity model.

**Architecture:** A new `traffic.py` module provides `DiurnalCurve` built-ins, `MarkovActivity`, `WorkloadEntry`, and `WorkloadMix`. `InputSynthesizer` is rewritten to consume `WorkloadMix`, computing time-varying Poisson rates and scheduling Markov state transitions. `SimulationEngine.__init__` drops `registry`/`synth_config` in favor of a single `mix: WorkloadMix` parameter and builds its internal `WorkloadRegistry` from the mix entries.

**Tech Stack:** Python 3.13, dataclasses, `math`, `numpy`, `pytest`

**Spec:** `docs/superpowers/specs/2026-06-07-workload-mix-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/scrutable/traffic.py` | `DiurnalCurve`, `FlatCurve`, `SinusoidalCurve`, `DoublePeakCurve`, `MarkovActivity`, `WorkloadEntry`, `WorkloadMix` |
| Modify | `src/scrutable/synthesizer.py` | Rewrite `InputSynthesizer` to take `WorkloadMix`; add time-varying rate and Markov activity |
| Modify | `src/scrutable/engine.py` | Replace `registry`+`synth_config` constructor params with `mix: WorkloadMix` |
| Modify | `src/scrutable/__init__.py` | Export new `traffic.py` types; remove `WorkloadRegistry` and `InputConfig` from public API |
| Modify | `examples/basic_simulation.py` | Update to use `WorkloadMix`/`WorkloadEntry` |
| Create | `tests/test_traffic.py` | Tests for DiurnalCurve impls and WorkloadMix |
| Modify | `tests/test_synthesizer.py` | Rewrite helper to use `WorkloadMix`; add time-varying and Markov tests |
| Modify | `tests/test_engine_rollout_wiring.py` | Update fixture to use new engine API |
| Modify | `tests/test_progressive_rollout_engine.py` | Update fixture to use new engine API |
| Modify | `tests/test_scenario.py` | Update helper to use new engine API |
| Create | `tests/test_engine_mix.py` | End-to-end mix integration test |

---

## Task 1: DiurnalCurve types

**Files:**
- Create: `src/scrutable/traffic.py`
- Create: `tests/test_traffic.py`

- [ ] **Step 1: Write failing tests for DiurnalCurve implementations**

Create `tests/test_traffic.py`:

```python
import math
import numpy as np
import pytest
from scrutable.traffic import FlatCurve, SinusoidalCurve, DoublePeakCurve


def test_flat_curve_returns_one():
    curve = FlatCurve()
    for phase in [0.0, 0.25, 0.5, 0.75, 0.999]:
        assert curve(phase) == 1.0


def test_sinusoidal_curve_peak_at_phase():
    curve = SinusoidalCurve(peak_phase=0.25, trough_depth=0.5)
    assert curve(0.25) == pytest.approx(1.5)
    assert curve(0.75) == pytest.approx(0.5)


def test_sinusoidal_curve_non_negative():
    curve = SinusoidalCurve(peak_phase=0.0, trough_depth=1.0)
    phases = np.linspace(0.0, 1.0, 1000, endpoint=False)
    assert all(curve(p) >= 0.0 for p in phases)


def test_sinusoidal_curve_mean_is_one():
    curve = SinusoidalCurve(peak_phase=0.3, trough_depth=0.7)
    phases = np.linspace(0.0, 1.0, 10_000, endpoint=False)
    assert np.mean([curve(p) for p in phases]) == pytest.approx(1.0, abs=1e-3)


def test_double_peak_curve_mean_is_one():
    curve = DoublePeakCurve(peak1_phase=0.25, peak2_phase=0.75, trough_depth=0.6)
    phases = np.linspace(0.0, 1.0, 10_000, endpoint=False)
    assert np.mean([curve(p) for p in phases]) == pytest.approx(1.0, abs=1e-3)


def test_double_peak_curve_has_two_local_maxima():
    curve = DoublePeakCurve(peak1_phase=0.2, peak2_phase=0.7, trough_depth=0.8)
    phases = np.linspace(0.0, 1.0, 1000, endpoint=False)
    values = [curve(p) for p in phases]
    peak1_idx = int(0.2 * 1000)
    peak2_idx = int(0.7 * 1000)
    midpoint_idx = int(0.45 * 1000)
    assert values[peak1_idx] > values[midpoint_idx]
    assert values[peak2_idx] > values[midpoint_idx]
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_traffic.py -v
```

Expected: `ModuleNotFoundError: No module named 'scrutable.traffic'`

- [ ] **Step 3: Implement DiurnalCurve types in `traffic.py`**

Create `src/scrutable/traffic.py`:

```python
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Protocol
from scrutable.models import WorkloadModel


class DiurnalCurve(Protocol):
    def __call__(self, phase: float) -> float: ...


@dataclass(frozen=True)
class FlatCurve:
    def __call__(self, phase: float) -> float:
        return 1.0


@dataclass(frozen=True)
class SinusoidalCurve:
    peak_phase: float
    trough_depth: float

    def __call__(self, phase: float) -> float:
        return 1.0 + self.trough_depth * math.cos(2.0 * math.pi * (phase - self.peak_phase))


@dataclass(frozen=True)
class DoublePeakCurve:
    peak1_phase: float
    peak2_phase: float
    trough_depth: float

    def __call__(self, phase: float) -> float:
        a = self.trough_depth / 2.0
        return (
            1.0
            + a * math.cos(4.0 * math.pi * (phase - self.peak1_phase))
            + a * math.cos(4.0 * math.pi * (phase - self.peak2_phase))
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_traffic.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```
git add src/scrutable/traffic.py tests/test_traffic.py
git commit -m "feat: DiurnalCurve types (FlatCurve, SinusoidalCurve, DoublePeakCurve)"
```

---

## Task 2: WorkloadMix types

**Files:**
- Modify: `src/scrutable/traffic.py` (append MarkovActivity, WorkloadEntry, WorkloadMix)
- Modify: `tests/test_traffic.py` (append WorkloadMix tests)

- [ ] **Step 1: Write failing tests for WorkloadMix**

Append to `tests/test_traffic.py`:

```python
from scrutable.models import WorkloadModel
from scrutable.traffic import MarkovActivity, WorkloadEntry, WorkloadMix


def _model(wid: str) -> WorkloadModel:
    return WorkloadModel(
        workload_id=wid,
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=1000.0,
        error_shape=1.5,
        noise_sigma=0.001,
    )


def test_workload_mix_valid_shares_no_error():
    m1, m2 = _model("w1"), _model("w2")
    WorkloadMix(
        total_rate=100.0,
        period=3600.0,
        entries=[WorkloadEntry(model=m1, share=0.7), WorkloadEntry(model=m2, share=0.3)],
    )  # should not raise


def test_workload_mix_invalid_shares_raises():
    m1 = _model("w1")
    with pytest.raises(ValueError, match="sum to 1.0"):
        WorkloadMix(total_rate=100.0, period=3600.0, entries=[WorkloadEntry(model=m1, share=0.7)])


def test_workload_mix_rate_at_flat():
    m1, m2 = _model("w1"), _model("w2")
    mix = WorkloadMix(
        total_rate=100.0,
        period=3600.0,
        entries=[WorkloadEntry(model=m1, share=0.7), WorkloadEntry(model=m2, share=0.3)],
    )
    assert mix.rate_at("w1", 0.0) == pytest.approx(70.0)
    assert mix.rate_at("w2", 0.0) == pytest.approx(30.0)


def test_workload_mix_rate_at_sinusoidal():
    model = _model("w1")
    curve = SinusoidalCurve(peak_phase=0.0, trough_depth=0.5)
    mix = WorkloadMix(
        total_rate=100.0,
        period=1000.0,
        entries=[WorkloadEntry(model=model, share=1.0, diurnal=curve)],
    )
    # At t=0, phase=0.0: multiplier=1+0.5*cos(0)=1.5
    assert mix.rate_at("w1", 0.0) == pytest.approx(150.0)
    # At t=500, phase=0.5: multiplier=1+0.5*cos(π)=0.5
    assert mix.rate_at("w1", 500.0) == pytest.approx(50.0)


def test_workload_entry_default_diurnal_is_flat():
    model = _model("w1")
    mix = WorkloadMix(
        total_rate=200.0,
        period=3600.0,
        entries=[WorkloadEntry(model=model, share=1.0)],
    )
    assert mix.rate_at("w1", 0.0) == pytest.approx(200.0)
    assert mix.rate_at("w1", 1800.0) == pytest.approx(200.0)


def test_markov_activity_defaults():
    act = MarkovActivity(onset_rate=2.0, recovery_rate=0.5)
    assert act.initial_active is True
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_traffic.py -v -k "workload_mix or markov"
```

Expected: `ImportError` or `AttributeError` on `WorkloadMix`/`MarkovActivity`

- [ ] **Step 3: Append WorkloadMix types to `traffic.py`**

Append to `src/scrutable/traffic.py` (after `DoublePeakCurve`):

```python

@dataclass
class MarkovActivity:
    onset_rate: float
    recovery_rate: float
    initial_active: bool = True


@dataclass
class WorkloadEntry:
    model: WorkloadModel
    share: float
    diurnal: DiurnalCurve = field(default_factory=FlatCurve)
    activity: MarkovActivity | None = None


@dataclass
class WorkloadMix:
    total_rate: float
    period: float
    entries: list[WorkloadEntry]
    _lookup: dict[str, WorkloadEntry] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        total = sum(e.share for e in self.entries)
        if abs(total - 1.0) >= 1e-6:
            raise ValueError(f"WorkloadEntry shares must sum to 1.0, got {total:.8f}")
        self._lookup = {e.model.workload_id: e for e in self.entries}

    def rate_at(self, workload_id: str, t: float) -> float:
        entry = self._lookup[workload_id]
        phase = (t % self.period) / self.period
        return self.total_rate * entry.share * entry.diurnal(phase)
```

- [ ] **Step 4: Run all traffic tests**

```
pytest tests/test_traffic.py -v
```

Expected: 12 passed

- [ ] **Step 5: Commit**

```
git add src/scrutable/traffic.py tests/test_traffic.py
git commit -m "feat: MarkovActivity, WorkloadEntry, WorkloadMix"
```

---

## Task 3: Rewrite synthesizer and engine

**Files:**
- Modify: `src/scrutable/synthesizer.py`
- Modify: `src/scrutable/engine.py`
- Modify: `tests/test_synthesizer.py`

> **Note:** After this task, `test_scenario.py`, `test_engine_rollout_wiring.py`, and `test_progressive_rollout_engine.py` will fail (engine API changed). They are fixed in Task 5. Run only `tests/test_synthesizer.py` to verify this task.

- [ ] **Step 1: Write failing synthesizer tests using `WorkloadMix`**

Replace `tests/test_synthesizer.py` entirely:

```python
import numpy as np
import pytest
from scrutable.event_loop import EventLoop
from scrutable.observations import ObservationBuffer
from scrutable.models import WorkloadModel, WorkloadState
from scrutable.workload import WorkloadRegistry
from scrutable.simulator import ServiceSimulator
from scrutable.synthesizer import InputSynthesizer
from scrutable.traffic import WorkloadEntry, WorkloadMix, SinusoidalCurve


def _model(wid: str) -> WorkloadModel:
    return WorkloadModel(
        workload_id=wid,
        latency_median=0.01,
        latency_sigma=0.1,
        error_scale=1000.0,
        error_shape=1.5,
        noise_sigma=0.001,
    )


def _make_synth(tiny_infra, mix: WorkloadMix, seed: int = 42):
    loop = EventLoop()
    registry = WorkloadRegistry()
    for entry in mix.entries:
        registry.register(entry.model)
    workload_states = {
        entry.model.workload_id: WorkloadState(workload_id=entry.model.workload_id)
        for entry in mix.entries
    }
    buffer = ObservationBuffer()
    rng = np.random.default_rng(seed)
    sim = ServiceSimulator(loop, tiny_infra, registry, workload_states, buffer, rng)
    synth = InputSynthesizer(mix, loop, sim, rng)
    return loop, synth, buffer


def _single_workload_mix(wid: str, total_rate: float) -> WorkloadMix:
    return WorkloadMix(
        total_rate=total_rate,
        period=3600.0,
        entries=[WorkloadEntry(model=_model(wid), share=1.0)],
    )


def test_synthesizer_produces_responses(tiny_infra):
    mix = _single_workload_mix("wl1", 10.0)
    loop, synth, buffer = _make_synth(tiny_infra, mix)
    synth.start()
    loop.run(1.0)
    assert len(buffer.window(0.0, 2.0)) > 0


def test_synthesizer_rate_approximated(tiny_infra):
    mix = _single_workload_mix("wl1", 100.0)
    loop, synth, buffer = _make_synth(tiny_infra, mix, seed=0)
    synth.start()
    loop.run(10.0)
    count = len(buffer.window(0.0, 12.0))
    assert 700 < count < 1300


def test_synthesizer_multiple_workloads(tiny_infra):
    mix = WorkloadMix(
        total_rate=20.0,
        period=3600.0,
        entries=[
            WorkloadEntry(model=_model("wl1"), share=0.5),
            WorkloadEntry(model=_model("wl2"), share=0.5),
        ],
    )
    loop, synth, buffer = _make_synth(tiny_infra, mix)
    synth.start()
    loop.run(5.0)
    all_resp = buffer.window(0.0, 10.0)
    wids = {r.workload_id for r in all_resp}
    assert "wl1" in wids
    assert "wl2" in wids


def test_synthesizer_schedules_continuously(tiny_infra):
    mix = _single_workload_mix("wl1", 10.0)
    loop, synth, buffer = _make_synth(tiny_infra, mix)
    synth.start()
    loop.run(1.0)
    count_1s = len(buffer.window(0.0, 2.0))
    loop.run(2.0)
    count_2s = len(buffer.window(0.0, 3.0))
    assert count_2s > count_1s


def test_synthesizer_sinusoidal_peak_exceeds_trough(tiny_infra):
    curve = SinusoidalCurve(peak_phase=0.0, trough_depth=0.5)
    mix = WorkloadMix(
        total_rate=200.0,
        period=1000.0,
        entries=[WorkloadEntry(model=_model("wl1"), share=1.0, diurnal=curve)],
    )
    loop, synth, buffer = _make_synth(tiny_infra, mix, seed=0)
    synth.start()
    loop.run(1000.0)
    # Compare narrow bands: near peak (phase≈0, rate≈300) vs near trough (phase≈0.5, rate≈100)
    peak_count = len(buffer.window(0.0, 100.0))
    trough_count = len(buffer.window(450.0, 550.0))
    assert peak_count > trough_count


def test_synthesizer_70_30_split(tiny_infra):
    mix = WorkloadMix(
        total_rate=100.0,
        period=3600.0,
        entries=[
            WorkloadEntry(model=_model("wl1"), share=0.7),
            WorkloadEntry(model=_model("wl2"), share=0.3),
        ],
    )
    loop, synth, buffer = _make_synth(tiny_infra, mix, seed=0)
    synth.start()
    loop.run(30.0)
    responses = buffer.window(0.0, 35.0)
    count1 = sum(1 for r in responses if r.workload_id == "wl1")
    count2 = sum(1 for r in responses if r.workload_id == "wl2")
    ratio = count1 / count2
    assert 1.6 < ratio < 3.2  # expected ≈ 7/3 = 2.33
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_synthesizer.py -v
```

Expected: `TypeError` — `InputSynthesizer.__init__` does not accept `WorkloadMix`

- [ ] **Step 3: Rewrite `synthesizer.py`**

Replace `src/scrutable/synthesizer.py` entirely:

```python
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scrutable.event_loop import EventLoop
from scrutable.simulator import ServiceSimulator
from scrutable.models import Request
from scrutable.traffic import WorkloadMix, MarkovActivity


@dataclass
class InputConfig:
    workload_rates: dict[str, float]


class InputSynthesizer:
    def __init__(
        self,
        mix: WorkloadMix,
        loop: EventLoop,
        simulator: ServiceSimulator,
        rng: np.random.Generator,
    ) -> None:
        self._mix = mix
        self._loop = loop
        self._simulator = simulator
        self._rng = rng
        self._counter: int = 0
        self._active: dict[str, bool] = {}

    def start(self) -> None:
        for entry in self._mix.entries:
            wid = entry.model.workload_id
            if entry.activity is not None:
                self._active[wid] = entry.activity.initial_active
                self._schedule_transition(wid, entry.activity, self._loop.now)
            if self._active.get(wid, True):
                self._schedule_next(wid, self._loop.now)

    def _schedule_next(self, workload_id: str, current_time: float) -> None:
        rate = self._mix.rate_at(workload_id, current_time)
        if rate <= 0.0:
            return
        inter_arrival = self._rng.exponential(1.0 / rate)
        next_time = current_time + inter_arrival
        self._loop.schedule(
            next_time,
            lambda wid=workload_id, t=next_time: self._issue_and_reschedule(wid, t),
        )

    def _issue_and_reschedule(self, workload_id: str, issued_at: float) -> None:
        if not self._active.get(workload_id, True):
            return
        request = Request(
            request_id=f"req-{self._counter}",
            workload_id=workload_id,
            issued_at=issued_at,
        )
        self._counter += 1
        self._simulator.handle_request(request)
        self._schedule_next(workload_id, issued_at)

    def _schedule_transition(
        self, workload_id: str, activity: MarkovActivity, current_time: float
    ) -> None:
        is_active = self._active[workload_id]
        rate = activity.onset_rate if is_active else activity.recovery_rate
        delay = self._rng.exponential(1.0 / rate)
        next_time = current_time + delay
        self._loop.schedule(
            next_time,
            lambda wid=workload_id, act=activity, t=next_time: self._transition(wid, act, t),
        )

    def _transition(self, workload_id: str, activity: MarkovActivity, at: float) -> None:
        was_active = self._active[workload_id]
        self._active[workload_id] = not was_active
        if not was_active:
            self._schedule_next(workload_id, at)
        self._schedule_transition(workload_id, activity, at)
```

- [ ] **Step 4: Update `engine.py` to use `WorkloadMix`**

Replace `src/scrutable/engine.py` entirely:

```python
from __future__ import annotations
import numpy as np
from scrutable.event_loop import EventLoop
from scrutable.plant import Plant
from scrutable.workload import WorkloadRegistry
from scrutable.observations import ObservationBuffer
from scrutable.simulator import ServiceSimulator
from scrutable.synthesizer import InputSynthesizer
from scrutable.disturbance import DisturbanceInjector, TimedDisturbance, StochasticDisturbance
from scrutable.operations import RolloutSystem, OperationsSystem
from scrutable.detector import Detector
from scrutable.actuator import Actuator
from scrutable.models import WorkloadState, RolloutState
from scrutable.rollout import Rollout
from scrutable.traffic import WorkloadMix


class SimulationEngine:
    def __init__(
        self,
        infra: Plant,
        mix: WorkloadMix,
        seed: int | None = None,
    ) -> None:
        self._rng = np.random.default_rng(seed)
        self._loop = EventLoop()
        self._infra = infra
        self._workload_states: dict[str, WorkloadState] = {
            entry.model.workload_id: WorkloadState(entry.model.workload_id)
            for entry in mix.entries
        }
        registry = WorkloadRegistry()
        for entry in mix.entries:
            registry.register(entry.model)
        self._buffer = ObservationBuffer()
        self._simulator = ServiceSimulator(
            self._loop, infra, registry, self._workload_states, self._buffer, self._rng
        )
        self._synthesizer = InputSynthesizer(
            mix, self._loop, self._simulator, self._rng
        )
        self._injector = DisturbanceInjector(
            self._loop, infra, self._workload_states, self._rng
        )
        self._rollouts = RolloutSystem()
        self._ops = OperationsSystem(infra)
        self._detectors: list[Detector] = []
        self._actuators: list[Actuator] = []
        self._started: bool = False

    def add_detector(self, detector: Detector) -> None:
        if detector.tick_interval <= 0:
            raise ValueError(
                f"detector.tick_interval must be > 0, got {detector.tick_interval!r}"
            )
        self._detectors.append(detector)

    def add_actuator(self, actuator: Actuator) -> None:
        self._actuators.append(actuator)

    def add_timed_disturbance(self, td: TimedDisturbance) -> None:
        self._injector.add_timed(td)

    def add_stochastic_disturbance(self, sd: StochasticDisturbance) -> None:
        self._injector.add_stochastic(sd)

    @property
    def buffer(self) -> ObservationBuffer:
        return self._buffer

    @property
    def rollouts(self) -> RolloutSystem:
        return self._rollouts

    @property
    def ops(self) -> OperationsSystem:
        return self._ops

    def run(self, until: float) -> None:
        if self._started:
            raise RuntimeError("SimulationEngine.run called more than once")
        self._started = True
        self._synthesizer.start()
        for detector in self._detectors:
            self._schedule_detector_tick(detector, 0.0)
        self._loop.run(until)

    def _schedule_detector_tick(self, detector: Detector, current_time: float) -> None:
        next_tick = current_time + detector.tick_interval

        def tick(d=detector, t=next_tick) -> None:
            window = self._buffer.window(t - d.window_size, t)
            inferences = d.detect(window)
            for inf in inferences:
                for act in self._actuators:
                    act.act(inf, t, self._rollouts, self._ops)
            self._schedule_detector_tick(d, t)

        self._loop.schedule(next_tick, tick)

    def add_rollout(self, rollout: Rollout) -> None:
        rollout._activate(self._infra, self._workload_states)
        self._rollouts.register(rollout)
        self._schedule_rollout_stage(rollout, stage_idx=0, at=rollout.start_at)

    def _schedule_rollout_stage(self, rollout: Rollout, stage_idx: int, at: float) -> None:
        def advance():
            status = rollout.status
            if status.state not in (RolloutState.PENDING, RolloutState.IN_PROGRESS):
                return
            if not rollout._check_gates(stage_idx, self._loop.now):
                rollout.halt(self._loop.now)
                return
            rollout._deploy_stage(stage_idx, self._loop.now)
            next_idx = stage_idx + 1
            if next_idx < len(rollout.cluster_order):
                self._schedule_rollout_stage(
                    rollout, next_idx, self._loop.now + rollout.stage_interval
                )
        self._loop.schedule(at, advance)
```

- [ ] **Step 5: Run synthesizer tests**

```
pytest tests/test_synthesizer.py -v
```

Expected: 6 passed. (Other engine test files will fail if run — that is expected and resolved in Task 5.)

- [ ] **Step 6: Commit**

```
git add src/scrutable/synthesizer.py src/scrutable/engine.py tests/test_synthesizer.py
git commit -m "feat: rewrite synthesizer and engine to use WorkloadMix"
```

---

## Task 4: MarkovActivity support in synthesizer

**Files:**
- Modify: `tests/test_synthesizer.py` (append Markov tests)

The Markov implementation is already in `synthesizer.py` from Task 3. This task verifies it with targeted tests.

- [ ] **Step 1: Append Markov activity tests to `tests/test_synthesizer.py`**

```python
from scrutable.traffic import MarkovActivity


def test_markov_high_onset_rate_reduces_arrivals(tiny_infra):
    # onset_rate=10 (active ~0.1s), recovery_rate=0.1 (inactive ~10s)
    # mean active fraction ≈ 0.1 / (10 + 0.1) ≈ 0.01
    activity = MarkovActivity(onset_rate=10.0, recovery_rate=0.1)
    mix = WorkloadMix(
        total_rate=1000.0,
        period=3600.0,
        entries=[WorkloadEntry(model=_model("wl1"), share=1.0, activity=activity)],
    )
    loop, synth, buffer = _make_synth(tiny_infra, mix, seed=0)
    synth.start()
    loop.run(100.0)
    count = len(buffer.window(0.0, 102.0))
    # Without activity: 1000 req/s * 100s = 100_000; with ~1% active ≈ 1000
    assert count < 10_000


def test_markov_high_recovery_rate_approaches_full_rate(tiny_infra):
    # onset_rate=0.001 (active ~1000s), recovery_rate=100.0 (inactive ~0.01s)
    # mean active fraction ≈ 100 / (0.001 + 100) ≈ 1.0
    activity = MarkovActivity(onset_rate=0.001, recovery_rate=100.0)
    mix = WorkloadMix(
        total_rate=100.0,
        period=3600.0,
        entries=[WorkloadEntry(model=_model("wl1"), share=1.0, activity=activity)],
    )
    loop, synth, buffer = _make_synth(tiny_infra, mix, seed=0)
    synth.start()
    loop.run(10.0)
    count = len(buffer.window(0.0, 12.0))
    # Expected ≈ 1000 arrivals; allow ±40%
    assert 600 < count < 1400


def test_markov_initial_inactive_delays_start(tiny_infra):
    # Workload starts inactive; arrivals should begin only after first recovery
    activity = MarkovActivity(onset_rate=0.001, recovery_rate=10.0, initial_active=False)
    mix = WorkloadMix(
        total_rate=1000.0,
        period=3600.0,
        entries=[WorkloadEntry(model=_model("wl1"), share=1.0, activity=activity)],
    )
    loop, synth, buffer = _make_synth(tiny_infra, mix, seed=0)
    synth.start()
    loop.run(0.05)  # 50ms; mean inactive period=0.1s, so likely still inactive
    count_early = len(buffer.window(0.0, 0.06))
    loop.run(5.0)   # long enough for recovery
    count_later = len(buffer.window(0.0, 6.0))
    assert count_early == 0
    assert count_later > 0
```

- [ ] **Step 2: Run tests to confirm they pass (implementation was done in Task 3)**

```
pytest tests/test_synthesizer.py -v
```

Expected: 10 passed

- [ ] **Step 3: Commit**

```
git add tests/test_synthesizer.py
git commit -m "test: MarkovActivity synthesizer tests"
```

---

## Task 5: Engine callsites, exports, and examples

**Files:**
- Modify: `tests/test_engine_rollout_wiring.py`
- Modify: `tests/test_progressive_rollout_engine.py`
- Modify: `tests/test_scenario.py`
- Create: `tests/test_engine_mix.py`
- Modify: `src/scrutable/__init__.py`
- Modify: `examples/basic_simulation.py`

- [ ] **Step 1: Update `tests/test_engine_rollout_wiring.py`**

Replace the file:

```python
import pytest
from scrutable.models import Release, ReleaseChange, RolloutState, WorkloadModel
from scrutable.rollout import Rollout
from scrutable.plant import PlantConfig, Plant
from scrutable.engine import SimulationEngine
from scrutable.traffic import WorkloadEntry, WorkloadMix


@pytest.fixture
def simple_engine():
    plant = Plant(PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1", "r1c2"]},
        nodes={"r1c1": ["r1c1n1"], "r1c2": ["r1c2n1"]},
    ))
    model = WorkloadModel(
        workload_id="wl1",
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=1000.0,
        error_shape=1.5,
        noise_sigma=0.001,
    )
    mix = WorkloadMix(
        total_rate=5.0,
        period=3600.0,
        entries=[WorkloadEntry(model=model, share=1.0)],
    )
    return SimulationEngine(infra=plant, mix=mix, seed=42)


def test_add_rollout_completes_all_stages(simple_engine):
    release = Release(release_id="v1", changes=[ReleaseChange(change_id="ch1")])
    rollout = Rollout(release, ["r1c1", "r1c2"], stage_interval=5.0, start_at=0.0)
    simple_engine.add_rollout(rollout)
    simple_engine.run(until=20.0)
    s = rollout.status
    assert s.state == RolloutState.COMPLETED
    assert s.stages_completed == 2


def test_add_rollout_gate_false_halts(simple_engine):
    release = Release(release_id="v2", changes=[ReleaseChange(change_id="ch1")])
    gates = [[], [lambda *_: False]]
    rollout = Rollout(release, ["r1c1", "r1c2"], stage_interval=5.0, start_at=0.0, gates=gates)
    simple_engine.add_rollout(rollout)
    simple_engine.run(until=20.0)
    s = rollout.status
    assert s.state == RolloutState.HALTED
    assert s.stages_completed == 1
```

- [ ] **Step 2: Update `tests/test_progressive_rollout_engine.py`**

Replace the file entirely. The fixture and `test_capacity_fraction_reflects_weights` both use the old engine API; all other test functions are unchanged:

```python
import pytest
from scrutable.models import (
    Release, ReleaseChange, RolloutState, Disturbance, DisturbanceScope, WorkloadModel,
)
from scrutable.rollout import Rollout
from scrutable.plant import PlantConfig, Plant
from scrutable.engine import SimulationEngine
from scrutable.traffic import WorkloadEntry, WorkloadMix


def _make_engine(plant, total_rate=5.0, seed=42):
    model = WorkloadModel(
        workload_id="wl1",
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=1000.0,
        error_shape=1.5,
        noise_sigma=0.001,
    )
    mix = WorkloadMix(
        total_rate=total_rate,
        period=3600.0,
        entries=[WorkloadEntry(model=model, share=1.0)],
    )
    return SimulationEngine(infra=plant, mix=mix, seed=seed)


@pytest.fixture
def two_cluster_engine():
    plant = Plant(PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1", "r1c2"]},
        nodes={"r1c1": ["r1c1n1"], "r1c2": ["r1c2n1"]},
    ))
    return _make_engine(plant)


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
    engine = _make_engine(plant)
    release = Release(release_id="v1", changes=[ReleaseChange(change_id="ch1")])
    rollout = Rollout(release, ["r1c1", "r1c2"], stage_interval=10.0, start_at=0.0)
    engine.add_rollout(rollout)
    engine.run(until=3.0)

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
```

- [ ] **Step 3: Update `tests/test_scenario.py`**

Replace the imports block (lines 1–10) and the `_make_registry` + `_make_engine` functions (lines 12–30) with:

```python
import numpy as np
from scrutable.models import WorkloadModel, Disturbance, DisturbanceScope, WorkloadState, Inference
from scrutable.disturbance import TimedDisturbance
from scrutable.engine import SimulationEngine
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
```

All test functions below `_make_engine` are unchanged.

- [ ] **Step 4: Write `tests/test_engine_mix.py`**

```python
import numpy as np
import scrutable as sc
from scrutable.profiles import CONSISTENT_FAST, sample_workload


def test_engine_mix_share_ratio(tiny_infra):
    rng = np.random.default_rng(42)
    model_a = sample_workload(CONSISTENT_FAST, "wl-a", rng)
    model_b = sample_workload(CONSISTENT_FAST, "wl-b", rng)
    mix = sc.WorkloadMix(
        total_rate=200.0,
        period=3600.0,
        entries=[
            sc.WorkloadEntry(model=model_a, share=0.7),
            sc.WorkloadEntry(model=model_b, share=0.3),
        ],
    )
    engine = sc.SimulationEngine(infra=tiny_infra, mix=mix, seed=0)
    engine.run(30.0)
    responses = engine.buffer.window(0.0, 35.0)
    count_a = sum(1 for r in responses if r.workload_id == "wl-a")
    count_b = sum(1 for r in responses if r.workload_id == "wl-b")
    ratio = count_a / count_b
    # Expected ≈ 7/3 = 2.33; allow ±35%
    assert 1.5 < ratio < 3.1
```

- [ ] **Step 5: Run all affected tests**

```
pytest tests/test_engine_rollout_wiring.py tests/test_progressive_rollout_engine.py tests/test_scenario.py tests/test_engine_mix.py -v
```

Expected: all pass

- [ ] **Step 6: Update `src/scrutable/__init__.py`**

Replace the file:

```python
from scrutable.engine import SimulationEngine
from scrutable.plant import PlantConfig, Plant
from scrutable.traffic import (
    FlatCurve,
    SinusoidalCurve,
    DoublePeakCurve,
    MarkovActivity,
    WorkloadEntry,
    WorkloadMix,
)
from scrutable.models import (
    WorkloadModel,
    WorkloadState,
    NodeState,
    ClusterState,
    Request,
    Response,
    Disturbance,
    DisturbanceScope,
    Inference,
    RolloutState,
    RolloutStateTransition,
    ReleaseStatus,
    ReleaseChange,
    Release,
)
from scrutable.disturbance import TimedDisturbance, StochasticDisturbance
from scrutable.operations import RolloutSystem, OperationsSystem
from scrutable.rollout import Rollout, GateCallback
from scrutable.detector import Detector
from scrutable.detectors.slo import (
    SloTarget, LatencySloCalibrator, LatencySloDetector,
    ErrorRateSloTarget, ErrorRateSloCalibrator, ErrorRateSloDetector,
)
from scrutable.actuator import Actuator
from scrutable.profiles import (
    FieldDist,
    WorkloadProfile,
    sample_workload,
    CONSISTENT_FAST,
    HIGH_VARIANCE_LATENCY,
    BURSTY_ERRORS,
    SLOW_RELIABLE,
    LATENCY_VARIANCE_SPECTRUM,
)
```

- [ ] **Step 7: Update `examples/basic_simulation.py`**

Replace the file:

```python
import numpy as np
import scrutable as sc
from scrutable import sample_workload, CONSISTENT_FAST, HIGH_VARIANCE_LATENCY, BURSTY_ERRORS, SLOW_RELIABLE

SEED = 42
DURATION = 30.0
TOTAL_RATE = 1000.0
WORKLOADS_PER_PROFILE = 5

PROFILES = [CONSISTENT_FAST, HIGH_VARIANCE_LATENCY, BURSTY_ERRORS, SLOW_RELIABLE]


def build_mix(rng: np.random.Generator) -> sc.WorkloadMix:
    total_workloads = len(PROFILES) * WORKLOADS_PER_PROFILE
    share = 1.0 / total_workloads
    entries = []
    for profile in PROFILES:
        for i in range(WORKLOADS_PER_PROFILE):
            wid = f"{profile.name}-{i}"
            model = sample_workload(profile, wid, rng)
            entries.append(sc.WorkloadEntry(model=model, share=share))
    return sc.WorkloadMix(total_rate=TOTAL_RATE, period=3600.0, entries=entries)


def main() -> None:
    rng = np.random.default_rng(SEED)

    plant_config = sc.PlantConfig(
        regions=["r1", "r2"],
        clusters={"r1": ["r1c1", "r1c2"], "r2": ["r2c1", "r2c2"]},
        nodes={
            "r1c1": ["r1c1n1", "r1c1n2", "r1c1n3"],
            "r1c2": ["r1c2n1", "r1c2n2", "r1c2n3"],
            "r2c1": ["r2c1n1", "r2c1n2", "r2c1n3"],
            "r2c2": ["r2c2n1", "r2c2n2", "r2c2n3"],
        },
    )
    plant = sc.Plant(plant_config)
    mix = build_mix(rng)

    total_workloads = len(PROFILES) * WORKLOADS_PER_PROFILE

    engine = sc.SimulationEngine(infra=plant, mix=mix, seed=SEED)
    engine.run(DURATION)

    responses = engine.buffer.window(0.0, DURATION + 1.0)
    latencies = np.array([r.latency for r in responses])
    errors = sum(1 for r in responses if r.error_code != 0)

    profile_counts = "  ".join(f"5x {p.name}" for p in PROFILES)

    print("Scrutable — basic simulation")
    print(f"Infrastructure: 2 regions, 4 clusters, 12 nodes")
    print(f"Workloads:      {total_workloads} ({profile_counts})")
    print(f"Rate:           {int(TOTAL_RATE)} req/s total  |  Duration: {int(DURATION)}s  |  seed={SEED}")
    print()
    print(f"Responses:      {len(responses):,}")
    if len(latencies) > 0:
        p50 = float(np.percentile(latencies, 50))
        p95 = float(np.percentile(latencies, 95))
        p99 = float(np.percentile(latencies, 99))
        print(f"Latency:        p50={p50:.3f}s  p95={p95:.3f}s  p99={p99:.3f}s")
    print(f"Errors:         {errors:,} ({errors / len(responses) * 100:.1f}%)" if responses else "Errors:         0")


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Run the full test suite**

```
pytest -v
```

Expected: all tests pass

- [ ] **Step 9: Commit**

```
git add tests/test_engine_rollout_wiring.py tests/test_progressive_rollout_engine.py tests/test_scenario.py tests/test_engine_mix.py src/scrutable/__init__.py examples/basic_simulation.py
git commit -m "feat: update engine callsites, exports, and examples to use WorkloadMix"
```

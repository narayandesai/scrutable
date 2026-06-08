# Workload Mix Control Interface Design

**Date:** 2026-06-07
**Status:** Approved

## Overview

Replace the current flat `InputConfig` / `WorkloadRegistry` pair with a `WorkloadMix` that bundles traffic control (rate, share, diurnal curve, Markov activity) and workload model references in a single object. The engine's public API simplifies to a single `mix` parameter; internal wiring is unchanged.

## New types (`scrutable/traffic.py`)

### `DiurnalCurve` (protocol)

```python
class DiurnalCurve(Protocol):
    def __call__(self, phase: float) -> float: ...
```

`phase ∈ [0, 1)` is position within one period. All built-in curves are normalized so their mean over [0, 1] = 1.0, meaning `total_rate * share` is the *time-averaged* rate for a workload (not the peak).

Three built-in implementations:

- **`FlatCurve()`** — constant 1.0; the default.
- **`SinusoidalCurve(peak_phase: float, trough_depth: float)`** — single peak per period.
  - `peak_phase ∈ [0, 1)`: position of peak (e.g. 0.75 ≈ 18:00 if period = 86400 s).
  - `trough_depth ∈ [0, 1]`: amplitude; `multiplier(φ) = 1 + trough_depth * cos(2π(φ − peak_phase))`. Trough value = `1 − trough_depth`. Mean = 1.0 by construction.
- **`DoublePeakCurve(peak1_phase: float, peak2_phase: float, trough_depth: float)`** — superposition of two half-amplitude sinusoids at `peak1_phase` and `peak2_phase`. Normalized to mean 1.0.

### `MarkovActivity`

Two-state Markov on/off model for a workload.

```python
@dataclass
class MarkovActivity:
    onset_rate: float       # active→inactive rate λ; mean active duration = 1/λ
    recovery_rate: float    # inactive→active rate μ; mean inactive duration = 1/μ
    initial_active: bool = True
```

Mean fraction of time active = `μ / (λ + μ)`.

### `WorkloadEntry`

Bundles a workload model with its traffic control parameters.

```python
@dataclass
class WorkloadEntry:
    model: WorkloadModel
    share: float                           # fraction of total_rate; all entries must sum to 1.0
    diurnal: DiurnalCurve = field(default_factory=FlatCurve)
    activity: MarkovActivity | None = None
```

`workload_id` is derived from `entry.model.workload_id`.

### `WorkloadMix`

Top-level traffic configuration; replaces `InputConfig` as the engine's public interface.

```python
@dataclass
class WorkloadMix:
    total_rate: float            # time-averaged req/s across all workloads
    period: float                # simulation seconds per diurnal cycle
    entries: list[WorkloadEntry]
```

`__post_init__` validates `abs(sum(e.share for e in entries) − 1.0) < 1e-6` and builds `self._lookup: dict[str, WorkloadEntry] = {e.model.workload_id: e for e in entries}`.

Key method:

```python
def rate_at(self, workload_id: str, t: float) -> float:
    entry = self._lookup[workload_id]
    phase = (t % self.period) / self.period
    return self.total_rate * entry.share * entry.diurnal(phase)
```

## Synthesizer changes

`InputSynthesizer` accepts `WorkloadMix` instead of `InputConfig`.

**Time-varying rate.** `_schedule_next` draws inter-arrival time from `Exp(1 / mix.rate_at(workload_id, current_time))` at each event. No structural change — the Poisson process adapts naturally.

**Markov activity.** The synthesizer maintains `_active: dict[str, bool]` for workloads that have a `MarkovActivity`. At `start()`:

1. Initialize `_active[wid]` from `entry.activity.initial_active`.
2. Schedule the first state-transition event for each such workload.

State transition behavior:

- **active→inactive**: set `_active[wid] = False`; schedule next transition from `Exp(recovery_rate)`; stop arrivals (`_issue_and_reschedule` checks `_active[wid]` before calling `_schedule_next`).
- **inactive→active**: set `_active[wid] = True`; schedule next transition from `Exp(onset_rate)`; resume arrivals by calling `_schedule_next(wid, loop.now)`.

Workloads without a `MarkovActivity` are always active; no state is tracked and no extra events are generated.

## Engine interface change

`SimulationEngine.__init__` drops `registry` and `synth_config`, gains `mix`:

```python
def __init__(self, infra: Plant, mix: WorkloadMix, seed: int | None = None)
```

At construction the engine:

1. Builds a `WorkloadRegistry` from `mix.entries` and passes it to `ServiceSimulator` (no change to `ServiceSimulator`).
2. Initializes `WorkloadState` for each entry.
3. Constructs `InputSynthesizer` with the mix.

`InputConfig` and `WorkloadRegistry` remain in the codebase for internal use but are no longer part of the public engine API. Existing examples (`basic_simulation.py`, scenario files) are updated to use `WorkloadMix`.

## Testing

### `tests/test_traffic.py` (new)

- `WorkloadMix` raises if shares do not sum to 1.0.
- `rate_at` returns correct values for flat, sinusoidal, and double-peak curves at known phases.
- `SinusoidalCurve` integrates to mean 1.0 over a full period (numerical check).
- `DoublePeakCurve` same normalization check.

### `tests/test_synthesizer.py` (extended)

- With a flat mix, total arrival count over a fixed duration matches `total_rate * duration` within statistical tolerance.
- With a sinusoidal curve, arrivals in the peak half-period exceed arrivals in the trough half-period.
- With `MarkovActivity` with very high `onset_rate`, a workload produces far fewer arrivals than its share implies; with very high `recovery_rate`, it approaches the full share.

### `tests/test_engine_mix.py` (new)

End-to-end run with a two-workload mix (70/30 split) verifies response counts are roughly proportional to shares.

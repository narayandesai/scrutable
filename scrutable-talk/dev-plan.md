# Development Plan

## Phase 1: Control Theory Rename

Rename scrutable internals to use control theory vocabulary consistently. This is a
prerequisite for all subsequent work — the talk uses control theory framing throughout.

### Renames

| Current | New |
|---|---|
| `Pathology` | `Disturbance` |
| `TimedPathology` | `TimedDisturbance` |
| `StochasticPathology` | `StochasticDisturbance` |
| `PathologyInjector` | `DisturbanceInjector` |
| `PathologyScope` | `DisturbanceScope` |
| `apply_pathology` / `remove_pathology` | `apply_disturbance` / `remove_disturbance` |
| `InfrastructureModel` | `Plant` |
| `InfrastructureConfig` | `PlantConfig` |
| `ResponseBuffer` | `ObservationBuffer` |
| `WorkloadSynthesizer` | `InputSynthesizer` |
| `SynthesizerConfig` | `InputConfig` |

### Keep as-is

- `Detector`, `Actuator`, `Inference` — already correct or intentionally richer
- `RolloutSystem`, `OperationsSystem` — descriptive, no clearer control theory equivalent
- `NodeState`, `ClusterState`, `WorkloadState`, `WorkloadModel` — internal state
- `SimulationEngine` — fine as-is

---

## Phase 2: SLO Threshold Demo

Demonstrate SLO threshold detection across a spectrum of services ordered by latency
variance. Show detection working cleanly on low-variance services and degrading to
failure on high-variance ones. This is the core visual for the talk's section 4.

### Step 1: Increase event rates

Increase total throughput to 20-50k QPS to produce production-realistic dynamics and
ensure reliable P99.9 estimation (roughly 1000+ requests per measurement window per
service). This is a config change to the `InputSynthesizer`.

### Step 2: Build a burn-in calibration utility

- Run the simulation for a configurable burn-in period with no disturbances
- Measure per-aggregate P99.9 latency and baseline error rate over that window
- Return calibrated thresholds (e.g. 2x P99.9 for latency SLO)
- This mirrors how SLOs are actually set in production

### Step 3: Implement a latency SLO detector

A reference `Detector` implementation that:
- Computes rolling P50, P90, P99, P99.9 latency over a configurable window
- Compares P99.9 against a burn-in-calibrated threshold
- Emits an `Inference` when the threshold is breached, with confidence proportional
  to how far above threshold
- Computes SNR per-percentile (signal(p) / noise(p)) — not just at P99.9. See
  slo-snr.md for full methodology.

### Step 4: Define the service spectrum

Five services ordered by increasing latency variance, spanning from clearly detectable
to undetectable for a fixed-magnitude disturbance. Use and extend existing profiles
(`CONSISTENT_FAST` at the low end, `HIGH_VARIANCE_LATENCY` at the high end) with
intermediate profiles filling the spectrum.

### Step 5: Design the disturbance scenario

- Fixed-magnitude latency disturbance (e.g. 3x latency multiplier on all nodes)
- Injected at a known time T after burn-in completes
- Same disturbance applied identically across all five services
- Duration long enough to span several detector windows

### Step 6: Build the time-series visualization

For each service in the spectrum, produce a time-series plot showing:
- P50, P90, P99, P99.9 latency over simulation time
- SLO threshold line (from burn-in calibration)
- Vertical marker at disturbance injection time
- Vertical marker at detection time (if detected)

The across-spectrum comparison is the talk's key visual: the same disturbance becomes
invisible as variance increases.

---

## Phase 3: Canary Rollout Demo

*Design deferred — see todo.md*

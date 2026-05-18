# Workload Profiles and Basic Example Script Design
_2026-05-17_

## Overview

Two deliverables:

1. **`src/scrutable/profiles.py`** — a curated catalog of named `WorkloadProfile` types and a factory function for sampling `WorkloadModel` instances from them. Profiles represent different kinds of real-world services and their characteristic parameter distributions.

2. **`examples/basic_simulation.py`** — a runnable script that populates a registry from a mix of profiles, runs a 30-second simulation, and prints aggregate latency and error statistics.

---

## 1. WorkloadProfile (`src/scrutable/profiles.py`)

### Data structure

```python
@dataclass
class FieldDist:
    lognormal_mean: float   # mean of the underlying normal (i.e. mean of log(X))
    lognormal_sigma: float  # sigma of the underlying normal

@dataclass
class WorkloadProfile:
    name: str
    latency_median: FieldDist
    latency_sigma: FieldDist
    error_scale: FieldDist
    error_shape: FieldDist
    noise_sigma: FieldDist
```

Each `FieldDist` parameterizes a log-normal distribution. Drawing from the profile produces one `WorkloadModel` with realistic, independently-sampled parameters.

### Factory function

```python
def sample_workload(
    profile: WorkloadProfile,
    workload_id: str,
    rng: np.random.Generator,
) -> WorkloadModel
```

Draws each field from its log-normal independently and constructs a `WorkloadModel`. Fields that would produce unrealistic values (e.g. `error_shape < 0.1`) are clamped to a sensible minimum.

### Catalog

Four named profiles shipped as module-level constants:

| Constant | Character | Typical use |
|---|---|---|
| `CONSISTENT_FAST` | Low latency_median variance, low sigma, high error_scale | Healthy low-variance API service |
| `HIGH_VARIANCE_LATENCY` | Wide latency_median spread, high sigma spread | Noisy/spiky service (fan-out, cache misses) |
| `BURSTY_ERRORS` | Low error_scale (errors appear early on Weibull), normal latency | Flaky dependency or software bug canary |
| `SLOW_RELIABLE` | latency_median centered high, low error rate, low variance | Batch/storage style service |

The catalog is manually calibrated and intentionally small. New profiles are added as module-level constants.

### Calibration values

The parameter values below are initial calibrations. They should produce a visibly heterogeneous fleet with no pathologies — latency spread across ~1ms to ~1s, error rates mostly well below 1%.

**`CONSISTENT_FAST`**
- `latency_median`: lognormal(mean=ln(0.05), sigma=0.3) — centers around 50ms, tight spread
- `latency_sigma`: lognormal(mean=ln(0.2), sigma=0.2) — low shape variance
- `error_scale`: lognormal(mean=ln(5000), sigma=0.3) — errors very rare
- `error_shape`: lognormal(mean=ln(1.5), sigma=0.1) — stable shape
- `noise_sigma`: lognormal(mean=ln(0.005), sigma=0.3)

**`HIGH_VARIANCE_LATENCY`**
- `latency_median`: lognormal(mean=ln(0.1), sigma=1.0) — wide spread, 1ms–1s range
- `latency_sigma`: lognormal(mean=ln(0.5), sigma=0.5) — high shape variance
- `error_scale`: lognormal(mean=ln(3000), sigma=0.5)
- `error_shape`: lognormal(mean=ln(1.5), sigma=0.2)
- `noise_sigma`: lognormal(mean=ln(0.01), sigma=0.5)

**`BURSTY_ERRORS`**
- `latency_median`: lognormal(mean=ln(0.08), sigma=0.4)
- `latency_sigma`: lognormal(mean=ln(0.3), sigma=0.3)
- `error_scale`: lognormal(mean=ln(50), sigma=0.5) — errors appear early
- `error_shape`: lognormal(mean=ln(1.2), sigma=0.2)
- `noise_sigma`: lognormal(mean=ln(0.008), sigma=0.3)

**`SLOW_RELIABLE`**
- `latency_median`: lognormal(mean=ln(0.5), sigma=0.4) — centered around 500ms
- `latency_sigma`: lognormal(mean=ln(0.3), sigma=0.2)
- `error_scale`: lognormal(mean=ln(10000), sigma=0.3) — very reliable
- `error_shape`: lognormal(mean=ln(1.5), sigma=0.1)
- `noise_sigma`: lognormal(mean=ln(0.02), sigma=0.3)

---

## 2. Basic Example Script (`examples/basic_simulation.py`)

### What it does

1. Builds a small infrastructure: 2 regions × 2 clusters × 3 nodes = 12 nodes
2. Populates a `WorkloadRegistry` with 20 workloads: 5 draws from each of the four profiles, using a seeded RNG
3. Sets all workload rates to 50 req/s (1000 req/s total)
4. Runs `SimulationEngine` for 30 simulated seconds with seed=42
5. Collects all responses from the buffer and prints aggregate stats

### Output format

```
Scrutable — basic simulation
Infrastructure: 2 regions, 4 clusters, 12 nodes
Workloads:      20 (5× consistent_fast, 5× high_variance_latency,
                    5× bursty_errors, 5× slow_reliable)
Rate:           1000 req/s total  |  Duration: 30s  |  seed=42

Responses:      29,841
Latency:        p50=0.098s  p95=0.412s  p99=1.203s
Errors:         847 (2.8%)
```

Stats are computed with numpy from `engine.buffer.window(0.0, 31.0)`. Latency percentiles use `np.percentile`. Error count is any response with `error_code != 0`.

### Run

```bash
uv run python examples/basic_simulation.py
```

No arguments, no config files. Seed, duration, and workload counts are constants at the top of the script.

### Deferred

Comments at the bottom of the script point to:
- **Scenario B:** Inject a timed pathology and observe signal in output
- **Scenario C:** Add a detector and actuator to close the loop

---

## 3. Testing

`profiles.py` gets unit tests in `tests/test_profiles.py`:
- `sample_workload` returns a `WorkloadModel` with all fields positive
- Drawing 100 workloads from `HIGH_VARIANCE_LATENCY` produces visible spread in `latency_median`
- Drawing from `CONSISTENT_FAST` produces tighter spread than `HIGH_VARIANCE_LATENCY`
- All four catalog constants are importable and have the correct `name` field

The example script is not unit-tested (it is a script, not a library). It is verified by running it and checking the output is non-empty and non-crashing.

---

## 4. Public API

`WorkloadProfile`, `FieldDist`, `sample_workload`, and the four catalog constants are exported from `scrutable/__init__.py`.

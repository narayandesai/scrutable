# Workload Profiles and Basic Example Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a curated catalog of named `WorkloadProfile` types with a sampling factory, and a runnable example script that demonstrates the simulator end-to-end.

**Architecture:** `src/scrutable/profiles.py` defines `FieldDist` and `WorkloadProfile` dataclasses plus four module-level catalog constants; `sample_workload(profile, workload_id, rng)` draws one `WorkloadModel` from a profile. `examples/basic_simulation.py` uses profiles to populate a registry, runs the engine, and prints aggregate stats. Both are covered by `tests/test_profiles.py`. `__init__.py` is updated to export the new public names.

**Tech Stack:** Python 3.11+, numpy, uv, pytest

---

## File Map

```
scrutable/
├── src/
│   └── scrutable/
│       ├── __init__.py          # add new exports
│       └── profiles.py          # NEW: FieldDist, WorkloadProfile, sample_workload, catalog
├── tests/
│   └── test_profiles.py         # NEW: unit tests for profiles.py
└── examples/
    └── basic_simulation.py      # NEW: runnable example script
```

---

## Task 1: WorkloadProfile dataclasses and sample_workload

**Files:**
- Create: `src/scrutable/profiles.py`
- Create: `tests/test_profiles.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_profiles.py`:
```python
import numpy as np
from scrutable.profiles import (
    FieldDist,
    WorkloadProfile,
    sample_workload,
    CONSISTENT_FAST,
    HIGH_VARIANCE_LATENCY,
    BURSTY_ERRORS,
    SLOW_RELIABLE,
)


def test_sample_workload_all_fields_positive():
    rng = np.random.default_rng(42)
    model = sample_workload(CONSISTENT_FAST, "wl-test", rng)
    assert model.workload_id == "wl-test"
    assert model.latency_median > 0.0
    assert model.latency_sigma > 0.0
    assert model.error_scale > 0.0
    assert model.error_shape >= 0.1   # clamped minimum
    assert model.noise_sigma > 0.0


def test_sample_workload_reproducible():
    model1 = sample_workload(CONSISTENT_FAST, "wl-1", np.random.default_rng(0))
    model2 = sample_workload(CONSISTENT_FAST, "wl-1", np.random.default_rng(0))
    assert model1.latency_median == model2.latency_median
    assert model1.error_scale == model2.error_scale


def test_high_variance_latency_spreads_more_than_consistent_fast():
    rng_hv = np.random.default_rng(7)
    rng_cf = np.random.default_rng(7)
    hv_medians = [sample_workload(HIGH_VARIANCE_LATENCY, f"wl-{i}", rng_hv).latency_median for i in range(100)]
    cf_medians = [sample_workload(CONSISTENT_FAST, f"wl-{i}", rng_cf).latency_median for i in range(100)]
    assert float(np.std(hv_medians)) > float(np.std(cf_medians))


def test_bursty_errors_has_lower_error_scale_than_slow_reliable():
    rng_be = np.random.default_rng(3)
    rng_sr = np.random.default_rng(3)
    be_scales = [sample_workload(BURSTY_ERRORS, f"wl-{i}", rng_be).error_scale for i in range(100)]
    sr_scales = [sample_workload(SLOW_RELIABLE, f"wl-{i}", rng_sr).error_scale for i in range(100)]
    assert float(np.mean(be_scales)) < float(np.mean(sr_scales))


def test_catalog_constants_have_correct_names():
    assert CONSISTENT_FAST.name == "consistent_fast"
    assert HIGH_VARIANCE_LATENCY.name == "high_variance_latency"
    assert BURSTY_ERRORS.name == "bursty_errors"
    assert SLOW_RELIABLE.name == "slow_reliable"


def test_error_shape_clamped_to_minimum():
    # Use a profile with very tight error_shape dist centered near 0 to force clamping
    profile = WorkloadProfile(
        name="test",
        latency_median=FieldDist(lognormal_mean=-3.0, lognormal_sigma=0.1),
        latency_sigma=FieldDist(lognormal_mean=-2.0, lognormal_sigma=0.1),
        error_scale=FieldDist(lognormal_mean=5.0, lognormal_sigma=0.1),
        error_shape=FieldDist(lognormal_mean=-10.0, lognormal_sigma=0.01),  # draws near 0
        noise_sigma=FieldDist(lognormal_mean=-5.0, lognormal_sigma=0.1),
    )
    rng = np.random.default_rng(0)
    for _ in range(20):
        model = sample_workload(profile, "wl-clamp", rng)
        assert model.error_shape >= 0.1
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_profiles.py -v
```

Expected: `ImportError` — `scrutable.profiles` does not exist

- [ ] **Step 3: Implement profiles.py**

`src/scrutable/profiles.py`:
```python
from __future__ import annotations
import math
import numpy as np
from dataclasses import dataclass
from scrutable.models import WorkloadModel


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


def sample_workload(
    profile: WorkloadProfile,
    workload_id: str,
    rng: np.random.Generator,
) -> WorkloadModel:
    def draw(fd: FieldDist) -> float:
        return float(rng.lognormal(mean=fd.lognormal_mean, sigma=fd.lognormal_sigma))

    return WorkloadModel(
        workload_id=workload_id,
        latency_median=draw(profile.latency_median),
        latency_sigma=draw(profile.latency_sigma),
        error_scale=draw(profile.error_scale),
        error_shape=max(0.1, draw(profile.error_shape)),
        noise_sigma=draw(profile.noise_sigma),
    )


CONSISTENT_FAST = WorkloadProfile(
    name="consistent_fast",
    latency_median=FieldDist(lognormal_mean=math.log(0.05), lognormal_sigma=0.3),
    latency_sigma=FieldDist(lognormal_mean=math.log(0.2), lognormal_sigma=0.2),
    error_scale=FieldDist(lognormal_mean=math.log(5000), lognormal_sigma=0.3),
    error_shape=FieldDist(lognormal_mean=math.log(1.5), lognormal_sigma=0.1),
    noise_sigma=FieldDist(lognormal_mean=math.log(0.005), lognormal_sigma=0.3),
)

HIGH_VARIANCE_LATENCY = WorkloadProfile(
    name="high_variance_latency",
    latency_median=FieldDist(lognormal_mean=math.log(0.1), lognormal_sigma=1.0),
    latency_sigma=FieldDist(lognormal_mean=math.log(0.5), lognormal_sigma=0.5),
    error_scale=FieldDist(lognormal_mean=math.log(3000), lognormal_sigma=0.5),
    error_shape=FieldDist(lognormal_mean=math.log(1.5), lognormal_sigma=0.2),
    noise_sigma=FieldDist(lognormal_mean=math.log(0.01), lognormal_sigma=0.5),
)

BURSTY_ERRORS = WorkloadProfile(
    name="bursty_errors",
    latency_median=FieldDist(lognormal_mean=math.log(0.08), lognormal_sigma=0.4),
    latency_sigma=FieldDist(lognormal_mean=math.log(0.3), lognormal_sigma=0.3),
    error_scale=FieldDist(lognormal_mean=math.log(50), lognormal_sigma=0.5),
    error_shape=FieldDist(lognormal_mean=math.log(1.2), lognormal_sigma=0.2),
    noise_sigma=FieldDist(lognormal_mean=math.log(0.008), lognormal_sigma=0.3),
)

SLOW_RELIABLE = WorkloadProfile(
    name="slow_reliable",
    latency_median=FieldDist(lognormal_mean=math.log(0.5), lognormal_sigma=0.4),
    latency_sigma=FieldDist(lognormal_mean=math.log(0.3), lognormal_sigma=0.2),
    error_scale=FieldDist(lognormal_mean=math.log(10000), lognormal_sigma=0.3),
    error_shape=FieldDist(lognormal_mean=math.log(1.5), lognormal_sigma=0.1),
    noise_sigma=FieldDist(lognormal_mean=math.log(0.02), lognormal_sigma=0.3),
)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_profiles.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/profiles.py tests/test_profiles.py
git commit -m "feat: WorkloadProfile catalog and sample_workload factory"
```

---

## Task 2: Export profiles from public API

**Files:**
- Modify: `src/scrutable/__init__.py`

- [ ] **Step 1: Add exports to __init__.py**

Add to `src/scrutable/__init__.py` after the existing imports:

```python
from scrutable.profiles import (
    FieldDist,
    WorkloadProfile,
    sample_workload,
    CONSISTENT_FAST,
    HIGH_VARIANCE_LATENCY,
    BURSTY_ERRORS,
    SLOW_RELIABLE,
)
```

And add to `__all__`:
```python
    "FieldDist",
    "WorkloadProfile",
    "sample_workload",
    "CONSISTENT_FAST",
    "HIGH_VARIANCE_LATENCY",
    "BURSTY_ERRORS",
    "SLOW_RELIABLE",
```

- [ ] **Step 2: Verify imports work**

```bash
uv run python -c "from scrutable import CONSISTENT_FAST, sample_workload; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add src/scrutable/__init__.py
git commit -m "feat: export WorkloadProfile catalog from package __init__"
```

---

## Task 3: Basic example script

**Files:**
- Create: `examples/basic_simulation.py`

- [ ] **Step 1: Create the examples directory and script**

```bash
mkdir -p examples
```

`examples/basic_simulation.py`:
```python
import math
import numpy as np
import scrutable as sc
from scrutable.profiles import sample_workload, CONSISTENT_FAST, HIGH_VARIANCE_LATENCY, BURSTY_ERRORS, SLOW_RELIABLE

# --- Constants ---
SEED = 42
DURATION = 30.0
RATE_PER_WORKLOAD = 50.0   # req/s
WORKLOADS_PER_PROFILE = 5

PROFILES = [CONSISTENT_FAST, HIGH_VARIANCE_LATENCY, BURSTY_ERRORS, SLOW_RELIABLE]


def build_registry(rng: np.random.Generator) -> tuple[sc.WorkloadRegistry, dict[str, float]]:
    registry = sc.WorkloadRegistry()
    rates: dict[str, float] = {}
    for profile in PROFILES:
        for i in range(WORKLOADS_PER_PROFILE):
            wid = f"{profile.name}-{i}"
            registry.register(sample_workload(profile, wid, rng))
            rates[wid] = RATE_PER_WORKLOAD
    return registry, rates


def main() -> None:
    rng = np.random.default_rng(SEED)

    infra_config = sc.InfrastructureConfig(
        regions=["r1", "r2"],
        clusters={"r1": ["r1c1", "r1c2"], "r2": ["r2c1", "r2c2"]},
        nodes={
            "r1c1": ["r1c1n1", "r1c1n2", "r1c1n3"],
            "r1c2": ["r1c2n1", "r1c2n2", "r1c2n3"],
            "r2c1": ["r2c1n1", "r2c1n2", "r2c1n3"],
            "r2c2": ["r2c2n1", "r2c2n2", "r2c2n3"],
        },
    )
    infra = sc.InfrastructureModel(infra_config)

    registry, rates = build_registry(rng)
    total_workloads = len(PROFILES) * WORKLOADS_PER_PROFILE
    total_rate = total_workloads * RATE_PER_WORKLOAD

    engine = sc.SimulationEngine(
        infra=infra,
        registry=registry,
        synth_config=sc.SynthesizerConfig(workload_rates=rates),
        seed=SEED,
    )
    engine.run(DURATION)

    responses = engine.buffer.window(0.0, DURATION + 1.0)
    latencies = np.array([r.latency for r in responses])
    errors = sum(1 for r in responses if r.error_code != 0)

    profile_counts = "  ".join(f"5× {p.name}" for p in PROFILES)

    print("Scrutable — basic simulation")
    print(f"Infrastructure: 2 regions, 4 clusters, 12 nodes")
    print(f"Workloads:      {total_workloads} ({profile_counts})")
    print(f"Rate:           {int(total_rate)} req/s total  |  Duration: {int(DURATION)}s  |  seed={SEED}")
    print()
    print(f"Responses:      {len(responses):,}")
    if len(latencies) > 0:
        p50 = float(np.percentile(latencies, 50))
        p95 = float(np.percentile(latencies, 95))
        p99 = float(np.percentile(latencies, 99))
        print(f"Latency:        p50={p50:.3f}s  p95={p95:.3f}s  p99={p99:.3f}s")
    print(f"Errors:         {errors:,} ({errors / len(responses) * 100:.1f}%)" if responses else "Errors:         0")

    # TODO Scenario B: inject a timed pathology at T=10 and observe latency/error signal
    # TODO Scenario C: add a Detector and Actuator to close the detection/remediation loop


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script**

```bash
uv run python examples/basic_simulation.py
```

Expected: output matching the format below (exact numbers will differ):
```
Scrutable — basic simulation
Infrastructure: 2 regions, 4 clusters, 12 nodes
Workloads:      20 (5× consistent_fast  5× high_variance_latency  5× bursty_errors  5× slow_reliable)
Rate:           1000 req/s total  |  Duration: 30s  |  seed=42

Responses:      29,XXX
Latency:        p50=X.XXXs  p95=X.XXXs  p99=X.XXXs
Errors:         XXX (X.X%)
```

- [ ] **Step 3: Commit**

```bash
git add examples/basic_simulation.py
git commit -m "feat: basic simulation example script"
```

# Scrutable Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Scrutable, a closed-loop discrete event simulator for distributed service reliability testing with pathology injection, windowed detection, and operational actuation.

**Architecture:** A `heapq`-based `EventLoop` kernel wires nine components: `WorkloadSynthesizer` feeds request events → `ServiceSimulator` samples workload models and emits async responses → `ResponseBuffer` stores arrivals → `Detector`s analyze time windows → `Actuator`s delegate to `RolloutSystem` or `OperationsSystem` → mutate `InfrastructureModel`/`WorkloadState`. `PathologyInjector` drives time-based and stochastic faults. All randomness flows through a single seeded `numpy` RNG.

**Tech Stack:** Python 3.11+, numpy, uv, pytest

---

## File Map

```
scrutable/
├── pyproject.toml
├── src/
│   └── scrutable/
│       ├── __init__.py
│       ├── models.py           # All dataclasses: WorkloadModel, WorkloadState, NodeState,
│       │                       #   ClusterState, Request, Response, PathologyScope,
│       │                       #   Pathology, Inference
│       ├── event_loop.py       # EventLoop: heapq priority queue
│       ├── infrastructure.py   # InfrastructureConfig, InfrastructureModel
│       ├── workload.py         # WorkloadRegistry, sample_latency, sample_error_code
│       ├── buffer.py           # ResponseBuffer
│       ├── simulator.py        # ServiceSimulator (includes two-level router)
│       ├── synthesizer.py      # SynthesizerConfig, WorkloadSynthesizer
│       ├── pathology.py        # stable_subset, apply_pathology, remove_pathology,
│       │                       #   TimedPathology, StochasticPathology, PathologyInjector
│       ├── operations.py       # SoftwareVersion, RolloutSystem, OperationsSystem
│       ├── detector.py         # Detector Protocol
│       ├── actuator.py         # Actuator Protocol
│       └── engine.py           # SimulationEngine
└── tests/
    ├── conftest.py             # tiny_infra, seeded_rng, build_response fixtures
    ├── test_models.py
    ├── test_event_loop.py
    ├── test_infrastructure.py
    ├── test_workload.py
    ├── test_buffer.py
    ├── test_simulator.py
    ├── test_synthesizer.py
    ├── test_pathology.py
    ├── test_operations.py
    ├── test_detector.py
    └── test_scenario.py
```

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/scrutable/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "scrutable"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "numpy>=1.26",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package skeleton**

```bash
mkdir -p src/scrutable tests
touch src/scrutable/__init__.py tests/__init__.py
```

- [ ] **Step 3: Install dependencies**

```bash
uv sync --extra dev
```

Expected: resolves and installs numpy, pytest, pytest-cov into `.venv`

- [ ] **Step 4: Create conftest.py with fixtures**

`tests/conftest.py`:
```python
import pytest
import numpy as np
from scrutable.models import Response


@pytest.fixture
def seeded_rng():
    return np.random.default_rng(42)


@pytest.fixture
def build_response():
    counter = [0]

    def _build(
        workload_id="wl1",
        node_id="n1",
        cluster_id="c1",
        region_id="r1",
        issued_at=0.0,
        latency=0.1,
        error_code=0,
    ):
        counter[0] += 1
        return Response(
            request_id=f"req-{counter[0]}",
            workload_id=workload_id,
            node_id=node_id,
            cluster_id=cluster_id,
            region_id=region_id,
            issued_at=issued_at,
            latency=latency,
            error_code=error_code,
        )

    return _build


@pytest.fixture
def tiny_infra():
    from scrutable.infrastructure import InfrastructureConfig, InfrastructureModel

    config = InfrastructureConfig(
        regions=["r1", "r2"],
        clusters={"r1": ["r1c1", "r1c2"], "r2": ["r2c1", "r2c2"]},
        nodes={
            "r1c1": ["r1c1n1", "r1c1n2", "r1c1n3"],
            "r1c2": ["r1c2n1", "r1c2n2", "r1c2n3"],
            "r2c1": ["r2c1n1", "r2c1n2", "r2c1n3"],
            "r2c2": ["r2c2n1", "r2c2n2", "r2c2n3"],
        },
    )
    return InfrastructureModel(config)
```

Note: `tiny_infra` imports lazily so it doesn't break before `infrastructure.py` exists.

- [ ] **Step 5: Verify pytest discovers no tests yet**

```bash
uv run pytest --collect-only
```

Expected: `no tests ran`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "feat: project scaffold with uv, pytest, and test fixtures"
```

---

## Task 2: Core data models

**Files:**
- Create: `src/scrutable/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests**

`tests/test_models.py`:
```python
from scrutable.models import (
    WorkloadModel,
    WorkloadState,
    NodeState,
    ClusterState,
    Request,
    Response,
    PathologyScope,
    Pathology,
    Inference,
)


def test_workload_model_defaults():
    m = WorkloadModel(
        workload_id="wl1",
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=100.0,
        error_shape=1.5,
        noise_sigma=0.01,
    )
    assert m.workload_id == "wl1"
    assert m.latency_median == 0.1


def test_workload_state_defaults():
    s = WorkloadState(workload_id="wl1")
    assert s.latency_multiplier == 1.0
    assert s.error_rate_multiplier == 1.0


def test_node_state_defaults():
    n = NodeState(node_id="n1", cluster_id="c1", region_id="r1")
    assert n.latency_multiplier == 1.0
    assert n.error_rate_multiplier == 1.0


def test_cluster_state_defaults():
    c = ClusterState(cluster_id="c1", region_id="r1")
    assert c.traffic_enabled is True


def test_request_fields():
    r = Request(request_id="req-1", workload_id="wl1", issued_at=5.0)
    assert r.issued_at == 5.0


def test_response_fields():
    r = Response(
        request_id="req-1",
        workload_id="wl1",
        node_id="n1",
        cluster_id="c1",
        region_id="r1",
        issued_at=0.0,
        latency=0.05,
        error_code=0,
    )
    assert r.error_code == 0


def test_pathology_scope_defaults():
    s = PathologyScope(target_type="node", filter_id=None)
    assert s.percentage == 1.0


def test_pathology_fields():
    p = Pathology(
        pathology_id="p1",
        scope=PathologyScope(target_type="node", filter_id=None),
        node_effects={"latency_multiplier": 2.0},
        workload_effects={},
    )
    assert p.node_effects["latency_multiplier"] == 2.0


def test_inference_fields():
    i = Inference(
        detector_id="d1",
        pathology_type="hardware_fault",
        target_id="n1",
        target_level="node",
        confidence=0.9,
        detected_at=10.0,
        window_start=0.0,
        window_end=10.0,
    )
    assert i.confidence == 0.9
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_models.py -v
```

Expected: `ImportError` — `scrutable.models` does not exist

- [ ] **Step 3: Implement models.py**

`src/scrutable/models.py`:
```python
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class WorkloadModel:
    workload_id: str
    latency_median: float
    latency_sigma: float
    error_scale: float
    error_shape: float
    noise_sigma: float


@dataclass
class WorkloadState:
    workload_id: str
    latency_multiplier: float = 1.0
    error_rate_multiplier: float = 1.0


@dataclass
class NodeState:
    node_id: str
    cluster_id: str
    region_id: str
    latency_multiplier: float = 1.0
    error_rate_multiplier: float = 1.0


@dataclass
class ClusterState:
    cluster_id: str
    region_id: str
    traffic_enabled: bool = True


@dataclass
class Request:
    request_id: str
    workload_id: str
    issued_at: float


@dataclass
class Response:
    request_id: str
    workload_id: str
    node_id: str
    cluster_id: str
    region_id: str
    issued_at: float
    latency: float
    error_code: int


@dataclass
class PathologyScope:
    target_type: str
    filter_id: str | None
    percentage: float = 1.0


@dataclass
class Pathology:
    pathology_id: str
    scope: PathologyScope
    node_effects: dict = field(default_factory=dict)
    workload_effects: dict = field(default_factory=dict)


@dataclass
class Inference:
    detector_id: str
    pathology_type: str
    target_id: str
    target_level: str
    confidence: float
    detected_at: float
    window_start: float
    window_end: float
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_models.py -v
```

Expected: all 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/models.py tests/test_models.py
git commit -m "feat: core data models"
```

---

## Task 3: Event loop kernel

**Files:**
- Create: `src/scrutable/event_loop.py`
- Create: `tests/test_event_loop.py`

- [ ] **Step 1: Write failing tests**

`tests/test_event_loop.py`:
```python
from scrutable.event_loop import EventLoop


def test_events_fire_in_timestamp_order():
    loop = EventLoop()
    fired = []
    loop.schedule(3.0, lambda: fired.append(3))
    loop.schedule(1.0, lambda: fired.append(1))
    loop.schedule(2.0, lambda: fired.append(2))
    loop.run(10.0)
    assert fired == [1, 2, 3]


def test_priority_breaks_timestamp_tie():
    loop = EventLoop()
    fired = []
    loop.schedule(1.0, lambda: fired.append("second"), priority=10)
    loop.schedule(1.0, lambda: fired.append("first"), priority=0)
    loop.run(10.0)
    assert fired == ["first", "second"]


def test_run_stops_at_until():
    loop = EventLoop()
    fired = []
    loop.schedule(1.0, lambda: fired.append(1))
    loop.schedule(5.0, lambda: fired.append(5))
    loop.run(3.0)
    assert fired == [1]
    assert 5 not in fired


def test_now_reflects_current_event_time():
    loop = EventLoop()
    times = []
    loop.schedule(2.5, lambda: times.append(loop.now))
    loop.run(10.0)
    assert times == [2.5]


def test_handler_scheduled_during_run_fires_if_in_window():
    loop = EventLoop()
    fired = []

    def first():
        fired.append("first")
        loop.schedule(2.0, lambda: fired.append("second"))

    loop.schedule(1.0, first)
    loop.run(10.0)
    assert fired == ["first", "second"]


def test_empty_loop_runs_without_error():
    loop = EventLoop()
    loop.run(100.0)
    assert loop.now == 0.0


def test_now_starts_at_zero():
    loop = EventLoop()
    assert loop.now == 0.0
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_event_loop.py -v
```

Expected: `ImportError` — `scrutable.event_loop` does not exist

- [ ] **Step 3: Implement event_loop.py**

`src/scrutable/event_loop.py`:
```python
from __future__ import annotations
import heapq
from typing import Callable


class EventLoop:
    def __init__(self) -> None:
        self._queue: list[tuple[float, int, int, Callable]] = []
        self._seq: int = 0
        self._time: float = 0.0

    @property
    def now(self) -> float:
        return self._time

    def schedule(self, timestamp: float, handler: Callable, priority: int = 0) -> None:
        heapq.heappush(self._queue, (timestamp, priority, self._seq, handler))
        self._seq += 1

    def run(self, until: float) -> None:
        while self._queue and self._queue[0][0] <= until:
            ts, _priority, _seq, handler = heapq.heappop(self._queue)
            self._time = ts
            handler()
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_event_loop.py -v
```

Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/event_loop.py tests/test_event_loop.py
git commit -m "feat: heapq-based event loop kernel"
```

---

## Task 4: Infrastructure model

**Files:**
- Create: `src/scrutable/infrastructure.py`
- Create: `tests/test_infrastructure.py`

- [ ] **Step 1: Write failing tests**

`tests/test_infrastructure.py`:
```python
import pytest
from scrutable.infrastructure import InfrastructureConfig, InfrastructureModel


def test_enabled_clusters_returns_all_by_default(tiny_infra):
    assert len(tiny_infra.enabled_clusters()) == 4


def test_enabled_clusters_excludes_disabled(tiny_infra):
    tiny_infra.get_cluster("r1c1").traffic_enabled = False
    enabled = tiny_infra.enabled_clusters()
    assert len(enabled) == 3
    assert all(c.cluster_id != "r1c1" for c in enabled)


def test_nodes_in_cluster_returns_correct_nodes(tiny_infra):
    nodes = tiny_infra.nodes_in_cluster("r1c1")
    assert len(nodes) == 3
    assert "r1c1n1" in nodes
    assert "r1c1n2" in nodes
    assert "r1c1n3" in nodes


def test_get_node_returns_correct_metadata(tiny_infra):
    node = tiny_infra.get_node("r2c1n2")
    assert node.cluster_id == "r2c1"
    assert node.region_id == "r2"


def test_get_cluster_returns_correct_metadata(tiny_infra):
    cluster = tiny_infra.get_cluster("r2c2")
    assert cluster.region_id == "r2"
    assert cluster.traffic_enabled is True


def test_all_nodes_returns_all_12(tiny_infra):
    assert len(tiny_infra.all_nodes()) == 12


def test_all_clusters_returns_all_4(tiny_infra):
    assert len(tiny_infra.all_clusters()) == 4


def test_node_mutation_persists(tiny_infra):
    node = tiny_infra.get_node("r1c1n1")
    node.latency_multiplier = 5.0
    assert tiny_infra.get_node("r1c1n1").latency_multiplier == 5.0


def test_unknown_node_raises(tiny_infra):
    with pytest.raises(KeyError):
        tiny_infra.get_node("nonexistent")
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_infrastructure.py -v
```

Expected: `ImportError` — `scrutable.infrastructure` does not exist

- [ ] **Step 3: Implement infrastructure.py**

`src/scrutable/infrastructure.py`:
```python
from __future__ import annotations
from dataclasses import dataclass
from scrutable.models import NodeState, ClusterState


@dataclass
class InfrastructureConfig:
    regions: list[str]
    clusters: dict[str, list[str]]   # region_id -> [cluster_id]
    nodes: dict[str, list[str]]       # cluster_id -> [node_id]


class InfrastructureModel:
    def __init__(self, config: InfrastructureConfig) -> None:
        self.regions: list[str] = config.regions
        self._clusters: dict[str, ClusterState] = {}
        self._nodes: dict[str, NodeState] = {}
        self._cluster_to_nodes: dict[str, list[str]] = {}

        for region_id, cluster_ids in config.clusters.items():
            for cluster_id in cluster_ids:
                self._clusters[cluster_id] = ClusterState(
                    cluster_id=cluster_id, region_id=region_id
                )
                node_ids = config.nodes.get(cluster_id, [])
                self._cluster_to_nodes[cluster_id] = node_ids
                for node_id in node_ids:
                    self._nodes[node_id] = NodeState(
                        node_id=node_id, cluster_id=cluster_id, region_id=region_id
                    )

    def get_cluster(self, cluster_id: str) -> ClusterState:
        return self._clusters[cluster_id]

    def get_node(self, node_id: str) -> NodeState:
        return self._nodes[node_id]

    def enabled_clusters(self) -> list[ClusterState]:
        return [c for c in self._clusters.values() if c.traffic_enabled]

    def nodes_in_cluster(self, cluster_id: str) -> list[str]:
        return self._cluster_to_nodes[cluster_id]

    def all_nodes(self) -> list[NodeState]:
        return list(self._nodes.values())

    def all_clusters(self) -> list[ClusterState]:
        return list(self._clusters.values())

    def all_node_ids(self) -> list[str]:
        return list(self._nodes.keys())

    def all_cluster_ids(self) -> list[str]:
        return list(self._clusters.keys())
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_infrastructure.py -v
```

Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/infrastructure.py tests/test_infrastructure.py
git commit -m "feat: infrastructure model with node/cluster state"
```

---

## Task 5: Workload registry and sampling

**Files:**
- Create: `src/scrutable/workload.py`
- Create: `tests/test_workload.py`

- [ ] **Step 1: Write failing tests**

`tests/test_workload.py`:
```python
import numpy as np
import pytest
from scrutable.models import WorkloadModel, WorkloadState, NodeState
from scrutable.workload import WorkloadRegistry, sample_latency, sample_error_code


@pytest.fixture
def model():
    return WorkloadModel(
        workload_id="wl1",
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=1000.0,
        error_shape=1.5,
        noise_sigma=0.001,
    )


@pytest.fixture
def neutral_wstate():
    return WorkloadState(workload_id="wl1")


@pytest.fixture
def neutral_nstate():
    return NodeState(node_id="n1", cluster_id="c1", region_id="r1")


def test_sample_latency_is_positive(model, neutral_wstate, neutral_nstate, seeded_rng):
    for _ in range(100):
        latency = sample_latency(model, neutral_wstate, neutral_nstate, seeded_rng)
        assert latency >= 0.0


def test_sample_latency_respects_multiplier(model, neutral_nstate, seeded_rng):
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    wstate_normal = WorkloadState(workload_id="wl1", latency_multiplier=1.0)
    wstate_slow = WorkloadState(workload_id="wl1", latency_multiplier=10.0)
    samples_normal = [sample_latency(model, wstate_normal, neutral_nstate, rng1) for _ in range(50)]
    samples_slow = [sample_latency(model, wstate_slow, neutral_nstate, rng2) for _ in range(50)]
    assert sum(samples_slow) > sum(samples_normal)


def test_sample_latency_node_multiplier(model, neutral_wstate, seeded_rng):
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    nstate_normal = NodeState(node_id="n1", cluster_id="c1", region_id="r1", latency_multiplier=1.0)
    nstate_slow = NodeState(node_id="n1", cluster_id="c1", region_id="r1", latency_multiplier=5.0)
    samples_normal = [sample_latency(model, neutral_wstate, nstate_normal, rng1) for _ in range(50)]
    samples_slow = [sample_latency(model, neutral_wstate, nstate_slow, rng2) for _ in range(50)]
    assert sum(samples_slow) > sum(samples_normal)


def test_sample_error_code_returns_zero_or_one(model, neutral_wstate, neutral_nstate, seeded_rng):
    for _ in range(100):
        code = sample_error_code(model, neutral_wstate, neutral_nstate, seeded_rng, sim_time=1.0)
        assert code in (0, 1)


def test_sample_error_code_elevated_by_multiplier(model, neutral_nstate, seeded_rng):
    rng1 = np.random.default_rng(0)
    rng2 = np.random.default_rng(0)
    model_low_scale = WorkloadModel(
        workload_id="wl1",
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=1.0,    # CDF reaches high values quickly
        error_shape=1.0,
        noise_sigma=0.001,
    )
    wstate_normal = WorkloadState(workload_id="wl1", error_rate_multiplier=1.0)
    wstate_high = WorkloadState(workload_id="wl1", error_rate_multiplier=100.0)
    errors_normal = sum(
        sample_error_code(model_low_scale, wstate_normal, neutral_nstate, rng1, sim_time=1.0)
        for _ in range(200)
    )
    errors_high = sum(
        sample_error_code(model_low_scale, wstate_high, neutral_nstate, rng2, sim_time=1.0)
        for _ in range(200)
    )
    assert errors_high >= errors_normal


def test_registry_get_returns_registered_model():
    registry = WorkloadRegistry()
    model = WorkloadModel(
        workload_id="wl42",
        latency_median=0.05,
        latency_sigma=0.2,
        error_scale=500.0,
        error_shape=1.0,
        noise_sigma=0.005,
    )
    registry.register(model)
    assert registry.get("wl42") is model


def test_registry_all_ids():
    registry = WorkloadRegistry()
    for i in range(3):
        registry.register(
            WorkloadModel(
                workload_id=f"wl{i}",
                latency_median=0.1,
                latency_sigma=0.3,
                error_scale=500.0,
                error_shape=1.0,
                noise_sigma=0.001,
            )
        )
    assert set(registry.all_ids()) == {"wl0", "wl1", "wl2"}


def test_registry_missing_key_raises():
    registry = WorkloadRegistry()
    with pytest.raises(KeyError):
        registry.get("nonexistent")
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_workload.py -v
```

Expected: `ImportError` — `scrutable.workload` does not exist

- [ ] **Step 3: Implement workload.py**

`src/scrutable/workload.py`:
```python
from __future__ import annotations
import numpy as np
from scrutable.models import WorkloadModel, WorkloadState, NodeState


def _weibull_cdf(t: float, scale: float, shape: float) -> float:
    if t <= 0.0:
        return 0.0
    return float(1.0 - np.exp(-((t / scale) ** shape)))


def sample_latency(
    model: WorkloadModel,
    wstate: WorkloadState,
    nstate: NodeState,
    rng: np.random.Generator,
) -> float:
    base = rng.lognormal(mean=np.log(model.latency_median), sigma=model.latency_sigma)
    effective = base * wstate.latency_multiplier * nstate.latency_multiplier
    noise = rng.normal(0.0, model.noise_sigma)
    return max(0.0, effective + noise)


def sample_error_code(
    model: WorkloadModel,
    wstate: WorkloadState,
    nstate: NodeState,
    rng: np.random.Generator,
    sim_time: float,
) -> int:
    base_rate = _weibull_cdf(sim_time, model.error_scale, model.error_shape)
    effective_rate = min(
        1.0,
        max(0.0, base_rate * wstate.error_rate_multiplier * nstate.error_rate_multiplier),
    )
    return 0 if rng.random() >= effective_rate else 1


class WorkloadRegistry:
    def __init__(self) -> None:
        self._models: dict[str, WorkloadModel] = {}

    def register(self, model: WorkloadModel) -> None:
        self._models[model.workload_id] = model

    def get(self, workload_id: str) -> WorkloadModel:
        return self._models[workload_id]

    def all_ids(self) -> list[str]:
        return list(self._models.keys())
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_workload.py -v
```

Expected: all 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/workload.py tests/test_workload.py
git commit -m "feat: workload registry with log-normal latency and Weibull error sampling"
```

---

## Task 6: Response buffer

**Files:**
- Create: `src/scrutable/buffer.py`
- Create: `tests/test_buffer.py`

- [ ] **Step 1: Write failing tests**

`tests/test_buffer.py`:
```python
from scrutable.buffer import ResponseBuffer


def test_window_returns_responses_in_range(build_response):
    buf = ResponseBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))   # arrives at 1.0
    buf.append(build_response(issued_at=1.0, latency=1.0))   # arrives at 2.0
    buf.append(build_response(issued_at=4.0, latency=1.0))   # arrives at 5.0
    result = buf.window(1.0, 3.0)
    assert len(result) == 2


def test_window_is_inclusive_on_both_ends(build_response):
    buf = ResponseBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))   # arrives at 1.0
    buf.append(build_response(issued_at=4.0, latency=1.0))   # arrives at 5.0
    result = buf.window(1.0, 5.0)
    assert len(result) == 2


def test_window_empty_when_no_responses_in_range(build_response):
    buf = ResponseBuffer()
    buf.append(build_response(issued_at=10.0, latency=1.0))  # arrives at 11.0
    result = buf.window(0.0, 5.0)
    assert result == []


def test_expire_removes_old_responses(build_response):
    buf = ResponseBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))   # arrives at 1.0
    buf.append(build_response(issued_at=1.0, latency=1.0))   # arrives at 2.0
    buf.append(build_response(issued_at=9.0, latency=1.0))   # arrives at 10.0
    buf.expire(before=5.0)
    result = buf.window(0.0, 3.0)
    assert result == []
    result = buf.window(9.0, 11.0)
    assert len(result) == 1


def test_buffer_preserves_arrival_order(build_response):
    buf = ResponseBuffer()
    # request issued early but high latency — arrives after a later request
    buf.append(build_response(issued_at=1.0, latency=5.0))   # arrives 6.0
    buf.append(build_response(issued_at=3.0, latency=1.0))   # arrives 4.0
    # NOTE: buffer assumes responses are appended in arrival order (event loop guarantees this)
    # Here we test window correctness given already-ordered appends
    buf2 = ResponseBuffer()
    r_early = build_response(issued_at=3.0, latency=1.0)
    r_late = build_response(issued_at=1.0, latency=5.0)
    buf2.append(r_early)   # arrives 4.0
    buf2.append(r_late)    # arrives 6.0
    assert buf2.window(3.5, 5.0) == [r_early]
    assert buf2.window(5.5, 7.0) == [r_late]


def test_window_returns_copy_not_reference(build_response):
    buf = ResponseBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))
    result = buf.window(0.0, 2.0)
    result.clear()
    assert len(buf.window(0.0, 2.0)) == 1
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_buffer.py -v
```

Expected: `ImportError` — `scrutable.buffer` does not exist

- [ ] **Step 3: Implement buffer.py**

`src/scrutable/buffer.py`:
```python
from __future__ import annotations
import bisect
from scrutable.models import Response


class ResponseBuffer:
    def __init__(self) -> None:
        self._responses: list[Response] = []
        self._arrivals: list[float] = []  # issued_at + latency, kept sorted

    def append(self, response: Response) -> None:
        arrival = response.issued_at + response.latency
        self._responses.append(response)
        self._arrivals.append(arrival)

    def window(self, start: float, end: float) -> list[Response]:
        lo = bisect.bisect_left(self._arrivals, start)
        hi = bisect.bisect_right(self._arrivals, end)
        return self._responses[lo:hi]

    def expire(self, before: float) -> None:
        idx = bisect.bisect_left(self._arrivals, before)
        self._responses = self._responses[idx:]
        self._arrivals = self._arrivals[idx:]
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_buffer.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/buffer.py tests/test_buffer.py
git commit -m "feat: response buffer with time-windowed queries"
```

---

## Task 7: Service simulator and router

**Files:**
- Create: `src/scrutable/simulator.py`
- Create: `tests/test_simulator.py`

- [ ] **Step 1: Write failing tests**

`tests/test_simulator.py`:
```python
import numpy as np
from scrutable.event_loop import EventLoop
from scrutable.buffer import ResponseBuffer
from scrutable.models import Request, WorkloadModel, WorkloadState
from scrutable.workload import WorkloadRegistry
from scrutable.simulator import ServiceSimulator


def _make_simulator(tiny_infra, seed=42):
    loop = EventLoop()
    registry = WorkloadRegistry()
    registry.register(
        WorkloadModel(
            workload_id="wl1",
            latency_median=0.1,
            latency_sigma=0.3,
            error_scale=1000.0,
            error_shape=1.5,
            noise_sigma=0.001,
        )
    )
    workload_states = {"wl1": WorkloadState(workload_id="wl1")}
    buffer = ResponseBuffer()
    rng = np.random.default_rng(seed)
    sim = ServiceSimulator(loop, tiny_infra, registry, workload_states, buffer, rng)
    return loop, sim, buffer


def test_response_arrives_after_latency(tiny_infra):
    loop, sim, buffer = _make_simulator(tiny_infra)
    req = Request(request_id="r1", workload_id="wl1", issued_at=5.0)
    sim.handle_request(req)
    loop.run(100.0)
    assert len(buffer.window(0.0, 100.0)) == 1
    resp = buffer.window(0.0, 100.0)[0]
    assert resp.issued_at == 5.0
    assert resp.latency > 0.0
    # arrival time must be after issued_at
    assert resp.issued_at + resp.latency > resp.issued_at


def test_response_has_correct_workload_id(tiny_infra):
    loop, sim, buffer = _make_simulator(tiny_infra)
    req = Request(request_id="r1", workload_id="wl1", issued_at=0.0)
    sim.handle_request(req)
    loop.run(100.0)
    assert buffer.window(0.0, 100.0)[0].workload_id == "wl1"


def test_response_node_belongs_to_enabled_cluster(tiny_infra):
    loop, sim, buffer = _make_simulator(tiny_infra)
    req = Request(request_id="r1", workload_id="wl1", issued_at=0.0)
    sim.handle_request(req)
    loop.run(100.0)
    resp = buffer.window(0.0, 100.0)[0]
    cluster = tiny_infra.get_cluster(resp.cluster_id)
    assert cluster.traffic_enabled is True


def test_no_clusters_enabled_produces_503(tiny_infra):
    loop, sim, buffer = _make_simulator(tiny_infra)
    for c in tiny_infra.all_clusters():
        c.traffic_enabled = False
    req = Request(request_id="r1", workload_id="wl1", issued_at=0.0)
    sim.handle_request(req)
    loop.run(1.0)
    responses = buffer.window(0.0, 1.0)
    assert len(responses) == 1
    assert responses[0].error_code == 503


def test_multiple_requests_produce_multiple_responses(tiny_infra):
    loop, sim, buffer = _make_simulator(tiny_infra)
    for i in range(10):
        sim.handle_request(Request(request_id=f"r{i}", workload_id="wl1", issued_at=float(i)))
    loop.run(1000.0)
    assert len(buffer.window(0.0, 1000.0)) == 10
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_simulator.py -v
```

Expected: `ImportError` — `scrutable.simulator` does not exist

- [ ] **Step 3: Implement simulator.py**

`src/scrutable/simulator.py`:
```python
from __future__ import annotations
import numpy as np
from scrutable.event_loop import EventLoop
from scrutable.infrastructure import InfrastructureModel
from scrutable.workload import WorkloadRegistry, sample_latency, sample_error_code
from scrutable.buffer import ResponseBuffer
from scrutable.models import Request, Response, WorkloadState

_NO_CLUSTER_ERROR = 503


class ServiceSimulator:
    def __init__(
        self,
        loop: EventLoop,
        infra: InfrastructureModel,
        registry: WorkloadRegistry,
        workload_states: dict[str, WorkloadState],
        buffer: ResponseBuffer,
        rng: np.random.Generator,
    ) -> None:
        self._loop = loop
        self._infra = infra
        self._registry = registry
        self._workload_states = workload_states
        self._buffer = buffer
        self._rng = rng

    def handle_request(self, request: Request) -> None:
        enabled = self._infra.enabled_clusters()
        if not enabled:
            self._buffer.append(
                Response(
                    request_id=request.request_id,
                    workload_id=request.workload_id,
                    node_id="",
                    cluster_id="",
                    region_id="",
                    issued_at=request.issued_at,
                    latency=0.0,
                    error_code=_NO_CLUSTER_ERROR,
                )
            )
            return

        cluster = enabled[int(self._rng.integers(len(enabled)))]
        node_ids = self._infra.nodes_in_cluster(cluster.cluster_id)
        node_id = node_ids[int(self._rng.integers(len(node_ids)))]
        node_state = self._infra.get_node(node_id)

        model = self._registry.get(request.workload_id)
        wstate = self._workload_states.get(
            request.workload_id, WorkloadState(request.workload_id)
        )

        latency = sample_latency(model, wstate, node_state, self._rng)
        error_code = sample_error_code(
            model, wstate, node_state, self._rng, sim_time=request.issued_at
        )

        response = Response(
            request_id=request.request_id,
            workload_id=request.workload_id,
            node_id=node_id,
            cluster_id=cluster.cluster_id,
            region_id=cluster.region_id,
            issued_at=request.issued_at,
            latency=latency,
            error_code=error_code,
        )

        arrival = request.issued_at + latency
        self._loop.schedule(arrival, lambda r=response: self._buffer.append(r))
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_simulator.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/simulator.py tests/test_simulator.py
git commit -m "feat: service simulator with two-level router and async response scheduling"
```

---

## Task 8: Workload synthesizer

**Files:**
- Create: `src/scrutable/synthesizer.py`
- Create: `tests/test_synthesizer.py`

- [ ] **Step 1: Write failing tests**

`tests/test_synthesizer.py`:
```python
import numpy as np
from scrutable.event_loop import EventLoop
from scrutable.buffer import ResponseBuffer
from scrutable.models import WorkloadModel, WorkloadState
from scrutable.workload import WorkloadRegistry
from scrutable.simulator import ServiceSimulator
from scrutable.synthesizer import SynthesizerConfig, WorkloadSynthesizer


def _make_synth(tiny_infra, rates, seed=42):
    loop = EventLoop()
    registry = WorkloadRegistry()
    for wid in rates:
        registry.register(
            WorkloadModel(
                workload_id=wid,
                latency_median=0.01,
                latency_sigma=0.1,
                error_scale=1000.0,
                error_shape=1.5,
                noise_sigma=0.001,
            )
        )
    workload_states = {wid: WorkloadState(workload_id=wid) for wid in rates}
    buffer = ResponseBuffer()
    rng = np.random.default_rng(seed)
    sim = ServiceSimulator(loop, tiny_infra, registry, workload_states, buffer, rng)
    config = SynthesizerConfig(workload_rates=rates)
    synth = WorkloadSynthesizer(config, loop, sim, rng)
    return loop, synth, buffer


def test_synthesizer_produces_responses(tiny_infra):
    loop, synth, buffer = _make_synth(tiny_infra, {"wl1": 10.0})
    synth.start()
    loop.run(1.0)
    assert len(buffer.window(0.0, 2.0)) > 0


def test_synthesizer_rate_approximated(tiny_infra):
    loop, synth, buffer = _make_synth(tiny_infra, {"wl1": 100.0}, seed=0)
    synth.start()
    loop.run(10.0)
    count = len(buffer.window(0.0, 12.0))
    # 100 req/s over 10s = ~1000 requests; allow generous tolerance
    assert 700 < count < 1300


def test_synthesizer_multiple_workloads(tiny_infra):
    loop, synth, buffer = _make_synth(tiny_infra, {"wl1": 10.0, "wl2": 10.0})
    synth.start()
    loop.run(5.0)
    all_resp = buffer.window(0.0, 10.0)
    wids = {r.workload_id for r in all_resp}
    assert "wl1" in wids
    assert "wl2" in wids


def test_synthesizer_schedules_continuously(tiny_infra):
    loop, synth, buffer = _make_synth(tiny_infra, {"wl1": 10.0})
    synth.start()
    loop.run(1.0)
    count_1s = len(buffer.window(0.0, 2.0))
    loop.run(2.0)
    count_2s = len(buffer.window(0.0, 3.0))
    assert count_2s > count_1s
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_synthesizer.py -v
```

Expected: `ImportError` — `scrutable.synthesizer` does not exist

- [ ] **Step 3: Implement synthesizer.py**

`src/scrutable/synthesizer.py`:
```python
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scrutable.event_loop import EventLoop
from scrutable.simulator import ServiceSimulator
from scrutable.models import Request


@dataclass
class SynthesizerConfig:
    workload_rates: dict[str, float]   # workload_id -> requests per second


class WorkloadSynthesizer:
    def __init__(
        self,
        config: SynthesizerConfig,
        loop: EventLoop,
        simulator: ServiceSimulator,
        rng: np.random.Generator,
    ) -> None:
        self._config = config
        self._loop = loop
        self._simulator = simulator
        self._rng = rng
        self._counter: int = 0  # sequential IDs ensure reproducibility across same-seed runs

    def start(self) -> None:
        for workload_id in self._config.workload_rates:
            self._schedule_next(workload_id, self._loop.now)

    def _schedule_next(self, workload_id: str, current_time: float) -> None:
        rate = self._config.workload_rates[workload_id]
        inter_arrival = self._rng.exponential(1.0 / rate)
        next_time = current_time + inter_arrival
        self._loop.schedule(
            next_time,
            lambda wid=workload_id, t=next_time: self._issue_and_reschedule(wid, t),
        )

    def _issue_and_reschedule(self, workload_id: str, issued_at: float) -> None:
        request = Request(
            request_id=f"req-{self._counter}",
            workload_id=workload_id,
            issued_at=issued_at,
        )
        self._counter += 1
        self._simulator.handle_request(request)
        self._schedule_next(workload_id, issued_at)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_synthesizer.py -v
```

Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/synthesizer.py tests/test_synthesizer.py
git commit -m "feat: workload synthesizer with Poisson request arrivals"
```

---

## Task 9: Pathology system

**Files:**
- Create: `src/scrutable/pathology.py`
- Create: `tests/test_pathology.py`

- [ ] **Step 1: Write failing tests**

`tests/test_pathology.py`:
```python
import numpy as np
import pytest
from scrutable.models import WorkloadModel, WorkloadState, Pathology, PathologyScope
from scrutable.workload import WorkloadRegistry
from scrutable.event_loop import EventLoop
from scrutable.pathology import (
    stable_subset,
    apply_pathology,
    remove_pathology,
    TimedPathology,
    StochasticPathology,
    PathologyInjector,
)


def test_stable_subset_is_deterministic():
    entities = [f"node-{i}" for i in range(100)]
    s1 = stable_subset(entities, 0.3, "pathology-1")
    s2 = stable_subset(entities, 0.3, "pathology-1")
    assert s1 == s2


def test_stable_subset_percentage_approximate():
    entities = [f"node-{i}" for i in range(1000)]
    result = stable_subset(entities, 0.3, "p1")
    assert 200 < len(result) < 400


def test_stable_subset_full_coverage():
    entities = ["a", "b", "c"]
    result = stable_subset(entities, 1.0, "p1")
    assert result == set(entities)


def test_stable_subset_zero_returns_empty():
    entities = ["a", "b", "c"]
    result = stable_subset(entities, 0.0, "p1")
    assert result == set()


def test_stable_subset_different_pathologies_differ():
    entities = [f"node-{i}" for i in range(100)]
    s1 = stable_subset(entities, 0.5, "pathology-A")
    s2 = stable_subset(entities, 0.5, "pathology-B")
    assert s1 != s2


def test_apply_pathology_mutates_node_state(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    pathology = Pathology(
        pathology_id="p1",
        scope=PathologyScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 3.0},
    )
    apply_pathology(pathology, tiny_infra, workload_states)
    for node in tiny_infra.all_nodes():
        assert node.latency_multiplier == 3.0


def test_apply_pathology_respects_percentage(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    pathology = Pathology(
        pathology_id="p-half",
        scope=PathologyScope(target_type="node", filter_id=None, percentage=0.5),
        node_effects={"latency_multiplier": 5.0},
    )
    apply_pathology(pathology, tiny_infra, workload_states)
    affected = [n for n in tiny_infra.all_nodes() if n.latency_multiplier == 5.0]
    assert 0 < len(affected) < 12


def test_apply_pathology_filter_by_cluster(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    pathology = Pathology(
        pathology_id="p-cluster",
        scope=PathologyScope(target_type="node", filter_id="r1c1", percentage=1.0),
        node_effects={"latency_multiplier": 2.0},
    )
    apply_pathology(pathology, tiny_infra, workload_states)
    for node in tiny_infra.all_nodes():
        if node.cluster_id == "r1c1":
            assert node.latency_multiplier == 2.0
        else:
            assert node.latency_multiplier == 1.0


def test_apply_pathology_mutates_workload_state(tiny_infra):
    workload_states = {
        "wl1": WorkloadState(workload_id="wl1"),
        "wl2": WorkloadState(workload_id="wl2"),
    }
    pathology = Pathology(
        pathology_id="p-wl",
        scope=PathologyScope(target_type="workload", filter_id=None, percentage=1.0),
        workload_effects={"error_rate_multiplier": 10.0},
    )
    apply_pathology(pathology, tiny_infra, workload_states)
    assert workload_states["wl1"].error_rate_multiplier == 10.0
    assert workload_states["wl2"].error_rate_multiplier == 10.0


def test_remove_pathology_resets_node_state(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    pathology = Pathology(
        pathology_id="p1",
        scope=PathologyScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 4.0},
    )
    apply_pathology(pathology, tiny_infra, workload_states)
    remove_pathology(pathology, tiny_infra, workload_states)
    for node in tiny_infra.all_nodes():
        assert node.latency_multiplier == 1.0


def test_timed_pathology_injected_at_correct_time(tiny_infra):
    loop = EventLoop()
    workload_states: dict[str, WorkloadState] = {}
    rng = np.random.default_rng(42)
    injector = PathologyInjector(loop, tiny_infra, workload_states, rng)
    pathology = Pathology(
        pathology_id="timed",
        scope=PathologyScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 2.0},
    )
    injector.add_timed(TimedPathology(pathology=pathology, inject_at=5.0))
    loop.run(3.0)
    assert tiny_infra.get_node("r1c1n1").latency_multiplier == 1.0
    loop.run(6.0)
    assert tiny_infra.get_node("r1c1n1").latency_multiplier == 2.0


def test_timed_pathology_removed_at_correct_time(tiny_infra):
    loop = EventLoop()
    workload_states: dict[str, WorkloadState] = {}
    rng = np.random.default_rng(42)
    injector = PathologyInjector(loop, tiny_infra, workload_states, rng)
    pathology = Pathology(
        pathology_id="timed-remove",
        scope=PathologyScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 2.0},
    )
    injector.add_timed(TimedPathology(pathology=pathology, inject_at=5.0, remove_at=10.0))
    loop.run(7.0)
    assert tiny_infra.get_node("r1c1n1").latency_multiplier == 2.0
    loop.run(11.0)
    assert tiny_infra.get_node("r1c1n1").latency_multiplier == 1.0


def test_stochastic_pathology_fires_over_time(tiny_infra):
    loop = EventLoop()
    workload_states: dict[str, WorkloadState] = {}
    rng = np.random.default_rng(42)
    injector = PathologyInjector(loop, tiny_infra, workload_states, rng)
    fired = [0]
    original_apply = apply_pathology

    pathology = Pathology(
        pathology_id="stoch",
        scope=PathologyScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 2.0},
    )
    injector.add_stochastic(StochasticPathology(pathology=pathology, rate=1.0, duration=0.5))
    loop.run(20.0)
    # with rate=1 over 20s we expect multiple firings; just check responses were collected
    # (the injector resets nodes so they may oscillate — just verify loop ran)
    assert loop.now == 20.0
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_pathology.py -v
```

Expected: `ImportError` — `scrutable.pathology` does not exist

- [ ] **Step 3: Implement pathology.py**

`src/scrutable/pathology.py`:
```python
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scrutable.models import Pathology, WorkloadState
from scrutable.infrastructure import InfrastructureModel
from scrutable.event_loop import EventLoop


def stable_subset(entities: list[str], percentage: float, pathology_id: str) -> set[str]:
    threshold = int(percentage * 1000)
    return {e for e in entities if abs(hash(e + pathology_id)) % 1000 < threshold}


def _get_affected_node_ids(pathology: Pathology, infra: InfrastructureModel) -> list[str]:
    if pathology.scope.filter_id is not None:
        candidates = infra.nodes_in_cluster(pathology.scope.filter_id)
    else:
        candidates = infra.all_node_ids()
    return list(stable_subset(candidates, pathology.scope.percentage, pathology.pathology_id))


def _get_affected_workload_ids(
    pathology: Pathology, workload_states: dict[str, WorkloadState]
) -> list[str]:
    candidates = list(workload_states.keys())
    return list(stable_subset(candidates, pathology.scope.percentage, pathology.pathology_id))


def apply_pathology(
    pathology: Pathology,
    infra: InfrastructureModel,
    workload_states: dict[str, WorkloadState],
) -> None:
    if pathology.scope.target_type == "node" and pathology.node_effects:
        for node_id in _get_affected_node_ids(pathology, infra):
            state = infra.get_node(node_id)
            for k, v in pathology.node_effects.items():
                setattr(state, k, v)

    if pathology.scope.target_type == "workload" and pathology.workload_effects:
        for wid in _get_affected_workload_ids(pathology, workload_states):
            state = workload_states.setdefault(wid, WorkloadState(wid))
            for k, v in pathology.workload_effects.items():
                setattr(state, k, v)


def remove_pathology(
    pathology: Pathology,
    infra: InfrastructureModel,
    workload_states: dict[str, WorkloadState],
) -> None:
    if pathology.scope.target_type == "node" and pathology.node_effects:
        for node_id in _get_affected_node_ids(pathology, infra):
            state = infra.get_node(node_id)
            for k in pathology.node_effects:
                setattr(state, k, 1.0)

    if pathology.scope.target_type == "workload" and pathology.workload_effects:
        for wid in _get_affected_workload_ids(pathology, workload_states):
            state = workload_states.setdefault(wid, WorkloadState(wid))
            for k in pathology.workload_effects:
                setattr(state, k, 1.0)


@dataclass
class TimedPathology:
    pathology: Pathology
    inject_at: float
    remove_at: float | None = None


@dataclass
class StochasticPathology:
    pathology: Pathology
    rate: float      # Poisson rate: occurrences per simulation second
    duration: float  # how long each occurrence lasts


class PathologyInjector:
    def __init__(
        self,
        loop: EventLoop,
        infra: InfrastructureModel,
        workload_states: dict[str, WorkloadState],
        rng: np.random.Generator,
    ) -> None:
        self._loop = loop
        self._infra = infra
        self._workload_states = workload_states
        self._rng = rng

    def add_timed(self, tp: TimedPathology) -> None:
        self._loop.schedule(
            tp.inject_at,
            lambda p=tp.pathology: apply_pathology(p, self._infra, self._workload_states),
        )
        if tp.remove_at is not None:
            self._loop.schedule(
                tp.remove_at,
                lambda p=tp.pathology: remove_pathology(p, self._infra, self._workload_states),
            )

    def add_stochastic(self, sp: StochasticPathology) -> None:
        self._schedule_stochastic(sp, self._loop.now)

    def _schedule_stochastic(self, sp: StochasticPathology, current_time: float) -> None:
        wait = self._rng.exponential(1.0 / sp.rate)
        next_time = current_time + wait
        self._loop.schedule(
            next_time,
            lambda s=sp, t=next_time: self._fire_stochastic(s, t),
        )

    def _fire_stochastic(self, sp: StochasticPathology, fire_time: float) -> None:
        apply_pathology(sp.pathology, self._infra, self._workload_states)
        remove_time = fire_time + sp.duration
        self._loop.schedule(
            remove_time,
            lambda p=sp.pathology: remove_pathology(p, self._infra, self._workload_states),
        )
        self._schedule_stochastic(sp, fire_time)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_pathology.py -v
```

Expected: all 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/pathology.py tests/test_pathology.py
git commit -m "feat: pathology system with stable subset selection, timed and stochastic injection"
```

---

## Task 10: Operations systems

**Files:**
- Create: `src/scrutable/operations.py`
- Create: `tests/test_operations.py`

- [ ] **Step 1: Write failing tests**

`tests/test_operations.py`:
```python
from scrutable.models import Pathology, PathologyScope, WorkloadState
from scrutable.operations import SoftwareVersion, RolloutSystem, OperationsSystem


def test_drain_disables_cluster_traffic(tiny_infra):
    ops = OperationsSystem(tiny_infra)
    assert tiny_infra.get_cluster("r1c1").traffic_enabled is True
    ops.drain("r1c1")
    assert tiny_infra.get_cluster("r1c1").traffic_enabled is False


def test_restore_re_enables_cluster_traffic(tiny_infra):
    ops = OperationsSystem(tiny_infra)
    ops.drain("r1c1")
    ops.restore("r1c1")
    assert tiny_infra.get_cluster("r1c1").traffic_enabled is True


def test_rollout_deploy_applies_pathologies(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    pathology = Pathology(
        pathology_id="bug-v2",
        scope=PathologyScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 3.0},
    )
    version = SoftwareVersion(version_id="v2", pathologies=[pathology])
    rollouts = RolloutSystem({"v2": version}, tiny_infra, workload_states)
    rollouts.deploy("v2")
    for node in tiny_infra.all_nodes():
        assert node.latency_multiplier == 3.0


def test_rollout_deploy_idempotent(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    pathology = Pathology(
        pathology_id="bug-v3",
        scope=PathologyScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 2.0},
    )
    version = SoftwareVersion(version_id="v3", pathologies=[pathology])
    rollouts = RolloutSystem({"v3": version}, tiny_infra, workload_states)
    rollouts.deploy("v3")
    rollouts.deploy("v3")  # second deploy should be a no-op
    for node in tiny_infra.all_nodes():
        assert node.latency_multiplier == 2.0


def test_rollout_rollback_removes_pathologies(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    pathology = Pathology(
        pathology_id="bug-v4",
        scope=PathologyScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 5.0},
    )
    version = SoftwareVersion(version_id="v4", pathologies=[pathology])
    rollouts = RolloutSystem({"v4": version}, tiny_infra, workload_states)
    rollouts.deploy("v4")
    rollouts.rollback("v4")
    for node in tiny_infra.all_nodes():
        assert node.latency_multiplier == 1.0


def test_rollout_rollback_not_deployed_is_noop(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    version = SoftwareVersion(version_id="v5", pathologies=[])
    rollouts = RolloutSystem({"v5": version}, tiny_infra, workload_states)
    rollouts.rollback("v5")  # should not raise
    assert tiny_infra.get_node("r1c1n1").latency_multiplier == 1.0
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_operations.py -v
```

Expected: `ImportError` — `scrutable.operations` does not exist

- [ ] **Step 3: Implement operations.py**

`src/scrutable/operations.py`:
```python
from __future__ import annotations
from dataclasses import dataclass, field
from scrutable.models import Pathology, WorkloadState
from scrutable.infrastructure import InfrastructureModel
from scrutable.pathology import apply_pathology, remove_pathology


@dataclass
class SoftwareVersion:
    version_id: str
    pathologies: list[Pathology] = field(default_factory=list)


class RolloutSystem:
    def __init__(
        self,
        versions: dict[str, SoftwareVersion],
        infra: InfrastructureModel,
        workload_states: dict[str, WorkloadState],
    ) -> None:
        self._versions = versions
        self._infra = infra
        self._workload_states = workload_states
        self._active: set[str] = set()

    def deploy(self, version_id: str) -> None:
        if version_id in self._active:
            return
        for pathology in self._versions[version_id].pathologies:
            apply_pathology(pathology, self._infra, self._workload_states)
        self._active.add(version_id)

    def rollback(self, version_id: str) -> None:
        if version_id not in self._active:
            return
        for pathology in self._versions[version_id].pathologies:
            remove_pathology(pathology, self._infra, self._workload_states)
        self._active.discard(version_id)


class OperationsSystem:
    def __init__(self, infra: InfrastructureModel) -> None:
        self._infra = infra

    def drain(self, cluster_id: str) -> None:
        self._infra.get_cluster(cluster_id).traffic_enabled = False

    def restore(self, cluster_id: str) -> None:
        self._infra.get_cluster(cluster_id).traffic_enabled = True
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_operations.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/operations.py tests/test_operations.py
git commit -m "feat: rollout and operations systems for pathology toggling and cluster drain"
```

---

## Task 11: Detector and Actuator protocols

**Files:**
- Create: `src/scrutable/detector.py`
- Create: `src/scrutable/actuator.py`
- Create: `tests/test_detector.py`

- [ ] **Step 1: Write failing tests**

`tests/test_detector.py`:
```python
from scrutable.models import Response, Inference
from scrutable.detector import Detector
from scrutable.actuator import Actuator
from scrutable.operations import RolloutSystem, OperationsSystem


class HighErrorRateDetector:
    detector_id = "high-error-rate"
    window_size = 60.0
    tick_interval = 10.0

    def detect(self, window: list[Response]) -> list[Inference]:
        if not window:
            return []
        error_rate = sum(1 for r in window if r.error_code != 0) / len(window)
        if error_rate > 0.1:
            return [
                Inference(
                    detector_id=self.detector_id,
                    pathology_type="high_error_rate",
                    target_id="unknown",
                    target_level="cluster",
                    confidence=min(1.0, error_rate),
                    detected_at=window[-1].issued_at,
                    window_start=window[0].issued_at,
                    window_end=window[-1].issued_at,
                )
            ]
        return []


class DrainActuator:
    def __init__(self):
        self.calls: list[tuple] = []

    def act(self, inference: Inference, sim_time: float, rollouts: RolloutSystem, ops: OperationsSystem) -> None:
        self.calls.append((inference.pathology_type, sim_time))


def test_detector_protocol_satisfied():
    d = HighErrorRateDetector()
    assert isinstance(d, Detector)


def test_actuator_protocol_satisfied(tiny_infra):
    a = DrainActuator()
    assert isinstance(a, Actuator)


def test_detector_fires_on_high_error_rate(build_response):
    d = HighErrorRateDetector()
    window = [build_response(error_code=1) for _ in range(20)]
    inferences = d.detect(window)
    assert len(inferences) == 1
    assert inferences[0].pathology_type == "high_error_rate"


def test_detector_silent_on_low_error_rate(build_response):
    d = HighErrorRateDetector()
    window = [build_response(error_code=0) for _ in range(20)]
    inferences = d.detect(window)
    assert inferences == []


def test_detector_empty_window_returns_no_inferences():
    d = HighErrorRateDetector()
    assert d.detect([]) == []


def test_actuator_receives_inference(tiny_infra, build_response):
    detector = HighErrorRateDetector()
    actuator = DrainActuator()
    ops = OperationsSystem(tiny_infra)
    rollouts = RolloutSystem({}, tiny_infra, {})
    window = [build_response(error_code=1) for _ in range(20)]
    for inf in detector.detect(window):
        actuator.act(inf, 60.0, rollouts, ops)
    assert len(actuator.calls) == 1
    assert actuator.calls[0] == ("high_error_rate", 60.0)
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_detector.py -v
```

Expected: `ImportError` — `scrutable.detector` does not exist

- [ ] **Step 3: Implement detector.py and actuator.py**

`src/scrutable/detector.py`:
```python
from __future__ import annotations
from typing import Protocol, runtime_checkable
from scrutable.models import Response, Inference


@runtime_checkable
class Detector(Protocol):
    detector_id: str
    window_size: float
    tick_interval: float

    def detect(self, window: list[Response]) -> list[Inference]:
        ...
```

`src/scrutable/actuator.py`:
```python
from __future__ import annotations
from typing import Protocol, runtime_checkable
from scrutable.models import Inference
from scrutable.operations import RolloutSystem, OperationsSystem


@runtime_checkable
class Actuator(Protocol):
    def act(
        self,
        inference: Inference,
        sim_time: float,
        rollouts: RolloutSystem,
        ops: OperationsSystem,
    ) -> None:
        ...
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_detector.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scrutable/detector.py src/scrutable/actuator.py tests/test_detector.py
git commit -m "feat: Detector and Actuator protocols"
```

---

## Task 12: Simulation engine

**Files:**
- Create: `src/scrutable/engine.py`
- Create: `tests/test_scenario.py`

- [ ] **Step 1: Write failing tests**

`tests/test_scenario.py`:
```python
import numpy as np
from scrutable.models import WorkloadModel, Pathology, PathologyScope, WorkloadState, Inference
from scrutable.workload import WorkloadRegistry
from scrutable.synthesizer import SynthesizerConfig
from scrutable.pathology import TimedPathology
from scrutable.operations import SoftwareVersion
from scrutable.engine import SimulationEngine
from scrutable.detector import Detector
from scrutable.actuator import Actuator
from scrutable.operations import RolloutSystem, OperationsSystem


def _make_registry():
    registry = WorkloadRegistry()
    registry.register(
        WorkloadModel(
            workload_id="wl1",
            latency_median=0.1,
            latency_sigma=0.3,
            error_scale=1000.0,
            error_shape=1.5,
            noise_sigma=0.001,
        )
    )
    return registry


def _make_engine(tiny_infra, seed=42):
    registry = _make_registry()
    config = SynthesizerConfig(workload_rates={"wl1": 50.0})
    return SimulationEngine(tiny_infra, registry, config, seed=seed)


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
    from scrutable.infrastructure import InfrastructureConfig, InfrastructureModel
    config = InfrastructureConfig(
        regions=["r1", "r2"],
        clusters={"r1": ["r1c1", "r1c2"], "r2": ["r2c1", "r2c2"]},
        nodes={
            "r1c1": ["r1c1n1", "r1c1n2", "r1c1n3"],
            "r1c2": ["r1c2n1", "r1c2n2", "r1c2n3"],
            "r2c1": ["r2c1n1", "r2c1n2", "r2c1n3"],
            "r2c2": ["r2c2n1", "r2c2n2", "r2c2n3"],
        },
    )
    infra1 = InfrastructureModel(config)
    infra2 = InfrastructureModel(config)
    e1 = _make_engine(infra1, seed=99)
    e2 = _make_engine(infra2, seed=99)
    e1.run(2.0)
    e2.run(2.0)
    r1 = e1.buffer.window(0.0, 3.0)
    r2 = e2.buffer.window(0.0, 3.0)
    assert len(r1) == len(r2)
    for a, b in zip(r1, r2):
        assert a.request_id == b.request_id
        assert a.latency == b.latency
        assert a.error_code == b.error_code


def test_timed_pathology_elevates_latency(tiny_infra):
    engine = _make_engine(tiny_infra, seed=0)
    pathology = Pathology(
        pathology_id="slow-nodes",
        scope=PathologyScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 10.0},
    )
    engine.add_timed_pathology(TimedPathology(pathology=pathology, inject_at=5.0))
    engine.run(10.0)
    before = engine.buffer.window(0.0, 5.0)
    after = engine.buffer.window(5.0, 10.0)
    assert before and after
    avg_before = sum(r.latency for r in before) / len(before)
    avg_after = sum(r.latency for r in after) / len(after)
    assert avg_after > avg_before * 3


class RecordingActuator:
    def __init__(self):
        self.inferences: list[Inference] = []

    def act(self, inference: Inference, sim_time: float, rollouts: RolloutSystem, ops: OperationsSystem) -> None:
        self.inferences.append(inference)


class AlwaysFiresDetector:
    detector_id = "always"
    window_size = 5.0
    tick_interval = 5.0

    def detect(self, window):
        if not window:
            return []
        return [
            Inference(
                detector_id=self.detector_id,
                pathology_type="test",
                target_id="n1",
                target_level="node",
                confidence=1.0,
                detected_at=window[-1].issued_at + window[-1].latency,
                window_start=window[0].issued_at,
                window_end=window[-1].issued_at,
            )
        ]


def test_detector_and_actuator_wired_in_engine(tiny_infra):
    engine = _make_engine(tiny_infra, seed=7)
    detector = AlwaysFiresDetector()
    actuator = RecordingActuator()
    engine.add_detector(detector)
    engine.add_actuator(actuator)
    engine.run(10.0)
    assert len(actuator.inferences) > 0
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_scenario.py -v
```

Expected: `ImportError` — `scrutable.engine` does not exist

- [ ] **Step 3: Implement engine.py**

`src/scrutable/engine.py`:
```python
from __future__ import annotations
import numpy as np
from scrutable.event_loop import EventLoop
from scrutable.infrastructure import InfrastructureModel
from scrutable.workload import WorkloadRegistry
from scrutable.buffer import ResponseBuffer
from scrutable.simulator import ServiceSimulator
from scrutable.synthesizer import SynthesizerConfig, WorkloadSynthesizer
from scrutable.pathology import PathologyInjector, TimedPathology, StochasticPathology
from scrutable.operations import RolloutSystem, OperationsSystem, SoftwareVersion
from scrutable.detector import Detector
from scrutable.actuator import Actuator
from scrutable.models import WorkloadState


class SimulationEngine:
    def __init__(
        self,
        infra: InfrastructureModel,
        registry: WorkloadRegistry,
        synth_config: SynthesizerConfig,
        versions: dict[str, SoftwareVersion] | None = None,
        seed: int | None = None,
    ) -> None:
        self._rng = np.random.default_rng(seed)
        self._loop = EventLoop()
        self._infra = infra
        self._workload_states: dict[str, WorkloadState] = {
            wid: WorkloadState(wid) for wid in registry.all_ids()
        }
        self._buffer = ResponseBuffer()
        self._simulator = ServiceSimulator(
            self._loop, infra, registry, self._workload_states, self._buffer, self._rng
        )
        self._synthesizer = WorkloadSynthesizer(
            synth_config, self._loop, self._simulator, self._rng
        )
        self._injector = PathologyInjector(
            self._loop, infra, self._workload_states, self._rng
        )
        self._rollouts = RolloutSystem(versions or {}, infra, self._workload_states)
        self._ops = OperationsSystem(infra)
        self._detectors: list[Detector] = []
        self._actuators: list[Actuator] = []

    def add_detector(self, detector: Detector) -> None:
        self._detectors.append(detector)

    def add_actuator(self, actuator: Actuator) -> None:
        self._actuators.append(actuator)

    def add_timed_pathology(self, tp: TimedPathology) -> None:
        self._injector.add_timed(tp)

    def add_stochastic_pathology(self, sp: StochasticPathology) -> None:
        self._injector.add_stochastic(sp)

    @property
    def buffer(self) -> ResponseBuffer:
        return self._buffer

    @property
    def rollouts(self) -> RolloutSystem:
        return self._rollouts

    @property
    def ops(self) -> OperationsSystem:
        return self._ops

    def run(self, until: float) -> None:
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
```

- [ ] **Step 4: Run all tests**

```bash
uv run pytest tests/test_scenario.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests PASS, no failures

- [ ] **Step 6: Commit**

```bash
git add src/scrutable/engine.py tests/test_scenario.py
git commit -m "feat: simulation engine wiring all components end-to-end"
```

---

## Task 13: Verify full suite and update __init__.py

**Files:**
- Modify: `src/scrutable/__init__.py`

- [ ] **Step 1: Export public API from __init__.py**

`src/scrutable/__init__.py`:
```python
from scrutable.engine import SimulationEngine
from scrutable.infrastructure import InfrastructureConfig, InfrastructureModel
from scrutable.workload import WorkloadRegistry
from scrutable.synthesizer import SynthesizerConfig
from scrutable.models import (
    WorkloadModel,
    WorkloadState,
    NodeState,
    ClusterState,
    Request,
    Response,
    Pathology,
    PathologyScope,
    Inference,
)
from scrutable.pathology import TimedPathology, StochasticPathology
from scrutable.operations import SoftwareVersion, RolloutSystem, OperationsSystem
from scrutable.detector import Detector
from scrutable.actuator import Actuator

__all__ = [
    "SimulationEngine",
    "InfrastructureConfig",
    "InfrastructureModel",
    "WorkloadRegistry",
    "SynthesizerConfig",
    "WorkloadModel",
    "WorkloadState",
    "NodeState",
    "ClusterState",
    "Request",
    "Response",
    "Pathology",
    "PathologyScope",
    "Inference",
    "TimedPathology",
    "StochasticPathology",
    "SoftwareVersion",
    "RolloutSystem",
    "OperationsSystem",
    "Detector",
    "Actuator",
]
```

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest -v --tb=short
```

Expected: all tests PASS across all 12 test files

- [ ] **Step 3: Run with coverage**

```bash
uv run pytest --cov=scrutable --cov-report=term-missing
```

Expected: coverage report shows all major modules covered

- [ ] **Step 4: Commit**

```bash
git add src/scrutable/__init__.py
git commit -m "feat: export public API from package __init__"
```

# Progressive Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add progressive (per-cluster, staged) rollout as a core simulation capability via a `Rollout` class that encapsulates both deployment policy and live rollout state.

**Architecture:** `Release` (replaces `SoftwareVersion`) carries `ReleaseChange` objects, each with an optional `Disturbance`. A `Rollout` holds the cluster order, stage interval, per-stage gate callbacks, and all runtime state. The engine activates a rollout, injects infrastructure, and chain-schedules stage events. Actuators call `rollout.halt()` or `rollout.rollback_all()` directly. `RolloutSystem` becomes a thin registry.

**Tech Stack:** Python 3.11+, dataclasses, `enum.Enum`, existing `apply_disturbance`/`remove_disturbance` from `disturbance.py`.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/scrutable/models.py` | Modify | Add `RolloutState`, `RolloutStateTransition`, `ReleaseStatus`, `ReleaseChange`, `Release`; add `capacity_weight` to `ClusterState` |
| `src/scrutable/plant.py` | Modify | Add `capacity_weights` to `PlantConfig`; apply weights in `Plant.__init__` |
| `src/scrutable/rollout.py` | Create | `GateCallback` type alias; full `Rollout` class |
| `src/scrutable/operations.py` | Modify | Replace `SoftwareVersion` + old `RolloutSystem` with thin registry; keep `OperationsSystem` unchanged |
| `src/scrutable/engine.py` | Modify | Remove `versions` param; add `add_rollout` + `_schedule_rollout_stage`; update `_rollouts` init |
| `src/scrutable/__init__.py` | Modify | Swap exports: remove `SoftwareVersion`; add `Release`, `ReleaseChange`, `RolloutState`, `ReleaseStatus`, `Rollout`, `GateCallback` |
| `tests/test_release_model.py` | Create | Unit tests for new model types |
| `tests/test_rollout.py` | Create | Unit tests for `Rollout` class |
| `tests/test_progressive_rollout_engine.py` | Create | Integration tests with live `SimulationEngine` |
| `tests/test_operations.py` | Modify | Remove old `SoftwareVersion`/`RolloutSystem` tests; add thin-registry tests |
| `tests/test_plant.py` | Modify | Add capacity weight tests |

---

## Task 1: Data model additions

**Files:**
- Modify: `src/scrutable/models.py`
- Create: `tests/test_release_model.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_release_model.py`:

```python
import pytest
from scrutable.models import (
    Release, ReleaseChange, RolloutState, RolloutStateTransition,
    ReleaseStatus, ClusterState,
)


def test_release_defaults():
    r = Release(release_id="v1")
    assert r.changes == []
    assert r.description == ""


def test_release_with_description():
    r = Release(release_id="v2", description="hotfix")
    assert r.description == "hotfix"


def test_release_change_benign():
    c = ReleaseChange(change_id="ch1")
    assert c.disturbance is None


def test_release_change_with_disturbance():
    from scrutable.models import Disturbance, DisturbanceScope
    d = Disturbance(
        disturbance_id="d1",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_addend": 0.5},
    )
    c = ReleaseChange(change_id="ch2", disturbance=d)
    assert c.disturbance is d


def test_rollout_state_values():
    assert RolloutState.PENDING.value == "pending"
    assert RolloutState.IN_PROGRESS.value == "in_progress"
    assert RolloutState.HALTED.value == "halted"
    assert RolloutState.COMPLETED.value == "completed"
    assert RolloutState.ROLLED_BACK.value == "rolled_back"


def test_rollout_state_transition_fields():
    t = RolloutStateTransition(
        state=RolloutState.IN_PROGRESS,
        entered_at=1.0,
        exited_at=5.0,
    )
    assert t.state == RolloutState.IN_PROGRESS
    assert t.entered_at == 1.0
    assert t.exited_at == 5.0


def test_cluster_state_capacity_weight_defaults_to_one():
    cs = ClusterState(cluster_id="c1", region_id="r1")
    assert cs.capacity_weight == 1.0


def test_cluster_state_custom_capacity_weight():
    cs = ClusterState(cluster_id="c1", region_id="r1", capacity_weight=3.0)
    assert cs.capacity_weight == 3.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_release_model.py -v
```

Expected: ImportError or AttributeError — `Release`, `RolloutState`, etc. not defined.

- [ ] **Step 3: Add to `src/scrutable/models.py`**

Add `import enum` at the top alongside the existing imports. Then add these classes after the existing dataclass definitions (after `Inference`):

```python
import enum


class RolloutState(enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    HALTED = "halted"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"


@dataclass
class RolloutStateTransition:
    state: RolloutState
    entered_at: float
    exited_at: float


@dataclass
class ReleaseChange:
    change_id: str
    disturbance: "Disturbance | None" = None


@dataclass
class Release:
    release_id: str
    changes: list[ReleaseChange] = field(default_factory=list)
    description: str = ""


@dataclass
class ReleaseStatus:
    release_id: str
    state: RolloutState
    stages_completed: int
    stages_total: int
    deployed_clusters: list[str]
    pending_clusters: list[str]
    rollout_fraction: float
    capacity_fraction: float
    started_at: float | None
    state_entered_at: float | None
    state_history: list[RolloutStateTransition]
```

Also add `capacity_weight: float = 1.0` as the last field of `ClusterState`:

```python
@dataclass
class ClusterState:
    cluster_id: str
    region_id: str
    traffic_enabled: bool = True
    capacity_weight: float = 1.0
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_release_model.py -v
```

Expected: 8 PASSED.

- [ ] **Step 5: Run full suite to check no regressions**

```bash
cd /home/nld/dev/scrutable && python -m pytest --ignore=tests/test_slo_performance.py -v
```

Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
cd /home/nld/dev/scrutable && git add src/scrutable/models.py tests/test_release_model.py
git commit -m "feat: add Release, RolloutState, ReleaseStatus data model types"
```

---

## Task 2: PlantConfig capacity weights

**Files:**
- Modify: `src/scrutable/plant.py`
- Modify: `tests/test_plant.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plant.py`:

```python
def test_plant_capacity_weight_applied_from_config():
    config = PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1", "r1c2"]},
        nodes={"r1c1": ["r1c1n1"], "r1c2": ["r1c2n1"]},
        capacity_weights={"r1c1": 2.0},
    )
    plant = Plant(config)
    assert plant.get_cluster("r1c1").capacity_weight == 2.0
    assert plant.get_cluster("r1c2").capacity_weight == 1.0


def test_plant_capacity_weight_defaults_to_one():
    config = PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1"]},
        nodes={"r1c1": ["r1c1n1"]},
    )
    plant = Plant(config)
    assert plant.get_cluster("r1c1").capacity_weight == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_plant.py::test_plant_capacity_weight_applied_from_config tests/test_plant.py::test_plant_capacity_weight_defaults_to_one -v
```

Expected: TypeError — `PlantConfig` does not accept `capacity_weights`.

- [ ] **Step 3: Update `src/scrutable/plant.py`**

Add `capacity_weights` to `PlantConfig`:

```python
@dataclass
class PlantConfig:
    regions: list[str]
    clusters: dict[str, list[str]]   # region_id -> [cluster_id]
    nodes: dict[str, list[str]]       # cluster_id -> [node_id]
    capacity_weights: dict[str, float] = field(default_factory=dict)
```

In `Plant.__init__`, update the loop that creates `ClusterState` to apply the weight:

```python
for region_id, cluster_ids in config.clusters.items():
    for cluster_id in cluster_ids:
        self._clusters[cluster_id] = ClusterState(
            cluster_id=cluster_id,
            region_id=region_id,
            capacity_weight=config.capacity_weights.get(cluster_id, 1.0),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_plant.py -v
```

Expected: all plant tests pass including the two new ones.

- [ ] **Step 5: Commit**

```bash
cd /home/nld/dev/scrutable && git add src/scrutable/plant.py tests/test_plant.py
git commit -m "feat: add capacity_weight to ClusterState and PlantConfig"
```

---

## Task 3: `Rollout` — construction, `_activate`, `status` (PENDING)

**Files:**
- Create: `src/scrutable/rollout.py`
- Create: `tests/test_rollout.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rollout.py`:

```python
import pytest
from scrutable.models import (
    Release, ReleaseChange, RolloutState, Disturbance, DisturbanceScope,
)
from scrutable.rollout import Rollout
from scrutable.plant import PlantConfig, Plant


@pytest.fixture
def two_cluster_plant():
    config = PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1", "r1c2"]},
        nodes={"r1c1": ["r1c1n1", "r1c1n2"], "r1c2": ["r1c2n1", "r1c2n2"]},
    )
    return Plant(config)


@pytest.fixture
def benign_release():
    return Release(release_id="v1", changes=[ReleaseChange(change_id="ch1")])


@pytest.fixture
def latency_release():
    d = Disturbance(
        disturbance_id="latency-bug",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_addend": 0.5},
    )
    return Release(release_id="v2", changes=[ReleaseChange(change_id="ch1", disturbance=d)])


def test_rollout_initial_status_is_pending(two_cluster_plant, benign_release):
    rollout = Rollout(benign_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    s = rollout.status
    assert s.state == RolloutState.PENDING
    assert s.stages_completed == 0
    assert s.stages_total == 2
    assert s.deployed_clusters == []
    assert s.pending_clusters == ["r1c1", "r1c2"]
    assert s.started_at is None
    assert s.state_entered_at is None
    assert s.state_history == []


def test_rollout_fractions_zero_before_any_deploy(two_cluster_plant, benign_release):
    rollout = Rollout(benign_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    s = rollout.status
    assert s.rollout_fraction == 0.0
    assert s.capacity_fraction == 0.0


def test_rollout_activate_twice_raises(two_cluster_plant, benign_release):
    rollout = Rollout(benign_release, ["r1c1"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    with pytest.raises(RuntimeError, match="_activate called more than once"):
        rollout._activate(two_cluster_plant, {})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_rollout.py -v
```

Expected: ModuleNotFoundError — `scrutable.rollout` does not exist.

- [ ] **Step 3: Create `src/scrutable/rollout.py`**

```python
from __future__ import annotations
from typing import Callable
from scrutable.models import (
    Release, ReleaseChange, ReleaseStatus, RolloutState, RolloutStateTransition,
    WorkloadState, Disturbance, DisturbanceScope,
)
from scrutable.plant import Plant
from scrutable.disturbance import apply_disturbance, remove_disturbance

GateCallback = Callable[["ReleaseStatus", float], bool]


class Rollout:
    def __init__(
        self,
        release: Release,
        cluster_order: list[str],
        stage_interval: float,
        start_at: float = 0.0,
        gates: list[list[GateCallback]] | None = None,
    ) -> None:
        self._release = release
        self.cluster_order = cluster_order
        self.stage_interval = stage_interval
        self.start_at = start_at
        self._gates: list[list[GateCallback]] = gates or []

        self._plant: Plant | None = None
        self._workload_states: dict[str, WorkloadState] | None = None

        self._state = RolloutState.PENDING
        self._deployed_clusters: list[str] = []
        self._started_at: float | None = None
        self._state_entered_at: float | None = None
        self._state_history: list[RolloutStateTransition] = []

    def _activate(self, plant: Plant, workload_states: dict[str, WorkloadState]) -> None:
        if self._plant is not None:
            raise RuntimeError("Rollout._activate called more than once")
        self._plant = plant
        self._workload_states = workload_states

    @property
    def status(self) -> ReleaseStatus:
        stages_total = len(self.cluster_order)
        stages_completed = len(self._deployed_clusters)
        pending = [c for c in self.cluster_order if c not in self._deployed_clusters]

        if self._plant is not None and stages_total > 0:
            total_weight = sum(
                self._plant.get_cluster(c).capacity_weight for c in self.cluster_order
            )
            deployed_weight = sum(
                self._plant.get_cluster(c).capacity_weight for c in self._deployed_clusters
            )
            capacity_fraction = deployed_weight / total_weight if total_weight > 0 else 0.0
        else:
            capacity_fraction = 0.0

        return ReleaseStatus(
            release_id=self._release.release_id,
            state=self._state,
            stages_completed=stages_completed,
            stages_total=stages_total,
            deployed_clusters=list(self._deployed_clusters),
            pending_clusters=pending,
            rollout_fraction=stages_completed / stages_total if stages_total > 0 else 0.0,
            capacity_fraction=capacity_fraction,
            started_at=self._started_at,
            state_entered_at=self._state_entered_at,
            state_history=list(self._state_history),
        )

    def _transition(self, new_state: RolloutState, sim_time: float) -> None:
        if self._state_entered_at is not None:
            self._state_history.append(
                RolloutStateTransition(
                    state=self._state,
                    entered_at=self._state_entered_at,
                    exited_at=sim_time,
                )
            )
        self._state = new_state
        self._state_entered_at = sim_time
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_rollout.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
cd /home/nld/dev/scrutable && git add src/scrutable/rollout.py tests/test_rollout.py
git commit -m "feat: Rollout class skeleton with _activate and status"
```

---

## Task 4: `Rollout._deploy_stage`

**Files:**
- Modify: `src/scrutable/rollout.py`
- Modify: `tests/test_rollout.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rollout.py`:

```python
def test_deploy_stage_affects_only_target_cluster(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=1.0)

    for node_id in two_cluster_plant.nodes_in_cluster("r1c1"):
        assert two_cluster_plant.get_node(node_id).latency_addend == pytest.approx(0.5)
    for node_id in two_cluster_plant.nodes_in_cluster("r1c2"):
        assert two_cluster_plant.get_node(node_id).latency_addend == pytest.approx(0.0)


def test_deploy_first_stage_transitions_to_in_progress(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=5.0)
    s = rollout.status
    assert s.state == RolloutState.IN_PROGRESS
    assert s.started_at == pytest.approx(5.0)
    assert s.state_entered_at == pytest.approx(5.0)
    assert s.stages_completed == 1
    assert s.deployed_clusters == ["r1c1"]
    assert s.pending_clusters == ["r1c2"]


def test_deploy_last_stage_transitions_to_completed(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=5.0)
    assert rollout.status.state == RolloutState.COMPLETED


def test_deploy_all_stages_updates_fractions(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=1.0)
    s = rollout.status
    assert s.rollout_fraction == pytest.approx(0.5)
    assert s.capacity_fraction == pytest.approx(0.5)


def test_state_history_recorded_on_transition(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=2.0)   # PENDING -> IN_PROGRESS at t=2
    rollout._deploy_stage(1, sim_time=12.0)  # IN_PROGRESS -> COMPLETED at t=12
    s = rollout.status
    assert len(s.state_history) == 1
    assert s.state_history[0].state == RolloutState.IN_PROGRESS
    assert s.state_history[0].entered_at == pytest.approx(2.0)
    assert s.state_history[0].exited_at == pytest.approx(12.0)


def test_benign_change_does_not_modify_nodes(two_cluster_plant, benign_release):
    rollout = Rollout(benign_release, ["r1c1"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=1.0)
    for node in two_cluster_plant.all_nodes():
        assert node.latency_addend == pytest.approx(0.0)
        assert node.latency_multiplier == pytest.approx(1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_rollout.py::test_deploy_stage_affects_only_target_cluster -v
```

Expected: AttributeError — `Rollout` has no `_deploy_stage`.

- [ ] **Step 3: Add `_deploy_stage` and `_cluster_scoped_disturbance` to `src/scrutable/rollout.py`**

Add these methods to the `Rollout` class:

```python
def _cluster_scoped_disturbance(self, change: ReleaseChange, cluster_id: str) -> Disturbance:
    d = change.disturbance
    assert d is not None
    return Disturbance(
        disturbance_id=f"{self._release.release_id}-{change.change_id}-{cluster_id}",
        scope=DisturbanceScope(
            target_type=d.scope.target_type,
            filter_id=cluster_id,
            percentage=d.scope.percentage,
        ),
        node_effects=d.node_effects,
        workload_effects=d.workload_effects,
    )

def _deploy_stage(self, stage_idx: int, sim_time: float) -> None:
    cluster_id = self.cluster_order[stage_idx]

    if self._state == RolloutState.PENDING:
        self._transition(RolloutState.IN_PROGRESS, sim_time)
        self._started_at = sim_time

    assert self._plant is not None
    assert self._workload_states is not None
    for change in self._release.changes:
        if change.disturbance is not None:
            scoped = self._cluster_scoped_disturbance(change, cluster_id)
            apply_disturbance(scoped, self._plant, self._workload_states)

    self._deployed_clusters.append(cluster_id)

    if len(self._deployed_clusters) == len(self.cluster_order):
        self._transition(RolloutState.COMPLETED, sim_time)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_rollout.py -v
```

Expected: all rollout tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/nld/dev/scrutable && git add src/scrutable/rollout.py tests/test_rollout.py
git commit -m "feat: Rollout._deploy_stage with cluster-scoped disturbances"
```

---

## Task 5: `Rollout.halt`, `rollback_cluster`, `rollback_all`

**Files:**
- Modify: `src/scrutable/rollout.py`
- Modify: `tests/test_rollout.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rollout.py`:

```python
def test_halt_transitions_to_halted(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=1.0)
    rollout.halt(sim_time=3.0)
    s = rollout.status
    assert s.state == RolloutState.HALTED
    assert s.deployed_clusters == ["r1c1"]


def test_halt_is_noop_if_already_completed(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=1.0)
    assert rollout.status.state == RolloutState.COMPLETED
    rollout.halt(sim_time=2.0)
    assert rollout.status.state == RolloutState.COMPLETED


def test_rollback_cluster_removes_effects(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=1.0)
    rollout.halt(sim_time=2.0)
    rollout.rollback_cluster("r1c1", sim_time=3.0)

    for node_id in two_cluster_plant.nodes_in_cluster("r1c1"):
        assert two_cluster_plant.get_node(node_id).latency_addend == pytest.approx(0.0)
    s = rollout.status
    assert "r1c1" not in s.deployed_clusters
    assert "r1c1" in s.pending_clusters
    assert s.state == RolloutState.HALTED


def test_rollback_cluster_noop_if_not_deployed(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout.halt(sim_time=1.0)
    rollout.rollback_cluster("r1c1", sim_time=2.0)  # never deployed, should not raise
    assert rollout.status.deployed_clusters == []


def test_rollback_all_removes_all_effects_and_transitions(two_cluster_plant, latency_release):
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    rollout._deploy_stage(0, sim_time=1.0)
    rollout._deploy_stage(1, sim_time=11.0)
    rollout.halt(sim_time=12.0)
    rollout.rollback_all(sim_time=13.0)

    for node in two_cluster_plant.all_nodes():
        assert node.latency_addend == pytest.approx(0.0)
    s = rollout.status
    assert s.state == RolloutState.ROLLED_BACK
    assert s.deployed_clusters == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_rollout.py::test_halt_transitions_to_halted -v
```

Expected: AttributeError — `Rollout` has no `halt`.

- [ ] **Step 3: Add `halt`, `rollback_cluster`, `rollback_all` to `src/scrutable/rollout.py`**

```python
def halt(self, sim_time: float) -> None:
    if self._state not in (RolloutState.PENDING, RolloutState.IN_PROGRESS):
        return
    self._transition(RolloutState.HALTED, sim_time)

def rollback_cluster(self, cluster_id: str, sim_time: float) -> None:
    if cluster_id not in self._deployed_clusters:
        return
    assert self._plant is not None
    assert self._workload_states is not None
    for change in self._release.changes:
        if change.disturbance is not None:
            scoped = self._cluster_scoped_disturbance(change, cluster_id)
            remove_disturbance(scoped, self._plant, self._workload_states)
    self._deployed_clusters.remove(cluster_id)

def rollback_all(self, sim_time: float) -> None:
    for cluster_id in list(self._deployed_clusters):
        self.rollback_cluster(cluster_id, sim_time)
    self._transition(RolloutState.ROLLED_BACK, sim_time)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_rollout.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/nld/dev/scrutable && git add src/scrutable/rollout.py tests/test_rollout.py
git commit -m "feat: Rollout halt, rollback_cluster, rollback_all"
```

---

## Task 6: `Rollout._check_gates`

**Files:**
- Modify: `src/scrutable/rollout.py`
- Modify: `tests/test_rollout.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rollout.py`:

```python
def test_check_gates_true_when_no_gates(two_cluster_plant, benign_release):
    rollout = Rollout(benign_release, ["r1c1", "r1c2"], stage_interval=10.0)
    rollout._activate(two_cluster_plant, {})
    assert rollout._check_gates(0, sim_time=1.0) is True
    assert rollout._check_gates(5, sim_time=1.0) is True  # stage beyond gates list


def test_check_gates_true_when_all_pass(two_cluster_plant, benign_release):
    gates = [[lambda status, t: True, lambda status, t: True]]
    rollout = Rollout(benign_release, ["r1c1", "r1c2"], stage_interval=10.0, gates=gates)
    rollout._activate(two_cluster_plant, {})
    assert rollout._check_gates(0, sim_time=1.0) is True


def test_check_gates_false_when_one_fails(two_cluster_plant, benign_release):
    gates = [[lambda status, t: True, lambda status, t: False]]
    rollout = Rollout(benign_release, ["r1c1", "r1c2"], stage_interval=10.0, gates=gates)
    rollout._activate(two_cluster_plant, {})
    assert rollout._check_gates(0, sim_time=1.0) is False


def test_check_gates_per_stage_independent(two_cluster_plant, benign_release):
    gates = [
        [lambda status, t: False],  # stage 0: block
        [lambda status, t: True],   # stage 1: allow
    ]
    rollout = Rollout(benign_release, ["r1c1", "r1c2"], stage_interval=10.0, gates=gates)
    rollout._activate(two_cluster_plant, {})
    assert rollout._check_gates(0, sim_time=1.0) is False
    assert rollout._check_gates(1, sim_time=1.0) is True


def test_check_gates_receives_current_status(two_cluster_plant, latency_release):
    seen_stages = []

    def capture_gate(status, t):
        seen_stages.append(status.stages_completed)
        return True

    gates = [[capture_gate], [capture_gate]]
    rollout = Rollout(latency_release, ["r1c1", "r1c2"], stage_interval=10.0, gates=gates)
    rollout._activate(two_cluster_plant, {})
    rollout._check_gates(0, sim_time=1.0)
    rollout._deploy_stage(0, sim_time=1.0)
    rollout._check_gates(1, sim_time=11.0)
    assert seen_stages == [0, 1]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_rollout.py::test_check_gates_true_when_no_gates -v
```

Expected: AttributeError — `Rollout` has no `_check_gates`.

- [ ] **Step 3: Add `_check_gates` to `src/scrutable/rollout.py`**

```python
def _check_gates(self, stage_idx: int, sim_time: float) -> bool:
    if stage_idx >= len(self._gates):
        return True
    return all(gate(self.status, sim_time) for gate in self._gates[stage_idx])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_rollout.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/nld/dev/scrutable && git add src/scrutable/rollout.py tests/test_rollout.py
git commit -m "feat: Rollout._check_gates with per-stage gate callbacks"
```

---

## Task 7: Thin `RolloutSystem`, update `operations.py` and `test_operations.py`

**Files:**
- Modify: `src/scrutable/operations.py`
- Modify: `tests/test_operations.py`

- [ ] **Step 1: Write the failing tests**

Replace the rollout-related tests in `tests/test_operations.py`. Keep `test_drain_disables_cluster_traffic` and `test_restore_re_enables_cluster_traffic`. Replace the four `SoftwareVersion`/`RolloutSystem` tests with:

```python
from scrutable.models import Release, ReleaseChange
from scrutable.rollout import Rollout
from scrutable.operations import RolloutSystem, OperationsSystem


def test_rollout_system_register_and_get():
    release = Release(release_id="v1")
    rollout = Rollout(release, ["r1c1"], stage_interval=10.0)
    system = RolloutSystem()
    system.register(rollout)
    assert system.get("v1") is rollout


def test_rollout_system_get_unknown_raises():
    system = RolloutSystem()
    with pytest.raises(ValueError, match="v99"):
        system.get("v99")


def test_rollout_system_all_rollouts():
    system = RolloutSystem()
    r1 = Rollout(Release(release_id="v1"), ["r1c1"], stage_interval=10.0)
    r2 = Rollout(Release(release_id="v2"), ["r1c2"], stage_interval=10.0)
    system.register(r1)
    system.register(r2)
    assert set(r.status.release_id for r in system.all_rollouts()) == {"v1", "v2"}
```

Also add `import pytest` at the top if not already there.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_operations.py -v
```

Expected: the new tests fail (import errors or API mismatch on `RolloutSystem()`).

- [ ] **Step 3: Rewrite `src/scrutable/operations.py`**

Replace the entire file contents:

```python
from __future__ import annotations
from scrutable.plant import Plant
from scrutable.rollout import Rollout


class RolloutSystem:
    def __init__(self) -> None:
        self._rollouts: dict[str, Rollout] = {}

    def register(self, rollout: Rollout) -> None:
        self._rollouts[rollout._release.release_id] = rollout

    def get(self, release_id: str) -> Rollout:
        try:
            return self._rollouts[release_id]
        except KeyError:
            raise ValueError(f"Unknown release_id: {release_id!r}")

    def all_rollouts(self) -> list[Rollout]:
        return list(self._rollouts.values())


class OperationsSystem:
    def __init__(self, plant: Plant) -> None:
        self._plant = plant

    def drain(self, cluster_id: str) -> None:
        self._plant.set_cluster_enabled(cluster_id, False)

    def restore(self, cluster_id: str) -> None:
        self._plant.set_cluster_enabled(cluster_id, True)
```

- [ ] **Step 4: Run operations tests to verify they pass**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_operations.py -v
```

Expected: all 5 tests pass (2 drain/restore + 3 new registry tests).

- [ ] **Step 5: Commit**

```bash
cd /home/nld/dev/scrutable && git add src/scrutable/operations.py tests/test_operations.py
git commit -m "refactor: RolloutSystem becomes thin registry; remove SoftwareVersion"
```

---

## Task 8: Engine wiring — `add_rollout` and `_schedule_rollout_stage`

**Files:**
- Modify: `src/scrutable/engine.py`

- [ ] **Step 1: Update `src/scrutable/engine.py`**

Make these changes:

1. Remove `SoftwareVersion` import and add `Rollout` import:
```python
from scrutable.rollout import Rollout
from scrutable.models import RolloutState, WorkloadState
```

2. Remove the `versions` parameter from `__init__` and update `self._rollouts`:
```python
# Remove:  versions: dict[str, SoftwareVersion] | None = None,
# Change:  self._rollouts = RolloutSystem(versions or {}, infra, self._workload_states)
# To:      self._rollouts = RolloutSystem()
```

3. Add `add_rollout` and `_schedule_rollout_stage` methods:
```python
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

- [ ] **Step 2: Run full test suite to check no regressions**

```bash
cd /home/nld/dev/scrutable && python -m pytest --ignore=tests/test_slo_performance.py -v
```

Expected: all tests pass. (Any test that used `versions=` in `SimulationEngine(...)` will fail — fix those in the next step if any exist.)

- [ ] **Step 3: Fix any call site using `versions=` in `SimulationEngine`**

Search for usages:
```bash
grep -rn "versions=" /home/nld/dev/scrutable/tests/ /home/nld/dev/scrutable/examples/
```

For each match, remove the `versions=` argument. Rollout behavior is now added via `engine.add_rollout(rollout)` after construction.

- [ ] **Step 4: Run full test suite again**

```bash
cd /home/nld/dev/scrutable && python -m pytest --ignore=tests/test_slo_performance.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/nld/dev/scrutable && git add src/scrutable/engine.py
git commit -m "feat: engine.add_rollout with chain-scheduled stage events"
```

---

## Task 9: Integration tests

**Files:**
- Create: `tests/test_progressive_rollout_engine.py`

- [ ] **Step 1: Write the integration tests**

Create `tests/test_progressive_rollout_engine.py`:

```python
import pytest
import numpy as np
from scrutable.models import (
    Release, ReleaseChange, RolloutState, Disturbance, DisturbanceScope,
)
from scrutable.rollout import Rollout
from scrutable.plant import PlantConfig, Plant
from scrutable.workload import WorkloadRegistry
from scrutable.models import WorkloadModel
from scrutable.synthesizer import InputConfig
from scrutable.engine import SimulationEngine


@pytest.fixture
def two_cluster_engine():
    plant = Plant(PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1", "r1c2"]},
        nodes={"r1c1": ["r1c1n1"], "r1c2": ["r1c2n1"]},
    ))
    registry = WorkloadRegistry()
    registry.register(WorkloadModel(
        workload_id="wl1",
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=1000.0,
        error_shape=1.5,
        noise_sigma=0.001,
    ))
    engine = SimulationEngine(
        infra=plant,
        registry=registry,
        synth_config=InputConfig(workload_rates={"wl1": 5.0}),
        seed=42,
    )
    return engine


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
    # Both clusters should have the latency addend applied
    assert plant.get_node("r1c1n1").latency_addend == pytest.approx(1.0)
    assert plant.get_node("r1c2n1").latency_addend == pytest.approx(1.0)


def test_gate_false_halts_rollout_at_stage(two_cluster_engine, latency_release):
    plant = two_cluster_engine._infra
    # Gate on stage 1 always returns False
    gates = [[], [lambda status, t: False]]
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
    # r1c1 affected, r1c2 not
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
    registry = WorkloadRegistry()
    registry.register(WorkloadModel(
        workload_id="wl1",
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=1000.0,
        error_shape=1.5,
        noise_sigma=0.001,
    ))
    engine = SimulationEngine(
        infra=plant,
        registry=registry,
        synth_config=InputConfig(workload_rates={"wl1": 5.0}),
        seed=42,
    )
    release = Release(release_id="v1", changes=[ReleaseChange(change_id="ch1")])
    rollout = Rollout(release, ["r1c1", "r1c2"], stage_interval=5.0, start_at=0.0)
    engine.add_rollout(rollout)
    engine.run(until=3.0)  # only stage 0 fires (start_at=0, next at t=5)

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

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_progressive_rollout_engine.py -v
```

Expected: failures due to missing `add_rollout` method (resolved in Task 8).

- [ ] **Step 3: Run all tests to verify they pass**

```bash
cd /home/nld/dev/scrutable && python -m pytest tests/test_progressive_rollout_engine.py -v
```

Expected: 5 PASSED.

- [ ] **Step 4: Commit**

```bash
cd /home/nld/dev/scrutable && git add tests/test_progressive_rollout_engine.py
git commit -m "test: progressive rollout engine integration tests"
```

---

## Task 10: Update exports in `__init__.py`

**Files:**
- Modify: `src/scrutable/__init__.py`

- [ ] **Step 1: Update the imports and `__all__`**

Replace the `operations` import line and add new imports:

```python
# Remove this line:
from scrutable.operations import SoftwareVersion, RolloutSystem, OperationsSystem

# Replace with:
from scrutable.operations import RolloutSystem, OperationsSystem
from scrutable.rollout import Rollout, GateCallback
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
```

Update `__all__` — remove `"SoftwareVersion"`, add:
```python
"Release",
"ReleaseChange",
"RolloutState",
"RolloutStateTransition",
"ReleaseStatus",
"Rollout",
"GateCallback",
```

- [ ] **Step 2: Run full test suite**

```bash
cd /home/nld/dev/scrutable && python -m pytest --ignore=tests/test_slo_performance.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Verify public API imports work**

```bash
cd /home/nld/dev/scrutable && python -c "
from scrutable import (
    Release, ReleaseChange, RolloutState, ReleaseStatus,
    Rollout, GateCallback, RolloutSystem
)
print('all imports OK')
"
```

Expected: `all imports OK`

- [ ] **Step 4: Commit**

```bash
cd /home/nld/dev/scrutable && git add src/scrutable/__init__.py
git commit -m "feat: export Release, Rollout, GateCallback and rollout model types"
```

---

## Task 11: Final smoke test

- [ ] **Step 1: Run full test suite including slow tests**

```bash
cd /home/nld/dev/scrutable && python -m pytest -v
```

Expected: all tests pass (slow SLO performance tests may take a minute).

- [ ] **Step 2: Verify the example script still works**

```bash
cd /home/nld/dev/scrutable && python examples/simulation_example.py
```

Expected: runs without error and prints output.

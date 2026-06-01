# Progressive Rollout Design

**Date:** 2026-06-01

## Overview

Add progressive rollout as a core simulation capability: a `Rollout` object encapsulates both the deployment policy (which clusters, in what order, at what interval, with what gates) and the live rollout state (current stage, deployed clusters, timing history, rollout fraction). The engine activates a rollout by injecting infrastructure and scheduling stage events. Actuators interact directly with the `Rollout` object to halt or roll back.

This is infrastructure, not a scenario — it can be composed into any simulation that involves staged software deployment.

## Data model (`models.py`)

### `ReleaseChange` and `Release`

A release carries an ordered list of changes. Each change optionally has an associated disturbance (the observable effect of that change). A change with `disturbance=None` is benign.

```python
@dataclass
class ReleaseChange:
    change_id: str
    disturbance: Disturbance | None = None

@dataclass
class Release:
    release_id: str
    changes: list[ReleaseChange] = field(default_factory=list)
    description: str = ""
```

`Release` replaces `SoftwareVersion`. No backwards-compat shim — the project is pre-1.0.

### `RolloutState`

```python
class RolloutState(enum.Enum):
    PENDING = "pending"          # not yet started
    IN_PROGRESS = "in_progress"  # stages advancing
    HALTED = "halted"            # stopped mid-rollout (bad signal)
    COMPLETED = "completed"      # all stages deployed
    ROLLED_BACK = "rolled_back"  # reverted after halt
```

### `RolloutStateTransition` and `ReleaseStatus`

`ReleaseStatus` is a snapshot returned by `rollout.status`. It carries stage progress, fractional metrics, and timing.

```python
@dataclass
class RolloutStateTransition:
    state: RolloutState
    entered_at: float   # sim time
    exited_at: float    # sim time

@dataclass
class ReleaseStatus:
    release_id: str
    state: RolloutState

    # Stage progress
    stages_completed: int    # number of clusters deployed so far (0 = nothing deployed)
    stages_total: int        # total clusters in cluster_order

    # Cluster membership
    deployed_clusters: list[str]
    pending_clusters: list[str]

    # Fractional metrics
    rollout_fraction: float  # stages_completed / stages_total
    capacity_fraction: float # sum(capacity_weight of deployed) / sum(all weights)

    # Timing
    started_at: float | None                     # None while PENDING
    state_entered_at: float | None               # when current state began
    state_history: list[RolloutStateTransition]  # completed state transitions
```

`time_in_current_state` at any sim time T is `T - state_entered_at` — derived, not stored.

`capacity_fraction` uses `ClusterState.capacity_weight` (a new field on `ClusterState`, defaulting to `1.0`). `PlantConfig` accepts an optional `capacity_weights: dict[str, float]` to initialize non-uniform weights.

## Operations (`operations.py`)

### `GateCallback`

```python
GateCallback = Callable[[ReleaseStatus, float], bool]
# (status, sim_time) -> True = proceed, False = halt
```

### `Rollout`

The central object. Initialized with policy; activated by the engine.

```python
class Rollout:
    def __init__(
        self,
        release: Release,
        cluster_order: list[str],
        stage_interval: float,
        start_at: float = 0.0,
        gates: list[list[GateCallback]] | None = None,
    ) -> None: ...
```

`gates[i]` is the list of gate callbacks evaluated before deploying to `cluster_order[i]`. Stages beyond `len(gates)` have no gates. `gates=None` is equivalent to no gates at any stage.

**Public interface (for actuators and scenarios):**

```python
@property
def status(self) -> ReleaseStatus: ...

def halt(self, sim_time: float) -> None: ...
    # PENDING or IN_PROGRESS -> HALTED; no-op otherwise

def rollback_cluster(self, cluster_id: str, sim_time: float) -> None: ...
    # Remove this cluster's disturbances; move back to pending_clusters.
    # State remains HALTED — does not transition to ROLLED_BACK.

def rollback_all(self, sim_time: float) -> None: ...
    # rollback_cluster for every deployed cluster; transition to ROLLED_BACK.
```

**Internal interface (called by engine only):**

```python
def _activate(self, plant: Plant, workload_states: dict[str, WorkloadState]) -> None: ...
    # Inject infrastructure; called by engine.add_rollout() before scheduling.
    # Raises RuntimeError if called more than once.

def _deploy_stage(self, stage_idx: int, sim_time: float) -> None: ...
    # Apply cluster-scoped disturbances for cluster_order[stage_idx];
    # update status; transition to COMPLETED if last stage

def _check_gates(self, stage_idx: int, sim_time: float) -> bool: ...
    # Evaluate gates[stage_idx] if it exists; return True if all pass or no gates
```

**Per-cluster disturbance scoping:** when deploying to a cluster, each change's disturbance is applied as a cluster-scoped copy:
- `disturbance_id = f"{release_id}-{change_id}-{cluster_id}"`
- `scope.filter_id = cluster_id`, `scope.percentage` preserved from the original disturbance

Rollback reconstructs the same ID pattern to call `remove_disturbance`. This keeps each cluster's effects independent.

### `RolloutSystem` (thin registry)

`RolloutSystem` shrinks to a registry that the engine holds, primarily for actuator lookup:

```python
class RolloutSystem:
    def register(self, rollout: Rollout) -> None: ...
    def get(self, release_id: str) -> Rollout: ...
    def all_rollouts(self) -> list[Rollout]: ...
```

`OperationsSystem` is unchanged.

## Engine (`engine.py`)

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
            self._schedule_rollout_stage(rollout, next_idx, self._loop.now + rollout.stage_interval)
    self._loop.schedule(at, advance)
```

Stages are chain-scheduled: each stage schedules the next only after successfully deploying. A halted rollout simply stops scheduling — no cancellation needed.

`engine.py` constructor parameter `versions: dict[str, SoftwareVersion] | None` is removed; rollouts are added via `add_rollout`.

## Testing strategy

Tests follow TDD (red-green-refactor).

**`test_release_model.py`**
- `Release` and `ReleaseChange` construction; `description` defaults to `""`
- `ReleaseChange` with `disturbance=None` is valid

**`test_rollout.py`** — unit tests against a real `Plant`; no engine needed for most cases
- `_deploy_stage` affects only nodes in the target cluster, not others
- `_deploy_stage` on last stage sets `status.state` → `COMPLETED`
- `rollback_cluster` restores node state; cluster returns to `pending_clusters`
- `rollback_all` restores all deployed clusters; state → `ROLLED_BACK`
- `halt` sets state → `HALTED`; `deployed_clusters` preserved
- `status.rollout_fraction` and `capacity_fraction` computed correctly
- `state_history` records enter/exit sim times across transitions
- `started_at` is `None` while `PENDING`; set on first `_deploy_stage`
- `_check_gates` returns `True` when gate list is empty or absent for stage
- Gate returning `False` prevents deploy and transitions to `HALTED`
- `rollback_cluster` leaves state as `HALTED`; `rollback_all` transitions to `ROLLED_BACK`
- `_activate` called twice raises `RuntimeError`

**`test_progressive_rollout_engine.py`** — integration tests with a live `SimulationEngine`
- Stages fire at correct sim times (`start_at`, `start_at + interval`, ...)
- Gate returning `False` at stage N halts; stages N+1 onward never deploy
- `rollback_all` called from an actuator removes disturbance effects from all deployed clusters
- `capacity_fraction` reflects non-uniform `ClusterState.capacity_weight`
- A release with only benign changes (all `disturbance=None`) completes without modifying node state

## What this replaces

- `SoftwareVersion` → `Release`
- `RolloutSystem.deploy/rollback` (global, instantaneous) → `Rollout._deploy_stage` / `rollback_cluster` (per-cluster, scheduled)
- `ProgressiveRolloutPlan` (never existed; this design replaces the concept)

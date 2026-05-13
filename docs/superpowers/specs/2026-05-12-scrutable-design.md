# Scrutable Design Spec
_2026-05-12_

## Overview

Scrutable is a closed-loop discrete event simulator for a distributed service. It synthesizes probabilistic request traffic, simulates service behavior, injects pathologies, detects them via windowed analysis, and triggers operational responses. Its primary purpose is to serve as a testbed for detection and remediation algorithms, providing ground truth about what was injected and when.

**Language/tooling:** Python, uv, pytest.

---

## 1. Architecture

Nine components arranged in a closed feedback loop:

```
Synthesizer ──► Event Loop ──► Service Simulator ──► Response Buffer
                    ▲                  │                     │
                    │         Infrastructure Model      Detectors
                    │                  ▲                     │
                    └── Actuators ─────┴─── Pathology ───────┘
                                            Injector
```

| Component | Responsibility |
|---|---|
| **Event Loop Kernel** | `heapq` priority queue; advances simulation time event by event. ~100 lines, clean boundary for future Rust replacement. |
| **Infrastructure Model** | Hierarchical state: regions → clusters → nodes. Holds `NodeState`, `ClusterState`. Mutated by pathologies and operational responses. |
| **Workload Registry** | Lightweight parameter store. Each workload is a small parameter struct. Supports hundreds of thousands of entries. |
| **Workload Synthesizer** | Reads config, generates a probabilistic request schedule, feeds request events into the event loop. |
| **Service Simulator** | Handles request events. Samples workload model conditioned on current state to produce latency and error outcome. Schedules response event at `T + latency`. |
| **Pathology Injector** | Schedules pathology events: time-specified, stochastic, or actuator-triggered. Mutates `NodeState`, `WorkloadState`, or `ClusterState`. |
| **Response Buffer** | Append-only, time-ordered store of response records. Detectors query by time window. Configurable retention. |
| **Detector Framework** | Pluggable windowed detectors. Each runs on a periodic tick, analyzes a time window of responses, emits typed inferences. |
| **Actuator Framework** | Consumes inferences. Delegates to `RolloutSystem` or `OperationsSystem` to toggle pathologies or trigger operational responses. |

**Key invariants:**
- The event loop is strictly sequential — deterministic replay is a first-class property.
- Detectors and actuators run within simulation time, not wall-clock time.
- All randomness flows through a single seeded RNG. Any run is reproducible from its seed + config.
- Actuator-triggered state mutations happen within the current event handler, visible to all subsequent events.

---

## 2. Core Data Structures

```python
@dataclass
class Event:
    timestamp: float
    handler: Callable
    priority: int = 0         # tiebreak for same-timestamp events

@dataclass
class WorkloadModel:
    workload_id: str
    latency_median: float     # log-normal centroid
    latency_sigma: float
    error_scale: float        # Weibull transient error rate
    error_shape: float
    noise_sigma: float        # Gaussian noise layered on top

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
    node_id: str
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
    error_code: int           # 0 = success

@dataclass
class PathologyScope:
    target_type: str          # "node", "cluster", "region", "workload"
    filter_id: str | None     # specific cluster_id etc.; None = all
    percentage: float = 1.0   # stable hash-based subset selection

@dataclass
class Pathology:
    pathology_id: str
    scope: PathologyScope
    node_effects: dict        # e.g. {"latency_multiplier": 2.0}
    workload_effects: dict    # e.g. {"error_rate_multiplier": 5.0}

@dataclass
class Inference:
    detector_id: str
    pathology_type: str       # e.g. "software_bug", "hardware_fault"
    target_id: str
    target_level: str         # "node", "cluster", "region"
    confidence: float         # 0.0–1.0
    detected_at: float
    window_start: float
    window_end: float
```

**Stable subset selection:** When a pathology targets a percentage of entities, membership is determined by `hash(entity_id + pathology_id) % 1000 < percentage * 1000`. This is reproducible without consuming RNG state.

**Effective response parameters:** The simulator combines `WorkloadModel` (base params) × `WorkloadState` (pathology multipliers) × `NodeState` (node health multipliers) when sampling a response.

---

## 3. Component Interactions and Data Flow

### Initialization
1. Config loaded → `WorkloadRegistry` populated, `InfrastructureModel` built
2. RNG seeded
3. `PathologyInjector` schedules all time-based pathology events
4. `WorkloadSynthesizer` schedules the first request event per workload
5. Each `Detector` schedules its first periodic tick event
6. Event loop starts

### Request/Response Cycle (asynchronous)
```
Synthesizer schedules handle_request(req) at T
  └─► Router: rng.choice(enabled_clusters) → rng.choice(nodes_in_cluster)
        └─► Simulator samples WorkloadModel × WorkloadState × NodeState
              └─► schedules handle_response(resp) at T + latency
                    └─► ResponseBuffer.append(resp)
  └─► Synthesizer schedules next request for this workload at T + inter_arrival
```

Requests and responses are decoupled — in-flight requests are pending events in the queue. If no cluster has `traffic_enabled`, the request is recorded as an immediate failure response.

### Pathology Lifecycle
```
Time-based:   PathologyInjector schedules apply(p) at T
Stochastic:   PathologyInjector schedules recurring check → may schedule apply(p)
Actuator:     Actuator.act() → RolloutSystem or OperationsSystem
                → immediate state mutation within current event handler
```

All pathology application mutates `NodeState`, `WorkloadState`, or `ClusterState` directly.

### Detection and Actuation Cycle
```
Detector tick fires at T
  └─► ResponseBuffer.window(T - window_size, T) → list[Response]
        └─► detector analysis → list[Inference]
              └─► each Inference → Actuator.act(inference, sim_time, rollouts, ops)
                    └─► RolloutSystem.deploy/rollback() or OperationsSystem.drain()
                          └─► state mutation; no new events required
  └─► Detector schedules next tick at T + interval
```

### Actuator Interfaces
```python
class Actuator(Protocol):
    def act(
        self,
        inference: Inference,
        sim_time: float,
        rollouts: RolloutSystem,
        ops: OperationsSystem,
    ) -> None

class RolloutSystem:
    # deploys/reverts a software version, toggling associated pathologies
    def deploy(self, version_id: str, scope: PathologyScope) -> None
    def rollback(self, version_id: str, scope: PathologyScope) -> None

class OperationsSystem:
    # manages operational responses e.g. cluster drains
    def drain(self, cluster_id: str) -> None
    def restore(self, cluster_id: str) -> None
```

**Note:** Rollouts are currently modeled as instantaneous. Time-based rolling deploys are deferred.

---

## 4. Workload Model

Each workload is parameterized independently. A service may have hundreds of thousands of workloads; models are lightweight parameter structs, not objects with lifecycle.

**Latency sampling:**
```
base = lognormal(median=latency_median, sigma=latency_sigma)
effective = base * workload_state.latency_multiplier * node_state.latency_multiplier
noisy = max(0, effective + normal(0, noise_sigma))
```

**Error sampling:**
```
base_rate = weibull_cdf(t, scale=error_scale, shape=error_shape)
effective_rate = clamp(base_rate * workload_state.error_rate_multiplier
                       * node_state.error_rate_multiplier, 0, 1)
error_code = sample_error(effective_rate, rng)  # 0 if no error
```

Gaussian noise is applied to ensure signal realism — detectors cannot rely on unrealistically clean distributions.

---

## 5. Error Handling

**Config/init errors:** Raise exceptions at startup. Fail fast before the event loop starts.

**Runtime conditions:** Emit a `Response` with a designated error code rather than raising. The event loop never throws; handlers always produce a result. This keeps the simulation continuable and errors visible to detectors.

---

## 6. Testing Strategy

**Tooling:** pytest + uv.

**Unit tests** (pure functions, no event loop):
- `WorkloadModel` sampling: fixed seed, assert distribution properties
- `PathologyScope` hash-based subset: assert stable membership, correct coverage
- `ResponseBuffer.window()`: time-range filtering and retention expiry
- Router: two-level random selection respects `traffic_enabled`

**Component tests** (single component, injected dependencies):
- `PathologyInjector`: assert correct state mutations on `NodeState`/`WorkloadState`/`ClusterState`
- `RolloutSystem` / `OperationsSystem`: pathology toggle and drain behavior
- Individual detectors: synthetic `ResponseBuffer`, assert correct `Inference` output

**Scenario tests** (full simulation loop):
- Fixed seed + small infrastructure (2 regions × 2 clusters × 3 nodes) + small workload registry
- Inject known pathology at T=X, assert detector fires within expected window
- Reproducibility: two runs with same seed produce identical `ResponseBuffer`

**Test fixtures:**
- `tiny_infra`: 2 regions, 2 clusters each, 3 nodes each
- `seeded_rng`: fixed seed, reset per test
- `response_builder`: helper to construct synthetic `Response` lists

---

## Deferred

- **Time-based rolling deploys:** Rollouts currently apply instantaneously. Future work to model per-node rollout progression over simulation time.
- **Multi-hop requests:** Requests currently model a single node interaction. Call graphs and fan-out are deferred.
- **Load balancing beyond cluster drain:** Current model is a boolean per cluster. Weighted routing and more granular traffic steering are deferred.
- **Performance optimization:** Event loop kernel is designed with a clean boundary to enable future Rust replacement via PyO3.

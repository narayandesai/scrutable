from __future__ import annotations
import enum
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
    latency_addend: float = 0.0


@dataclass
class ClusterState:
    cluster_id: str
    region_id: str
    traffic_enabled: bool = True
    capacity_weight: float = 1.0


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
class DisturbanceScope:
    target_type: str
    filter_id: str | None
    percentage: float = 1.0


@dataclass
class Disturbance:
    disturbance_id: str
    scope: DisturbanceScope
    node_effects: dict = field(default_factory=dict)
    workload_effects: dict = field(default_factory=dict)


@dataclass
class Signal:
    sensor_id: str
    metric: str
    value: float
    window_start: float
    window_end: float
    sample_count: int


@dataclass
class Alarm:
    detector_id: str
    fault_type: str
    target_id: str
    target_level: str
    severity: float
    detected_at: float
    window_start: float
    window_end: float


class RolloutState(enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    HALTED = "halted"
    ROLLING_BACK = "rolling_back"
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
    disturbance: Disturbance | None = None


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

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
    latency_addend: float = 0.0


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
class Inference:
    detector_id: str
    pathology_type: str
    target_id: str
    target_level: str
    confidence: float
    detected_at: float
    window_start: float
    window_end: float

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
            # Safe: at event time T=issued_at, all prior arrivals are already buffered; latency=0 keeps order
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
        if not node_ids:
            # Safe: at event time T=issued_at, all prior arrivals are already buffered; latency=0 keeps order
            self._buffer.append(
                Response(
                    request_id=request.request_id,
                    workload_id=request.workload_id,
                    node_id="",
                    cluster_id=cluster.cluster_id,
                    region_id=cluster.region_id,
                    issued_at=request.issued_at,
                    latency=0.0,
                    error_code=_NO_CLUSTER_ERROR,
                )
            )
            return
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

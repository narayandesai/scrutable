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

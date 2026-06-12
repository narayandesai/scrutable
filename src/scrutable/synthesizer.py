from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scrutable.event_loop import EventLoop
from scrutable.simulator import ServiceSimulator
from scrutable.models import Request
from scrutable.traffic import WorkloadMix, MarkovActivity


@dataclass
class InputConfig:
    workload_rates: dict[str, float]


class InputProcess:
    def __init__(
        self,
        mix: WorkloadMix,
        loop: EventLoop,
        simulator: ServiceSimulator,
        rng: np.random.Generator,
    ) -> None:
        self._mix = mix
        self._loop = loop
        self._simulator = simulator
        self._rng = rng
        self._counter: int = 0
        self._active: dict[str, bool] = {}

    def start(self) -> None:
        for entry in self._mix.entries:
            wid = entry.model.workload_id
            if entry.activity is not None:
                self._active[wid] = entry.activity.initial_active
                self._schedule_transition(wid, entry.activity, self._loop.now)
            if self._active.get(wid, True):
                self._schedule_next(wid, self._loop.now)

    def _schedule_next(self, workload_id: str, current_time: float) -> None:
        rate = self._mix.rate_at(workload_id, current_time)
        if rate <= 0.0:
            return
        inter_arrival = self._rng.exponential(1.0 / rate)
        next_time = current_time + inter_arrival
        self._loop.schedule(
            next_time,
            lambda wid=workload_id, t=next_time: self._issue_and_reschedule(wid, t),
        )

    def _issue_and_reschedule(self, workload_id: str, issued_at: float) -> None:
        if not self._active.get(workload_id, True):
            return
        request = Request(
            request_id=f"req-{self._counter}",
            workload_id=workload_id,
            issued_at=issued_at,
        )
        self._counter += 1
        self._simulator.handle_request(request)
        self._schedule_next(workload_id, issued_at)

    def _schedule_transition(
        self, workload_id: str, activity: MarkovActivity, current_time: float
    ) -> None:
        is_active = self._active[workload_id]
        rate = activity.onset_rate if is_active else activity.recovery_rate
        delay = self._rng.exponential(1.0 / rate)
        next_time = current_time + delay
        self._loop.schedule(
            next_time,
            lambda wid=workload_id, act=activity, t=next_time: self._transition(wid, act, t),
        )

    def _transition(self, workload_id: str, activity: MarkovActivity, at: float) -> None:
        was_active = self._active[workload_id]
        self._active[workload_id] = not was_active
        if not was_active:
            self._schedule_next(workload_id, at)
        self._schedule_transition(workload_id, activity, at)

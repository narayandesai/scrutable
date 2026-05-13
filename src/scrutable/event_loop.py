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

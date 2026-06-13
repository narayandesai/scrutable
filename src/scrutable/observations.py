from __future__ import annotations
import bisect
from scrutable.models import Response


class ObservationBuffer:
    def __init__(self) -> None:
        self._responses: list[Response] = []
        self._arrivals: list[float] = []  # issued_at + latency, kept sorted

    def append(self, response: Response) -> None:
        arrival = response.issued_at + response.latency
        idx = bisect.bisect_right(self._arrivals, arrival)
        self._responses.insert(idx, response)
        self._arrivals.insert(idx, arrival)

    def window(self, start: float, end: float) -> list[Response]:
        lo = bisect.bisect_left(self._arrivals, start)
        hi = bisect.bisect_right(self._arrivals, end)
        return self._responses[lo:hi]

    def expire(self, before: float) -> None:
        idx = bisect.bisect_left(self._arrivals, before)
        self._responses = self._responses[idx:]
        self._arrivals = self._arrivals[idx:]

    @classmethod
    def from_responses(cls, responses: list[Response]) -> "ObservationBuffer":
        buf = cls()
        for r in sorted(responses, key=lambda r: r.issued_at + r.latency):
            arrival = r.issued_at + r.latency
            buf._responses.append(r)
            buf._arrivals.append(arrival)
        return buf


def merge_observation_buffers(buffers: list[ObservationBuffer]) -> ObservationBuffer:
    all_responses = [r for buf in buffers for r in buf._responses]
    return ObservationBuffer.from_responses(all_responses)

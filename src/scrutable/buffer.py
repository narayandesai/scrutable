from __future__ import annotations
import bisect
from scrutable.models import Response


class ResponseBuffer:
    def __init__(self) -> None:
        self._responses: list[Response] = []
        self._arrivals: list[float] = []  # issued_at + latency, kept sorted

    def append(self, response: Response) -> None:
        arrival = response.issued_at + response.latency
        self._responses.append(response)
        self._arrivals.append(arrival)

    def window(self, start: float, end: float) -> list[Response]:
        lo = bisect.bisect_left(self._arrivals, start)
        hi = bisect.bisect_right(self._arrivals, end)
        return self._responses[lo:hi]

    def expire(self, before: float) -> None:
        idx = bisect.bisect_left(self._arrivals, before)
        self._responses = self._responses[idx:]
        self._arrivals = self._arrivals[idx:]

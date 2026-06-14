from __future__ import annotations
from abc import ABC, abstractmethod
import numpy as np
from scrutable.models import Response
from scrutable.window_result import WindowResult


class ObservationBuffer(ABC):
    @abstractmethod
    def append(self, response: Response) -> None: ...

    @abstractmethod
    def window(self, start: float, end: float) -> WindowResult: ...

    @abstractmethod
    def expire(self, before: float) -> None: ...


class NumpyObservationBuffer(ObservationBuffer):
    def __init__(self) -> None:
        self._pending: list[tuple[float, float, float, int]] = []
        self._arrivals:    np.ndarray = np.empty(0, dtype=np.float64)
        self._latencies:   np.ndarray = np.empty(0, dtype=np.float64)
        self._issued_at:   np.ndarray = np.empty(0, dtype=np.float64)
        self._error_codes: np.ndarray = np.empty(0, dtype=np.int32)
        self._arrays_valid: bool = True  # empty arrays are already sorted
        self._low_water_mark: float = 0.0

    def append(self, response: Response) -> None:
        arrival = response.issued_at + response.latency
        self._pending.append(
            (arrival, response.latency, response.issued_at, int(response.error_code))
        )
        self._arrays_valid = False

    def _materialize(self) -> None:
        if self._arrays_valid:
            return
        # drop anything that was already expired
        pending = [(a, lat, iss, err) for a, lat, iss, err in self._pending
                   if a >= self._low_water_mark]
        if not pending:
            self._pending = []
            self._arrays_valid = True
            return
        pending.sort(key=lambda t: t[0])
        new = np.array(pending, dtype=np.float64)
        new_arrivals    = new[:, 0]
        new_latencies   = new[:, 1]
        new_issued_at   = new[:, 2]
        new_error_codes = new[:, 3].astype(np.int32)
        if len(self._arrivals) == 0:
            self._arrivals    = new_arrivals
            self._latencies   = new_latencies
            self._issued_at   = new_issued_at
            self._error_codes = new_error_codes
        else:
            all_arrivals = np.concatenate([self._arrivals, new_arrivals])
            order = np.argsort(all_arrivals, kind='stable')
            self._arrivals    = all_arrivals[order]
            self._latencies   = np.concatenate([self._latencies,   new_latencies  ])[order]
            self._issued_at   = np.concatenate([self._issued_at,   new_issued_at  ])[order]
            self._error_codes = np.concatenate([self._error_codes, new_error_codes])[order]
        self._pending = []
        self._arrays_valid = True

    def window(self, start: float, end: float) -> WindowResult:
        self._materialize()
        lo = int(np.searchsorted(self._arrivals, start, side='left'))
        hi = int(np.searchsorted(self._arrivals, end,   side='right'))
        count = hi - lo
        if count == 0:
            return WindowResult(
                t_start=start, t_end=end, count=0, error_rate=0.0,
                _latencies=np.empty(0, dtype=np.float64),
            )
        lats = self._latencies[lo:hi]
        iss  = self._issued_at[lo:hi]
        errs = self._error_codes[lo:hi]
        return WindowResult(
            t_start=float(iss.min()),
            t_end=float((iss + lats).max()),
            count=count,
            error_rate=float((errs != 0).sum()) / count,
            _latencies=lats.copy(),
        )

    def expire(self, before: float) -> None:
        self._materialize()
        idx = int(np.searchsorted(self._arrivals, before, side='left'))
        if idx > 0:
            self._arrivals    = self._arrivals[idx:]
            self._latencies   = self._latencies[idx:]
            self._issued_at   = self._issued_at[idx:]
            self._error_codes = self._error_codes[idx:]
        self._low_water_mark = max(self._low_water_mark, before)

    @classmethod
    def from_responses(cls, responses: list[Response]) -> "NumpyObservationBuffer":
        buf = cls()
        buf._pending = [
            (r.issued_at + r.latency, r.latency, r.issued_at, int(r.error_code))
            for r in responses
        ]
        if buf._pending:
            buf._arrays_valid = False
        return buf


def merge_observation_buffers(buffers: list[NumpyObservationBuffer]) -> NumpyObservationBuffer:
    for b in buffers:
        b._materialize()
    non_empty = [b for b in buffers if len(b._arrivals) > 0]
    merged = NumpyObservationBuffer()
    if not non_empty:
        return merged
    all_arrivals    = np.concatenate([b._arrivals    for b in non_empty])
    all_latencies   = np.concatenate([b._latencies   for b in non_empty])
    all_issued_at   = np.concatenate([b._issued_at   for b in non_empty])
    all_error_codes = np.concatenate([b._error_codes for b in non_empty])
    order = np.argsort(all_arrivals, kind='stable')
    merged._arrivals    = all_arrivals[order]
    merged._latencies   = all_latencies[order]
    merged._issued_at   = all_issued_at[order]
    merged._error_codes = all_error_codes[order]
    merged._arrays_valid = True
    return merged

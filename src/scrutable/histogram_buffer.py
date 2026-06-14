from __future__ import annotations
from math import ceil
import numpy as np
from scrutable.models import Response
from scrutable.window_result import WindowResult
from scrutable.observations import ObservationBuffer, NumpyObservationBuffer


class HistogramBuffer(ObservationBuffer):
    def __init__(
        self,
        total_duration: float,
        percentiles: tuple[float, ...],
        dt: float = 1.0,
        latency_lo: float = 1e-3,
        latency_hi: float = 10.0,
        n_bins: int = 200,
    ) -> None:
        self._total_duration = total_duration
        self._percentiles = percentiles
        self._dt = dt
        self._n_bins = n_bins
        self._n_cells = ceil(total_duration / dt) + 1
        self._bin_edges = np.logspace(
            np.log10(latency_lo), np.log10(latency_hi), n_bins + 1
        )
        self._counts = np.zeros((self._n_cells, n_bins), dtype=np.int32)
        self._errors = np.zeros(self._n_cells, dtype=np.int32)
        self._total  = np.zeros(self._n_cells, dtype=np.int32)
        self._expire_lo: int = 0  # cells before this index are expired

    def append(self, response: Response) -> None:
        arrival = response.issued_at + response.latency
        cell = min(int(arrival / self._dt), self._n_cells - 1)
        if cell < self._expire_lo:
            return
        bin_idx = int(np.searchsorted(self._bin_edges, response.latency, side='right')) - 1
        bin_idx = max(0, min(bin_idx, self._n_bins - 1))
        self._counts[cell, bin_idx] += 1
        self._total[cell] += 1
        if response.error_code != 0:
            self._errors[cell] += 1

    def window(self, start: float, end: float) -> WindowResult:
        lo = max(self._expire_lo, int(start / self._dt))
        hi = min(self._n_cells, int(end   / self._dt) + 1)
        if lo >= hi:
            return WindowResult(t_start=start, t_end=end, count=0, error_rate=0.0)
        total = int(self._total[lo:hi].sum())
        if total == 0:
            return WindowResult(t_start=start, t_end=end, count=0, error_rate=0.0)
        errors = int(self._errors[lo:hi].sum())
        hist = self._counts[lo:hi].sum(axis=0)
        precomputed = _percentiles_from_hist(hist, self._bin_edges, self._percentiles, total)
        return WindowResult(
            t_start=start,
            t_end=end,
            count=total,
            error_rate=errors / total,
            _precomputed=precomputed,
        )

    def expire(self, before: float) -> None:
        self._expire_lo = max(self._expire_lo, int(before / self._dt))

    @classmethod
    def from_numpy_buffer(
        cls,
        nbuf: NumpyObservationBuffer,
        total_duration: float,
        percentiles: tuple[float, ...],
        dt: float = 1.0,
        latency_lo: float = 1e-3,
        latency_hi: float = 10.0,
        n_bins: int = 200,
    ) -> "HistogramBuffer":
        hbuf = cls(
            total_duration=total_duration,
            percentiles=percentiles,
            dt=dt,
            latency_lo=latency_lo,
            latency_hi=latency_hi,
            n_bins=n_bins,
        )
        nbuf._materialize()
        if len(nbuf._arrivals) == 0:
            return hbuf
        cells = np.clip(
            (nbuf._arrivals / dt).astype(np.int64), 0, hbuf._n_cells - 1
        )
        bin_idxs = np.clip(
            np.searchsorted(hbuf._bin_edges, nbuf._latencies, side='right') - 1,
            0, n_bins - 1,
        ).astype(np.int64)
        np.add.at(hbuf._counts, (cells, bin_idxs), 1)
        np.add.at(hbuf._total,  cells, 1)
        np.add.at(hbuf._errors, cells, (nbuf._error_codes != 0).astype(np.int32))
        return hbuf


def _percentiles_from_hist(
    counts: np.ndarray,
    bin_edges: np.ndarray,
    percentiles: tuple[float, ...],
    total: int,
) -> dict[float, float]:
    if total == 0:
        return {p: 0.0 for p in percentiles}
    cdf = np.cumsum(counts)
    result: dict[float, float] = {}
    for p in percentiles:
        target = p / 100.0 * total
        idx = int(np.searchsorted(cdf, target, side='left'))
        idx = min(idx, len(counts) - 1)
        lo = float(bin_edges[idx])
        hi = float(bin_edges[idx + 1])
        prev = int(cdf[idx - 1]) if idx > 0 else 0
        span = int(cdf[idx]) - prev
        frac = ((target - prev) / span) if span > 0 else 0.0
        result[p] = lo + frac * (hi - lo)
    return result


def merge_histogram_buffers(buffers: list[HistogramBuffer]) -> HistogramBuffer:
    assert buffers, "merge_histogram_buffers requires at least one buffer"
    first = buffers[0]
    result = HistogramBuffer(
        total_duration=first._total_duration,
        percentiles=first._percentiles,
        dt=first._dt,
        latency_lo=float(first._bin_edges[0]),
        latency_hi=float(first._bin_edges[-1]),
        n_bins=first._n_bins,
    )
    for b in buffers:
        result._counts += b._counts
        result._errors += b._errors
        result._total  += b._total
    return result

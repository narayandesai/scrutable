# ObservationBuffer Optimization Design

**Date:** 2026-06-14
**Status:** Approved

## Problem

The simulation pipeline stores every individual `Response` object in memory. For the long-tail profile at 100k req/s over ~3630 seconds, this means hundreds of millions of Python objects (~250–350 bytes each due to unused string fields). Two compounding issues:

1. `ObservationBuffer` holds parallel Python lists — high per-object overhead, slow `window()` construction.
2. The parallel talk script accumulates raw response lists for all chunks before any analysis, holding both profiles in memory simultaneously.

## Goal

Reduce peak memory in the simulation analysis pipeline by two complementary paths:

- **Path A (exact):** Replace Python list internals with numpy arrays — ~10x reduction, no change to results.
- **Path B (approximate):** Replace individual response storage with a pre-allocated time-bucketed histogram — ~1000x reduction, percentile error bounded by bin resolution.

Both paths expose the same `ObservationBuffer` ABC and return `WindowResult` from `window()`, so sensors and detectors work unchanged across both.

## Module Layout

```
src/scrutable/
  window_result.py            new: WindowResult dataclass
  observations.py             ObservationBuffer ABC + NumpyObservationBuffer
  histogram_buffer.py         new: HistogramBuffer + merge_histogram_buffers
  engine.py                   update ObservationBuffer() → NumpyObservationBuffer()
  detectors/slo.py            update sensor/calibrator call sites
  scenarios/slo_performance.py  update _analyze_buffer call sites; add histogram kwargs
  scenarios/slo_spectrum.py     update call sites
scrutable-talk/
  noise_vs_window_parallel.py  workers return HistogramBuffer; lead sums
```

## WindowResult

`WindowResult` is the return type of `window()` for all buffer implementations.

```python
@dataclass
class WindowResult:
    t_start: float
    t_end: float
    count: int
    error_rate: float
    _latencies: np.ndarray | None      # exact values; None for histogram path
    _precomputed: dict[float, float]   # percentile → value; populated by histogram path

    def percentile(self, p: float) -> float: ...
    def __len__(self) -> int: ...
    def __bool__(self) -> bool: ...
```

- For `NumpyObservationBuffer`: `_latencies` is a numpy array slice; `percentile(p)` delegates to `np.percentile`.
- For `HistogramBuffer`: `_latencies` is `None`; `percentile(p)` looks up `_precomputed` (raises `KeyError` if `p` was not declared at construction).
- `error_rate`, `t_start`, `t_end`, and `count` are always populated by both paths.

### Consumer updates

All call sites in `detectors/slo.py`, `scenarios/slo_performance.py`, and `scenarios/slo_spectrum.py` that currently do:

```python
latencies = np.array([r.latency for r in window])
value = float(np.percentile(latencies, p))
t_start = min(r.issued_at for r in window)
t_end = max(r.issued_at + r.latency for r in window)
error_rate = sum(1 for r in window if r.error_code != 0) / len(window)
```

become:

```python
value = window.percentile(p)
t_start = window.t_start
t_end = window.t_end
error_rate = window.error_rate
```

## ObservationBuffer ABC

`observations.py` defines the ABC and `NumpyObservationBuffer`. The `merge_observation_buffers` free function remains here, returning `NumpyObservationBuffer`.

```python
class ObservationBuffer(ABC):
    @abstractmethod
    def append(self, response: Response) -> None: ...
    @abstractmethod
    def window(self, start: float, end: float) -> WindowResult: ...
    @abstractmethod
    def expire(self, before: float) -> None: ...
```

`from_responses` is **not** on the ABC — the two implementations have different constructor requirements. It is a concrete classmethod on `NumpyObservationBuffer` only.

## NumpyObservationBuffer

Replaces the current `ObservationBuffer` class. Stores four parallel numpy arrays: `arrivals (f8)`, `latencies (f8)`, `issued_at (f8)`, `error_codes (i4)`.

**Build phase:** `append()` pushes tuples onto an unsorted Python list (`_pending`). O(1) amortized.

**Materialize:** on first `window()` call (or explicitly), `_pending` is sorted by arrival time and assigned to the four numpy arrays. Invalidated by any subsequent `append()`. Re-sort happens on next `window()` call. For the simulation use case (all appends then all windows), this sorts exactly once.

**Window query:** `np.searchsorted` on `arrivals` for the time range; returns a `WindowResult` with `_latencies` as a numpy slice.

**`from_responses(cls, responses) -> NumpyObservationBuffer`:** convenience classmethod for constructing from a list of `Response` objects. Used by `merge_observation_buffers`.

**`merge_observation_buffers(buffers: list[NumpyObservationBuffer]) -> NumpyObservationBuffer`:** unchanged heapq-based streaming merge; still lives in `observations.py`.

**Memory:** ~32 bytes per response (4 × f8/i4 fields) vs ~250–350 bytes for a Python `Response` object. ~10x reduction.

## HistogramBuffer

Lives in `histogram_buffer.py`. Pre-allocated at construction time; no dynamic resizing.

### Constructor

```python
HistogramBuffer(
    total_duration: float,
    percentiles: tuple[float, ...],
    dt: float = 1.0,
    latency_lo: float = 1e-3,
    latency_hi: float = 10.0,
    n_bins: int = 200,
)
```

- `n_cells = ceil(total_duration / dt) + 1`
- `bin_edges`: `n_bins + 1` log-spaced edges from `latency_lo` to `latency_hi`
- Pre-allocated arrays: `_counts (n_cells × n_bins, int32)`, `_errors (n_cells, int32)`, `_total (n_cells, int32)`

### append()

```python
cell = int((response.issued_at + response.latency) / dt)
bin  = np.searchsorted(bin_edges, response.latency, side='right') - 1
_counts[cell, bin] += 1
_errors[cell] += response.error_code != 0
_total[cell] += 1
```

O(log n_bins) per call.

### window()

```python
lo = max(0, int(start / dt))
hi = min(n_cells, int(end / dt) + 1)
hist   = _counts[lo:hi].sum(axis=0)   # shape: (n_bins,)
total  = _total[lo:hi].sum()
errors = _errors[lo:hi].sum()
```

Percentiles computed in a single CDF pass over `hist` for all declared percentiles. Returns `WindowResult(t_start=start, t_end=end, count=total, error_rate=errors/total, _latencies=None, _precomputed={p: v, ...})`.

### expire()

Zero out cells with arrival index < `int(before / dt)`.

### from_numpy_buffer()

Class-specific factory used by workers in the parallel script:

```python
@classmethod
def from_numpy_buffer(
    cls,
    buf: NumpyObservationBuffer,
    total_duration: float,
    percentiles: tuple[float, ...],
    **kwargs,
) -> "HistogramBuffer": ...
```

Iterates the materialized numpy buffer and fills histogram counts in O(n) with vectorized `searchsorted`.

### merge_histogram_buffers()

```python
def merge_histogram_buffers(buffers: list[HistogramBuffer]) -> HistogramBuffer:
    result = HistogramBuffer(same params as inputs)
    for buf in buffers:
        result._counts += buf._counts
        result._errors += buf._errors
        result._total  += buf._total
    return result
```

O(n_cells × n_bins) regardless of request count. For the parallel script this replaces the heapq merge entirely.

**Memory:** ~2.9 MB per `HistogramBuffer` (3630 cells × 200 bins × 4 bytes + overhead) vs GBs of response data. ~1000x reduction.

### Percentile accuracy

With 200 log-spaced bins from 1 ms to 10 s, the relative bin width is `10^(4/200) - 1 ≈ 4.7%`. At 100k req/s with a 1-second bucket, each window has ample samples for stable tail estimates, so CDF interpolation within a bin is accurate to well under 1% of the true value at P99.9.

## Simulation Pipeline Integration (talk script)

**Worker side:** `_run_chunk_by_index` builds the engine as today (using `NumpyObservationBuffer`), then converts to `HistogramBuffer` before returning:

```python
hbuf = HistogramBuffer.from_numpy_buffer(
    engine.buffer,
    total_duration=total_duration,
    percentiles=PERCENTILES,
)
return hbuf
```

IPC payload: ~2.9 MB per worker vs potentially GBs.

**Lead side:** accumulate `HistogramBuffer` objects per profile, call `merge_histogram_buffers`, run analysis on merged `HistogramBuffer` via `WindowResult` interface.

```python
chunk_hbufs: dict[str, list[HistogramBuffer]] = {"spherical_cow": [], "long_tail": []}

for fut in as_completed(futures):
    name = futures[fut]
    chunk_hbufs[name].append(fut.result())

for name, profile in profiles_meta.items():
    buf = merge_histogram_buffers(chunk_hbufs.pop(name))
    ...
```

## Testing

- `tests/test_window_result.py`: `percentile()` for exact and precomputed paths; `error_rate`, `__len__`, `__bool__`; `KeyError` for undeclared percentile on histogram path.
- `tests/test_numpy_buffer.py`: `window()` matches current `ObservationBuffer` behavior exactly; lazy materialization; `append()` after `window()` re-sorts correctly; `merge_observation_buffers` unchanged.
- `tests/test_histogram_buffer.py`: `percentile()` accuracy within 5% of numpy ground truth at P50/P90/P99/P99.9 on synthetic lognormal data; `error_rate` correctness; `merge_histogram_buffers` produces same result as building from merged inputs.
- All existing tests continue to pass (consumers updated to `WindowResult` interface).

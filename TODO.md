# TODO

## Interface
- [ ] Add a way to run the simulator without writing Python — CLI entry point or example script
- [ ] Live replay web view: run simulation to completion, then replay results progressively in browser via Plotly Dash — show accumulating P50/P90/P99/P99.9 time series with playback speed control

## Known Limitations
- [ ] Overlapping disturbances on the same field: removing one resets the field to its default even if another is still active. Needs a per-field stack or reference-count in `disturbance.py` so the last writer wins on removal.
- [ ] `StochasticDisturbance` with `duration >= 1/rate` can produce overlapping occurrences (same root cause as above).

## Disturbance Recipes
Helper factories in `disturbance.py` (or a new `recipes.py`) that return pre-configured `TimedDisturbance` or `StochasticDisturbance` values for common operational scenarios:

- [ ] **Software bug** — `bug_disturbance(disturbance_id, cluster, error_rate_multiplier, inject_at, remove_at)`: node-scoped `TimedDisturbance` raising `error_rate_multiplier` on all nodes in a cluster for a fixed window; models a bad deploy
- [ ] **Dependency degraded** — `degraded_dependency(disturbance_id, workload_id, latency_addend, inject_at, remove_at)`: workload-scoped `TimedDisturbance` adding a fixed latency addend; models a slow upstream
- [ ] **Dependency failure** — `failed_dependency(disturbance_id, workload_id, error_rate_multiplier, inject_at, remove_at)`: workload-scoped `TimedDisturbance` spiking error rate to near 1.0; models a hard dependency outage
- [ ] **Noisy neighbor / diurnal contention** — `stochastic_contention(disturbance_id, cluster, latency_addend, rate, duration)`: node-scoped `StochasticDisturbance`; short bursts at Poisson rate model cache pressure or co-tenant interference
- [ ] **Two-state Markov disturbance**: node-set level disturbance alternating between normal and degraded states. Parameters: onset rate λ (good→bad), recovery rate μ (bad→good), scope (which nodes), and effect (latency_addend or error_rate during degraded state). Models cache undersizing (low μ, rare onset), racey errors (short high-μ bursts), or noisy-neighbor effects. Detection behavior depends on the relationship between burst duration (1/μ) and window size — interesting control theory angle. Requires a new timed event type in the simulator for state transitions. Note: `MarkovActivity` in `traffic.py` covers workload-level on/off; this is distinct node-level degradation.

## SLO Detection
- [x] Add empirical SNR to `PerformancePoint`: signal = mean shift in observed P99.9 across post-disturbance windows vs baseline; noise = std dev of P99.9 across burn-in windows. SNR < 1 means the disturbance is buried in estimator noise regardless of W. Requires storing per-window percentile values during the sweep, not just the binary fired/not. Consider whether to report SNR per window-size or once per profile (it is independent of W for large enough windows).

## Simulation
- [ ] Increase scale of simulation
- [ ] Workload shifts over time: calibrated SLO thresholds become stale when the underlying workload distribution changes (traffic mix shift, new feature rollout changing latency profile). Need a way to detect when recalibration is needed, or to model drift explicitly.
- [x] Calibrate realistic disturbance magnitude: updated default `disturbance_addend` from 0.8s to 0.3s (3× the 100ms median, models a slow dependency adding ~300ms). At `rate=1000, addend=0.3`: P99.9 detector gets recall=1.0/0.88 for σ≤0.3; recall=0 for σ≥0.6. P50 detector inverts the pattern (recall=0.98–1.00 for σ≥0.6, lower for tight services due to threshold being at 2× the baseline P50). This is the core talk result. Note: low P50 recall on tight services (0.60) is a calibration artifact — 50% coverage pushes post-disturbance P50 exactly to the 2× threshold.
- [ ] Ground disturbance magnitude in real service data: pick sigma values matching observed P50/P99 ratios for real services, and disturbance magnitudes matching real incidents (slow DB query, GC pause, etc.).
- [ ] **Burn-in length recommendations**: SNR noise estimate is `std` over burn-in windows; with only 30 windows the estimate has high variance and the within-profile percentile ordering (e.g. P75 > P50) is unreliable. Rule of thumb: ≥ 60 burn-in windows for stable std estimates. At `window_size=1s` that means `calibration_duration ≥ 60s`; at `window_size=5s`, `calibration_duration ≥ 300s`. Document this as a constraint in `sweep_slo_performance` docstring and enforce or warn when `calibration_duration / window_size < 60`.
- [ ] **P99.9 estimation requires sufficient events per window**: the P99.9 estimate is unreliable unless the window contains ≥ ~1000 responses (so the 1-in-1000 tail has ≥ 1 sample on average). Minimum constraint: `rate × window_size ≥ 1000`. At `rate=5 req/s` (per workload) with 1000 workloads, a `window_size=0.2s` suffices; but for the default `rate=5.0` (total), need `window_size ≥ 200s` — clearly impractical. Either raise the default rate or document the minimum QPS required for P99.9 sensing to be meaningful.
- [ ] **Calibration multiplier sensitivity**: the 2× default calibration multiplier sets the threshold at 2× the calibrated burn-in P99.9. For high-variance profiles this can place the threshold at the 99.99th+ percentile, making detection effectively impossible. Consider adaptive multiplier selection (e.g. set threshold at burn-in P99.9 + k×std for fixed k) rather than a scalar multiple, so the threshold tracks the variability of the signal rather than its magnitude.
- [ ] Explore low QPS dynamics: percentile estimation breaks down at low event rates — understand the boundary and whether it's worth modeling

## Talk
- [ ] Refine outline
- [ ] Build a development plan
- [ ] Design progressive rollout demo: failure mode, service profiles, scenarios

## Deferred from Design
- [x] Time-based rolling deploys: rollouts currently apply instantaneously; model per-node rollout progression over simulation time
- [ ] Multi-hop requests: currently a single node interaction; call graphs and fan-out deferred
- [ ] Load balancing beyond cluster drain: weighted routing and more granular traffic steering
- [ ] Performance: event loop kernel has a clean boundary for future Rust replacement via PyO3

## Polish
- [x] Add `pyrightconfig.json` to silence false-positive `reportMissingImports` warnings from Pyright (src layout + .venv not visible to Pyright by default)
- [x] `WorkloadRegistry.get()` raises a bare `KeyError` — a `ValueError` with the unknown ID in the message would be friendlier
- [x] Add workload percentage and time-of-day density: `WorkloadEntry.share` + `DiurnalCurve` support added to `traffic.py`
- [x] Map implementation naming to control theory vocabulary

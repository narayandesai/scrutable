# TODO

## Interface
- [ ] Add a way to run the simulator without writing Python — CLI entry point or example script

## Known Limitations
- [ ] Overlapping pathologies on the same field: removing one resets the field to 1.0 even if another is active. Needs a per-field stack or reference-count approach in `pathology.py`
- [ ] Stochastic pathologies with `duration >= 1/rate` can overlap themselves (same underlying issue)

## Pathologies
- [ ] Flush out pathology interface
- [ ] Implement pathologies: software bug, diurnal contention, dependency failure, dependency degraded

## Deferred from Design
- [ ] Time-based rolling deploys: rollouts currently apply instantaneously; model per-node rollout progression over simulation time
- [ ] Multi-hop requests: currently a single node interaction; call graphs and fan-out deferred
- [ ] Load balancing beyond cluster drain: weighted routing and more granular traffic steering
- [ ] Performance: event loop kernel has a clean boundary for future Rust replacement via PyO3

## Polish
- [x] Add `pyrightconfig.json` to silence false-positive `reportMissingImports` warnings from Pyright (src layout + .venv not visible to Pyright by default)
- [x] `WorkloadRegistry.get()` raises a bare `KeyError` — a `ValueError` with the unknown ID in the message would be friendlier

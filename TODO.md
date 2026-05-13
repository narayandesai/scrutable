# TODO

## Interface
- [ ] Add a way to run the simulator without writing Python — CLI entry point or example script

## Known Limitations
- [ ] Overlapping pathologies on the same field: removing one resets the field to 1.0 even if another is active. Needs a per-field stack or reference-count approach in `pathology.py`
- [ ] Stochastic pathologies with `duration >= 1/rate` can overlap themselves (same underlying issue)

## Deferred from Design
- [ ] Time-based rolling deploys: rollouts currently apply instantaneously; model per-node rollout progression over simulation time
- [ ] Multi-hop requests: currently a single node interaction; call graphs and fan-out deferred
- [ ] Load balancing beyond cluster drain: weighted routing and more granular traffic steering
- [ ] Performance: event loop kernel has a clean boundary for future Rust replacement via PyO3

## Polish
- [ ] Add `pyrightconfig.json` to silence false-positive `reportMissingImports` warnings from Pyright (src layout + .venv not visible to Pyright by default)
- [ ] `WorkloadRegistry.get()` raises a bare `KeyError` — a `ValueError` with the unknown ID in the message would be friendlier
- [ ] `PathologyInjector` is not exported from `__init__.py` — decide if it belongs in the public API

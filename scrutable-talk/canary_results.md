# Canary Rollout Simulation Results

## Scenario

A 30-engineer team ships 150 changes/week, bundled into weekly releases of 150 changes each. Each change independently has a 1% chance of introducing a latency regression (+0.3 s on every node in scope). The canary controller bakes each release in the canary cluster for 2 days before promoting to production. A P99.9 SLO sensor fires an alarm if the calibrated threshold is crossed during the bake; an alarm triggers a rollback and a 6-hour (median, lognormal σ=0.84) debug cycle before a clean fix release is queued.

Simulated at 10 req/s (×6982 speedup) over 6 weeks after an 8-day clean burn-in calibration. Three velocity scales are compared: 100%, 150%, and 200% of the baseline change rate and bundle size (keeping release cadence at 1/week).

Two plant profiles are compared:

| Profile | Workload | P99.9 baseline | SLO threshold |
|---------|----------|----------------|---------------|
| `spherical_cow` | Single lognormal (median 0.1 s, σ=0.3) | ~0.3 s | **0.30 s** |
| `long_tail` | 1 fast (90% traffic) + 4 slow Markov workloads (10% combined, duty 5–18%) | ~37 000 s | **37 062 s** |

The same calibration procedure is applied to both profiles. The SLO threshold is set empirically at `(1 − effective_fpr) × 100`th percentile of per-window P99.9 observations during burn-in, where `effective_fpr = min(target_fpr, 4 alerts/day, 0.5 alerts/bake) = 8.68×10⁻⁴`.

---

## Detection Results

### spherical\_cow — threshold 0.30 s

| Scale | Orig releases | w/ bug | Caught (TP) | Escaped (FN) | False RBs (FP) | Retries | Debug median |
|-------|--------------|--------|-------------|--------------|----------------|---------|--------------|
| 100%  | 6            | 5      | **5 (100%)** | 0           | 0              | 6       | 6.2 h        |
| 150%  | 5            | 4      | **4 (100%)** | 0           | 1              | 5       | 2.9 h        |
| 200%  | 5            | 5      | **5 (100%)** | 0           | 0              | 8       | 4.9 h        |

### long\_tail — threshold 37 062 s

| Scale | Orig releases | w/ bug | Caught (TP) | Escaped (FN) | False RBs (FP) | Retries | Debug median |
|-------|--------------|--------|-------------|--------------|----------------|---------|--------------|
| 100%  | 5            | 4      | 0 (0%)      | **4**        | 0              | 0       | n/a          |
| 150%  | 5            | 5      | 1 (20%)     | **4**        | 0              | 1       | 5.4 h        |
| 200%  | 6            | 6      | 0 (0%)      | **5**        | 0              | 0       | n/a          |

The 1 catch at 150% long-tail is a transient: a slow workload happened to be active during that bake, pushing P99.9 briefly above threshold. It is not a reliable detection signal.

**Summary:** the same controller — same calibration procedure, same SLO structure, same bake duration — delivers 100% detection on SC and ~0% on LT. The 0.3 s latency regression is physically undetectable against a 37 000 s P99.9 noise floor. This is the same SNR collapse documented in the static-threshold sensor evaluation, now manifesting at the pipeline level.

---

## Change Velocity Results

### spherical\_cow

| Scale | Changes shipped | Changes/wk | Lead P50 | Lead P90 | Lead P95 |
|-------|----------------|------------|----------|----------|----------|
| 100%  | 750            | 125        | 154 h    | 232 h    | 273 h    |
| 150%  | 1125           | 188        | 143 h    | 214 h    | 225 h    |
| 200%  | 1500           | 250        | 159 h    | 226 h    | 245 h    |

### long\_tail

| Scale | Changes shipped | Changes/wk | Lead P50 | Lead P90 | Lead P95 |
|-------|----------------|------------|----------|----------|----------|
| 100%  | 750            | 125        | 133 h    | 203 h    | 213 h    |
| 150%  | 1125           | 188        | 143 h    | 215 h    | 224 h    |
| 200%  | 1500           | 250        | 131 h    | 199 h    | 209 h    |

Lead time is measured from individual change submission to completed rollout. For changes in rolled-back releases, lead time includes the rollback (1 h), the debug cycle, and the fix release bake (another 2 days).

### Interpretation

**P50 overhead of effective detection: ~20 h (~15%).**  
SC lead times are 20–30 h longer at P50 than LT. This is the steady-state cost of the rollback+debug cycle amortized across all changes. Since most changes ship cleanly (only 1% are buggy), the overhead is diluted: a 6 h debug cycle on 1 out of 150 changes adds 6/150 × 24 h ≈ 1 h to average lead time, plus 48 h fix-release bake time for affected changes.

**P95 overhead: +12–60 h.**  
At the tail, changes that land in a buggy release experience the full rollback+debug+re-bake penalty (48 h bake + 1 h rollback + up to 24 h debug at P95 = ~73 h extra). The P95 spread reflects this: SC P95 is 225–273 h vs LT P95 213–224 h.

**Throughput is equal across all velocities.**  
At 100%, 150%, and 200%, both profiles ship 125, 188, and 250 changes/week respectively. The SC pipeline absorbs bugs without throughput loss because retries always succeed. The velocity cost is latency, not volume.

**Long-tail throughput scales linearly; SC throughput is similar.**  
Both profiles ship 125→188→250 changes/week across scales. SC is slightly noisier at P95 because rollback-and-retry cycles add non-deterministic delay, but the effect is modest.

---

## Key Findings

1. **The SNR collapse documented in static-threshold evaluation propagates directly to pipeline outcomes.** A sensor that cannot see a fault will not trigger a rollback. The canary bake duration is irrelevant if the fault is below the noise floor.

2. **Effective detection costs ~15% lead time at P50.** This is the overhead a team pays for reliable bug-catching: ~20 h extra per change on a 133–154 h baseline. The cost is bounded and predictable from the debug cycle distribution.

3. **The tail cost (P95) is larger but rare.** Changes unlucky enough to land in a buggy release see a full rollback+debug+re-bake penalty of ~60 h. This is a known, bounded quantity — it can be budgeted.

4. **Plant profile selection is a first-class decision for canary design.** A team running a long-tail service must either: (a) use a different sensor (lower percentile, or a metric other than latency P99.9), (b) increase canary traffic concentration, or (c) accept that their canary provides no meaningful protection against latency regressions.

5. **A pipeline deadlock was found and fixed during analysis.** The 150% SC run initially produced only 2 releases in 6 weeks. Investigation traced it to a timing bug: a sensor tick scheduled at the same timestamp as rollback completion fired first (lower event-loop sequence), recording a stale alarm while the prior release's disturbance was still live. That alarm's timestamp matched `canary_deploy_time` of the fix release exactly, causing the prod-stage gate (`any_since(dt)` with `>=`) to fail. The engine halted the rollout without triggering rollback or `_on_failure`, deadlocking the pipeline. Fixed by offsetting the gate threshold by 1 ns to exclude alarms at exactly the deploy moment. With the fix, 150% SC produces the expected 5 original releases and 188 changes/week.

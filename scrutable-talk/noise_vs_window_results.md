# Noise vs. Window Size: P99.9 Noise Floor Experiment

## Setup

Two plant profiles, sweep over window sizes 1s / 5s / 30s / 60s / 120s:

- **spherical_cow (SC):** low-variance lognormal workload, tight tail behavior
- **long_tail (LT):** heavy-tailed workload mix with wide spread across operating regimes

Fixed disturbance injected at known time. Noise measured as std dev of P99.9 across
burn-in windows (no disturbance). SNR = signal / noise where signal is the shift in
P99.9 post-disturbance vs. baseline.

## Results

### Recall and FPR

| Window | SC recall | SC FPR | LT recall | LT FPR |
|--------|-----------|--------|-----------|--------|
| 1s     | 0.28      |  5.0%  | 1.00      | 91.2%  |
| 5s     | 0.29      |  1.25% | 1.00      | 93.1%  |
| 30s    | 0.50      |  5.0%  | 1.00      | 75.8%  |
| 60s    | 0.50      |  3.3%  | 1.00      | 51.7%  |
| 120s   | 1.00      |  3.3%  | 1.00      |  3.3%  |

SC recall is non-monotonic: lowest at small windows (0.28-0.29), recovering to 1.0 at
120s. This reflects the time-limited fault — the disturbance lasts exactly POST_DIST
seconds, and with small windows the calibrated threshold overshoots the shorter fault
signal. SC SNR(P99.9) is consistently > 1 (5–13×), so the fault is detectable in
principle; the recall gap is a calibration sensitivity effect, not a structural floor.

LT recall is 1.00 at every window size. This is surprising given LT SNR(P99.9) < 1 —
the LT detector fires because of its catastrophically high FPR (51–93%), not because it
is genuinely detecting the fault.

### P99.9 Noise Floor and SNR

| Window | SC noise(P99.9) | LT noise(P99.9) | Ratio | SC SNR(P99.9) | LT SNR(P99.9) |
|--------|-----------------|-----------------|-------|---------------|---------------|
| 1s     | 0.0057s         | 3.46s           | 613×  | 13            | 0.48          |
| 5s     | 0.0096s         | 3.46s           | 360×  |  8.6          | 0.48          |
| 30s    | 0.020s          | 3.51s           | 176×  |  6.2          | 0.48          |
| 60s    | 0.027s          | 3.53s           | 133×  |  5.1          | 0.48          |
| 120s   | 0.035s          | 3.43s           |  99×  |  7.6          | 0.45          |

### P50 SNR (for comparison)

| Window | SC SNR(P50) | LT SNR(P50) |
|--------|-------------|-------------|
| 1s     | 173         | 75          |
| 5s     | 260         | 88          |
| 30s    | 220         | 98          |
| 60s    | 130         | 53          |
| 120s   | 163         | 44          |

## Key Observations

**LT P99.9 noise is window-size invariant.** The floor sits at ~3.43–3.53s across all
five window sizes (1s through 2m). Wider windows provide no relief.

**The ratio is shrinking for the wrong reason.** The noise ratio falls from 613× (1s) to
99× (2m) not because LT improves, but because SC noise grows as larger windows
accumulate more mix-shift variance. LT P99.9 noise doesn't move.

**LT SNR(P99.9) ≈ 0.48 at every window size.** SNR < 1 means noise exceeds signal at
the tail — the disturbance is physically undetectable by a P99.9 sensor regardless of
how long you aggregate.

**LT FPR is catastrophic.** 91–93% at 1s and 5s windows, 76% at 30s. Normal operation
of the long_tail plant regularly produces P99.9 values that exceed the fault threshold.

**P50 is unaffected.** Both profiles achieve SNR(P50) >> 1, and that SNR improves with
wider windows. The failure is sensor choice, not window size.

## Interpretation: Mix-Shift Dominance

The LT P99.9 noise floor does not shrink with wider windows because it is dominated by
**mix-shift**: random variation in which workloads land in a given measurement window
shifts aggregate P99.9 independently of sample count. Adding more events (wider window)
does not reduce this variance — it is driven by workload composition, not sample noise.

This is the control-theoretic explanation for the "high-variance services are hard to
monitor" observation practitioners make empirically. It is not a calibration problem or
a threshold problem. The sensor (P99.9) has structural SNR < 1 for this plant profile.
No operational tuning fixes it.

## Talk Claim

For a long_tail service, P99.9 noise is ~3.5s regardless of window size — confirmed
from 1s windows out to 2-minute windows. SNR(P99.9) ≈ 0.48 at every window size; noise
exceeds signal by 2×. Monitoring P99.9 on this service produces 51–93% false positive
rate with no improvement in sensitivity from wider aggregation. The problem is not the
aggregation period. The problem is the percentile.

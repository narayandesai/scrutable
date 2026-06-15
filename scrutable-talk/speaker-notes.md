# Speaker Notes

## Slide: P99.9 noise floor is window-size invariant for high-variance services

The table shows noise at P99.9 across three window sizes for two profiles. The key thing to say out loud:

The ratio is falling — 613× at 1s, 176× at 30s — and that looks like progress. It isn't. The long_tail noise is sitting at 3.5 seconds across every window size. The ratio is shrinking because the spherical_cow noise is *growing* as wider windows accumulate more mix-shift variance. These numbers are converging, but not in the direction you want.

The SNR column is the real result. Long_tail SNR(P99.9) is 0.48 at 1 second, 0.48 at 5 seconds, 0.48 at 30 seconds. It doesn't move. SNR < 1 means noise exceeds signal — you cannot detect this fault with a P99.9 sensor regardless of how long you aggregate.

Why doesn't it improve? The noise at P99.9 for a heavy-tailed service isn't sample noise — it's mix-shift. Each measurement window captures a slightly different composition of workloads, and those workloads have different tail behavior. That randomness shifts P99.9 by ~3.5 seconds in normal operation, with no disturbance at all. You can't average that away by collecting more events in a longer window because the variance is in which workloads show up, not in how many.

The false positive rate for long_tail at a 1-second window is 91%. The detector fires constantly on normal operation. At 30 seconds it's 76%. Still useless.

Meanwhile, SNR(P50) for the same service is 300–400 at every window size. The signal is there. The disturbance is real and detectable. The problem is entirely the choice of sensor.

The punchline: this is not a calibration problem. It is not a "use a longer window" problem. The sensor — P99.9 — has structural SNR < 1 for this plant. No operational tuning fixes it.

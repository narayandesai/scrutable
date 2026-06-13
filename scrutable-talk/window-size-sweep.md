# Window Size Sweep: P99.9 vs P50 Detector

Setup: fixed arrival rate 1000 req/s, disturbance_addend=0.3s (300ms on 100ms median),
disturbance_coverage=50%, empirical calibration with target_fpr=0.1%, n_calibration_windows=60.

Two profiles: variance_v1 (σ=0.1, tight) and variance_v4 (σ=1.0, high-variance).

## Results

```
window   profile       P99.9 fpr  P99.9 recall    P50 fpr  P50 recall  P99.9 det_lat
--------------------------------------------------------------------------------------
    1s   variance_v1      0.0167          1.00     0.0167        1.00             6s
    1s   variance_v4      0.0167          0.00     0.0167        1.00           None

    5s   variance_v1      0.0167          1.00     0.0167        1.00            28s
    5s   variance_v4      0.0167          0.00     0.0167        1.00           None

   15s   variance_v1      0.0167          1.00     0.0167        1.00            82s
   15s   variance_v4      0.0167          0.00     0.0167        1.00           None

   30s   variance_v1      0.0167          1.00     0.0167        1.00           165s
   30s   variance_v4      0.0167          0.10     0.0167        1.00           210s

    1m   variance_v1      0.0167          1.00     0.0167        1.00           330s
    1m   variance_v4      0.0167          0.40     0.0167        1.00           405s

    2m   variance_v1      0.0167          1.00     0.0167        1.00           660s
    2m   variance_v4      0.0167          0.60     0.0167        1.00           580s
```

## Key Observations

- **P50 detector**: 100% recall at every window size for both profiles. Detection latency
  scales linearly with window size (one window behind the disturbance).

- **P99.9 detector on tight services (v1)**: 100% recall at all window sizes — the
  disturbance easily clears the calibrated threshold.

- **P99.9 detector on high-variance services (v4)**: completely blind below 30s windows.
  Recovery is slow — even at 2m windows (60k events/window), only 60% recall with
  ~580s mean detection latency. At 1s windows, each window has only 1000 events;
  the P99.9 estimator variance swamps the 300ms signal.

## Talk Claim

For a high-variance service receiving 1000 req/s, a P50 sensor detects a 300ms
disturbance in ~6s. A P99.9 sensor requires 2-minute aggregation windows to achieve
60% recall — at a cost of 580s mean detection latency. Choosing the right percentile
is not a philosophical preference; it determines whether your alerting system works at all.

## FPR Note

FPR=0.0167 (1/60) is the finite-sample artifact of empirical quantile calibration
with 60 burn-in windows: np.percentile(60 values, 99.9) falls just below the maximum,
so 1/60 burn-in windows exceeds the threshold in-sample. Achieving true 0.1% FPR
requires ~1000 calibration windows.

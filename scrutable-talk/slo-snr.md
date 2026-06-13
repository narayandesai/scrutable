# SNR Methodology for SLO Threshold Detection

## Core Idea

SNR is a property of the sensing methodology, not of the distribution alone. For a
given SLO detector (defined by which percentile it monitors and how it sets thresholds),
SNR measures how reliably that detector can distinguish a disturbance from normal
variation.

## Signal

The signal is the shift in a percentile p caused by the disturbance:

    signal(p) = percentile_p(post-disturbance) - percentile_p(baseline)

For a fixed latency multiplier M applied uniformly to all nodes, the signal is largest
in absolute terms at the tail (P99.9 shifts more than P50 in absolute latency). But
absolute shift is not what determines detectability — SNR does.

## Noise

The noise is the natural variation in the estimated percentile under normal operation.
Three sources contribute:

1. **Within-workload variance** — the lognormal sigma. Even a single stable workload
   produces per-request fluctuation.

2. **Cross-workload mix variance** — different workloads have different baseline
   medians. Random variation in which workloads land in a given measurement window
   shifts aggregate percentiles even under perfectly stable conditions. This is the
   dominant noise source for high-variance service populations.

3. **Sample noise** — finite window size means estimated percentiles have statistical
   uncertainty. Shrinks with higher QPS and longer windows.

The noise floor is measured empirically: run multiple burn-in windows (no disturbance),
compute the target percentile for each window, take the standard deviation across
windows. This is noise(p).

## SNR as a Profile, Not a Number

SNR is not a single number for a service — it is a profile across the distribution:

    SNR(p) = signal(p) / noise(p)

Different disturbance types produce different SNR profiles:

- **Uniform node degradation** (all nodes slower): shifts the whole distribution.
  Signal is visible at P50, P90, P99, P99.9. SNR(P50) may be the highest because
  P50 is estimated from the dense part of the distribution — more samples, lower
  noise floor.

- **Tail-affecting disturbance** (occasional severe slowdowns, e.g. lock contention):
  low signal at P50, high signal at P99.9. But P99.9 noise is also high. SNR profile
  peaks in the tail.

- **Partial workload degradation** (only some workloads affected): signal depends on
  the affected workloads' position in the mix. May be invisible in aggregate percentiles
  if the affected fraction is small.

## The Indictment of Static SLO Thresholds

Static SLO detectors monitor one fixed percentile (typically P99 or P99.9), chosen
by convention rather than by where the signal is strongest for this service and this
disturbance class. This means:

- For a service with high tail variance, P99.9 may have SNR < 1 even for a substantial
  disturbance — the fault is undetectable by the chosen sensor.
- A P10 or P50 regression (meaningful to users) may go undetected entirely if the SLO
  only watches the tail.
- The threshold is calibrated to the noise floor at the chosen percentile, but that
  percentile may not be the most informative one.

## Optimal Sensing

For a given plant (service profile) and disturbance class, there exists a percentile
(or combination of percentiles) that maximizes SNR. A smarter detector would:

1. Characterize the noise floor across percentiles during burn-in
2. Select or weight percentiles by their SNR for the expected disturbance class
3. Combine evidence across percentiles rather than monitoring a single threshold

This is a research question: what is the optimal sensing strategy as a function of
plant parameters and disturbance type?

## Measurement in Scrutable

For each service in the spectrum:

1. Run burn-in (no disturbance), compute P50/P90/P99/P99.9 for each window
2. Measure noise(p) = std dev of each percentile across burn-in windows
3. Inject disturbance, measure signal(p) = shift in each percentile post-injection
4. Compute SNR(p) = signal(p) / noise(p) for each percentile

The spectrum visualization shows: as service variance increases, SNR(p) degrades across
all percentiles, but at different rates. The detector fails when SNR(P99.9) < 1, but
SNR(P50) may still be > 1 — pointing at the opportunity for smarter sensing.

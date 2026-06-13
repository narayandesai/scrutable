# Reframing Reliability as Control

*15-minute workshop talk*

---

## 1. The reframe (2 min)

- Practitioners have built a reliability toolkit — SLOs, canaries, cell drains — through operational hard knocks
- These are feedback controllers. They just aren't called that.
- The research gap: the plant family has never been formally characterized, and the controllers have never been rigorously evaluated

## 2. The plant is characterizable (3 min)

- What does a production service look like as a control plant? Outputs: latency and error rate. Disturbances: pathologies (bugs, dependency failures, hardware faults)
- Key observation: reliability is an attractor. Services get engineered toward predictability — the unreliable ones get fixed. This compresses the observable space.
- Empirical claim [cite prior talks]: lognormal latency + Weibull error rate spans the space of production-realistic behavior
- Consequence: we can simulate the universe of services people actually care about

## 3. A testbed with ground truth (2 min)

- Scrutable: discrete-event simulator, parametric workload models, fault injection with known timing and scope
- The key property: you know exactly what you injected and when — so you can measure detection latency, false positive rate, blast radius
- Reproducible across the full plant family
- [Show a single low-variance service: clean burn-in, disturbance injected, detector fires — ground truth confirmed]

<!-- deferred: spectrum sweep (5 services, low→high variance) — pull back in if time allows -->

## 4. One controller, done rigorously: SLO thresholds (5 min)

- SLO thresholds are the canonical sensor: monitor P99.9, alert when it crosses a burn-in-calibrated threshold
- The setup: same disturbance (fixed latency multiplier) applied to all five services; thresholds calibrated identically from burn-in
- [Demo: time-series visualization — show detection working cleanly on low-variance services, failing on high-variance ones. Same disturbance becomes invisible as variance grows.]
- Why does detection fail? SNR framing:
  - Signal: shift in percentile p after disturbance → signal(p) = percentile_p(post) − percentile_p(baseline)
  - Noise: natural variation in estimated percentile during burn-in → noise(p) = std dev of percentile_p across burn-in windows
  - SNR(p) = signal(p) / noise(p)
- The result: for high-variance services, SNR(P99.9) < 1 regardless of window size — the fault is physically undetectable by the chosen sensor
- The indictment of static thresholds: the sensor is fixed at P99.9 by convention, but that may not be where the signal is. For some disturbance types, SNR(P50) > SNR(P99.9) — a P50 regression is more detectable than a tail regression, and a static tail threshold misses it entirely
- Punchline: these controllers work, but nobody knows how well — and when they fail, it's not because the threshold is wrong, it's because the sensor is pointed at the wrong percentile for this service and this disturbance class

## 5. The method generalizes (3 min)

- The same framework applies to the other canonical controllers:
  - *Canary rollouts*: what is the minimum canary fraction to achieve SNR > 1 for a given fault class and plant profile? Canary fraction is a design parameter with a measurable optimum.
  - *Cell drains*: blast radius reduction is quantifiable — how much does draining a cell reduce the fraction of users affected, and at what cost to availability?
- We don't have to settle for "these work in practice." We can ask: are they close to optimal? Is there a better controller derivable from plant parameters?
- Open questions:
  - Is there a detectability bound as a function of plant parameters? (A formal SNR floor below which no threshold-based sensor can detect.)
  - Which region of plant space is hardest to control — and do real services cluster there?
  - Can we derive better controllers than the ones practitioners invented by intuition?
- *Implicit invitation*: this is a playground for control and ML researchers with real-world grounding. The simulator is open; the plant family is bounded; the ground truth is exact.

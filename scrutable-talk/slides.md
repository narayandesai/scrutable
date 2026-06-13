---
marp: true
theme: gaia
class: lead
paginate: true
backgroundColor: #fff
style: |
  section {
    font-family: 'Helvetica Neue', Arial, sans-serif;
  }
  section.lead h1 {
    font-size: 1.8em;
  }
  section h2 {
    color: #2a5db0;
    border-bottom: 2px solid #2a5db0;
    padding-bottom: 0.2em;
  }
  ul {
    font-size: 0.85em;
  }
  code {
    background: #f4f4f4;
    padding: 0.1em 0.3em;
    border-radius: 3px;
  }
---

# Reframing Reliability as Control

**Narayan Desai**

---

<!-- _class: '' -->

## The reliability toolkit

- Practitioners have built a toolkit through hard knocks: SLOs, canaries, cell drains
- These are **feedback controllers** — they just aren't called that
- The gap: the *plant family* has never been formally characterized, and the controllers have never been rigorously evaluated

---

<!-- _class: '' -->

## What does a production service look like as a plant?

- **Outputs:** latency distribution, error rate
- **Disturbances:** bugs, dependency failures, hardware faults

**Key observation:** reliability is an attractor

- Unreliable services get fixed → the observable space is compressed
- Empirical claim: lognormal latency + Weibull error rate spans production-realistic behavior
- Consequence: **we can simulate the universe of services people actually care about**

---

<!-- _class: '' -->

## Scrutable: a testbed with ground truth

- Discrete-event simulator with parametric workload models
- Fault injection with known timing and scope

**The key property:** you know exactly what you injected and when

- Measure detection latency, false positive rate, blast radius
- Reproducible across the full plant family

*Example: clean burn-in → disturbance injected → detector fires → ground truth confirmed*

---

<!-- _class: '' -->

## SLO thresholds: one controller, done rigorously

SLO thresholds are the canonical sensor: monitor P99.9, alert when it crosses a burn-in-calibrated threshold

**Setup:** same disturbance (fixed latency multiplier) applied across five services; thresholds calibrated identically from burn-in

**Result:** detection works cleanly on low-variance services, fails on high-variance ones — same disturbance becomes invisible as variance grows

---

<!-- _class: '' -->

## Why does detection fail? The SNR framing

$$\text{SNR}(p) = \frac{\text{signal}(p)}{\text{noise}(p)} = \frac{\text{percentile}_p(\text{post}) - \text{percentile}_p(\text{baseline})}{\text{std dev of } \text{percentile}_p \text{ across burn-in windows}}$$

- For high-variance services, **SNR(P99.9) < 1** regardless of window size
- The fault is physically undetectable by the chosen sensor

**The indictment of static thresholds:** for some disturbance types, SNR(P50) > SNR(P99.9) — the sensor is pointed at the wrong percentile

---

<!-- _class: '' -->

## The method generalizes

The same framework applies to the other canonical controllers:

- **Canary rollouts:** what is the minimum canary fraction for SNR > 1? Canary fraction has a measurable optimum.
- **Cell drains:** blast radius reduction is quantifiable — at what cost to availability?

We don't have to settle for "these work in practice." We can ask: **are they close to optimal?**

---

<!-- _class: '' -->

## Open questions

- Is there a **detectability bound** as a function of plant parameters?
- Which region of plant space is **hardest to control** — and do real services cluster there?
- Can we **derive** better controllers than the ones practitioners invented by intuition?

---

# Thank you

The simulator is open. The plant family is bounded. The ground truth is exact.

*A playground for control and ML researchers with real-world grounding.*

---

<!-- _class: '' -->

## Appendix: plant family coverage

| Distribution | Parameter | Range |
|---|---|---|
| Lognormal | σ (shape) | 0.1 → 2.0 |
| Weibull | k (shape) | 0.5 → 3.0 |
| Latency multiplier | fault magnitude | 1.5× → 10× |

*Five representative services span low-variance → high-variance extremes*

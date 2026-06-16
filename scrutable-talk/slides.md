---
marp: true
theme: default
paginate: true
style: |
  /* ── Base ── */
  section {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 26px;
    padding: 48px 64px 40px;
    color: #1a1a2e;
    background: #ffffff;
  }

  /* ── Title slide ── */
  section.title {
    background: linear-gradient(150deg, #0f1729 0%, #1c2f6b 55%, #0f1729 100%);
    color: #ffffff;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: flex-start;
    padding: 80px 100px;
  }
  section.title h1 {
    font-size: 1.9em;
    color: #ffffff;
    border: none;
    font-weight: 700;
    margin-bottom: 0.4em;
    line-height: 1.2;
  }
  section.title p {
    color: #8ab0d8;
    font-size: 0.85em;
    margin-top: 0.2em;
  }
  section.title::after { display: none; }

  /* ── Outro slide ── */
  section.outro {
    background: linear-gradient(150deg, #0f1729 0%, #1c2f6b 55%, #0f1729 100%);
    color: #ffffff;
    display: flex;
    flex-direction: column;
    justify-content: center;
    text-align: center;
  }
  section.outro h1 {
    font-size: 1.8em;
    color: #ffffff;
    border: none;
    margin-bottom: 0.4em;
  }
  section.outro p, section.outro em { color: #8ab0d8; font-size: 0.85em; }
  section.outro::after { display: none; }

  /* ── Content headings ── */
  h2 {
    color: #2a5db0;
    font-size: 1.05em;
    border-bottom: 3px solid #2a5db0;
    padding-bottom: 0.25em;
    margin: 0 0 0.7em;
  }

  /* ── Lists ── */
  ul {
    font-size: 0.83em;
    line-height: 1.65;
    margin: 0.3em 0;
    padding-left: 1.2em;
  }
  li { margin-bottom: 0.25em; }

  /* ── Callout boxes ── */
  .callout {
    background: #e8f0fc;
    border-left: 4px solid #2a5db0;
    padding: 0.55em 1em;
    margin: 0.7em 0;
    border-radius: 0 6px 6px 0;
    font-size: 0.82em;
    line-height: 1.5;
  }
  .warning {
    background: #fdecea;
    border-left: 4px solid #e84040;
    padding: 0.55em 1em;
    margin: 0.7em 0;
    border-radius: 0 6px 6px 0;
    font-size: 0.82em;
    line-height: 1.5;
  }

  /* ── Two-column layout ── */
  .columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 2em;
    font-size: 0.83em;
  }
  .columns h3 {
    color: #2a5db0;
    font-size: 1em;
    margin: 0 0 0.5em;
    border-bottom: 1px solid #c8d8f0;
    padding-bottom: 0.2em;
  }

  /* ── Tables ── */
  table {
    font-size: 0.76em;
    width: 100%;
    border-collapse: collapse;
    margin: 0.6em 0;
  }
  th {
    background: #2a5db0;
    color: white;
    padding: 0.4em 0.9em;
    text-align: left;
    font-weight: 600;
  }
  td {
    padding: 0.35em 0.9em;
    border-bottom: 1px solid #e0e6f0;
  }
  tr:nth-child(even) td { background: #f4f7ff; }

  /* ── Inline code ── */
  code {
    background: #f0f4ff;
    color: #2a5db0;
    padding: 0.1em 0.4em;
    border-radius: 4px;
    font-size: 0.88em;
  }

  /* ── Page number ── */
  section::after { color: #b0bcd4; font-size: 0.58em; }
---

<!-- _class: title -->

# Reframing Reliability as Control

**Narayan Desai**

---

## The reliability toolkit

- Practitioners have built a toolkit through hard knocks: SLOs, canaries, cell drains
- These are **feedback controllers** — they just aren't called that
- The gap: the *plant family* has never been formally characterized, and the controllers have never been rigorously evaluated

---

## What does a production service look like as a plant?

<div class="columns">
<div>

### Outputs & disturbances

- **Outputs:** latency distribution, error rate
- **Disturbances:** bugs, dependency failures, hardware faults

</div>
<div>

### Key observation

**Reliability is an attractor.** Unreliable services get fixed → the observable space is compressed.

- Empirical claim: lognormal latency + Weibull error rate spans production-realistic behavior
- Consequence: **we can simulate the universe of services people actually care about**

</div>
</div>

---

## Scrutable: a testbed with ground truth

- Discrete-event simulator with parametric workload models
- Fault injection with known timing and scope

<div class="callout">

**The key property:** you know exactly what you injected and when — so you can measure detection latency, false positive rate, and blast radius reproducibly across the full plant family.

</div>

*Example: clean burn-in → disturbance injected → detector fires → ground truth confirmed*

---

## SLO thresholds: one controller, done rigorously

SLO thresholds are the canonical sensor: monitor P99.9, alert when it crosses a burn-in-calibrated threshold

<div class="callout">

**Setup:** same disturbance (fixed latency multiplier) applied across five services; thresholds calibrated identically from burn-in

</div>

<div class="warning">

**Result:** detection works cleanly on low-variance services, fails on high-variance ones — same disturbance becomes invisible as variance grows

</div>

---

## Why does detection fail? The SNR framing

$$\text{SNR}(p) = \frac{\text{signal}(p)}{\text{noise}(p)} = \frac{\text{percentile}_p(\text{post}) - \text{percentile}_p(\text{baseline})}{\text{std dev of } \text{percentile}_p \text{ across burn-in windows}}$$

- For high-variance services, **SNR(P99.9) < 1** regardless of window size
- The fault is physically undetectable by the chosen sensor

<div class="warning">

**The indictment of static thresholds:** for some disturbance types, SNR(P50) > SNR(P99.9) — the sensor is pointed at the wrong percentile

</div>

---

## P99.9 noise floor is window-size invariant for high-variance services

<div style="font-size:0.78em;font-family:'Helvetica Neue',Arial,sans-serif;max-width:680px;margin:0.3em auto">
  <div style="display:flex;gap:1.5em;margin-bottom:0.5em;padding-left:3em">
    <span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:12px;height:12px;background:#2a5db0;border-radius:2px;flex-shrink:0"></span>spherical_cow</span>
    <span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:12px;height:12px;background:#e84040;border-radius:2px;flex-shrink:0"></span>long_tail</span>
    <span style="margin-left:auto;font-weight:bold;color:#e84040">SNR(P99.9)</span>
  </div>
  <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
    <span style="width:2.5em;text-align:right;font-weight:bold;color:#1a1a2e;flex-shrink:0">1s</span>
    <div style="flex:1">
      <div style="height:14px;display:flex;align-items:center;margin-bottom:2px"><div style="min-width:3px;width:0.17%;height:100%;background:#2a5db0;border-radius:1px"></div><span style="color:#2a5db0;margin-left:4px">0.006s</span></div>
      <div style="height:20px"><div style="width:98.6%;height:100%;background:#e84040;border-radius:2px;display:flex;align-items:center;padding-left:8px;box-sizing:border-box"><span style="color:white;font-weight:bold">3.46s</span></div></div>
    </div>
    <span style="color:#e84040;font-weight:bold;width:3em;text-align:right;flex-shrink:0">0.48</span>
  </div>
  <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
    <span style="width:2.5em;text-align:right;font-weight:bold;color:#1a1a2e;flex-shrink:0">5s</span>
    <div style="flex:1">
      <div style="height:14px;display:flex;align-items:center;margin-bottom:2px"><div style="min-width:4px;width:0.29%;height:100%;background:#2a5db0;border-radius:1px"></div><span style="color:#2a5db0;margin-left:4px">0.010s</span></div>
      <div style="height:20px"><div style="width:98.6%;height:100%;background:#e84040;border-radius:2px;display:flex;align-items:center;padding-left:8px;box-sizing:border-box"><span style="color:white;font-weight:bold">3.46s</span></div></div>
    </div>
    <span style="color:#e84040;font-weight:bold;width:3em;text-align:right;flex-shrink:0">0.48</span>
  </div>
  <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
    <span style="width:2.5em;text-align:right;font-weight:bold;color:#1a1a2e;flex-shrink:0">30s</span>
    <div style="flex:1">
      <div style="height:14px;display:flex;align-items:center;margin-bottom:2px"><div style="min-width:6px;width:0.57%;height:100%;background:#2a5db0;border-radius:1px"></div><span style="color:#2a5db0;margin-left:4px">0.020s</span></div>
      <div style="height:20px"><div style="width:100%;height:100%;background:#e84040;border-radius:2px;display:flex;align-items:center;padding-left:8px;box-sizing:border-box"><span style="color:white;font-weight:bold">3.51s</span></div></div>
    </div>
    <span style="color:#e84040;font-weight:bold;width:3em;text-align:right;flex-shrink:0">0.48</span>
  </div>
  <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
    <span style="width:2.5em;text-align:right;font-weight:bold;color:#1a1a2e;flex-shrink:0">60s</span>
    <div style="flex:1">
      <div style="height:14px;display:flex;align-items:center;margin-bottom:2px"><div style="min-width:7px;width:0.77%;height:100%;background:#2a5db0;border-radius:1px"></div><span style="color:#2a5db0;margin-left:4px">0.027s</span></div>
      <div style="height:20px"><div style="width:100%;height:100%;background:#e84040;border-radius:2px;display:flex;align-items:center;padding-left:8px;box-sizing:border-box"><span style="color:white;font-weight:bold">3.53s</span></div></div>
    </div>
    <span style="color:#e84040;font-weight:bold;width:3em;text-align:right;flex-shrink:0">0.48</span>
  </div>
  <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
    <span style="width:2.5em;text-align:right;font-weight:bold;color:#1a1a2e;flex-shrink:0">2m</span>
    <div style="flex:1">
      <div style="height:14px;display:flex;align-items:center;margin-bottom:2px"><div style="min-width:9px;width:1.00%;height:100%;background:#2a5db0;border-radius:1px"></div><span style="color:#2a5db0;margin-left:4px">0.035s</span></div>
      <div style="height:20px"><div style="width:98.0%;height:100%;background:#e84040;border-radius:2px;display:flex;align-items:center;padding-left:8px;box-sizing:border-box"><span style="color:white;font-weight:bold">3.43s</span></div></div>
    </div>
    <span style="color:#e84040;font-weight:bold;width:3em;text-align:right;flex-shrink:0">0.45</span>
  </div>
  <div style="display:flex;align-items:center;gap:6px">
    <span style="width:2.5em;flex-shrink:0"></span>
    <div style="flex:1;position:relative;height:16px">
      <div style="position:absolute;top:0;left:0;right:0;height:1px;background:#ddd"></div>
      <span style="position:absolute;left:0;transform:translateX(-50%);color:#999;font-size:0.9em">0</span>
      <span style="position:absolute;left:28.4%;transform:translateX(-50%);color:#999;font-size:0.9em">1s</span>
      <span style="position:absolute;left:56.8%;transform:translateX(-50%);color:#999;font-size:0.9em">2s</span>
      <span style="position:absolute;left:85.3%;transform:translateX(-50%);color:#999;font-size:0.9em">3s</span>
      <span style="position:absolute;right:0;color:#999;font-size:0.9em">3.5s</span>
    </div>
    <span style="width:3em;flex-shrink:0"></span>
  </div>
</div>

<div class="callout" style="font-size:0.78em;margin-top:0.4em">

The long\_tail noise floor sits at ~3.5s <strong>regardless of window size</strong> — confirmed across 1s through 2m. Mix-shift dominated: SC noise grows slowly with window size; LT noise doesn't move.

</div>

---

## The method generalizes

The same framework applies to the other canonical controllers:

- **Canary rollouts:** what is the minimum canary fraction for SNR > 1? Canary fraction has a measurable optimum.
- **Cell drains:** blast radius reduction is quantifiable — at what cost to availability?

<div class="callout">

We don't have to settle for "these work in practice." We can ask: **are they close to optimal?** Is there a better controller derivable from plant parameters?

</div>

---

## Open questions

- Is there a **detectability bound** as a function of plant parameters?
- Which region of plant space is **hardest to control** — and do real services cluster there?
- Can we **derive** better controllers than the ones practitioners invented by intuition?

---

<!-- _class: outro -->

# Thank you

The simulator is open. The plant family is bounded. The ground truth is exact.

*A playground for control and ML researchers with real-world grounding.*

---

## Appendix: plant family coverage

| Distribution | Parameter | Range |
|---|---|---|
| Lognormal | σ (shape) | 0.1 → 2.0 |
| Weibull | k (shape) | 0.5 → 3.0 |
| Latency multiplier | fault magnitude | 1.5× → 10× |

*Five representative services span low-variance → high-variance extremes*

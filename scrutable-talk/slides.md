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

<svg viewBox="0 0 680 210" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:680px;display:block;margin:0.3em auto 0">
  <defs><style>
    .wl  { font: bold 14px 'Helvetica Neue',sans-serif; fill: #1a1a2e; }
    .scv { font: 11px 'Helvetica Neue',sans-serif; fill: #2a5db0; }
    .ltv { font: bold 11px 'Helvetica Neue',sans-serif; fill: #fff; }
    .snr { font: bold 13px 'Helvetica Neue',sans-serif; fill: #e84040; }
    .ax  { font: 11px 'Helvetica Neue',sans-serif; fill: #999; }
    .leg { font: 12px 'Helvetica Neue',sans-serif; fill: #444; }
  </style></defs>

  <!-- Legend -->
  <rect x="150" y="2"  width="12" height="12" fill="#2a5db0" rx="2"/>
  <text x="166" y="13" class="leg">spherical_cow</text>
  <rect x="295" y="2"  width="12" height="12" fill="#e84040" rx="2"/>
  <text x="311" y="13" class="leg">long_tail</text>
  <text x="510" y="13" class="leg" font-weight="bold" fill="#e84040">SNR(P99.9)</text>

  <!-- Bar area: x=68 to x=638 = 570px; max=3.51s → 162.4px/s -->

  <!-- 1s -->
  <text x="62" y="50"  text-anchor="end" class="wl">1s</text>
  <rect x="68" y="30"  width="3"   height="16" fill="#2a5db0" rx="1"/>
  <text x="73" y="42"  class="scv">0.006s</text>
  <rect x="68" y="50"  width="562" height="22" fill="#e84040" rx="2"/>
  <text x="78" y="66"  class="ltv">3.46s</text>
  <text x="638" y="66" text-anchor="end" class="snr">0.48</text>

  <!-- 5s -->
  <text x="62" y="110" text-anchor="end" class="wl">5s</text>
  <rect x="68" y="90"  width="4"   height="16" fill="#2a5db0" rx="1"/>
  <text x="74" y="102" class="scv">0.010s</text>
  <rect x="68" y="110" width="562" height="22" fill="#e84040" rx="2"/>
  <text x="78" y="126" class="ltv">3.46s</text>
  <text x="638" y="126" text-anchor="end" class="snr">0.48</text>

  <!-- 30s -->
  <text x="62" y="170" text-anchor="end" class="wl">30s</text>
  <rect x="68" y="150" width="6"   height="16" fill="#2a5db0" rx="1"/>
  <text x="76" y="162" class="scv">0.020s</text>
  <rect x="68" y="170" width="570" height="22" fill="#e84040" rx="2"/>
  <text x="78" y="186" class="ltv">3.51s</text>
  <text x="638" y="186" text-anchor="end" class="snr">0.48</text>

  <!-- Axis -->
  <line x1="68" y1="200" x2="638" y2="200" stroke="#ddd" stroke-width="1"/>
  <text x="68"  y="210" text-anchor="middle" class="ax">0</text>
  <text x="230" y="210" text-anchor="middle" class="ax">1s</text>
  <text x="392" y="210" text-anchor="middle" class="ax">2s</text>
  <text x="554" y="210" text-anchor="middle" class="ax">3s</text>
  <text x="638" y="210" text-anchor="middle" class="ax">3.5s</text>
</svg>

<div class="callout" style="font-size:0.78em;margin-top:0.4em">

The long\_tail noise floor sits at ~3.5s <strong>regardless of window size</strong> — mix-shift dominated. Wider windows only grow SC noise. For the same disturbance, SNR(P50) ≈ 300–400 on long\_tail at every window size.

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

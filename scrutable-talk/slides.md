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
**Distinguished Engineer, Switch Inc.**

---

## The pragmatic reliability toolkit

- Practitioners have built a toolkit through hard knocks: SLOs, canaries
- These practices are very artisinal; every service uses tuned methods to sense
- Limited rigor, generally very noisy/effort intensive
- Key problem: every unhappy service is different

---

## What if we could formalize as control theory?

- Monitoring metrics are **sensors**, mitigations are **feedback controllers**
- The gap: the *space of production services* has never been formally characterized or rigorously evaluated
- Missing a *realistic* model/simulator of production services. 

---

## Prior art: reliability analytics

- Build granular per-workload parametric log-normal models from historical data
- Validate using KS statistic against per-workload empirical distribution 
- Performance events can be transformed into quantiles (controlling for workload differences)
- This approach has been used to reliably model hundreds of services in production at >500M qps with good accuracy, low noise floor

---

## Scrutable: a simulator with accurate noisy behavior

- Key idea: use these parametric models to build a discrete event simulator that produces realistic performance data
- Discrete-event simulator with parametric workload models
- Fault injection with known timing and scope gives us ground truth, and allows us to assess effectivess of sensors and feedback controllers
- Investment in reliability is an attractor in the space; this results in consistency of performance and failure rates

<div class="callout">

**The key property:** you know exactly what you injected and when — so you can measure detection latency, false positive rate, SNR in a realistic environment.

</div>

*Example: clean burn-in → disturbance injected → detector fires → ground truth confirmed*

---

## SLO detection — scenario design

<div class="columns">
<div>

### Calibration phase
- Service runs clean for N windows
- P99.9 sampled per window (configurable: 1 s–2 min)
- Threshold set to hit target FPR (e.g. 0.1 % per window)

### Evaluation phase
- **Same plant**, disturbance injected at a known time
- Disturbance: latency multiplier applied to all nodes
- Sensor fires when P99.9 exceeds calibrated threshold

</div>
<div>

### What we measure

| Metric | How |
|---|---|
| Detection latency | Time from injection to first alarm |
| False positive rate | Alarm frequency on clean traffic |
| SNR | Signal / noise at each percentile |

**Ground truth is known:** injection time, scope, and magnitude are precisely known — we can evaluate outcomes!

</div>
</div>

---

## SLOs

SLO thresholds are the canonical practicioner sensor: monitor P99.9, alert when it crosses a calibrated threshold

<div class="callout">

**Setup:** same disturbance (fixed latency multiplier) applied across five services; thresholds calibrated identically from burn-in

</div>

<div class="warning">

**Result:** detection works cleanly on low-variance services, fails on high-variance ones — same disturbance becomes invisible as natural workload variance grows

</div>

---

## Evaluating SLOs using SNR

$$\text{SNR}(p) = \frac{\text{signal}(p)}{\text{noise}(p)} = \frac{\text{percentile}_p(\text{post}) - \text{percentile}_p(\text{baseline})}{\text{std dev of } \text{percentile}_p \text{ across burn-in windows}}$$

- For high-variance services, **SNR(P99.9) < 1** regardless of window size
- The fault is physically undetectable by the chosen sensor

<div class="warning">

**The indictment of static thresholds:** for some disturbance types, SNR(P50) > SNR(P99.9) — the sensor is pointed at the wrong percentile

</div>

---

## Practioners think long windows will save us from SLO noise

<div style="font-size:0.72em;font-family:'Helvetica Neue',Arial,sans-serif;margin-top:0.3em">
<div style="display:grid;grid-template-columns:1fr 1fr;gap:2em">

<div>
<div style="font-weight:bold;margin-bottom:4px;color:#1a1a2e">SNR(P99.9) — detectable when &gt; 1</div>
<div style="position:relative;height:170px;padding-top:20px;box-sizing:border-box;display:flex;align-items:flex-end;gap:5px;border-bottom:1px solid #ccc;overflow:visible">
  <div style="position:absolute;left:0;right:0;bottom:calc(1.82% + 1px);border-top:1.5px dashed #e84040;z-index:1"></div>
  <!-- <span style="position:absolute;right:2px;bottom:calc(1.82% + 3px);color:#e84040;font-weight:bold;font-size:0.9em">SNR=1</span> -->
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:92.7%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">51</span></div>
    <div style="flex:1;height:2px;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#e84040">.48</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:54.5%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">30</span></div>
    <div style="flex:1;height:2px;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#e84040">.48</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:26.4%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">14</span></div>
    <div style="flex:1;height:2px;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#e84040">.48</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:18.9%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">10</span></div>
    <div style="flex:1;height:2px;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#e84040">.48</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:13.8%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">7.6</span></div>
    <div style="flex:1;height:2px;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#e84040">.45</span></div>
  </div>
</div>
<div style="display:flex;gap:5px;padding-top:3px;color:#888">
  <div style="flex:1;text-align:center">1s</div><div style="flex:1;text-align:center">5s</div><div style="flex:1;text-align:center">30s</div><div style="flex:1;text-align:center">60s</div><div style="flex:1;text-align:center">2m</div>
</div>
</div>

<div>
<div style="font-weight:bold;margin-bottom:4px;color:#1a1a2e">False positive rate — alarm without fault</div>
<div style="position:relative;height:170px;padding-top:20px;box-sizing:border-box;display:flex;align-items:flex-end;gap:5px;border-bottom:1px solid #ccc;overflow:visible">
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:5%;background:#2a5db0;border-radius:2px 2px 0 0;min-height:2px;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#2a5db0">5%</span></div>
    <div style="flex:1;height:91.2%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#e84040;font-weight:bold">91%</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:1.25%;background:#2a5db0;border-radius:2px 2px 0 0;min-height:2px;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#2a5db0">1%</span></div>
    <div style="flex:1;height:93.1%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#e84040;font-weight:bold">93%</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:5%;background:#2a5db0;border-radius:2px 2px 0 0;min-height:2px;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#2a5db0">5%</span></div>
    <div style="flex:1;height:75.8%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#e84040;font-weight:bold">76%</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:3.3%;background:#2a5db0;border-radius:2px 2px 0 0;min-height:2px;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#2a5db0">3%</span></div>
    <div style="flex:1;height:51.7%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#e84040;font-weight:bold">52%</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:3.3%;background:#2a5db0;border-radius:2px 2px 0 0;min-height:2px;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#2a5db0">3%</span></div>
    <div style="flex:1;height:3.3%;background:#e84040;opacity:0.3;border-radius:2px 2px 0 0;min-height:2px;position:relative"><span style="position:absolute;bottom:calc(100% + 1px);left:0;right:0;text-align:center;color:#aaa">3%†</span></div>
  </div>
</div>
<div style="display:flex;gap:5px;padding-top:3px;color:#888">
  <div style="flex:1;text-align:center">1s</div><div style="flex:1;text-align:center">5s</div><div style="flex:1;text-align:center">30s</div><div style="flex:1;text-align:center">60s</div><div style="flex:1;text-align:center">2m</div>
</div>
</div>

</div>
<div style="display:flex;gap:1.5em;margin-top:0.4em;align-items:center">
  <span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:10px;height:10px;background:#2a5db0;border-radius:2px"></span> spherical_cow</span>
  <span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:10px;height:10px;background:#e84040;border-radius:2px"></span> long_tail</span>
  <span style="color:#aaa;margin-left:auto">† 2m degenerate: calibration = evaluation set</span>
</div>
</div>

<div class="callout" style="font-size:0.78em;margin-top:0.4em">

SC detects perfectly at every window size (SNR 7–51, all above the line). LT SNR stays at **0.48** — noise exceeds signal regardless of window. FPR: 51–93% on clean traffic through 60s windows. Wider windows don't fix either problem.

</div>

---

## Canary rollout — how the controller works

Changes arrive as a Poisson process; each independently carries a bug with probability *p*.

<div class="columns">
<div>

### Rollout sequence
1. **Bundle** N changes into a release
2. **Deploy to canary** (20 % of nodes) — bake for T s under the SLO sensor
3. **Gate:** any SLO alarm since canary deploy?
   - No alarm → promote to **prod**
   - Alarm → **rollback** (completes in ~1 h)
4. **Remediation cycle:** debug phase (lognormal, median 6 h) → re-deploy fixed release

</div>
<div>

### Actuation outcomes

| Outcome | Label | Meaning |
|---|---|---|
| Buggy release rolled back | TP | Canary caught the fault |
| Bug promoted to prod | FN | Escaped detection |
| Clean release rolled back | FP | Noise triggered alarm |

**Canary fraction governs SNR.** Too small → bug signal below the noise floor → FN rate rises. The SNR framework gives a principled minimum fraction.

</div>
</div>

---

## Canary detection: service variance is a decisive factor

*150 changes/week, 1 % bug rate, 2-day bake, P99.9 SLO, 5-min window — varied at 100 %/150 %/200 % velocity*

<div style="font-size:0.72em;font-family:'Helvetica Neue',Arial,sans-serif;margin-top:0.5em">
<div style="display:grid;grid-template-columns:1fr 1fr;gap:2em">

<div>
<div style="font-weight:bold;margin-bottom:4px;color:#1a1a2e">Bug catch rate (higher = better)</div>
<div style="position:relative;height:155px;padding-top:20px;box-sizing:border-box;display:flex;align-items:flex-end;gap:8px;border-bottom:1px solid #ccc">
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:100%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">100%</span></div>
    <div style="flex:1;min-height:2px;height:0.5%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#e84040">0%</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:100%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">100%</span></div>
    <div style="flex:1;height:20%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#e84040">20%</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:100%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">100%</span></div>
    <div style="flex:1;min-height:2px;height:0.5%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#e84040">0%</span></div>
  </div>
</div>
<div style="display:flex;gap:8px;padding-top:3px;color:#888">
  <div style="flex:1;text-align:center">100%</div><div style="flex:1;text-align:center">150%</div><div style="flex:1;text-align:center">200%</div>
</div>
</div>

<div>
<div style="font-weight:bold;margin-bottom:4px;color:#1a1a2e">Change lead time P50 (lower = better)</div>
<div style="position:relative;height:155px;padding-top:20px;box-sizing:border-box;display:flex;align-items:flex-end;gap:8px;border-bottom:1px solid #ccc">
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:56%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">154h</span></div>
    <div style="flex:1;height:48%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#e84040">133h</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:52%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">143h</span></div>
    <div style="flex:1;height:52%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#e84040">143h</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:58%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">159h</span></div>
    <div style="flex:1;height:47%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#e84040">131h</span></div>
  </div>
</div>
<div style="display:flex;gap:8px;padding-top:3px;color:#888">
  <div style="flex:1;text-align:center">100%</div><div style="flex:1;text-align:center">150%</div><div style="flex:1;text-align:center">200%</div>
</div>
<div style="color:#888;font-size:0.88em;margin-top:2px">normalized to 275h max</div>
</div>

</div>
<div style="display:flex;gap:1.5em;margin-top:0.5em;align-items:center">
  <span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:10px;height:10px;background:#2a5db0;border-radius:2px"></span> spherical_cow (P99.9 threshold 0.30 s)</span>
  <span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:10px;height:10px;background:#e84040;border-radius:2px"></span> long_tail (P99.9 threshold 37 062 s)</span>
</div>
</div>

<div class="callout" style="font-size:0.78em;margin-top:0.4em">

SC catches **100 % of bugs** at all velocities. LT catches **~0 %** — the 0.3 s disturbance is invisible against a 37 000 s noise floor. The velocity cost of effective detection is modest: P50 lead times are within 10–25 h across all scales (~10–15 %).

</div>

---

## Canary rollout — P95 lead time and throughput

*Same simulation — tail latency and change throughput across scales*

<div style="font-size:0.72em;font-family:'Helvetica Neue',Arial,sans-serif;margin-top:0.5em">
<div style="display:grid;grid-template-columns:1fr 1fr;gap:2em">

<div>
<div style="font-weight:bold;margin-bottom:4px;color:#1a1a2e">Lead time P95 — tail cost of rollback+debug cycles</div>
<div style="position:relative;height:155px;padding-top:20px;box-sizing:border-box;display:flex;align-items:flex-end;gap:8px;border-bottom:1px solid #ccc">
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:100%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">273h</span></div>
    <div style="flex:1;height:78%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#e84040">213h</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:82%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">225h</span></div>
    <div style="flex:1;height:82%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#e84040">224h</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:90%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">245h</span></div>
    <div style="flex:1;height:77%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#e84040">209h</span></div>
  </div>
</div>
<div style="display:flex;gap:8px;padding-top:3px;color:#888">
  <div style="flex:1;text-align:center">100%</div><div style="flex:1;text-align:center">150%</div><div style="flex:1;text-align:center">200%</div>
</div>
</div>

<div>
<div style="font-weight:bold;margin-bottom:4px;color:#1a1a2e">Changes shipped per week</div>
<div style="position:relative;height:155px;padding-top:20px;box-sizing:border-box;display:flex;align-items:flex-end;gap:8px;border-bottom:1px solid #ccc">
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:50%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">125</span></div>
    <div style="flex:1;height:50%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#e84040">125</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:75%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">188</span></div>
    <div style="flex:1;height:75%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#e84040">188</span></div>
  </div>
  <div style="flex:1;display:flex;gap:2px;align-items:flex-end;height:100%">
    <div style="flex:1;height:100%;background:#2a5db0;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#2a5db0;font-weight:bold">250</span></div>
    <div style="flex:1;height:100%;background:#e84040;border-radius:2px 2px 0 0;position:relative"><span style="position:absolute;bottom:calc(100%+1px);left:0;right:0;text-align:center;color:#e84040">250</span></div>
  </div>
</div>
<div style="display:flex;gap:8px;padding-top:3px;color:#888">
  <div style="flex:1;text-align:center">100%</div><div style="flex:1;text-align:center">150%</div><div style="flex:1;text-align:center">200%</div>
</div>
</div>

</div>
<div style="display:flex;gap:1.5em;margin-top:0.5em;align-items:center">
  <span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:10px;height:10px;background:#2a5db0;border-radius:2px"></span> spherical_cow</span>
  <span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:10px;height:10px;background:#e84040;border-radius:2px"></span> long_tail</span>
</div>
</div>

<div class="callout" style="font-size:0.78em;margin-top:0.4em">

P95 overhead of effective detection: **+30–60 h** (rollback ~1 h + debug median 6 h, compounded at tail). Throughput is equal when the pipeline isn't stalled — the cost is latency, not volume.

</div>

---

## The method generalizes

The same framework applies to the other canonical controllers:

- **SLO thresholds:** optimal percentile and window size are derivable from plant parameters, not trial and error
- **Canary rollouts:** minimum canary fraction for SNR > 1 is computable; cadence vs. batch-size trade-offs are quantifiable

<div class="callout">

We don't have to settle for "these work in practice." We can ask: **are they close to optimal?** Is there a better controller derivable from plant parameters?

</div>

---

## Open questions

- Is there a **detectability bound** as a function of service workload parameters? (almost certainly yes)
- What is the distribution of actual production services across the space?
- Are there other dimensions that should be added to this model?
- Which region of service space is **hardest to control** — and do real services cluster there?
- Can we **derive** better controllers than the ones practitioners invented by intuition?

---

<!-- _class: outro -->

# Questions?


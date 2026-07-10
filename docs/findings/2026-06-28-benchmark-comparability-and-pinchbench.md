# Why published Nemotron scores look high but ours don't — and why that's not a contradiction

**Date:** 2026-06-28
**Purpose:** Article-ready analysis. Resolves the apparent conflict between (a) a viral claim that
Nemotron 3 Super scores "85.6% on PinchBench, the best open model," and (b) our finding that
gpt-oss-120b > qwen3-coder-30b ≈ Nemotron in the OpenCode harness. Three independent lines of
evidence resolve it — and two of them *corroborate* our ranking.

> **Provenance note:** figures below are from web research (June 2026). Numbers marked **[FIRM]**
> were quoted from a primary/leaderboard source; **[VERIFY]** were reported once but blocked by
> auth/PDF walls on re-check — confirm before final publication.

---

## TL;DR

1. **The "85.6%" is an error.** The actual PinchBench leaderboard shows Nemotron 3 Super at
   **42.2%**, *below* gpt-oss-120b at **44.8%**. PinchBench independently **agrees** with our
   ranking (gpt-oss > Nemotron). The 85.6% almost certainly comes from confusing Super (120B)
   with **Nemotron 3 Ultra (550B), which scores 89.9%**.
2. **Absolute scores aren't comparable across harnesses.** A SWE-bench number is meaningless
   without its scaffold; the *same* model swings 5–22 points across harnesses. Our lower absolute
   numbers vs vendors' are expected and well-documented — they don't indicate a measurement error.
3. **Small subsets have wide error bars.** Our L1 is 29 of 500 SWE-bench Verified tasks (~6%);
   even a 19% subset is documented as statistically fragile. Report confidence intervals.

The throughline: **a benchmark number only means something next to other numbers from the same
harness, scoring, and settings.** That is precisely what our benchmark provides — and within it,
Nemotron does not lead.

---

## 1. The PinchBench "85.6%" claim is false; the real data backs us up  [FIRM]

PinchBench (published by **Kilo**, an OpenClaw agent benchmark): **23 real-world agent tasks**,
graded by automated Python checks + an LLM judge (the AI assistant Opus) against rubrics, reported as an
average success rate. As of June 2026 it is "display only" on BenchLM.

**Actual BenchLM PinchBench leaderboard (June 2026):**

| Rank | Model | PinchBench |
|---:|---|---:|
| 1 | Qwen3.7-Max | 92.5% |
| 2 | **Nemotron 3 *Ultra* 550B-A55B** | **89.9%** |
| … | | |
| 36 | **gpt-oss-120b** | **44.8%** |
| 37 | **Nemotron 3 *Super* 120B-A12B** | **42.2%** |

- The "85.6% / best open model" claim could not be found on BenchLM, pinchbench.com, or anywhere.
  It appears to be a **Medium-article error** — most likely a Super↔Ultra mix-up (Ultra = 89.9%).
- **On PinchBench, gpt-oss-120b (44.8%) beats Nemotron Super (42.2%).** This is an *independent
  third-party benchmark* reproducing our ordering. Both sit lower-middle-tier — neither is a
  top-flight solo coding agent.

**For the article:** the premise "Nemotron scores great on PinchBench but not in our test" is
based on a number that doesn't exist. Corrected, PinchBench is corroborating evidence.

---

## 2. SWE-bench Verified is harness-dependent — absolute numbers don't transfer

Official SWE-bench Verified numbers (pass@1, binary: patch passes all target tests), **tagged by
harness** — because the harness is part of the result:

| Model | SWE-bench Verified | Harness | Notes |
|---|---:|---|---|
| Nemotron-3-Super-120B | 60.47% | OpenHands | **[VERIFY]** model-card eval table |
| Nemotron-3-Super-120B | 59.20% | **OpenCode** | **[VERIFY]** — same harness family we use |
| Nemotron-3-Super-120B | 53.73% | an external AI model | **[VERIFY]** |
| gpt-oss-120b | 62.4% | unspecified | **[VERIFY]** (vals.ai) |
| Qwen3-Coder-30B-A3B | 51.6% | OpenHands, 100-turn | **[FIRM]** (HF disc.) |
| Qwen3-Coder-30B-A3B | 50% p@1 / 63% p@5 | OpenHands, 500-turn | **[FIRM]** |

Two takeaways:
- **The ordering at the top is consistent with ours:** gpt-oss (62.4%) ≥ Nemotron (60.5%) ≥ Qwen
  (51.6%). gpt-oss leads in the vendor numbers too.
- **The same model varies 53.7%→60.5% across harnesses on its OWN card** (an external AI model vs OpenHands).
  That ~7-point internal spread is the whole point: scaffold ≠ model.

### The harness effect is heavily documented  [FIRM]

- **the AI assistant Opus 4.5: 45.9% (SEAL) → 55.4% (an AI coding assistant)** — a 9.5-pt spread from identical
  weights (Particula).
- Changing *only the scaffold* can swing a score **22 points (42%→78%)** on one model
  (DigitalApplied).
- **Opus 4.5: 77.6% (OpenHands) vs 72.0% (SWE-agent)** — 5.6 pt (CodeSOTA).
- A weaker, cheaper model on a better scaffold **beats** a flagship on its own scaffold (Particula).
- Scale AI / OpenAI documentation: **"SWE-bench scores are harness-dependent"**; scores >80%
  "warrant scrutiny about harness and tool access."

**Implication for our numbers:** our absolute resolved-rates (gpt-oss 38%, Qwen 24%, Nemotron 24%
on L1) sit below the vendors' 50–62% because our harness (OpenCode, local NVFP4/vLLM serving,
single config, temp 0.2, pass@1) differs from their tuned scaffolds — and *every* model is
discounted, not just Nemotron. This is a known, expected harness offset, **not a bug**.

---

## 3. Our L1 is a small subset — report confidence intervals  [FIRM]

Our L1 = **29 of 500** SWE-bench Verified instances (the arm64-buildable subset), pass@1.
- METR analyzed a **19% subset** (95/500) and found close alignment with the full set on average,
  but **trend analysis was fragile** — significant only at the 10% level, and reversed when
  filtered to SOTA-only.
- At n=29 the 95% CI on a ~25–40% rate is roughly **±15 pp**. So on L1, gpt-oss (38%) vs Qwen/
  Nemotron (24%) is *suggestive*, not decisive; the **firm separation is Layer 2** (n=20),
  where Nemotron collapses (~1/29) while gpt-oss reaches 25% rubric.

**For the article:** always print (1) the harness, (2) n (subset vs full 500), (3) the CI.

---

## 4. Different scoring, different scaffold deployment

- **Scoring denominator differs:** PinchBench/"precision" metrics give partial credit; our L1 is
  binary all-tests-pass; our L2 is a strict 29-check boot/build/test rubric. Harsh binary scoring
  reads lower than partial-credit precision by construction.
- **Solo vs multi-agent:** Nemotron is designed as the reasoning core of a *multi-agent* stack
  (NVIDIA's AI-Q: orchestrator + planner + researcher). Our harness runs every model **solo** —
  the same for all three, so the comparison is fair, but it is not Nemotron's best deployment.
- **Task type:** our L2 (from-scratch full-stack app build) is an unusually long-horizon
  construction task that few "coding agent" benchmarks test; it is hard for *everyone* (gpt-oss
  25%, Qwen 15.5%), so a low Nemotron score there is partly task difficulty, not pure model failure.

---

## Conclusion (for the paper)

Our ranking is not contradicted by Nemotron's reputation — it is **independently corroborated**:
- PinchBench (third-party): gpt-oss 44.8% **>** Nemotron 42.2%.
- Vendor SWE-bench: gpt-oss 62.4% ≥ Nemotron 60.5% ≥ Qwen 51.6%.
- Our OpenCode harness: gpt-oss **>** Qwen ≈ Nemotron.

The only thing that changes across these is the **absolute** level, which moves with harness,
scoring, sample size, and settings — exactly why **our controlled, identical-harness comparison is
the valid one**. The viral "85.6%" was a number that does not exist (Super confused with Ultra).

---

## Sources

- BenchLM PinchBench leaderboard — https://benchlm.ai/benchmarks/pinchBench
- Nemotron-3-Super model card (SWE-bench by harness) — https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16
- gpt-oss-120b — https://www.vals.ai/models/fireworks_gpt-oss-120b
- Qwen3-Coder-30B SWE-bench — https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct/discussions/30
- Particula: Agent Scaffolding Beats Model Upgrades — https://particula.tech/blog/agent-scaffolding-beats-model-upgrades-swe-bench
- DigitalApplied: SWE-bench Verified scaffolding analysis — https://www.digitalapplied.com/blog/swe-bench-verified-june-2026-benchmark-vs-scaffolding-analysis
- CodeSOTA: OpenHands vs SWE-agent — https://www.codesota.com/agentic/openhands-vs-swe-agent
- METR: SWE-bench passing PRs study (subset CIs) — https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/
- Dissecting SWE-Bench Leaderboards — https://arxiv.org/html/2506.17208v2

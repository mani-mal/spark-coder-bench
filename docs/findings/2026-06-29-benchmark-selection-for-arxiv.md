# Benchmark selection for the arXiv paper — scope decision

**Date:** 2026-06-29
**Status:** Decision note. Reviewed against our actual harness (L1 = SWE-bench Verified arm64
subset; L2 = from-scratch full-stack app build) and a verification sweep of five candidate
benchmarks (Terminal-Bench 2, SWE-bench Pro, SWE Atlas, LiveCodeBench, + SWE-bench Verified).

## Question

We use **SWE-bench Verified** (L1) and a **custom from-scratch app build** (L2). Are those the
right and complete set of benchmarks to publish, or should we add Terminal-Bench 2 (tb2),
SWE-bench Pro, SWE Atlas, or LiveCodeBench?

## Framing first (this drives every call below)

Two facts constrain the answer more than the benchmark menu does:

1. **The paper's contribution is DGX Spark serving/efficiency + methodology, not a leaderboard.**
   The deliverables are: local serving feasibility on GB10/SM121, efficiency (energy/token, decode
   tok/s, peak unified memory), and methodological results (the autonomous-tool-use gate; harness-
   dependence of SWE-bench scores; agentic ≠ code-gen). The benchmark is the *vehicle*. Adding
   benchmark names does not, by itself, strengthen the contribution.
2. **arm64 local-runnability is the binding constraint, and efficiency metrics die under emulation.**
   We already pay for this: only **29/500** SWE-bench Verified images build natively on aarch64;
   SWE-bench's own arm64 support is officially "experimental / best-effort / untested." Any
   benchmark that needs x86 Docker images runs under QEMU (~observed 6× slowdown elsewhere), which
   **invalidates our throughput/energy numbers** — the core contribution. So a benchmark is only
   additive here if it runs **natively on arm64** *or* we accept quality-only (no efficiency) data
   from it and disclose the emulation.

Also: the two bigger credibility risks for this paper are **n=29 wide CIs** and **N=2 models with
data** — neither is fixed by adding benchmarks; more benchmarks multiply the arm64 build surface.

## What we already have is appropriately scoped (not under-covered)

Our two-axis design is already broader than most single-benchmark model comparisons:
- **L1 — agentic repo-level bug-fix** (SWE-bench Verified, binary pass@1).
- **L2 — agentic from-scratch full-stack construction** (29-check boot/build/test rubric). This
  long-horizon "build an app from nothing" axis is unusual and is a genuine contribution; few
  "coding agent" benchmarks test it.

The one real *gap* is a **contamination-controlled** axis: SWE-bench Verified tasks largely predate
model cutoffs and are a documented contamination risk. We have no clean measurement that controls
for training-set leakage.

## Per-candidate verdict

| Benchmark | Capability axis | arm64 local? | Decision |
|---|---|---|---|
| **SWE-bench Verified** | agentic patch-fix | partial (build-locally; 29/500) | **Keep — L1 anchor.** |
| **LiveCodeBench** | single-shot codegen, **contamination-controlled** | **yes — pure-Python harness → our vLLM endpoint, no per-task Docker** | **ADD.** Highest value-to-cost. |
| **Terminal-Bench 2** | **agentic terminal/CLI tool-use** (true agent loop) | risky — Harbor/Docker; per-task images likely amd64 → QEMU | **Pilot, gated.** Add only if a native-arm64 pilot works; else quality-only or defer. |
| **SWE-bench Pro** | agentic patch-fix (harder, contamination-hardened) | no — x86-recommended, arm64 unreliable | **Future work / related work.** Same axis as L1; diminishing returns + arm64 pain. |
| **SWE Atlas** | agentic SWE (codebase Q&A, test-writing, refactoring) | no — effectively **Modal-cloud-bound** | **Out of scope.** Cloud sandboxes break the "local private DGX Spark" thesis and the controlled-hardware comparison. Cite as related/future. |

### Why LiveCodeBench is the one clear add
- **Orthogonal axis that operationalizes our own thesis.** Our DeepSeek finding argues code-gen ≠
  agentic tool-use. LiveCodeBench measures *exactly* the single-shot code-gen axis, cleanly, so we
  can show a model's code-gen score next to its agentic (L1/L2) score and make the separation
  empirical instead of anecdotal.
- **Fills the contamination gap.** Time-windowed problems → pick a window after each model's cutoff;
  the only contamination-controlled number in the paper.
- **Near-zero arm64/infra cost.** Pure-Python `lcb_runner` pointed at the OpenAI-compatible vLLM
  endpoint we already run. No per-task Docker, no x86 images, no QEMU. Efficiency metrics (decode
  tok/s, energy/token) are even *cleaner* here than in the agentic layers (no tool-loop variance).

### Why Terminal-Bench 2 is gated, not a default add
It is the *ideal* agentic complement (it stresses autonomous tool-use disposition — our DeepSeek
theme — in a different modality from patch-gen). But its Harbor/Docker per-task images are likely
amd64, so on GB10 it probably runs under QEMU. Emulated timings would poison our energy/throughput
tables. **Action:** run a 2–3 task native-arm64 pilot. If images build/run native → add as a third
agentic layer. If they need emulation → either report **quality-only** for tb2 (explicitly excluded
from all efficiency tables, emulation disclosed) or defer to future work. Do not let emulated
timings into any efficiency metric.

### Why the two Scale AI benchmarks are out (for this paper)
SWE-bench Pro and SWE Atlas are both strong and current, but: SWE-bench Pro is x86/Docker-first and
covers the *same* axis we already have; SWE Atlas is effectively bound to Modal **cloud** sandboxes.
Running on cloud compute contradicts the paper's entire premise (local, private, on-box inference on
one DGX Spark) and would make the hardware comparison uncontrolled. Both belong in **Related Work**
(as the contamination-hardened / capability-broadened successors) and **Future Work**, not in the
results matrix.

## Recommendation

1. **Keep** L1 (SWE-bench Verified subset) + L2 (app build) as the agentic spine.
2. **Add LiveCodeBench** as a third axis: contamination-controlled, single-shot code-gen, arm64-
   native, cheap. It is the highest-leverage addition and directly serves the code-gen-vs-agentic
   thesis.
3. **Pilot Terminal-Bench 2** on native arm64; promote to a results layer only if it runs without
   emulation, otherwise quality-only or future work.
4. **Cite SWE-bench Pro and SWE Atlas in Related/Future Work**; do not run them (x86/cloud-bound,
   off-thesis).
5. **Spend the remaining effort on the real credibility risks, not more benchmarks:** report 95% CIs
   on every rate, state n and harness next to every number (already decided in the comparability
   note), and expand the arm64 SWE-bench subset beyond 29 if more images can be built natively.

## Caveats on the source research
The verification sweep flagged some specifics as possibly model-fabricated — exact arXiv IDs,
post-cutoff model names, and a few hyper-precise counts/scores. This note deliberately relies only
on the corroborated capability / run-method / arm64-feasibility facts. **Verify exact citations
(arXiv IDs, version numbers, task counts) by hand before they go into the paper.**

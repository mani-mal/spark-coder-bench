# DGX Spark Local Coding-Model Benchmark — End-to-End Overview

**Status: COMPLETE (matrix banked 2026-07-02; analysis addenda through 2026-07-11).** Full 3-model × 3-layer matrix banked and aggregated.
This is the single-page map of the whole study. Detailed rationale for every decision is in
`docs/findings/` (indexed at the bottom); raw per-run data is in `results/raw/`, aggregated in
`results/summary/benchmark-{long,summary}.csv`.

---

## 1. What this is (and is NOT)

A **reproducible, methodology-focused** comparison of local coding models on **one DGX Spark**.
The contribution is **serving/efficiency reality + evaluation methodology on consumer Grace
Blackwell**, NOT a public leaderboard. Numbers here are valid **relative, same-box** comparisons;
they are deliberately not comparable to public leaderboards (different config, hardware, contamination
handling).

**Hardware:** DGX Spark **GB10**, aarch64 / Grace Blackwell, **sm_121a** (consumer Blackwell,
no native FP4 compute path in these runtimes → FP4 weights run through weight-only kernels),
**128 GB unified LPDDR5x, ~273 GB/s** bandwidth (≈6× lower than discrete Blackwell's ~1.7 TB/s →
decode is **memory-bandwidth-bound**). Unified memory ⇒ `nvidia-smi` memory is N/A (we read
`/proc/meminfo`); **one large model served at a time**.

## 2. The three models

| model | params (total/active) | quant | serves on |
|---|---|---|---|
| **gpt-oss-120b** | 116.8B / 5.1B (sparsity 0.044) | MXFP4 MoE | **vLLM only** |
| **qwen3-coder-30b** | 30.5B / 3.3B (sparsity 0.108) | bf16 MoE | **vLLM only** |
| **nemotron-3-super-120b-a12b** | ~120B / ~12B, hybrid Mamba/attn + MoE, reasoning | NVFP4 (MIXED_PRECISION) | **TRT-LLM only** |

**Serving-feasibility is itself a headline finding:** no single model serves on *both* runtimes on
this box, so a same-model vLLM-vs-TRT bridge is impossible here.
- nemotron: vLLM rejects its MIXED_PRECISION checkpoint → TRT-LLM only.
- qwen: bf16 MoE has no working sm_121a TRT kernel → vLLM only.
- gpt-oss: MXFP4 MoE autotunes on TRT but requests deadlock at the executor → vLLM only.
(Details: `2026-06-25-nemotron-super-vllm-mixed-precision.md`, `2026-06-29-qwen-trt-moe-blackwell-blocker.md`,
`2026-06-29-gpt-oss-trt-blocker.md`.)

## 3. The three layers (orthogonal axes of "coding ability")

| layer | what | metric | driver |
|---|---|---|---|
| **L1** | SWE-bench Verified (real repo bug-fix, agentic) | resolved pass@1 | OpenCode → served model; official SWE-bench eval |
| **L2** | Custom app-build ("taskflow") from a spec, agentic | TaskFlow API acceptance-check fraction (k/29; "working app" = ≥0.5, arbitrary); **not** full-stack quality — see `layer2_appcase/COVERAGE.md` | OpenCode; `run_rubric.py` |
| **L3** | LiveCodeBench single-shot code generation | pass@1 + Wilson 95% CI | `lcb_runner` → served model |

L1/L2 are **agentic** (multi-turn tool use); L3 is **single-shot generation** — orthogonal, so the
"code-gen ≠ agentic tool-use" thesis becomes empirical. L1 runs on an **arm64 subset (29 tasks)**
because SWE-bench Verified images are x86-only.

## 4. Final results (same box; relative comparison)

### L1 — SWE-bench Verified (29-task arm64 subset, N=1 pass@1)
| model | resolved | 
|---|---|
| gpt-oss-120b (vLLM) | **37.9%** (11/29) |
| qwen3-coder-30b (vLLM) | **24.1%** (7/29) |
| nemotron-super (TRT) | **20.7%** (6/29) |

**Regression rate (collateral damage):** of *applied* patches, gpt-oss regresses ≥1 previously-passing
test **33.3%** (8/24), qwen 31.8% (7/22), nemotron 21.4% (3/14). Severity diverges sharply — gpt-oss
broke **1078** `PASS_TO_PASS` tests vs nemotron **3**: gpt-oss's aggressive edits **resolve the most
*and* regress the most** (a few catastrophic patches), nemotron's fewer/smaller edits rarely do either.
Directional (n=29 subset). `analysis/regression-rate.py`, `results/summary/regression-rate.csv`.

### L2 — App-build acceptance-check fraction (contract-visible; corrected for C1)
The first L2 sweep was produced under a harness bug — the frozen API contract the prompt requires
was missing from the workspace (finding C1). After restoring it (app-repo tag `baseline-v7`) and
re-running the vLLM models, the corrected result (mean k/29; "working-app" = ≥0.5):

| model | node (N=20) | python (N=8) |
|---|---|---|
| gpt-oss-120b (vLLM) | **0.724** (working 16/20 = 80% [58,92]) | 0.069 (0/8 working) |
| qwen3-coder-30b (vLLM) | 0.178 (working 3/20 = 15% [5,36]) | 0.004 (0/8) |
| nemotron-super (TRT)\* | 0.009 (N=4) | 0.000 (N=4) |

\*nemotron was **not** rerun (TRT-only, floor-saturated; a contract cannot help a model whose
backend almost never boots), so its rows remain the contract-invisible measurement.

**The harness bug had inverted the conclusion.** Under the bug, gpt-oss (0.252) and qwen (0.155)
looked *statistically indistinguishable*; corrected, gpt-oss (0.724, **80%** working apps) clearly
and significantly beats qwen (0.178, **15%**) on node — the working-app Wilson intervals no longer
overlap. The bug helped only where a model could actually build a booting app: **gpt-oss node
jumped 2.9×** (the four contract-only checks went 0→48 passes), while qwen (capability-limited on
booting a full app) and both python tracks (floored) barely moved. This is the paper's thesis in
its strongest form — a single harness validity error compressed a real ~4× gap into a fake small
one. Full ablation: `results/summary/l2-ablation-contract.csv`,
`docs/findings/2026-07-03-l2-rerun-with-contract-decision.md`.

Two caveats survive: **python floors for both models** (a genuine node↔python asymmetry, not a
contract artifact), and the *original* pre-contract sweep also showed low-N ranking instability
(N=1 gpt-oss → N=8 qwen → N=20 gpt-oss) — but those flips were between two mis-measured scores, so
the durable low-N lesson is now folded into the larger C1 point. Report the Bernoulli working-app
rate + Wilson CI, never a single-N mean.

### L3 — LiveCodeBench (pre2024m06 window, n=512, pass@1)
| model | pass@1 | Wilson 95% CI | empty/truncated |
|---|---|---|---|
| gpt-oss-120b (vLLM) | **89.3%** | [86.3, 91.7] | ~1-2% |
| qwen3-coder-30b (vLLM) | **68.2%** | [64.0, 72.1] | ~0% |
| nemotron-super (TRT) | **61.3%** | [57.0, 65.4] | **27.9% (143/512)** |

**Critical L3 nuance:** nemotron's last place is largely a **fixed-token-budget artifact, not
capability**. Its verbose reasoning exhausted the shared 8192-token budget on **185/512** problems
(143 empty outputs + 42 with no extractable code), scored as fails. Truncation is difficulty-
correlated (no-code rate easy 14.3% / medium 34.3% / hard 71.5%), so a conditional rate on the
answered subset must **not** be compared to other models' full-512 rates. **Paired on the 327
problems nemotron answered with code: nemotron 96.0%, gpt-oss 95.4%, qwen 82.3%** — the artifact
reading survives and strengthens (nemotron ≈ gpt-oss when it answers). This *is* the methodology
finding: a single-shot, fixed-budget benchmark systematically penalizes verbose reasoning models,
and the penalty lands almost entirely on hard problems. (`2026-07-01-nemotron-trt-mtp-wedge.md`,
`2026-07-03-l3-conditional-selection-bias.md`; data `results/summary/l3-conditional-analysis.csv`.)

**Consistent story across layers:** gpt-oss ≥ qwen ≥ nemotron on raw scores, but every gap is
either statistically weak (L1/L2) or budget-confounded (L3 nemotron) — the paper's point is about
**how you measure**, not a clean capability ranking.

## 5. Shared config & fairness controls

- **L3 decode** (held constant across models for cross-layer comparability): seed 0, temperature 0.2,
  top_p 0.95, n=1, **max_tokens 8192**, **unquantized KV** (TRT nemotron uses FP8 KV — a runtime
  default, disclosed). Truncated-as-fail is deliberate and disclosed (`2026-06-30-kv-cache-quant-unified-memory.md`).
- **Contamination is POSSIBLE, not balanced or free:** window = `contest_date ≤ 2024-05-31` (before
  gpt-oss's June-2024 cutoff, the earliest of the three) = 512 problems. Equal *opportunity* to have
  seen the set bounds exposure asymmetry but does **not** equalize or "cancel" contamination (corpora
  and dedup differ per model). Report as contamination-possible + sensitivity analysis; not
  leaderboard-comparable.
- **Efficiency:** hardware energy/memory from `nvidia-smi` + `/proc/meminfo` for all runs; **vLLM
  throughput/decode-tok/s from Prometheus** (gpt-oss ~26.9 tok/s, qwen ~19.7 tok/s at L1). **TRT-LLM
  exposes no Prometheus** → nemotron has hardware energy but **no decode-tok/s / TTFT** (blank,
  disclosed). This is why nemotron L3 could be run 8-way parallel with no metric loss (see below).
  **Consolidated perf/resource table** (wall-clock, GPU util/power, peak unified memory, KV-cache %,
  throughput, energy — all 3 models × L1/L2/L3), **quality-adjusted efficiency** (energy per
  *successful* task: nemotron **143 kJ**/solve vs gpt-oss **12.8 kJ** at L1, ~11×), **p95 tail
  latency** (TTFT + e2e; e.g. L1 gpt-oss TTFT p95 **4.9 s**, e2e p95 **17.8 s**), and **L1 regression
  rate** (§4.1) all live in `2026-07-11-cross-model-performance-resource-usage.md`
  (`results/summary/{perf-resource,quality-adjusted-efficiency,latency-tail-p95,regression-rate}.csv`);
  coverage vs the full LLM-eval metric taxonomy is mapped in `2026-07-11-llm-eval-metric-coverage.md`.

## 6. Serving & harness mechanics (how a run happens)

1. **Serve one model:** `infra/vllm/serve-model.sh <profile>` (vLLM :8000) or
   `infra/trtllm/serve-model-trtllm.sh <profile>` (TRT-LLM :8355). Both sanity-gate + write a manifest.
2. **Run a layer:** `layer1_swebench/run-suite.sh`, `layer2_appcase/run-appcase.sh`, or
   `layer3_livecodebench/run-suite.sh` — each wraps generation in `infra/metrics/run-context.sh`
   (clean-window hardware/energy capture) and writes `results/raw/<run-id>/`.
3. **Aggregate:** `analysis/aggregate-runs.py` → `results/summary/benchmark-{long,summary}.csv`;
   `analysis/figures.py` → charts. Stats (Wilson CI, McNemar) in `analysis/stats.py`.
- Endpoint override: L3 uses `L3_BASE_URL` to point at :8355 for TRT (env.sh otherwise forces :8000).
- Long unattended runs are guarded by watchdogs (`layer3_livecodebench/l3-watchdog*.sh`):
  auto-resume from `--use_cache` on crash/stall, re-serve on runtime death, heartbeat + restart cap.

## 7. Hard-won operational findings (the "reality" contribution)

- **TRT-LLM 1.3.0rc9 on GB10 is fragile for non-NVIDIA MoE** (qwen/gpt-oss deadlock); only the
  FP4-native NVIDIA reasoning model (nemotron) serves.
- **Degraded-box state:** a 26h vLLM run left the GPU in a state where TRT nemotron wedged after one
  generation (warmup 656s, executor stuck). A **reboot** fully cleared it (warmup → 8s). Lesson:
  reset the box between heavy long-lived serves.
- **Non-streaming wedge:** TRT nemotron wedged mid-generation (~400 tok) on non-streaming requests;
  `lcb_runner` was patched to **stream** (the path OpenCode already used for L1/L2).
- **Throughput reality:** nemotron single-stream L3 ≈ 130h (bandwidth-bound, verbose reasoning to
  8192 tok). Run **8-way parallel** (`L3_MULTIPROCESS=8`) → ~9.5h, quality-neutral (batching doesn't
  change per-problem pass@1; no efficiency metrics lost since TRT has none).
- **Silent-failure traps fixed:** reasoning models return `content=None` on truncation (guard added);
  a resume-filter re-generated empty outputs forever (fixed); a watchdog nearly false-stalled on a
  frozen log mtime (now uses the TRT iteration counter as ground truth). Cost one 12h run before the
  guards existed.

## 8. Where everything lives

- **Results:** `results/raw/<run-id>/` (per run), `results/summary/*.csv` (aggregated), `reports/charts/`.
- **Config:** `infra/models.json` (registry), `infra/{vllm,trtllm}/model-profiles/*.env`.
- **Methodology:** `docs/methodology.md`, `README.md`, `layer3_livecodebench/coverage.md`.
- **L1/L2 capstone:** `docs/findings/2026-06-29-full-matrix-results.md`.
- **Findings index (docs/findings/):**
  - *Through banked matrix (06-24 → 07-01):* model swap & tool-use gate (deepseek 06-24), rubric/npm-ci
    confound (06-25), nemotron-vLLM mixed-precision (06-25), L1 arm64 enablement + results (06-26),
    L2 N-scaling results (06-25/26), architecture framing (06-26), comparability & benchmark selection
    (06-28/29), TRT blockers qwen/gpt-oss (06-29), NVIDIA-blog external validation (06-29), LiveCodeBench
    integration scope (06-29), gpt-oss L3 crash + KV-quant (06-30), nemotron TRT warmup/wedge + final
    L3 (07-01).
  - *Post-completion analysis & corrections (07-02 →):* codex audit verification + decision (07-02),
    environment provenance / pending upgrades pre-OTA (07-02), **L2 C1 contract-invisible bug +
    rerun-with-contract decision (07-03)**, **L3 conditional selection-bias correction (07-03)**,
    Qwen3.6 NVFP4-coder roster gap (07-08), **L3 fixed-token-budget rationale + verbosity options
    (07-11)**, **cross-model performance/resource consolidation + quality-adjusted efficiency +
    p95 tail latency + L1 regression rate (07-11)**, **LLM-eval metric-coverage map (07-11)**.

## 9. Open / not-done (none blocking)

Higher-N L1 (per-task repeats for significance), larger arm64 SWE-bench subset, figure regeneration
with L3, and the arXiv write-up. Nothing is mid-run; the box is clean (no container serving).

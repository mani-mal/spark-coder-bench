# Local Coding-Model Configurations on a Single DGX Spark: A Systems + Methodology Case Study

**A reproducible study of serving feasibility, task success, and efficiency for three
open-weight Mixture-of-Experts coding models on consumer Grace Blackwell (GB10 / sm_121a).**

> **This is a systems + methodology case study, not a model-ranking paper.** Each arm couples a
> model with a specific quantization, serving runtime, and agent scaffold, so every score
> describes a *deployment configuration on this one box*, not intrinsic model quality. The
> primary results are **serving feasibility** and **measurement methodology**; the quality
> numbers are exploratory and strictly relative/same-box. This framing follows an independent
> audit (`docs/codex/BENCHMARK_AUDIT_AND_ARXIV_RECOMMENDATION.md`) and its verification
> (`docs/findings/2026-07-02-codex-audit-verification-and-decision.md`).

Every table below maps to a committed source CSV and a one-command regeneration step. The whole
`results/summary/` + `reports/charts/` tree rebuilds from the retained raw runs with
`make rebuild` (`analysis/rebuild-all.sh`).

---

## 1. Motivation

Practitioners increasingly want to run capable coding agents **locally and privately** on
affordable hardware. The DGX Spark (GB10, 128 GB unified memory, ~$/desk-side) is a plausible
box for this. But "can a 120B-class coding model actually drive an agent on this hardware, and
how do you measure it honestly?" is under-documented. This study answers a deliberately narrow,
defensible question:

> What serving, measurement, and coding-agent evaluation constraints arise when three pinned
> open-weight model configurations run locally on one DGX Spark, and what lessons follow for
> reproducible benchmark design?

The contributions are: (1) a **serving-feasibility matrix** for GB10/sm_121a; (2) a **three-layer
local evaluation harness** with full raw-artifact retention and deterministic rescoring; and (3)
a set of **measurement lessons** — most sharply, a documented case (finding C1) where a single
harness-validity error compressed a real ~4× quality gap into a fake statistical tie.

## 2. Setup

**Hardware.** DGX Spark **GB10**, aarch64 / Grace Blackwell, **sm_121a** (consumer Blackwell:
no native FP4 *compute* path in these runtimes → FP4 weights run through weight-only kernels).
**128 GB unified LPDDR5x, ~273 GB/s** bandwidth (≈6× lower than discrete Blackwell's ~1.7 TB/s),
so decode is **memory-bandwidth-bound**. Because memory is unified, `nvidia-smi` reports all
`memory.*` fields as `[N/A]`; the model footprint is read from `/proc/meminfo` as host RAM. **One
large model is served at a time.**

**Serving.** OpenAI-compatible endpoints: **vLLM** on `:8000` and **TensorRT-LLM** on `:8355`.
Both sanity-gate the model and write a per-serve reproducibility manifest under `manifests/`.
Image digests are pinned in `infra/provenance/provenance.json`:

| Runtime | Image | Digest |
|---|---|---|
| vLLM | `nvcr.io/nvidia/vllm:26.02-py3` | `sha256:1bec659d…9d783da` |
| TensorRT-LLM | `nvcr.io/nvidia/tensorrt-llm/release:1.3.0rc9` | `sha256:6c3c31a5…ef1f0e6d` |

*Source:* `infra/provenance/provenance.json` · *Regen:* `make provenance`

**Agent.** [OpenCode](https://opencode.ai), identical version/config for every model, drives the
two agentic layers (L1, L2). L3 has no agent (single-shot generation against the endpoint).

## 3. The three configurations (model × quant × runtime, all coupled)

| Model | Arch | Total / Active | Sparsity | Quant | Serves on | Why locked |
|---|---|---|---|---|---|---|
| gpt-oss-120b | MoE (128 exp, top-4) | 116.8B / 5.1B | 4.4% | MXFP4 | **vLLM only** | MXFP4 MoE autotunes on TRT but deadlocks at the executor |
| nemotron-3-super-120b-a12b | MoE-hybrid Mamba/attn (512 exp, top-22), reasoning | ~120B / ~12B | 10.0% | NVFP4 (MIXED_PRECISION) | **TRT-LLM only** | vLLM rejects its MIXED_PRECISION checkpoint |
| qwen3-coder-30b | MoE (128 exp, top-8) | 30.5B / 3.3B | 10.8% | bf16 | **vLLM only** | bf16 MoE has no working sm_121a TRT kernel |

*Source:* `infra/models.json` (registry, single source of truth)

**Model identity is confounded with quant, runtime, and scaffold — by necessity, and disclosed.**
No model serves on both runtimes on this box, so the design **cannot** isolate a generic
"FP4-on-Blackwell" effect: the two 4-bit MoEs (gpt-oss MXFP4, nemotron NVFP4) run on *different*
runtimes. Where FP4 runs on vLLM it uses the **Marlin weight-only** kernel (no native FP4 compute
on sm_121a), so any FP4 advantage is storage/bandwidth, not tensor-core math. Held identical
across arms: seed, temperature, KV-cache dtype policy, `max_num_seqs`, OpenCode/vLLM versions.

> **DeepSeek-Coder-V2-Lite was evaluated and retired** as a candidate: it generates correct code
> but will not *autonomously* call tools (it wrote nothing to disk while claiming success), so it
> cannot drive the agent loop. gpt-oss-120b replaced it after passing an explicit autonomous
> tool-use gate. Agentic competence ≠ code-generation competence
> (`docs/findings/2026-06-24-deepseek-v2-lite-agentic-tool-use.md`).

### Headline systems result: the serving-feasibility matrix

The single most practitioner-useful finding is negative and structural: **no model serves on
both runtimes on GB10/sm_121a.** nemotron is TRT-LLM-only (vLLM rejects the checkpoint); qwen and
gpt-oss are vLLM-only (no working TRT MoE path on this silicon). A same-model vLLM-vs-TRT bridge
is therefore *impossible on this box* — which is exactly why the arms are configurations, not
clean model contrasts. Root causes are documented per model in
`docs/findings/2026-06-25-nemotron-super-vllm-mixed-precision.md`,
`2026-06-29-qwen-trt-moe-blackwell-blocker.md`, and `2026-06-29-gpt-oss-trt-blocker.md`.

## 4. The three measurement layers

| Layer | What | Metric | Driver |
|---|---|---|---|
| **L1** | SWE-bench Verified — real repo bug-fix, agentic | resolved pass@1 on a disclosed 29-task ARM64-buildable subset | OpenCode → served model; official SWE-bench eval |
| **L2** | TaskFlow app-build from a frozen spec, agentic | TaskFlow **API acceptance-check fraction** (k/29) | OpenCode; `run_rubric.py` |
| **L3** | LiveCodeBench single-shot code generation | pass@1 + Wilson 95% CI (n=512) | `lcb_runner` → served model |

L1/L2 are agentic (multi-turn tool use); L3 is single-shot — orthogonal axes, so "code-gen ≠
agentic tool-use" becomes empirical rather than assumed. L1 runs on an **ARM64-buildable 29-task
subset** because SWE-bench Verified's task images are x86-only; this is **not** SWE-bench Verified
performance and is not a random sample (selection flow disclosed in `layer1_swebench/`).

## 5. Results (same box; relative comparison only)

![Success by layer: L1 resolved pass@1, L2 node working-app rate, and L3 pass@1 for the three
models, each with Wilson 95% confidence intervals.](charts/fig_quality_by_layer.png)

*Figure 1. Success by layer, three models, with Wilson 95% CIs. gpt-oss ≥ qwen ≥ nemotron on raw
scores, but the L1/L2 gaps are statistically weak and the L3 nemotron gap is budget-confounded
(Figure 3). Source: `results/summary/l{1,2,3}-run-ledger.csv` · Regen: `python3 analysis/figures_quality.py`.*

### 5.1 Layer 1 — SWE-bench Verified 29-task ARM64 subset (N=1 pass@1)

| Model | Resolved (raw) | Model-valid rate | Notes |
|---|---|---|---|
| gpt-oss-120b (vLLM) | **37.9%** (11/29) | 37.9% (11/29) | no infra failures |
| qwen3-coder-30b (vLLM) | **24.1%** (7/29) | 24.1% (7/29) | no infra failures |
| nemotron-super (TRT) | **20.7%** (6/29) | **30.0%** (6/20) | 1 watchdog kill + 8 infra_missing excluded |

*Source:* `results/summary/l1-run-ledger.csv` · *Regen:* `python3 analysis/robust-summary.py`

**Failure taxonomy matters.** The raw denominator counts operational failures (a watchdog kill; 8
clone/DNS/guard-drops that were never a measured attempt) as model failures. Separating them (the
`is_model_valid` column) raises nemotron's rate from 20.7% to 30.0% and is the honest denominator
for a *model* comparison. Pairwise McNemar on the shared 29 tasks finds no significant separation
(p = 0.125 / 0.289 / 1.0) — appropriate for the methodology framing, fatal for a ranking framing.
*Stats regen:* `python3 analysis/stats.py --long results/summary/benchmark-long.csv`.

### 5.2 Layer 2 — App-build acceptance-check fraction (contract-visible; corrected for C1)

The **first L2 sweep was produced under a harness bug (finding C1):** the frozen API contract the
prompt requires (`benchmark-spec/api-contract.md`) was missing from the workspace — an
app-repo tag-lineage break (`baseline-v4`→`v6`) had dropped it, so four checks were structurally
unreachable and every model was graded against a contract it could not see. After restoring the
contract (app-repo tag **`baseline-v7`**) and re-running the vLLM models:

| Model | node (N=20) k/29 | node working@≥0.5 | python (N=8) k/29 |
|---|---|---|---|
| gpt-oss-120b (vLLM) | **0.724** | **16/20 = 80%** [58, 92] | 0.069 (0/8 working) |
| qwen3-coder-30b (vLLM) | 0.178 | 3/20 = 15% [5, 36] | 0.004 (0/8) |
| nemotron-super (TRT)\* | 0.009 (N=4) | 0/4 | 0.000 (N=4) |

\*nemotron was **not** rerun (TRT-only, floor-saturated — a visible contract cannot help a model
whose backend almost never boots a full app), so its rows remain the contract-invisible
measurement. Results are dual-reported as k/29 and the C1-rescored **k/25** (25 reachable checks):
gpt-oss node 0.744 (17/20 working), qwen node 0.204 (3/20).

*Source:* `results/summary/l2-rescore-25.csv`, `results/summary/l2-run-ledger.csv`
· *Regen:* `python3 analysis/l2-rescore.py` ; `python3 analysis/robust-summary.py`

**The bug had inverted the conclusion — this is the paper's thesis in its strongest form.** Under
the bug, gpt-oss (0.252) and qwen (0.155) looked statistically indistinguishable. Corrected,
gpt-oss (0.724, 80% working apps) clearly and significantly beats qwen (0.178, 15%) on node — the
working-app Wilson intervals no longer overlap. The contract helped **only where a model could
actually build a booting app**: gpt-oss node jumped **2.9×** (the four contract-only checks went
0→48 passes), while qwen (capability-limited on booting a full app) and both python tracks
(floored) barely moved. A single harness-validity error compressed a real ~4× gap into a fake
small one.

![L2 node working-app rate for gpt-oss and qwen, contract-invisible (under the C1 bug) versus
contract-visible (baseline-v7), with Wilson 95% CIs.](charts/fig_l2_contract_ablation.png)

*Figure 2. The C1 before/after ablation. Under the bug, gpt-oss (6/20) and qwen (4/20) working-app
rates overlapped — "indistinguishable"; with the contract restored, gpt-oss jumps to 16/20 while
qwen stays flat, and the intervals separate. A single missing spec file compressed a real gap into
a fake tie. Source: `results/summary/l2-ablation-contract.csv` · Regen: `python3 analysis/figures_quality.py`.*

*Before/after ablation source:* `results/summary/l2-ablation-contract.csv`
· `docs/findings/2026-07-03-l2-rerun-with-contract-decision.md`

Two caveats survive the correction: **python floors for both models** (a genuine node↔python
asymmetry, not a contract artifact), and the L2 metric is an **API-acceptance signal, not
full-stack app quality** — the "working app ≥ 0.5" cutoff is arbitrary and unvalidated (reported
for continuity only). What the 29 checks do and do not establish is enumerated in
`layer2_appcase/COVERAGE.md`. Report the Bernoulli working-app rate + Wilson CI, never a
single-N mean.

### 5.3 Layer 3 — LiveCodeBench (pre-2024-06 window, n=512, pass@1)

| Model | pass@1 | Wilson 95% CI | no-code / truncated |
|---|---|---|---|
| gpt-oss-120b (vLLM) | **89.3%** | [86.3, 91.7] | ~1–2% |
| qwen3-coder-30b (vLLM) | **68.2%** | [64.0, 72.1] | ~0% |
| nemotron-super (TRT) | **61.3%** | [57.0, 65.4] | **185/512 (see below)** |

*Source:* `results/summary/l3-run-ledger.csv`, `results/summary/benchmark-long.csv`
· *Regen:* `python3 analysis/robust-summary.py` (ledger); `python3 analysis/aggregate-runs.py`

**nemotron's last place is largely a fixed-token-budget artifact, not capability.** Its verbose
reasoning exhausted the shared 8192-token budget on **185/512** problems (143 empty outputs + 42
with output but no extractable code), all scored as fails. Truncation is **difficulty-correlated**
(no-code rate: easy 14.3% / medium 34.3% / **hard 71.5%**), so a conditional rate on the answered
subset must **not** be compared against other models' full-512 rates (a selection-bias trap the
first analysis fell into — finding C2). **Paired on the 327 problems nemotron answered with code:
nemotron 96.0%, gpt-oss 95.4%, qwen 82.3%** — the artifact reading survives and strengthens
(nemotron ≈ gpt-oss when it answers).

![Left: nemotron's no-code (truncation) rate rises with difficulty — easy 14%, medium 34%, hard
72%. Right: pass@1 on the 327 problems nemotron answered with code — nemotron 96.0%, gpt-oss 95.4%,
qwen 82.3%.](charts/fig_l3_truncation.png)

*Figure 3. nemotron's L3 last place is a fixed-token-budget artifact, not capability. Truncation
concentrates on hard problems (left); on the problems it actually answers, nemotron matches gpt-oss
(right). Source: `results/summary/l3-conditional-analysis.csv` · Regen: `python3 analysis/figures_quality.py`.*

*Source:* `results/summary/l3-conditional-analysis.csv`
· *Regen:* `python3 analysis/l3-conditional.py`
· `docs/findings/2026-07-03-l3-conditional-selection-bias.md`

This *is* the methodology finding: **a single-shot, fixed-budget benchmark systematically
penalizes verbose reasoning models, and the penalty lands almost entirely on hard problems.**

### 5.4 Consistent story across layers

On raw scores gpt-oss ≥ qwen ≥ nemotron, but every gap is either statistically weak (L1/L2) or
budget-confounded (L3 nemotron). The durable point is about **how you measure**, not a clean
capability ranking.

## 6. Measurement pitfalls (the "reality" contribution)

- **Unified memory ≠ VRAM.** `nvidia-smi memory.*` is `[N/A]` on GB10; the memory figure comes
  from `/proc/meminfo` and is whole-system, not dedicated GPU memory. Do not read it as VRAM.
- **tok/J is prompt-token-dominated.** The agent loop re-sends context every turn, so prompt
  tokens are a median ~98.7% of total; a naive `total_tokens / energy_j` therefore measures
  re-submitted context, not decode work. Report energy per **generated** token alongside it.
- **Restart-truncated energy windows.** Watchdog restarts reuse a run-id and overwrite the
  metric window, so a crash-prone run's energy can cover only its final segment. The gpt-oss L3
  energy cell is a known-broken capture (~3 orders of magnitude low) and is marked
  `energy_valid=0` in `results/summary/l3-run-ledger.csv` rather than published.
- **Robust energy summary.** Arithmetic mean L1 energy is dominated by one ~13 h nemotron
  operational runaway (~655 kJ); report median/IQR with an operational-failure sensitivity
  (`python3 analysis/robust-summary.py`), never a bare mean.
- **Telemetry asymmetry.** vLLM exposes Prometheus (gpt-oss ~26.9 tok/s, qwen ~19.7 tok/s at L1);
  **TRT-LLM exposes none**, so nemotron has hardware energy but no decode-tok/s or TTFT (blank,
  disclosed). Efficiency figures in `reports/charts/` inherit these gaps and should be read with
  the caveats above.

## 7. Operational findings (hard-won)

- **TRT-LLM 1.3.0rc9 on GB10 is fragile for non-NVIDIA MoE** (qwen/gpt-oss deadlock); only the
  FP4-native NVIDIA reasoning model (nemotron) serves on TRT.
- **Degraded-box state:** a 26 h vLLM run left the GPU in a state where TRT nemotron wedged after
  one generation (warmup 656 s). A reboot fully cleared it (warmup → 8 s) — reset the box between
  heavy long-lived serves.
- **Non-streaming wedge:** TRT nemotron wedged mid-generation on non-streaming requests;
  `lcb_runner` was patched to stream (the path OpenCode already used for L1/L2).
- **Throughput reality:** nemotron single-stream L3 ≈ 130 h (bandwidth-bound, verbose reasoning to
  8192 tok). Run 8-way parallel → ~9.5 h, quality-neutral (batching doesn't change per-problem
  pass@1; no efficiency metrics lost since TRT exposes none).
- **Silent-failure traps fixed:** reasoning models return `content=None` on truncation (guarded);
  a resume-filter re-generated empty outputs forever (fixed); a watchdog nearly false-stalled on a
  frozen log mtime (now uses the TRT iteration counter as ground truth).

## 8. Reproducibility

- **Raw retention.** Every run keeps its summaries, manifests, and clock records under
  `results/raw/<run-id>/`. Bulky per-run time series are regenerable and gitignored; summaries and
  manifests are committed.
- **Deterministic rescoring.** Scoring is fully automated and mechanical — no human scorers, no
  LLM judge, at any layer. `aggregate-runs.py` and `robust-summary.py` regenerate their tables
  byte-identically from retained outputs.
- **One-command rebuild.** `make rebuild` (`analysis/rebuild-all.sh`) re-derives every summary
  table, per-run ledger (L1/L2/L3), figure, and statistic from `results/raw/` — without
  re-serving any model. `analysis/stats.py --selftest` and `analysis/robust-summary.py --selftest`
  pass.
- **Immutable pins.** `infra/provenance/provenance.json` records container image digests, upstream
  dataset snapshot revisions (SWE-bench Verified, LiveCodeBench code_generation_lite), the L1
  subset checksums, and the frozen L3 window (`make provenance`).
- **Two-repo separation.** Model-generated app code lives only in `taskflow-local-app-benchmark`
  (driven by OpenCode); this repo never edits it. Claude Code built the tooling and this report
  but is **not** part of what was measured.

## 9. Limitations

- **Single box; three configurations.** Model identity is fully coupled to serving
  runtime/precision/scaffold. Conclusions are restricted to *these configurations on this
  machine*; serving incompatibility is a valid systems finding, not proof of intrinsic quality.
- **Small / unequal samples.** L1/L3 are single-attempt per cell; L2 is N = 20/8 (node/python) for
  vLLM models vs N = 4 for nemotron. All quality claims are descriptive.
- **Protocol changed mid-collection.** The C1 contract fix and rubric denominator changes mean
  some early runs are exploratory; confirmatory claims draw on the post-fix `baseline-v7` sweep.
- **L1 is a disclosed ARM64-buildable subset,** not SWE-bench Verified, and not a random sample —
  do not extrapolate to absolute SWE-bench numbers.
- **L3 is a fixed, historical, contamination-*possible* window.** Equal chronological eligibility
  is not equal contamination; the set is not exposure-balanced and is not leaderboard-comparable.
- **Generated code is executed without OS-level isolation on this kernel** (bubblewrap
  unavailable; disclosed). Publication-grade runs should use a no-network container/VM.

## 10. Conclusions

On a single DGX Spark, the story that survives scrutiny is not "model X wins." It is that **at
local-eval scale, serving feasibility and harness validity dominate model effects** — literally:
no model serves on both runtimes here, and a single missing spec file (C1) inverted the L2
conclusion, while a fixed token budget (L3) manufactured a last place for a verbose reasoning
model that is competitive when it answers. The practitioner takeaways are concrete: **gpt-oss-120b
on vLLM is the strongest local agentic configuration measured here** (L1 37.9%, L2 node 80% working
apps, L3 89.3%); **nemotron only serves on TRT-LLM** and needs a larger token budget to be judged
fairly; and **honest local benchmarking requires a failure taxonomy, robust energy statistics, and
byte-reproducible rescoring** far more than it requires another leaderboard number.

---

### Appendix A — Regeneration quick reference

| Artifact | Source CSV | Command |
|---|---|---|
| Aggregated long/summary tables | `results/summary/benchmark-{long,summary}.csv` | `python3 analysis/aggregate-runs.py` |
| Inferential statistics | `results/summary/stats-report.txt` | `python3 analysis/stats.py --long results/summary/benchmark-long.csv` |
| Efficiency figures (supplement) | `reports/charts/fig_{throughput,ttft,energy_per_task,…}.png` | `python3 analysis/figures.py` |
| Quality/thesis figures (Figs 1–3) | `reports/charts/fig_{quality_by_layer,l2_contract_ablation,l3_truncation}.png` | `python3 analysis/figures_quality.py` |
| L1/L2/L3 per-run ledgers | `results/summary/l{1,2,3}-run-ledger.csv` | `python3 analysis/robust-summary.py` |
| L2 C1 rescore (k/29 + k/25) | `results/summary/l2-rescore-25.csv`, `l2-ablation-contract.csv` | `python3 analysis/l2-rescore.py` |
| L3 conditional / selection-bias | `results/summary/l3-conditional-analysis.csv` | `python3 analysis/l3-conditional.py` |
| Provenance pins | `infra/provenance/provenance.json` | `make provenance` |
| **Everything at once** | (all of the above) | **`make rebuild`** |

### Appendix B — Source documents

Architecture diagram: `docs/architecture/benchmark-architecture.jpg`. Canonical protocol:
`docs/HELP.md`. Fairness controls + metric catalogue: `docs/methodology.md`. End-to-end map:
`docs/BENCHMARK_OVERVIEW.md`. Reframing decision + audit verification:
`docs/findings/2026-07-02-codex-audit-verification-and-decision.md`. Consolidated
performance/resource metrics + quality-adjusted efficiency:
`docs/findings/2026-07-11-cross-model-performance-resource-usage.md`
(`results/summary/{perf-resource,quality-adjusted-efficiency}.csv`); LLM-eval metric-coverage map:
`docs/findings/2026-07-11-llm-eval-metric-coverage.md`. Independent review:
`fable/review.md`. Dated findings: `docs/findings/`.

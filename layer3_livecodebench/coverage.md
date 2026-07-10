# Layer 3 coverage — LiveCodeBench problem window & exposure record

This is the Step-0 record: the exact problem set, the per-model contamination exposure, and the
generation-config deviations from LCB's standard run. Mirrors `../layer1_swebench/coverage.md`.

## Dataset

- **Source:** `livecodebench/code_generation_lite`, `release_v6` (loaded via `lcb_runner`,
  `datasets==3.5.0`, `trust_remote_code=True`).
- **release_v6 total:** **1055** problems, `contest_date` range **2023-05 → 2025-04**.
- v7 (post-2025 problems) is **not released** as of 2026-06-29.

## The window: fixed historical, contamination-possible (`contest_date <= 2024-05-31`)

| | |
|---|---|
| Window | `--end_date 2024-05-31` (problems on/before 2024-05-31) |
| **N (problems)** | **512** |
| Run-id window tag | `pre2024m06` |
| Property | fixed historical window; every model *could* have seen it (equal opportunity ≠ equal exposure), **NOT contamination-balanced and NOT contamination-free** |

`--end_date 2024-06-01` yields the same 512 (no problems are dated exactly 2024-06-01); we use
`2024-05-31` so the window is unambiguously *before* June 2024.

### Why this window — per-model training cutoffs

| Model | Training cutoff | Source |
|---|---|---|
| gpt-oss-120b | **June 2024** (earliest) | OpenAI model card / arXiv 2508.10925 |
| Qwen3-Coder-30B-A3B | April 2025 | Qwen HF card |
| Nemotron-3-Super-120B | February 2026 (latest) | NVIDIA build model card |

The window sits **before the earliest cutoff (gpt-oss, June 2024)**, so all three models are *past*
the entire problem set → equal *opportunity* to have memorized. This bounds the exposure
asymmetry — a *post*-2024 window would instead hand Qwen/Nemotron (later cutoffs) a clear
memorization edge over gpt-oss — but it does **not** make exposure equal or make contamination
"cancel": corpora, dedup, and benchmark ingestion differ per model, so actual memorization can
still differ on the same problems. Report this as a contamination-*possible* window and add a
sensitivity analysis, not as a contamination-balanced comparison.

There is **no contamination-free window**: release_v6 ends April 2025, which predates Qwen's
(April 2025) and Nemotron's (Feb 2026) cutoffs, so essentially zero v6 problems postdate either.
Contamination-free requires LCB v7 → future work. **Do not present L3 scores as contamination-free**;
they are a valid *relative* code-gen comparison across our own models only.

N = 512 gives Wilson 95% CIs far tighter than L1's n=29 — e.g. a 50% pass@1 lands at roughly
±4.3 points (≈ [45.7, 54.3]%).

## Generation config — deviations from LCB's standard run (disclosed)

Held identical to L1/L2 (`infra/models.json` shared block) for cross-layer comparability:

| Param | Value | Note |
|---|---|---|
| seed | **not passed** | M10 correction: L3 generation sends **no seed** to the endpoint (`GEN_CMD` in `run-suite.sh` passes `--n/--temperature/--max_tokens` only; lcb_runner sets no seed kwarg). The `infra/models.json` shared `seed:0` governs L1/L2 serving; it is **not** applied to L3 generation. In any case vLLM continuous batching is non-deterministic, so L3 is treated as unseeded single-sample. |
| temperature | 0.2 | shared (LCB leaderboard often uses different sampling) |
| n (samples/problem) | 1 | single-sample; pass@1 is a Bernoulli per problem |
| concurrency | **1** (`--multiprocess 1`) | **single-stream** — LCB defaults to concurrent sampling; we force sequential so decode tok/s & energy/token match the agentic layers |
| top_p | 0.95 | LCB default |
| max_tokens | 8192 | held constant across models |

**Consequence:** our L3 pass@1 is comparable **across our own models**, but **not** to the public
LCB leaderboard (different sampling config). Stated in the paper.

## Smoke / plumbing window (not a reported result)

`--start-date 2023-08-01 --end-date 2023-08-31` → **36** problems, used only to validate the
generate→eval→score pipeline end-to-end (on `tiny-smoke-test` = Qwen3-0.6B). Scores from this
window are mechanical-validation only and are not reported.

## Evaluation execution environment (sandbox deviation, disclosed)

The eval pass executes model-generated code to grade it. The intended isolation was
`bwrap --ro-bind / / --unshare-net` (read-only root, private /tmp, RW only on the LCB output +
HF cache, no network). **This kernel (DGX Spark GB10, aarch64) blocks unprivileged namespace
creation** — both `RTM_NEWADDR` on the loopback interface (net namespace) and uid-map setup
(user namespace) are denied, so `bwrap` cannot run here at all.

Eval therefore runs under lcb_runner's **built-in isolation**: each submission is graded in a
separate worker process (`--num_process_evaluate 12`) with a per-test wall-clock timeout
(`--timeout 6`) — the same harness the public LCB leaderboard runs unsandboxed. Risk is low: the
inputs are a coding model's competitive-programming solutions (not adversarial), and the
process+timeout layer contains runaway/looping code. **Filesystem and network are not isolated**
during grading — acceptable for this input class on a dedicated single-tenant eval box, but noted
so the threat model is explicit. `run-suite.sh` still attempts `--sandbox` (bwrap) first on hosts
that permit namespaces.

## Per-run artifacts (`results/raw/<profile>-l3-lcb-pre2024m06-<seq>/`)

- `run-summary.json` — 3-source efficiency window (authoritative for L3 inference accounting).
- `lcb-predictions.json` — generations per problem.
- `lcb-score.json` — `{n, passed, pass_at_1, wilson_ci_95, window, per_problem[...]}`.

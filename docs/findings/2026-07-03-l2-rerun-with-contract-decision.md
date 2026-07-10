# Decision: rerun Layer 2 with the API contract visible (closes C1)

**Date:** 2026-07-03
**Follows:** `2026-07-03-l2-contract-invisible.md` (finding C1)
**Status:** DONE (2026-07-04). Reran gpt-oss + qwen (node N=20, python N=8) from `baseline-v7`;
results below. Pre-contract runs archived at `results/_archive_l2_pre_contract_20260703/`.

---

## Decision

**Rerun Layer 2 for the two vLLM models (gpt-oss-120b, qwen3-coder-30b) with the frozen
`api-contract.md` present in the workspace**, and treat the pre-contract runs as the "before" arm
of an ablation.

## Why rerun (not just rescore)

The k/25 rescore already recovers a fair metric from the existing data, and would have been enough
to publish honestly. But a rerun is worth the compute because it does three things a rescore cannot:

1. **Restores the full 29-check metric.** With the contract visible, the four contract-only checks
   (`dashboard_summary_keys`, `project_archive`, `project_edit`, `task_update_status`) become
   reachable, so k/29 is a valid denominator again.
2. **Lets L2 make the claim the prompt actually makes.** The rescore only measures "build an app
   from the requirements prose"; the rerun measures "implement the communicated contract" — which
   is what `prompt.md` says and what the paper wants to report.
3. **Turns the bug into a headline result.** The before/after delta is a clean, quantified
   demonstration of the paper's own thesis — *at local-eval scale, harness/validity errors dominate
   model effects*. the AI reviewer called this "the single most interesting experiment this dataset now
   suggests."

## Methodology

- **Prerequisite (app repo).** `taskflow-local-app-benchmark` tag **`baseline-v7`** = `baseline-v6`
  + `benchmark-spec/api-contract.md` (restored byte-identical to the harness copy,
  md5 `6b90b481…`, which is the same file that was at `baseline-v4`). The L2 runner is invoked with
  `BASELINE=baseline-v7`.
- **Cells rerun:** gpt-oss-120b and qwen3-coder-30b, **node N=20 and python N=8** — matching the
  original vLLM design exactly for an apples-to-apples comparison.
- **nemotron-super excluded from the rerun.** It is TRT-only and was floor-saturated in the original
  L2 (node 0.009 with 0/4 working apps, python 0.000). The four contract checks require a *booted*
  backend to even be reached; nemotron almost never booted a working backend, so a visible contract
  cannot move its score. Rerunning it would spend fragile TRT compute for no measurable effect. Its
  original L2 rows are retained and carry the k/25 disclosure.
- **Data handling.** The pre-contract gpt-oss/qwen L2 runs are moved to
  `results/_archive_l2_pre_contract_20260703/` (the same pattern this repo used for
  `_archive_old_rubric_20260625`). The rerun writes into `results/raw/` with the original run-ids,
  so the corrected (contract-visible) numbers become the primary published L2 result; the archive
  is the "before" arm.

## Honest caveats

- **Environment moved (OTA).** The original L1/L2/L3 ran on kernel `6.17.0-1021`; a DGX Spark OTA
  since then moved the box to kernel `6.17.0-1026` (driver unchanged at `580.159.03`). The rerun
  runs on the post-OTA kernel. This is **irrelevant to L2 *quality*** (rubric pass rate depends on
  what the model generates, not the kernel); it is noted only because the before/after comparison
  is not run under a bit-identical environment. See
  `2026-07-02-environment-provenance-pre-ota.md`.
- **Generation is non-deterministic** (vLLM continuous batching; seed does not pin it), so even the
  same model+contract would not reproduce the old per-run scores exactly. The comparison is at the
  aggregate/Bernoulli level (mean pass-rate, working-app rate), not per-run.
- **The before/after delta conflates** contract-visibility with the (quality-irrelevant) kernel
  refresh and with generation variance. We attribute it to contract visibility on the grounds that
  the four affected checks are, by construction, contract-dependent and scored exactly 0 before.

## Results — the ablation (contract INVISIBLE → VISIBLE)

Full data: `results/summary/l2-ablation-contract.csv`. Working-app interval is 95% Wilson.

| model | track | mean k/29 before → after | boots before → after | working-app before → after | 4 dead-checks passes |
|---|---|---|---|---|---|
| gpt-oss-120b | node | 0.252 → **0.724** (2.9×) | 9/20 → 18/20 | 6/20 → **16/20** [58%,92%] | 0 → **48** |
| gpt-oss-120b | python | 0.056 → 0.069 | 3/8 → 1/8 | 0/8 → 0/8 | 0 → 1 |
| qwen3-coder-30b | node | 0.155 → 0.178 (1.1×) | 8/20 → 6/20 | 4/20 → 3/20 [5%,36%] | 0 → 11 |
| qwen3-coder-30b | python | 0.000 → 0.004 | 0/8 → 0/8 | 0/8 → 0/8 | 0 → 0 |

### Interpretation

- **The bug inverted the L2 conclusion.** Pre-contract, gpt-oss (0.252) and qwen (0.155) were
  reported as *statistically indistinguishable*. Contract-visible, gpt-oss (0.724, 80% working
  apps) beats qwen (0.178, 15%) decisively — the working-app Wilson intervals **no longer overlap**
  ([58,92] vs [5,36]).
- **The effect is concentrated exactly where the mechanism predicts.** A visible contract can only
  help a model that can build a *booting* app. gpt-oss on node (which boots) jumped 2.9×; qwen
  (capability-limited on booting a full backend) and both python tracks (floored) barely moved.
  This is stronger than the AI reviewer's "≈4 dead checks" estimate: because the checks are stateful, guessing
  the API wrong cascaded, so the bug suppressed the *whole* score for the capable model.
- **This is the paper's thesis in its sharpest form** — a single harness validity error compressed
  a real ≈4× capability gap into a fake "too close to call." It belongs in the paper as a
  before/after ablation, not a footnote.

### Caveats on the comparison

- **nemotron not rerun** (see methodology) — its L2 rows stay contract-invisible; disclosed in
  every table with an asterisk.
- **Post-OTA kernel** for the rerun (quality-irrelevant; see caveats above).
- **Only N=20/8 at one N** for the corrected arm — no low-N sweep, so the earlier "ranking flips
  with N" observation is not re-established under the fix; it was itself a property of the broken
  measurement and is now subsumed by this finding.

## Docs updated

Every L2 number was refreshed via `aggregate-runs.py` → `robust-summary.py` → `figures.py` →
`l2-rescore.py`, then `docs/HELP.md`, `docs/BENCHMARK_OVERVIEW.md`, `layer2_appcase/COVERAGE.md`,
and the C1 finding note. Ablation artifact: `results/summary/l2-ablation-contract.csv`.

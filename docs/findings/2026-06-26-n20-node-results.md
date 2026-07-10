# Layer-2 node N=20 — ranking flips a third time; a rubric crash that biased the mean

> **⚠️ Superseded (2026-07-04):** these numbers are from the original L2 sweep, later found to run under a harness bug — the API contract was missing from the workspace (finding C1). L2 was re-run with the contract restored; see `2026-07-03-l2-rerun-with-contract-decision.md` for the corrected numbers and the before/after ablation. This note is retained as a historical record of the pre-contract measurement.


**Date:** 2026-06-26
**Scope:** Layer 2 node track, N=20, gpt-oss-120b vs qwen3-coder-30b. Fixed 29-check rubric,
vLLM 0.15.1 on DGX Spark GB10. seed=0, temp=0.2. Extends the N=8 finding.

## Headline

At N=20, **gpt-oss-120b leads on node (0.252 vs 0.155)** — the *opposite* of N=8, where qwen
led (0.177 vs 0.121). This is the **third ranking flip** of the same head-to-head as N grew, and
the single strongest piece of evidence in the study for "low-N local-coding evals are unstable."

| N | gpt-oss node mean | qwen node mean | apparent leader |
|---|---|---|---|
| 1 | 0.69 | 0.00 | gpt-oss (decisive) |
| 3 | 0.241 | 0.218 | gpt-oss (tie) |
| 8 | 0.121 | 0.177 | qwen |
| 20 | **0.252** | **0.155** | gpt-oss |

Corrected N=20 (working-app rate = pass-rate ≥ 0.5, Wilson 95%):

| Model | mean | std | working | Wilson 95% CI |
|---|---|---|---|---|
| gpt-oss-120b | 0.252 | 0.302 | 6/20 (30%) | [15%, 52%] |
| qwen3-coder-30b | 0.155 | 0.247 | 4/20 (20%) | [8%, 42%] |

The CIs still overlap ([15,52] vs [8,42]), so gpt-oss's node lead is **not yet significant** even
at N=20 — but the direction is now consistent with the larger sample, and the variance is enormous
(std ≈ 0.30 on means ≈ 0.2). The honest summary remains: both models are unreliable one-shot
app-builders (~20–30% working-app rate), with high run-to-run variance and no significant node gap.

## A harness bug this sweep exposed (and the fix)

One gpt-oss run (node-17) initially **vanished from the sample** (gpt-oss showed n=19, not 20),
which silently biased its mean *upward* (0.263 over 19 vs 0.252 over the true 20). Cause: gpt-oss
built the backend in a **non-standard layout** — flat under `apps/node-track/src/` with no
`backend/` subdir that the contract specifies. The rubric's backend start did
`subprocess.Popen(cwd=<apps/node-track/backend>)` on that missing path, which raised
`FileNotFoundError` and **crashed `run_rubric.py` before it wrote `rubric-score.json`** — so the run
produced no score and dropped out of the aggregate.

This is the same anti-pattern as the earlier npm-ci / python-entrypoint confounds: a real model
failure (not following the contract layout) must score *low*, not crash-and-vanish. **Fix:**
`run_rubric.py` now checks `bdir.is_dir()` before starting the backend and wraps the `Popen` in a
try/except; a missing/un-startable backend records `backend_booted=False` and flows into the
canonical 29-check denominator like any other dead-backend run. node-17 was re-scored from its
committed branch → **0.034** (1/29: the frontend builds, backend never boots), and the N=20 means
above include it. Net effect of the bug was small here (0.263→0.252) but it was a systematic upward
bias that would compound silently in larger sweeps — exactly the kind of "broken build excluded =
looks better than it is" error the fixed-denominator design exists to prevent.

## Cross-layer picture (unchanged conclusion)

- Layer 2 node N=20: gpt-oss 0.252 vs qwen 0.155 (gpt-oss ahead, ns).
- Layer 1 SWE-bench: gpt-oss 37.9% vs qwen 24.1% pass@1 (gpt-oss ahead, ns).
- Layer 2 python (N=3): gpt-oss 0.046 vs qwen 0.000 (both ~0).

With the larger node sample, gpt-oss now leads on *both* layers in direction, though neither gap is
significant. The task-dependence point softens but the "raise N / report Bernoulli + CI, never an
N≤8 mean ranking" methodological message is reinforced by the third flip.

## Bottom line

gpt-oss-120b 0.252 vs qwen3-coder-30b 0.155 on node at N=20 (ns; working-app 30% vs 20%). The
ranking flipped three times on the way here — publish the success-rate-with-CI and the flip table,
not any single-N mean.

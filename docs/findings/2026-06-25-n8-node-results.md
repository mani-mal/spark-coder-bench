# Layer-2 N=8 node results — the N=1 ranking fully inverts; both models ~equally unreliable

> **⚠️ Superseded (2026-07-04):** these numbers are from the original L2 sweep, later found to run under a harness bug — the API contract was missing from the workspace (finding C1). L2 was re-run with the contract restored; see `2026-07-03-l2-rerun-with-contract-decision.md` for the corrected numbers and the before/after ablation. This note is retained as a historical record of the pre-contract measurement.


**Date:** 2026-06-25
**Scope:** Layer 2 (TaskFlow Local app build), **node track, N=8**, gpt-oss-120b vs
qwen3-coder-30b. Fixed 29-check rubric. vLLM 0.15.1 on DGX Spark GB10. seed=0, decode temp=0.2.
python track unchanged from N=3 (this sweep was `TRACKS=node`).

## Headline

At N=8 the two models are **statistically indistinguishable on node**, and the N=1 "gpt-oss wins"
snapshot has now **fully inverted** — qwen edges ahead on both mean and working-app rate. The real,
robust finding is that **both a 120B MXFP4 MoE and a 30B bf16 MoE produce a working full-stack app
only ~1-in-4 to ~1-in-8 times** in one shot, with high run-to-run variance.

| Model | mean pass-rate | std | "working app" rate (≥0.5) | Wilson 95% CI |
|---|---|---|---|---|
| gpt-oss-120b | 0.121 | 0.220 | 1/8 (12%) | [2%, 47%] |
| qwen3-coder-30b | 0.177 | 0.277 | 2/8 (25%) | [7%, 59%] |

Per-repeat pass-rate (bimodal: one good build, rest near-zero):
- **gpt-oss:** 0.69, 0.03, 0.00, 0.03, 0.00, 0.14, 0.00, 0.07
- **qwen:**    0.00, 0.00, 0.66, 0.00, 0.66, 0.00, 0.07, 0.03

"Working app" = pass-rate ≥ 0.5, i.e. the backend boots and enough of the contract is implemented to
score (the bimodal gap is wide — good runs cluster at 0.65-0.69, the rest at ≤0.14 — so the threshold
is not knife-edge sensitive).

## The ranking inverted as N grew — the cautionary result, sharpened

| N | gpt-oss node | qwen node | apparent winner |
|---|---|---|---|
| 1 | 0.69 | 0.00 | gpt-oss (decisive) |
| 3 | 0.241 | 0.218 | tie (gpt-oss nominally) |
| 8 | 0.121 | **0.177** | tie (qwen nominally) |

The apparent leader flipped from gpt-oss (N=1) to qwen (N=8) **purely by sampling more runs of the
exact same setup**. Nothing changed but the repeat count. This is the strongest evidence for the
paper's methodological point: **single-shot local-model coding evals can not only mislead about
magnitude, they can invert the ranking.** Repeats are mandatory.

## Statistical reading

The Wilson 95% intervals — gpt-oss [2%, 47%], qwen [7%, 59%] — overlap across almost their entire
range. There is no basis to claim either model is better at one-shot full-stack node builds. Report
the pair as **indistinguishable at this task and N**, with the shared finding being low reliability,
not a winner.

N=8 is still modest for a ~12-25% Bernoulli rate (the CIs remain wide). If a tighter bound is wanted,
N≥20 per cell would shrink them, but the qualitative conclusion (low, similar reliability;
indistinguishable) is already stable across N=3 and N=8 and is unlikely to change.

## python track (unchanged, N=3)

This sweep was node-only. python remains gpt-oss 0.046, qwen 0.000 — both weak/zero, for the genuine
reasons documented in [`2026-06-25-harness-issues-and-fixes.md`](./2026-06-25-harness-issues-and-fixes.md)
issue #7 (gpt-oss boots but deviates from contract; qwen's relative-import layout never boots).

## Harness health this run

Clean sweep: single owner, `flock` held, all 16 node cells (8 repeats × 2 models) built and scored,
no checkout/serve failures, charts regenerated. The fixes from the N=3 post-mortem (dirty-tree scrub,
30-min serve readiness) held.

## Bottom line for the paper

Primary metric: **Bernoulli "produces a working app" success rate with Wilson CI**, not mean
pass-rate ranking. node: gpt-oss 1/8 [2-47%], qwen 2/8 [7-59%] — indistinguishable, both low. Pair
this with the N=1→N=3→N=8 ranking-inversion table as the headline methodological result: on a
high-variance one-shot generation task, low-N evals are not just noisy, they can rank the wrong model
first.

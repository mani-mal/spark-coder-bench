# Layer-2 N=3 results — high variance, low reliability, and why N=1 was misleading

> **⚠️ Superseded (2026-07-04):** these numbers are from the original L2 sweep, later found to run under a harness bug — the API contract was missing from the workspace (finding C1). L2 was re-run with the contract restored; see `2026-07-03-l2-rerun-with-contract-decision.md` for the corrected numbers and the before/after ablation. This note is retained as a historical record of the pre-contract measurement.


**Date:** 2026-06-25
**Scope:** Layer 2 (TaskFlow Local app build), N=3, gpt-oss-120b vs qwen3-coder-30b, node + python
tracks, fixed 29-check rubric. vLLM 0.15.1 on DGX Spark GB10. seed=0, decode temp=0.2.

## Headline

**Both models are unreliable at this end-to-end app-build task, and they are statistically
indistinguishable on the node track.** The N=1 snapshot (gpt-oss 0.69 vs qwen 0.00 on node) looked
like a decisive gpt-oss win — but that was a **sampling artifact**: it caught gpt-oss on a good run
and qwen on a bad one. N=3 shows the real picture.

| Model | Track | mean pass-rate | std | per-repeat | backend booted |
|---|---|---|---|---|---|
| gpt-oss-120b | node | **0.241** | 0.317 | 0.69, 0.03, 0.00 | 1/3 |
| gpt-oss-120b | python | 0.046 | 0.016 | 0.07, 0.03, 0.03 | 1/3 |
| qwen3-coder-30b | node | **0.218** | 0.309 | 0.00, 0.00, 0.66 | 1/3 |
| qwen3-coder-30b | python | 0.000 | 0.000 | 0.00, 0.00, 0.00 | 0/3 |

Energy (Wh/run, mean): gpt-oss node 4.8, gpt-oss python 6.7, qwen node 7.0, qwen python 13.1.

## What the variance actually is

The per-cell scores are **bimodal**: one repeat boots and scores ~0.65–0.69, the others score ~0.
This is genuine run-to-run variation in code generation, not harness noise — verified:

- `:4000` is free between runs; no leftover-process / port-collision artifact.
- Each zero-run fails for a **different real reason**, e.g.:
  - gpt-oss node-3: `MODULE_NOT_FOUND` (requires a module it didn't create).
  - gpt-oss node-2: builds a different entrypoint (`src/index.js` vs node-1's `server.js`), backend
    doesn't come up healthy.
  - qwen node-1: `ERR_MODULE_NOT_FOUND` (imports `sqlite` while declaring `sqlite3`).
  - the one working run per cell prints `Server is running on :4000` and scores ~0.65.

So each repeat the model emits a **structurally different app** (different entrypoints, deps, layout),
and only ~1 in 3 actually boots and implements enough of the contract to score. **The reliability of
producing a working full-stack app in one shot is the finding** — roughly a 1/3 success rate for
both models on node, 0–1/3 on python.

## Track asymmetry

Both models are much weaker on python than node:
- gpt-oss python boots once but the API deviates from the contract (login 422, `/auth/me` 404,
  projects unprotected).
- qwen python never boots (relative-import layout incompatible with the pinned `app.main:app` and
  with standard entrypoints — see harness issue #7).

## Methodological caveats for the paper

1. **N=3 is too few given this variance.** With a ~1/3 boot rate and bimodal scores, the cell means
   (0.24 vs 0.22) carry wide uncertainty and should not be reported as a ranking. Either raise N
   (≥5–10) for tighter intervals, or reframe the primary metric as a **Bernoulli "produces a
   working app" success rate** (gpt-oss node 1/3, qwen node 1/3, both python ~0/3) with confidence
   intervals, which matches what's actually being measured.
2. **seed=0 does not give determinism here.** Despite a fixed seed, repeats vary substantially —
   consistent with vLLM continuous-batching / floating-point nondeterminism. Disclose that runs are
   not bitwise reproducible; this is *why* repeats are necessary, not a bug.
3. **The N=1→N=3 reversal is itself a useful cautionary result**: single-shot local-model coding
   evals can mislead badly; repeats are mandatory.

## Bottom line

Don't claim "gpt-oss beats qwen." Claim: at temp=0.2 on a one-shot full-stack build, **both a 120B
MXFP4 MoE and a 30B bf16 MoE are unreliable (~1/3 working builds on node, worse on python), with
statistically indistinguishable node quality and high run-to-run variance** — a more honest and more
interesting result than the N=1 snapshot suggested.

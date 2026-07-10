# Layer-2 python N=8 — both models fail the python full-stack build outright

> **⚠️ Superseded (2026-07-04):** these numbers are from the original L2 sweep, later found to run under a harness bug — the API contract was missing from the workspace (finding C1). L2 was re-run with the contract restored; see `2026-07-03-l2-rerun-with-contract-decision.md` for the corrected numbers and the before/after ablation. This note is retained as a historical record of the pre-contract measurement.


**Date:** 2026-06-26
**Scope:** Layer 2 python track, N=8, gpt-oss-120b vs qwen3-coder-30b. Fixed 29-check rubric,
vLLM 0.15.1 on DGX Spark GB10. seed=0, temp=0.2. Extends the N=3 python result.

## Headline

**Neither model produces a single working python full-stack app in 8 attempts.** This was
suggestive at N=3; at N=8 it is a firm result.

| Model | mean pass-rate | std | working-app rate | Wilson 95% CI |
|---|---|---|---|---|
| gpt-oss-120b | 0.056 | 0.052 | **0/8 (0%)** | [0%, 32%] |
| qwen3-coder-30b | 0.000 | 0.000 | **0/8 (0%)** | [0%, 32%] |

gpt-oss scrapes tiny partial credit (≈0.06: a few static checks pass) but never boots a contract-
compliant backend; qwen scores a flat 0.000 across all 8. No working app from either.

## Reading

- **The python track is a floor, not a discriminator.** Both models are pinned at a 0% working-app
  rate with overlapping [0,32%] intervals — there is no signal separating them here. Report it as a
  shared failure, not a comparison.
- **Sharp asymmetry vs the node track.** Same models, same task, different language stack:
  node gives ~20–30% working-app rates (gpt-oss 0.252 / qwen 0.155 at N=20); python gives 0%/0%.
  The models are markedly better at the Node/TypeScript full-stack build than the Python/FastAPI one
  — a language-stack effect worth stating plainly.
- **Failures are genuine, not harness artifacts** (the python harness was hardened earlier: per-run
  venv for PEP 668, FastAPI entrypoint probing — see issue #7 in the harness log). gpt-oss boots but
  deviates from the API contract; qwen's relative-import layout never boots under any standard
  entrypoint. These are real spec-compliance failures.

## Caveats

- pass@8 with N=8 still has a wide CI ([0,32%]); "0% observed" does not prove "never," but 0/8 for
  both is strong evidence the one-shot python build is beyond these models at temp=0.2.
- The python track exercises a different contract surface than node; the asymmetry is a property of
  *these models on this task*, not a universal Python-vs-Node claim.

## Bottom line

Layer 2 python at N=8: **gpt-oss 0% and qwen 0% working-app rate** — a shared, unambiguous failure
and a strong language-stack asymmetry against the node track. Combined with node N=20 (gpt-oss
ahead, ns) and Layer 1 SWE-bench (gpt-oss ahead, ns), the full picture: gpt-oss is the nominally
stronger model on the tasks where either succeeds, no gap is yet significant, and both collapse on
the python build.

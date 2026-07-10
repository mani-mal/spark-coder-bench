# Layer 2 graded a contract the models could not see (C1) — rescore to k/25

**Date:** 2026-07-03
**Trigger:** Independent AI code review (`docs/audits/independent-code-review.md`, finding C1), verified against raw data.
**Status:** RESOLVED BY RERUN (2026-07-04). This note documents the original bug and the
zero-compute rescore mitigation; the bug was subsequently **fixed at the source** by restoring the
contract (app-repo `baseline-v7`) and re-running L2 — see
`2026-07-03-l2-rerun-with-contract-decision.md` for the corrected numbers and the before/after
ablation. The k/25 rescore below now applies to the archived pre-contract data.

---

## What happened

`layer2_appcase/prompt.md` instructs the model: *"Frozen API contract you MUST implement exactly:
`benchmark-spec/api-contract.md`."* That file was **never present** in the frozen app workspace
the L2 runs check out.

- The contract was added in the app repo (`taskflow-local-app-benchmark`) at commit `8b89ebd`,
  tagged **`baseline-v4`**.
- The L2 runner defaults to **`baseline-v6`**. `git merge-base --is-ancestor baseline-v4
  baseline-v6` **fails** — v4 is not on v6's lineage. The contract was added on a branch v5/v6
  never included, so it silently dropped out when the runner default moved v4 → v6.
- The harness never copies `api-contract.md` into the workspace, and the routes/keys are not
  inlined into `prompt.md`, `AGENTS.md`, or the OpenCode config.

So the model was told to implement a contract it was never given.

## Impact (verified empirically)

Four canonical checks assert *unguessable* contract specifics — exact routes, exact JSON key
sets, PATCH-vs-PUT, semantics the requirements prose does not pin down:

| check | group |
|---|---|
| `dashboard_summary_keys` | dashboard |
| `project_archive` | projects |
| `project_edit` | projects |
| `task_update_status` | tasks |

Across the **61** scored L2 runs (the runs that produced a 29-check array; 3 further runs errored
out before scoring), each of these four checks is present in **61/61** and passed in **0/61** —
for all three models. They are ≈4/29 ≈ 14% of the metric, and they are dead weight in every
denominator. The k/29 numbers therefore measure *contract inference from the requirements prose*
plus luck on exact routes, not acceptance against a *communicated* contract.

## Fix: dual-report k/29 and k/25 (no reruns)

The full per-check results are retained in every `results/raw/*-l2-*/rubric-score.json`, so the
reachable rate is recomputed deterministically without touching raw artifacts:

- `layer2_appcase/rubric_tests/contract.py` — `UNREACHABLE_WITHOUT_CONTRACT` names the four checks.
- `layer2_appcase/rubric_tests/run_rubric.py` — future runs emit `pass_rate_25`
  (`passed_reachable`/`total_reachable`), plus `contract_present` and a warning when the workspace
  lacks `benchmark-spec/api-contract.md`.
- `analysis/aggregate-runs.py` — carries `rubric_pass_rate_25` in `benchmark-long.csv`, computed
  from the stored per-check list.
- `results/summary/l2-rescore-25.csv` — per-cell k/29 vs k/25 with working-app counts on both.

### Rescored result

| model | track | N | mean k/29 | mean k/25 | working-app k/29 | working-app k/25 |
|---|---|---|---|---|---|---|
| gpt-oss-120b | node | 20 | 0.2517 | 0.2920 | 6/20 | 6/20 |
| gpt-oss-120b | python | 8 | 0.0560 | 0.0743 | 0/8 | 0/8 |
| qwen3-coder-30b | node | 20 | 0.1552 | 0.1895 | 4/20 | 4/20 |
| qwen3-coder-30b | python | 8 | 0.0000 | 0.0000 | 0/8 | 0/8 |
| nemotron-super | node | 4 | 0.0086 | 0.0100 | 0/4 | 0/4 |
| nemotron-super | python | 4 | 0.0000 | 0.0000 | 0/4 | 0/4 |

**The model ordering is preserved** (gpt-oss > qwen on node under both denominators), absolute
levels rise ~16–22% relative, and the **working-app counts are identical** on both denominators —
the ≥0.5 apps clear the bar with room to spare, so the Bernoulli "produces a working app" story is
robust to the rescore.

## On-thesis reading

This is a textbook instance of the paper's own thesis — *harness/validity errors dominate model
effects at local-eval scale*. A contract the graders enforced but the models never saw handicapped
all three models identically by four dead checks. It is reported as a case study, not hidden.

## Forward fix (only if L2 is ever rerun)

Cut a new app-repo tag whose tree actually contains `benchmark-spec/api-contract.md` and point the
runner at it (or have the harness copy the contract into the workspace / inline it into the prompt).
`run_rubric.py` now records `contract_present` so this condition self-discloses. Rerunning L2 with
the contract visible would turn C1 into a clean before/after ablation — the single most interesting
experiment this dataset now suggests.

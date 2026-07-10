# Nemotron-3-Super collapses on Layer-2 app-building (high variance, peak 1/29)

> **⚠️ Superseded (2026-07-04):** these numbers are from the original L2 sweep, later found to run under a harness bug — the API contract was missing from the workspace (finding C1). L2 was re-run with the contract restored; see `2026-07-03-l2-rerun-with-contract-decision.md` for the corrected numbers and the before/after ablation. This note is retained as a historical record of the pre-contract measurement.


**Date:** 2026-06-27
**Model:** nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4
**Runtime:** TensorRT-LLM 1.3.0rc9 (the only runtime that serves this MIXED_PRECISION checkpoint; see 2026-06-27-nemotron-trtllm-memory.md)
**Layer:** 2 (TaskFlow Local full-stack app build, node track)
**Driver:** OpenCode agent loop, pinned prompt, `apps/node-track/` only

## What we ran

Four independent node-track builds (`nemotron-super-trt-l2-node-{1..4}`), each a fresh
checkout of `baseline-v6`, full 3-source metric capture, scored by the pinned rubric
(29 checks: boot, auth, rbac, projects, tasks, comments, validation, dashboard,
frontend build, lockfile reproducibility).

## Result: no convergence, four distinct failure modes

| Run | Where it built | What it produced | Backend boot | Score |
|-----|----------------|------------------|:------------:|:-----:|
| 1 | repo **root** (`src/`, `package.json`, `test/` at top level) — ignored "build in `apps/node-track/` only" | full ~28-file app (controllers/models/routes/auth/tests), but TS won't compile: missing `@types/cors,helmet,morgan`, `../models.Task` import typo, `User` vs `IUser` export | ✗ | 0/29 |
| 2 | `apps/node-track/backend` ✅ | backend stub — `src/index.ts` only, no real implementation, no frontend | ✗ | 0/29 |
| 3 | created only `apps/` | essentially nothing under `apps/node-track/` | ✗ | 0/29 |
| 4 | `apps/node-track/backend` ✅ (+ a stray root `package.json`) | backend **booted** and answered `GET /api/health`; frontend missing `build` script | ✓ | **1/29** |

Aggregate: **{0, 0, 0, 1} / 29**, peak 1/29, the single passing check being `health_ok`.

## Interpretation

This is **not** a fixable harness or directory bug. If it were, the failure would be
consistent (e.g. "always builds at repo root"). Instead each run fails differently:
wrong location + non-compiling (run 1), right location but barely-started (run 2),
near-empty (run 3), right location + boots but incomplete (run 4). The variance *is*
the finding.

Nemotron-3-Super is a hybrid Mamba/attention **reasoning** model, NVIDIA-co-optimized,
not tuned for the long autonomous file-editing trajectory that OpenCode drives. It
passes the isolated tool-use gate (single `write_file` call, writes a correct
`fizzbuzz.py`) but cannot sustain the dozens-of-edits loop a full app build needs.
By contrast qwen3-coder-30b and gpt-oss-120b (vLLM) follow the directory instruction
and produce working apps at N=20.

Sanity gate (text coherence) and tool-use gate both PASS for this model — so this is a
capability boundary on *agentic app construction*, not a serving defect.

## Decision on run scale (for the TRT-LLM matrix)

- **Layer-2 TRT-LLM cells → N=5** (nemotron keeps these 4 node runs — outcome is
  floor-saturated, a 5th run buys nothing — plus N=4 python). The vLLM baseline already
  pins each model's Layer-2 pass-rate at N=20 node / N=8 python; the TRT-LLM cells exist
  to measure **runtime** effects (energy, throughput, TTFT, peak unified memory), which
  are low-variance, so N=5 is statistically adequate and avoids ~30h of redundant builds.
- **Layer-1 TRT-LLM → full 29-task SWE-bench-style suite ×1** per model×runtime, matching
  the vLLM Layer-1 design.
- **Ordering: model-contiguous** (all nemotron-TRT, then qwen-trt, then gpt-oss-trt) to
  minimize the crash-prone weight-load memory spikes (one per model swap).

## Layer-1 result (the other half of the split)

Full SWE-bench-Verified arm64 subset, 29 tasks ×1, OpenCode + TRT-LLM NVFP4:

**Nemotron-trt L1: resolved 6/29 (21%)** — empty-patch 15, attempted-but-failed 8.
Wins: django-10880, django-10914, matplotlib-13989, flask-5014, requests-1142, requests-1766.
(All four sympy tasks resolved=0.)

This is the key contrast with L2: the *same* model that scores peak ~1/29 on the L2 app build
lands ~21% of isolated single-file fixes on L1. It confirms the reasoning-model split — Nemotron
can produce minimal targeted patches but cannot sustain the long solo app-construction loop. Note
the absolute 21% sits well below Nemotron's vendor SWE-bench Verified (~59–60% on OpenHands/OpenCode
with their tuned scaffold); the gap is harness + 29-task-subset variance, not a defect — see
`2026-06-28-benchmark-comparability-and-pinchbench.md` and `2026-06-28-is-nemotron-result-fair.md`
for the full fairness review (sampling/parsers correct; PinchBench independently ranks gpt-oss
above Nemotron, corroborating our ordering).

### Operational notes (for reproducibility / methods section)

- **13h single-agent runaway:** task `pytest-dev__pytest-10081` hung the OpenCode agent for ~13h
  (wrote only forbidden test files, never returned), silently blocking the sweep at 20/29.
- **Fix — 30-min stuck-agent guard (`l1_guard2.sh`):** kills any agent alive >30 min so the suite
  advances and records the task unresolved. It subsequently auto-killed several more reasoning
  runaways (the sympy tasks repeatedly hit the cap). No single task can block the sweep again.
- **Transient DNS blip** dropped 4 sympy `git clone`s mid-run (`Temporary failure in name
  resolution`); re-run via the resumable suite (skips the 25 done) once network recovered.

## Reproduce

```bash
# Layer 2
PROVIDER=trt-local RUNTIME_TAG=trt METRICS_URL=http://127.0.0.1:8355/metrics \
  bash layer2_appcase/run-appcase.sh nemotron-super node 4
# Layer 1 (resumable)
PROVIDER=trt-local RUNTIME_TAG=trt METRICS_URL=http://127.0.0.1:8355/metrics \
  bash layer1_swebench/run-suite.sh nemotron-super 1 layer1_swebench/subset-verified.json
```
Scores land in `results/raw/nemotron-super-trt-l2-node-{1..4}/rubric-score.json` and
`results/raw/nemotron-super-trt-l1-*-1/resolved.json`.

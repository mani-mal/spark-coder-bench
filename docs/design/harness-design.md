# DGX Spark Coding-Model Benchmark Harness — Design Spec

**Date:** 2026-06-24
**Status:** Approved design (pre-implementation)
**Repo (measurement):** `dgx-spark-coding-model-benchmark`
**Repo (app under test):** `taskflow-local-app-benchmark`

## 1. Goal

A reproducible, publishable (GitHub + arXiv) performance comparison of two locally
served coding models on a single NVIDIA DGX Spark, driven by the OpenCode CLI agent
against a vLLM OpenAI-compatible endpoint. Two measurement layers:

- **Layer 1 (primary, quantitative):** executable code tasks scored automatically.
- **Layer 2 (case study, qualitative-but-automated):** one full-stack app build scored
  by an acceptance rubric implemented as automated tests.

Both layers are wrapped in the same three-source metric collection so hardware,
inference, and agent-accounting metrics are captured per task and joinable.

## 2. Hardware / platform reality (drives the design)

Probed on this box (2026-06-23/24):

- **Arch:** `aarch64` (ARM64 / GB10 Grace Blackwell, sm_121), 128 GB unified LPDDR5x, ~273 GB/s.
- **Unified memory:** `nvidia-smi` works, but with unified LPDDR5x it has no per-device VRAM to
  count, so its `memory.*` fields report `Not Supported`/`[N/A]` by design. The model's
  real footprint is read from `/proc/meminfo`. There is **no separate GPU-memory peak**.
- **DCGM:** `dcgmi` / `dcgm-exporter` NOT installed. **tegrastats:** NOT installed.
- **Docker:** present (v29.x) but current user hits permission denied; no qemu/binfmt registered.
- **vLLM:** already serving on `:8000` (API-key protected). ~107 GB unified memory in use.
- **Python 3.12**, git 2.43.

## 3. Decisions (confirmed with user)

1. **Layer 1 = ARM64-buildable subset of SWE-bench Verified**, not the full 500.
   Official SWE-bench Verified images are x86-64 only; no ARM64 image set exists and
   emulation is infeasible at scale. We run a curated subset whose task envs build
   natively on ARM64 and **document coverage honestly**. Build full infra + Layer 2 first.
2. **Sequential single-model serving on port 8000.** Nemotron 120B NVFP4 + Qwen 30B
   cannot co-reside in 128 GB. Serve one model → run its tasks → swap → serve the other.
   (The original prompt's dual 8001/8002 topology is not viable here.)
3. **Telemetry:** validated `nvidia-smi` + `/proc/meminfo` baseline is the guaranteed
   path; opportunistically add **DCGM** (bandwidth %, GPU power) and **tegrastats**
   (full-SoC power rails) if they install and work on GB10; degrade gracefully otherwise.

### FILL-IN variables (locked)

| Var | Value |
| --- | --- |
| `QWEN_MODEL` | `Qwen/Qwen3-Coder-30B-A3B-Instruct` |
| `NEMOTRON_MODEL` | `nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4` (project's "Nemotron", the Super reasoning model) |
| `N_REPEATS` | 3 (pilot) → final N driven by power analysis |
| `TASK_SAMPLE` | ARM64-buildable subset (size set by `select-arm64-subset.py`) |
| `VLLM_PORT` | 8000 (sequential) |
| `OPENCODE_BACKEND` | vLLM OpenAI-compatible endpoint at `http://127.0.0.1:8000/v1` |
| Serving | one model at a time |

## 4. Directory layout

```
dgx-spark-coding-model-benchmark/
  infra/
    vllm/serve-model.sh            # sequential serve on :8000; dumps EFFECTIVE config → manifest
    vllm/model-profiles/           # qwen / nemotron env, version-pinned (mirror dgx-coding-lab)
    metrics/collect-hw.sh          # nvidia-smi @250ms + /proc/meminfo; + DCGM dmon & tegrastats if present
    metrics/collect-vllm-prom.py   # scrape :8000/metrics → time series
    metrics/collect-opencode.py    # parse OpenCode session → tokens/turns/tools/failures/walltime
    metrics/clock-sync.py          # monotonic reference + cross-collector skew check
    metrics/run-context.sh         # start/stop all 3 collectors; write per-task window markers
    metrics/aggregate.py           # join 3 sources by epoch_ms; derive published metrics
  layer1_swebench/
    select-arm64-subset.py
    run-task.sh / run-suite.sh     # resumable/checkpointed
    eval/                          # official SWE-bench eval wrappers
  layer2_appcase/
    prompt.md                      # pinned identical prompt (references taskflow spec)
    rubric_tests/                  # acceptance tests written BEFORE the run
    run-appcase.sh
  analysis/
    stats.py                       # Wilson/beta-binomial CI, paired bootstrap + McNemar, power analysis, pass@k & pass^k
    figures.py                     # throughput, energy/task, TTFT dist, KV-vs-context, success-vs-energy Pareto
  manifests/                       # full run manifests for arXiv reproducibility
  results/raw/<model>-<layer>-<task>-<repeat>/   # per-run CSVs + manifest
  requirements.txt + environment.yml             # pinned versions
  harness/                         # existing probes fold into infra/metrics (collect-gpu-metrics.sh → collect-hw.sh)
  docs/  README.md
```

The three probes already built (`harness/collect-gpu-metrics.sh`, `stop-metrics.sh`,
`aggregate-gpu-metrics.py`) become the basis of `infra/metrics/collect-hw.sh` and the
aggregator; no duplicate hardware collector.

## 5. Metric collection — three synchronized sources

All collectors stamp every row with `epoch_ms`. They run on one host, so wall-clock
epoch is the join key; `clock-sync.py` records a monotonic reference and logs max skew
at startup. `run-context.sh` writes `task_start`/`task_end` epoch_ms per
(task, model, repeat) into `windows.csv`. `aggregate.py` slices each series to the
window and joins.

### a) Hardware (`collect-hw.sh`)
- **nvidia-smi @ 250 ms:** `utilization.gpu`, `utilization.memory`, `temperature.gpu`,
  `power.draw`/`.instant`/`.average`, `pstate`, `clocks.sm/gr`, throttle reasons, pcie link.
- **/proc/meminfo @ 250 ms:** unified memory used (the real footprint).
- **DCGM** (`dcgmi dmon`) if installed: SM activity %, memory-copy/bandwidth util, GPU power.
- **tegrastats** if installed: full-SoC power rails (CPU + LPDDR5x invisible to GPU counters).
- Reconcile DCGM/tegrastats with nvidia-smi where overlapping; manifest declares which is authoritative.

### b) Inference (`collect-vllm-prom.py`)
Scrape `:8000/metrics` (Prometheus) per task window: TTFT, prefill throughput (prompt tok/s),
decode throughput (gen tok/s), KV-cache usage % and size, running/waiting queue,
prompt+generation token counts, e2e request latency. Per-task values from window deltas;
TTFT/e2e distributions from histogram buckets (and vLLM request logs if enabled).

### c) Task accounting (`collect-opencode.py`)
From OpenCode headless sessions: total tokens, agent turns, tool calls, failed tool calls,
wall-clock per task. Parse OpenCode session storage; fall back to `opencode run` JSON output.

### Derived / published metrics (`aggregate.py`)
- Energy per task in **J and Wh** (trapezoidal ∫power·dt) **and** normalized **J/token + MJ/Mtok**.
- Energy attributed **separately to prefill vs decode** (phase timing from inference series).
- **Peak unified-memory** footprint.
- **TTFT distribution** p50/p90/p99.
- **Prefill vs decode throughput reported separately.**
- **KV-cache scaling vs context length.**
- **Tokens-per-joule.**
- Manifest declares **power-measurement level** (GPU-only vs full-SoC).

## 6. Layer 1 — SWE-bench Verified (ARM64 subset)

- `select-arm64-subset.py`: from `princeton-nlp/SWE-bench_Verified`, identify tasks whose
  containerized env builds/runs on ARM64; emit the subset + a coverage report.
- Per task: spin up the task's repo env → hand the issue to OpenCode (`opencode run` → vLLM)
  → produce a patch → apply → run **official SWE-bench evaluation** (FAIL_TO_PASS /
  PASS_TO_PASS) → resolved/not. **No human judgment.**
- Every task × both models × `N_REPEATS`, wrapped in 3-source metrics.
- Output: one tidy long-format CSV (`task_id, model, repeat, resolved`, + all metrics) plus
  a mean±std summary per model.
- **Resumable/checkpointed**: completed (task, model, repeat) cells are skipped on restart.
- README: SWE-bench Verified was deprecated by OpenAI (Feb 2026) over contamination, but is
  valid here as a **relative A/B on identical hardware** (contamination cancels across models);
  plus the ARM64 subset coverage statement.

## 7. Layer 2 — full-stack app build case study

- Single realistic task = the TaskFlow Local app (REST backend + frontend + endpoints).
  **Pinned exact prompt** in `prompt.md`, identical for both models (references the frozen
  `taskflow-local-app-benchmark` spec).
- **Acceptance rubric written as automated tests BEFORE the run** (`rubric_tests/`): backend
  boots, each endpoint returns expected status/shape, frontend builds and renders, integration
  test passes. **Score = checklist pass-rate**, run identically for both models. Subjective
  notes captured separately.
- `N_REPEATS` per model, same 3-source metrics. Framed as **illustrative case study**, not
  primary evidence. Each run starts from the app repo's frozen baseline tag on a fresh branch.

## 8. Statistical rigor (both layers, in `analysis/stats.py`)

- Success rate as an **estimate**: pass@1 as mean over N runs with **Wilson or beta-binomial**
  CIs (not Wald/CLT).
- **Paired significance** before any "better" claim: paired bootstrap or **McNemar** on
  per-task pass/fail; report p-value + effect size.
- **Power analysis up front**: given expected effect size and observed per-task variance,
  compute required N; this **drives** `N_REPEATS`.
- Report **pass@k and pass^k** (k>1) to separate "can solve" from "reliably solves".
- **Pin and log sampling temperature** for both models; do not assume temp=0 removes
  run-to-run variance.

## 9. Analysis & figures (`analysis/figures.py`)

Published figures: prefill/decode throughput, energy-per-task, TTFT distributions,
KV-cache-vs-context, peak memory, and **success-rate-vs-energy Pareto**.

## 10. Reproducibility deliverables

- **Run manifest** per run capturing ALL configs: model id + revision/quant, vLLM version +
  effective serving config + seed, OpenCode version + config + seed, driver/CUDA, DCGM version
  (if any), DGX OS version, sampling temperature, dataset commit, power-measurement level.
- **Pinned** `requirements.txt` + `environment.yml`.
- One top-level command per layer, end-to-end and **resumable**.

## 11. Framing note (writeup, not code)

Central hardware hypothesis around Spark's 273 GB/s bandwidth: **decode is
memory-bandwidth-bound and dominates inference time; prefill is compute-bound.** Expect
prefill-heavy vs decode-heavy tasks to favor different models; include at least one analysis
cut along this axis.

## 12. Build order (incremental — validate on ONE task before scaling)

1. `infra/` (sequential serve + config manifest) and `infra/metrics/` (all 3 collectors +
   clock-sync + run-context + aggregate), evolving the existing probes. Validate the full
   3-source join on **one trivial task** end-to-end.
2. Layer 2 app-case (rubric tests + runner). Validate **one** run + score + metrics.
3. Layer 1: `select-arm64-subset.py` → single task end-to-end → resumable suite.
4. `analysis/stats.py` + `figures.py`.
5. Manifests + pinned envs + README + **OpenCode run instructions** for the user.

## 13. Known risks / open items

- DCGM and tegrastats may not support GB10; baseline (nvidia-smi + /proc/meminfo) must
  always work without them.
- ARM64 SWE-bench subset may be small; coverage stated explicitly, no silent truncation.
- OpenCode session storage format must be confirmed during step 1 (fallback: JSON output).
- Docker permissions must be resolved (user in `docker` group or sudo) for Layer 1 + any
  containerized vLLM.
- Per-request TTFT precision depends on vLLM logging config; Prometheus histograms are the
  fallback.

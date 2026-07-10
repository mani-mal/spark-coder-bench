# Methodology

> **Canonical protocol lives in [`HELP.md`](HELP.md).** This file covers fairness controls and
> the per-run metric catalogue. Where the two ever disagree, HELP.md wins. The study is a
> **three-layer systems + methodology case study** (L1 SWE-bench subset, L2 TaskFlow app build,
> L3 LiveCodeBench), **not** a model-ranking paper — each arm couples a model with a runtime,
> quant, and scaffold, so results describe deployment *configurations*. See the reframing
> decision in [`findings/2026-07-02-external-audit-verification-and-decision.md`](findings/2026-07-02-external-audit-verification-and-decision.md).

## Goal

Characterize how local coding-model **configurations** behave across three layers on a single
DGX Spark — serving feasibility, task success, and efficiency — and report results reproducibly.
Layer 2 (the focus of the metric catalogue below) has each model build the same realistic
full-stack application (**TaskFlow Local**) from an identical frozen specification.

## What is held constant

- **Spec**: `benchmark-spec/` (requirements, expected output, run protocol, rubric).
- **Prompt**: the track prompt in `prompts/` (`build-node-track.md` / `build-python-track.md`).
- **Starting state**: every reported L2 run starts from the app repo's `baseline-v7` tag — the
  contract-visible baseline restored after the C1 lineage break (`baseline-v4`→`v6` had dropped
  `api-contract.md`, so the first sweep was graded against a contract the model could not see).
  See `findings/2026-07-03-l2-contract-invisible.md`.
- **Hardware**: one DGX Spark, same configuration for all runs.
- **Serving**: vLLM for gpt-oss and Qwen; **TRT-LLM for Nemotron** (its NVFP4 MIXED_PRECISION
  checkpoint does not load in vLLM). No model serves on both runtimes — a disclosed confound,
  not a free variable. Settings recorded per model in the run manifest.
- **Time box**: same budget per model per track (see `run-protocol.md`).
- **Agent harness**: OpenCode, same version and config, for every model.

## What varies

- The model under test: **gpt-oss-120b**, **Nemotron-3-Super-120B-A12B**, and
  **Qwen3-Coder-30B-A3B** — three MoE models spanning a sparsity spectrum
  (active/total = 4.4% / 10.0% / 10.8%). Defined in `infra/models.json`.
- The track (Node.js backend vs Python/FastAPI backend).

> DeepSeek-Coder-V2-Lite was evaluated and **retired** before timed runs: it generates
> correct code but does not autonomously call tools, so it cannot drive the agent loop.
> Replaced by gpt-oss-120b after the autonomous-tool-use gate (below). See
> `docs/findings/2026-06-24-deepseek-v2-lite-agentic-tool-use.md`.

### Disclosed confounds (cannot be equalized)

- **Quantization + runtime**: gpt-oss MXFP4 (vLLM), Nemotron NVFP4 (TRT-LLM), Qwen bf16 (vLLM).
  Nemotron only fits as NVFP4; Qwen has no validated NVFP4 checkpoint. The two 4-bit MoEs run on
  **different runtimes**, so the design **cannot** separate a model effect from a generic
  FP4-on-Blackwell effect — that needs a matched-model or factorial comparison and is out of
  scope here. Quant, runtime, and scaffold are all confounded with model identity.
- **FP4 is weight-only where it runs on vLLM**: gpt-oss's FP4 path uses vLLM's Marlin
  weight-only kernel — GB10/SM121 has no native FP4 *compute* — so any FP4 benefit is
  storage/bandwidth, not tensor-core math (recorded per model in the manifest).
- **max_model_len / gpu_memory_utilization** differ under the 128GB unified-memory limit.
- Held identical: seed, temperature, KV-cache dtype, `max_num_seqs`, OpenCode/vLLM versions.

### MoE / sparsity instrumentation

- Per-model **total vs active params** recorded in every run (`model` block) so decode
  throughput and tokens-per-joule can be normalized against both — the gap between
  per-total and per-active is a headline result.
- **Memory-controller utilization %** (`nvidia-smi utilization.memory`) is logged as the
  bandwidth-pressure proxy (true GB/s needs DCGM, not installed on this host — declared
  in the manifest as `bandwidth_source`).
- **Expert counts** verified from each model's `config.json` into the manifest.
- **MoE residency**: manifest records that no `--cpu-offload-gb` is used (all experts
  resident in unified memory) — the sparse-activation analysis depends on it.

### Correctness gates (before any timed run)

- **SM121/FP4 sanity check** (`infra/vllm/sanity-check.py`): a fixed prompt must produce
  coherent, non-repeating output; a failed check ABORTS the run rather than recording
  garbage metrics. Result logged per model in the serve manifest.
- **Autonomous tool-use gate**: before timed agentic runs, a model must (1) return a
  non-null, well-formed `tool_calls` from a direct vLLM request with `tool_choice:"auto"`
  (not prose, not hallucinated tool-output tokens) and (2) actually create a file on disk
  in an OpenCode smoke. A model that needs `tool_choice:"required"` to act fails this gate
  and is reported as a non-agentic baseline, not scored as if it tried. This is the gate
  DeepSeek-V2-Lite failed and gpt-oss-120b passed; rationale in `docs/findings/`.

## Metrics captured per run

Recorded into `results/raw/<model>-<track>/`. Grouped by purpose.

### A. Run identity & configuration (reproducibility — recorded once per run)

- Run id: `<model>-<track>-<seq>` (seq = repeat index)
- Model name + HF revision/commit hash; quantization (e.g. NVFP4)
- Track (node / python)
- Agent harness + version (OpenCode version)
- Serving stack: vLLM version, container image tag
- Decoding params: temperature, top_p, top_k, **seed**, max_model_len, max_tokens
- vLLM serving config: gpu_memory_utilization, max_num_seqs, max_num_batched_tokens
- Hardware: DGX Spark model, driver version, CUDA version
- Date/time, time box used

### B. Latency & throughput

- Time to first token (TTFT)
- Output (decode) throughput, tokens/sec
- Prefill throughput, tokens/sec (if available)
- Inter-token latency: median and p95
- Total wall-clock time for the run
- Total model generation (compute) time vs idle/tool time

### C. Token economics

- Input/prompt tokens (cumulative across all turns)
- Output/completion tokens (cumulative)
- **Reasoning tokens** (separate, for reasoning models like Nemotron Super)
- Prefix/KV-cache–hit tokens (if reported)
- Total tokens; tokens per turn

### D. Agent behavior & efficiency

- Number of agent turns
- Tool calls by type (read / edit / write / bash / list), with success/failure counts
- File edits; retries / self-corrections
- Manual interventions (count + category from `run-protocol.md`)
- Instruction-following: did it read the required spec files before coding? (y/n)
- Stopped appropriately vs overran the time box / got stuck in a loop
- Hallucinated/nonexistent packages or APIs referenced (count)

### E. Output quality & correctness (objective)

- Requirements satisfied / partial / missing (count, against an explicit checklist)
- Lines of code added (frontend / backend); file count by type
- Dependencies install: pass/fail
- Frontend build & typecheck: pass/fail (+ error count)
- Backend starts: pass/fail
- Tests: total / passing / failing; pass rate
- Code coverage % (if tooling available)
- Lint / type-error count
- Runtime crashes during a basic end-to-end smoke workflow (count)
- Security checks: passwords hashed (y/n), hardcoded secrets (count), protected routes (y/n)

### F. Layer 2 acceptance score

- **TaskFlow API acceptance-check fraction (k/29)**: the fraction of the 29 equally-weighted,
  fully-automated HTTP contract assertions in `layer2_appcase/rubric_tests/contract.py`
  (`CANONICAL_CHECKS`) that pass, scored against a fixed 29-check denominator.
- This is an **API-acceptance signal, not full-stack app quality**. The weighted 100-point
  rubric in `evaluation-rubric.md` is a *design artifact that was never implemented*; it is
  retained only as historical spec. What is and isn't covered by the 29 checks is enumerated in
  [`../layer2_appcase/COVERAGE.md`](../layer2_appcase/COVERAGE.md).

### G. Resource & energy

Captured by `infra/metrics/collect-hw.sh` (time series) + `infra/metrics/aggregate.py` (summary), wrapped per task by `infra/metrics/run-context.sh`.

- Peak / mean **unified (system) memory** used, and growth over baseline — from `/proc/meminfo`
- GPU utilization (mean / peak); GPU memory-controller utilization (mean / peak)
- GPU power draw (mean / peak) and **integrated energy (Wh)** over the run (trapezoidal)
- GPU temperature (peak), SM clock (mean), pstate, throttle reasons, PCIe link gen/width
- Energy per completed requirement / per passing test (efficiency proxy)

> **DGX Spark (GB10) caveat:** memory is **unified**, so `nvidia-smi` reports all `memory.*`
> fields as `[N/A]`. There is **no separate GPU-memory peak** on this hardware — the model's
> memory footprint appears as host RAM in `/proc/meminfo`, which is what we record. Disclose
> this in the report so the memory figure is not mistaken for dedicated VRAM. The sampler must
> be started **before** the build and stopped **after** it; a run started mid-build yields only
> a partial timeline and must be flagged as such.

### H. Reliability & variance (across repeated runs)

- N repeats per (model, track) — **recommend N ≥ 3**
- Mean ± std (or median + IQR) for every quantitative metric above
- Count of failed / abandoned runs, timeouts, crashes
- Determinism note (seed + temperature settings used)

## Scoring

Scoring is **fully automated and mechanical** — no human scorers and no LLM judge are used at
any layer (the earlier two-scorer / LLM-judge plan below the fold in `evaluation-rubric.md` was
not adopted; if it is ever restored it must be preregistered with blinding and agreement stats):

- **L1**: OpenCode's patch is applied and the repo's own gold test suite (FAIL_TO_PASS /
  PASS_TO_PASS) runs in Docker via the official SWE-bench harness. Resolved = pass@1.
- **L2**: `layer2_appcase/rubric_tests/run_rubric.py` boots the built app and fires 29 fixed
  HTTP assertions against the pinned contract → acceptance-check fraction (k/29). Equal weight
  per check; no subjective sections are scored.
- **L3**: `lcb_runner` executes each single-shot solution against LiveCodeBench hidden tests →
  pass@1 with Wilson 95% CI.

Because scoring is deterministic given the artifacts, runs can be rescored from retained
outputs; the coverage matrix ([`../layer2_appcase/COVERAGE.md`](../layer2_appcase/COVERAGE.md))
documents exactly what the L2 checks do and do not establish.

## Statistical treatment

- Run each (model, track) condition **N ≥ 3** times; report mean ± std (or median + IQR).
- For headline comparisons, report effect sizes and, where N permits, a significance
  test or bootstrap confidence interval — do not over-claim from a single run.
- State N explicitly in every table; never present a single run as the result.

## Fairness controls

- Same baseline, prompt, hardware, time box, and harness for every run.
- All manual interventions are logged and counted against agent-efficiency.
- an AI coding assistant never edits model-generated app code; it only measures and reports.
- Differences in serving settings that could not be equalized are disclosed in the report.

## Reproducibility

- The spec and prompts are frozen and version-controlled (master copies live here).
- Each L2 run is an isolated git branch in the app repo, started from `baseline-v7`
  (the contract-visible baseline; see the C1 note above).
- Harness scripts are idempotent so summaries and charts can be regenerated from raw data.

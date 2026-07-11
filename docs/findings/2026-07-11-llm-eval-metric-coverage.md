# LLM-eval metric coverage map — what we capture vs. the full taxonomy

**Date:** 2026-07-11
**Trigger:** `docs/llm_eval.txt` (a 12-category LLM-eval metric taxonomy) — *"find what we already have; if a metric is missing add it; ignore metrics we don't need."*
**Status:** Coverage mapped. One genuinely-missing-but-derivable metric (**quality-adjusted efficiency**) was computed and added (`analysis/quality-adjusted-efficiency.py`; also in the perf-resource doc). Everything else is marked have / raw-not-surfaced / out-of-scope with a reason.

---

## How to read the status column

| Status | Meaning |
|---|---|
| ✅ **Have** | Captured *and* surfaced in a doc/CSV |
| 🟡 **Raw** | Captured in a raw stream (`hw.csv`, `vllm-metrics.csv`) but not yet aggregated — cheap to surface if wanted |
| ➕ **Added** | Was missing; computed and added in this pass |
| ⬜ **N/A** | Out of scope *by design* for this study (see scope box) and correctly omitted |
| ❌ **Gap** | Not captured and arguably worth it — flagged, not dismissed |

**Study scope (what makes whole categories N/A):** one DGX Spark, **one GB10 GPU** (no multi-GPU / NVLink / tensor-pipeline parallel); **self-hosted** (no per-token dollar price → energy is the cost proxy); **single-/low-concurrency** static offline benchmark (mostly `seq=1`; not a serving-load / goodput study). Runtimes: gpt-oss & qwen on **vLLM** (full Prometheus), nemotron on **TensorRT-LLM** (no Prometheus → no inference-side telemetry — the standing asymmetry).

Primary sources referenced below: `results/raw/<run>/run-summary.json`, `hw.csv`, `vllm-metrics.csv`; `results/summary/*-run-ledger.csv`; `results/summary/perf-resource-summary.csv`; the perf-resource doc (`2026-07-11-cross-model-performance-resource-usage.md`).

---

## 1. Core latency

| Metric | Status | Source / note |
|---|---|---|
| TTFT | ✅ | `run-summary.inference.ttft_seconds` p50/p90/p99 (vLLM only) |
| Queue time | 🟡 | `vllm:num_requests_waiting` gauge captured (queue depth); explicit per-request queue-time histogram not surfaced. Near-zero at our concurrency |
| Prefill latency | ✅ | `prefill_time_s` |
| Prefill throughput | ✅ | `prefill_throughput_tok_s` (16k–86k tok/s) |
| TPOT | 🟡 | = mean ITL / (1 ÷ decode tok/s); we surface **ITL** + **decode tok/s** instead. Derivable, not separately printed |
| Inter-token latency (ITL) | ✅ | `vllm:inter_token_latency_seconds` p50/p90/p99 |
| Decode throughput | ✅ | `decode_throughput_tok_s` (~20–31 tok/s; the headline bandwidth-bound number) |
| End-to-end latency | ✅ | `e2e_latency_seconds` p50/p90/p99 |
| p50 / p99 | ✅ | computed for TTFT/e2e/ITL |
| **p95** | ➕ Added | now computed (TTFT + e2e) from the raw histograms — `analysis/latency-tail-p95.py` → `results/summary/latency-tail-p95.csv`; also made first-class in `aggregate.py` (`hist_quantiles` default now includes 0.95). e.g. L1 gpt-oss TTFT p95 **4.88 s**, e2e p95 **17.75 s** |

## 2. Throughput & capacity

| Metric | Status | Note |
|---|---|---|
| Output tok/s per request, aggregate tok/s, input tok/s, total tok/s | ✅ | from prompt/generation token counters + decode/prefill throughput |
| Requests/sec | 🟡 | derivable from `requests_succeeded` / window; not surfaced (single-stream, not meaningful) |
| Concurrent requests | ✅ | `num_requests_running` gauge (mean ~0.9 at L1 — confirms single-stream) |
| Batch size / iteration tokens | 🟡 | `vllm:iteration_tokens_total` captured raw; not aggregated |
| **Max sustainable concurrency / batching efficiency / goodput** | ⬜ N/A | not a serving-load study; we never swept concurrency to find the knee (except nemotron L3 8-way, for tractability). Deliberate scope cut |
| Tokens per GPU-second | ✅ | `tokens_per_joule` + energy phase split give the equivalent; GPU-time = wall-clock on 1 GPU |
| **Successful tasks/hour** | ➕ Added | `quality-adjusted-efficiency.csv` (L1: gpt-oss 8.4, qwen 6.7, nemotron 0.41 tasks/h) |

## 3. GPU performance

| Metric | Status | Note |
|---|---|---|
| GPU utilization | ✅ | `gpu_util_pct` |
| SM clock / graphics clock | ✅ | `sm_clock_mhz` (+ `gr_clock_mhz` in `hw.csv`) |
| Power consumption | ✅ | `gpu_power_w` (GPU-only via nvidia-smi; DCGM/tegrastats absent → understates full-SoC, consistent across models) |
| Temperature | ✅ | `gpu_temp_c` |
| **Thermal throttling** | 🟡 | `throttle_active_hex` captured in `hw.csv`, not aggregated. Temps 51–70 °C → no evidence of throttle; worth a one-line confirmation |
| PCIe bandwidth | 🟡 | `pcie_gen` / `pcie_width` captured raw; unified-memory SoC so PCIe transfer isn't the LLM data path |
| **Memory bandwidth utilization** | ❌ Gap (unfixable here) | the decisive metric for decode, but **DCGM not installed** → only the nvidia-smi `mem_util_pct` proxy exists and reads ~0. Our bandwidth-bound claim rests on *throughput* + architecture, not a measured BW%. Documented limitation (report §2/§6). Closing it needs DCGM/tegrastats |
| **Sustained/peak TFLOPS, Tensor-Core util, kernel time/launch overhead** | ⬜ N/A | kernel-level profiling (Nsight) is out of scope for a model-comparison bench; would need per-kernel tracing, not sampled counters |

## 4. Memory

| Metric | Status | Note |
|---|---|---|
| Peak memory (allocated) | ✅ | `unified_mem_peak_mib` (~106–115 GiB of 128) — perf-resource doc |
| Host RAM usage / swap | 🟡 | `host_mem_*_kib` + `cpu_load1` captured in `hw.csv`; not aggregated. Unified memory blurs host/GPU on GB10 |
| **Weight vs KV vs activation vs runtime breakdown** | 🟡 Partial | we have **total** unified peak, not the decomposition. Weight memory is analytically estimable (params × bytes/param; quant is in `run-summary.model`) — e.g. gpt-oss 116.8B @ mxfp4. See `2026-06-27-nemotron-trtllm-memory.md`. Adding an analytic weight/KV split is a reasonable enhancement |
| Fragmentation / reserved vs allocated | ❌ Gap | not captured; needs allocator-level (torch/TRT) introspection. Low value for a fixed offline bench |
| OOM rate | 🟡 | no per-request OOM counter, but OOM *incidents* are logged narratively (report §7 degraded-box) and gated by `is_model_valid`/`exit_code` |
| Memory headroom | ✅ | 128 GiB − peak (~13–22 GiB headroom); implicit in the peak column |

## 5. KV-cache

| Metric | Status | Note |
|---|---|---|
| Total KV-cache usage / utilization % | ✅ | `kv_cache_usage_perc` (0.6–5.8 % — never KV-bound) |
| Prefix-cache hit rate | ✅ | `prefix_cache_hit_rate` (~0.95 at L1) + raw `vllm:prefix_cache_hits/queries` |
| KV bytes/token, KV per request | 🟡 | analytic (formula in `llm_eval.txt` §5); architecture-specific. Covered conceptually in `2026-06-30-kv-cache-quant-unified-memory.md` |
| KV quantization impact | ✅ | nemotron TRT fp8 KV documented (`2026-06-30-…`, `infra/models.json` M17) |
| Eviction rate / fragmentation / paged-KV / offload | ⬜ N/A | never approached KV pressure (usage <6 %), so eviction/paging/offload never triggered — nothing to measure |

## 6. Context-window

| Metric | Status | Note |
|---|---|---|
| Max supported / usable context | ✅ | per-model serve config (`infra/models.json`); L3 uses 8192-token generation budget |
| **Context truncation rate** | ✅ | the L3 result itself: nemotron 185/512 no-code (143 empty + 42 no-extract), difficulty-correlated. See `2026-07-03-l3-conditional-selection-bias.md` + `2026-07-11-l3-token-budget-and-verbosity-options.md` |
| Long-context TTFT / memory per +1k tokens | 🟡 | derivable from paired prompt-length × TTFT in raw data; not swept as a dedicated curve |
| **Needle-in-haystack, effective context, position sensitivity, long-ctx degradation** | ⬜ N/A | this is a *coding-agent* benchmark, not a long-context retrieval study. Out of scope by design |

## 7. Model quality (general)

| Metric | Status | Note |
|---|---|---|
| Pass@1 | ✅ | L3 LiveCodeBench (gpt-oss 89.3 / qwen 68.2 / nemotron 61.3) |
| Exact match / accuracy | ✅ | L1 SWE-bench resolved is exact (tests pass); L2 is contract acceptance |
| Tool-call success rate | 🟡 | `tool_calls` counted per run; qualitative tool-use failure documented (`deepseek-agentic-tool-use-failure` memory). No clean pass/fail per call |
| Structured-output validity | 🟡 | L3 "no-extractable-code" (42) is a malformed-output signal; not a general schema-validity rate |
| Consistency (repeat runs) | ❌ Gap | mostly `repeat=1`; L3 is single-shot pass@1 (n=512 problems, not n-repeats/problem). Variance across repeats not measured — a real limitation for the agentic layers |
| Pass@k / human-preference / LLM-judge / factuality / hallucination / groundedness / citations / calibration / refusal / safety | ⬜ N/A | not applicable to a deterministic coding-benchmark (no judge, no RAG, no safety suite). Correctly omitted |

## 8. Coding-model metrics (the relevant core)

| Metric | Status | Note |
|---|---|---|
| Unit-test pass rate | ✅ | L1 SWE-bench (FAIL_TO_PASS), L2 k/29 acceptance checks |
| Pass@1 | ✅ | L3 |
| Repository task success rate | ✅ | L1 resolved rate (real repos, ARM64 subset) |
| Issue resolution rate | ✅ | = L1 resolved |
| **Regression rate** | ➕ Added | SWE-bench PASS_TO_PASS collateral damage now aggregated — `analysis/regression-rate.py` → `results/summary/regression-rate.csv`. Of applied L1 patches: gpt-oss **33.3%** / qwen 31.8% / nemotron 21.4% regress ≥1 passing test (gpt-oss broke 1078 PtP tests vs nemotron 3). Parsed from retained `logs/run_evaluation/*/report.json` — no re-run |
| Compilation/run success rate | 🟡 | L2 check #28 `frontend_build`; L3 code-extractability. No uniform per-layer compile rate |
| **Time / tokens / cost to successful solution** | ➕ Added | `quality-adjusted-efficiency.csv` — GPU-min per success + energy per success. Tokens-to-solution derivable from accounting (not yet aggregated) |
| Iterations / human-intervention count | 🟡 | `agent_turns` is null (collect-opencode field unmatched); `tool_calls` present. Runs were unattended (0 human interventions by design) |
| Static-analysis / security-defect / unnecessary-change / doc-quality / code-review-acceptance | ⬜ N/A | not scored — this was the unimplemented 100-pt rubric; L2 COVERAGE.md explicitly scopes these out |

## 9. Scalability — ⬜ **entirely N/A**

Single GB10, single replica. Multi-GPU scaling, tensor/pipeline-parallel efficiency, NVLink/interconnect, load-balancing, replica utilization, autoscaling, cold-start-of-Nth-replica — **none apply**. The one concurrency data point we have is nemotron L3 run 8-way parallel (tractability, not a scaling study). Cold-start / model-load time (§11) is the only scalability-adjacent metric worth a note; not currently captured per-run.

## 10. Cost & energy

| Metric | Status | Note |
|---|---|---|
| Average / peak power draw | ✅ | `gpu_power_w` mean + `hw.csv` peaks |
| Joules per token | ✅ | `energy.j_per_token` / `tokens_per_joule` |
| GPU-hours per workload | ✅ | wall-clock on 1 GPU = GPU-hours (perf-resource doc totals) |
| **Energy per successful task** | ➕ Added | the taxonomy's recommended *final* metric. `quality-adjusted-efficiency.csv`: L1 gpt-oss **12.8 kJ**/solve vs nemotron **143 kJ**/solve (~11×) |
| Idle power cost / utilization-adjusted cost | 🟡 | idle draw visible in `hw.csv` tails; not isolated |
| **$-denominated cost** (per-Mtok, per-request, per-task, tokens/$) | ⬜ N/A | self-hosted, no serving price. **Energy is our cost proxy** throughout — this is a deliberate substitution, stated in the report |

## 11. Reliability & operational

| Metric | Status | Note |
|---|---|---|
| Request/task success rate | ✅ | ledger `outcome` + `is_model_valid` |
| Error / exit-code | ✅ | `exit_code` per run; `infra_missing` / `watchdog_kill` outcomes recorded (L1: 8 infra_missing + 1 watchdog_kill) |
| Output truncation rate | ✅ | L3 185/512 (the central L3 finding) |
| Malformed-output rate | 🟡 | L3 42 no-extractable-code; not generalized to a JSON/tool malformed rate |
| Timeout / OOM / crash / restart | 🟡 | narratively documented (report §7 degraded-box, TRT wedge); not per-run counters |
| Model load time / cold-start | ❌ Gap | in vLLM/TRT startup logs, not captured per-run. Minor for an offline bench |
| Performance variance | 🟡 | cross-run spread visible (dur min/max in perf-resource doc; the nemotron L1 13 h runaway) but no formal variance metric — tied to the consistency gap (§7) |
| Availability / MTBF / MTTR | ⬜ N/A | not a production-uptime study |

## 12. CPU / storage / network

| Component | Status | Note |
|---|---|---|
| CPU utilization | 🟡 | `cpu_load1` in `hw.csv`; per-core / tokenizer-time not broken out |
| System RAM / swap | 🟡 | `host_mem_*` in `hw.csv` |
| Storage (model-load speed, IOPS) | ⬜ N/A | one-time weight load, not in the measured window |
| Network / inter-node | ⬜ N/A | single node, loopback API |
| Inference-engine scheduling/batching overhead | 🟡 | `num_preemptions`, queue depth captured raw; not analyzed |

---

## The taxonomy's "recommended minimum" checklist — our status

| Category | Minimum asked | Status |
|---|---|---|
| Configuration | model, params, precision, quant, engine | ✅ `run-summary.model` + `infra/models.json` + `gpu-static.txt` (driver/CUDA/GB10) |
| Workload | prompt/output tokens, context, temperature | ✅ token counters + serve config (temp 0.2, budget 8192) |
| Latency | TTFT, TPOT, e2e, p50, **p95** | ✅ (p95 added — p50/p90/**p95**/p99) |
| Throughput | input/output/aggregate tok/s | ✅ (vLLM models) |
| Capacity | batch size, concurrency, max usable ctx | 🟡 concurrency ~1 recorded; batch raw; ctx from config |
| GPU | util, mem used, **mem bandwidth**, power | ✅ except **bandwidth %** (no DCGM) |
| Memory | weight, KV, peak, fragmentation | 🟡 peak+KV ✅; weight analytic; fragmentation ❌ |
| Quality | unit-test pass, pass@1, compile, **regression** | ✅ pass/pass@1; 🟡 compile; **regression ➕ added** |
| Agent | tool calls, iterations, time/tokens to solution | 🟡 tool_calls ✅; iterations weak; **time/energy-to-solution ➕ added** |
| Reliability | errors, timeouts, OOMs, malformed | ✅ errors; 🟡 timeouts/OOM narrative; 🟡 malformed (L3) |
| Cost | GPU-hours, energy, cost/task, **cost/successful task** | ✅ energy proxy; **energy/successful-task ➕ added** |

## What was added vs. what's a real gap

**➕ Added (had the inputs on disk, weren't surfaced — all no-re-run):**
- **Quality-adjusted efficiency** — energy / GPU-minutes / tasks-per-hour **per successful task** (`analysis/quality-adjusted-efficiency.py`). The taxonomy's recommended final comparison: nemotron's per-solve energy is ~11× gpt-oss at L1.
- **p95 tail latency** (TTFT + e2e) — `analysis/latency-tail-p95.py` from the raw histograms; also made first-class in `aggregate.py`.
- **Regression rate** (SWE-bench PASS_TO_PASS collateral damage) — `analysis/regression-rate.py` from retained eval reports: gpt-oss 33.3% / qwen 31.8% / nemotron 21.4% of applied patches regress ≥1 passing test.

**❌ Genuine gaps remaining (ranked):**
1. **Memory-bandwidth utilization** — the one metric that would *directly* prove the decode-bound claim; blocked on DCGM/tegrastats not being installed. Highest scientific value, needs infra (a re-run under DCGM), not just re-aggregation.
2. **Cross-run consistency / variance** — mostly single-run per task; no repeat-based variance for the agentic layers. Matters for how much to trust a single L1/L2 number. Closing it *does* need re-runs (N≥3 repeats).

**⬜ Correctly ignored (out of scope, not deficiencies):** all of §9 scalability (single GPU), $-denominated cost (self-hosted → energy proxy), goodput/max-concurrency (offline bench), long-context retrieval quality (§6 tail), and the general-LLM quality metrics in §7 (judge/factuality/safety/RAG) that don't apply to a deterministic coding benchmark.

## Related
- `docs/findings/2026-07-11-cross-model-performance-resource-usage.md` (the consolidated perf/resource table this map cross-references)
- `layer2_appcase/COVERAGE.md` (why static-analysis / UI / security are out of L2 scope)
- `docs/findings/2026-06-27-nemotron-trtllm-memory.md`, `2026-06-30-kv-cache-quant-unified-memory.md`
- `reports/…report.md` §2 (bandwidth-bound), §6 (measurement pitfalls / telemetry asymmetry), §7 (operational)

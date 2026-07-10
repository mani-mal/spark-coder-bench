# qwen3-coder-30b will not serve on TensorRT-LLM on GB10 (sm_121a): bf16-MoE runtime blocker

**Date:** 2026-06-29
**Model:** Qwen/Qwen3-Coder-30B-A3B-Instruct (bf16, `qwen3_moe` architecture)
**Runtime:** TensorRT-LLM 1.3.0rc9 (`nvcr.io/nvidia/tensorrt-llm/release:1.3.0rc9`)
**Hardware:** DGX Spark GB10, Grace Blackwell, compute capability **sm_121a** (consumer Blackwell), 128 GB unified LPDDR5x
**Status:** **BLOCKED** — qwen3-coder-30b cannot be served under TRT-LLM on this box. Its
TRT-LLM bridge cell in the model×runtime matrix is recorded as a **runtime limitation, not a
model failure**. qwen3-coder-30b keeps its full **vLLM** results (L1 + L2 at N=20/8).

## Why this matters for the matrix

The TRT-LLM "bridge" runs exist to isolate the *runtime* effect (energy / throughput / TTFT /
peak memory) by serving the **same model** on both vLLM and TRT-LLM. For qwen that bridge is
impossible on this hardware+image: every MoE execution path TRT-LLM 1.3.0rc9 offers for a **bf16**
MoE either fails to compile, crashes at init, or deadlocks at inference on sm_121a. This is a
property of (runtime version × GPU SM target × MoE precision), independent of the model's coding
ability — which we already measured under vLLM.

Contrast: **nemotron-3-Super serves fine on the same TRT-LLM image** because its MoE is **NVFP4**,
which dispatches to the Blackwell FP4 tensor-core kernel path (`nvfp4_gemm_config` →
cutlass/cublaslt/cuda_core) — a different, working code path from the bf16 fused/unfused MoE that
breaks below.

## The four MoE backends tried (full ladder)

All four served with identical base config (`disable_overlap_scheduler: true`,
`kv_cache_config.free_gpu_memory_fraction: 0.8`, parsers `--tool_parser qwen3_coder`,
`MAX_BATCH_SIZE=4`, `MAX_SEQ_LEN` 65536). Only `moe_config.backend` (and, for #4, CUDA graphs)
changed.

| # | `moe_config.backend` | How far it got | Failure |
|---|---|---|---|
| 1 | `AUTO` (→ CUTLASS) | server ready | **Executor deadlock.** Autotuner selected the **SM80 (Ampere)** fused-MoE cutlass kernel; on Blackwell it fails `GPU lacks the shared memory resources to run fused_moe kernel` (`fused_moe_gemm_launcher_sm80.inl:79`) — *every* autotuner tactic failed for `fused_moe::gemm1/gemm2`. Server answers `/v1/models` but `/v1/chat/completions` never reaches the executor; GPU idle ~10%, requests never logged. |
| 2 | `TRITON` | weights loaded, KV cache built | **ptxas fatal at autotuner warmup.** The Triton grouped-matmul kernel `_p_matmul_ogs_NNT_bf16xbf16xbf16_*` emits PTX using `.tile::gather4` with destination state space `.shared::cluster` — a datacenter-Blackwell/Hopper feature **not supported on `.target sm_121a`**. `ptxas ... Feature '.tile::gather4 with destination state space as .shared::cluster' not supported on .target 'sm_121a' → Ptx assembly aborted`. Worker dies → `RuntimeError: Executor worker returned error` at startup. |
| 3 | `VANILLA` + CUDA graphs on | `forward()` executed | **CUDA-graph stream-capture crash.** The unfused reference MoE (`fused_moe_vanilla.py:547`) performs a host-syncing op (dynamic expert routing) inside the graph-capture region: `CUDA error: operation not permitted when stream is capturing` (`cudaErrorStreamCaptureUnsupported`) → `cudaErrorStreamCaptureInvalidated` → `Executor worker returned error` at init. |
| 4 | `VANILLA` + `cuda_graph_config: null` (eager) | **loaded, warmed up, server live** | **Executor deadlock at inference.** Autotuner + generation warmup *succeed* ("Run warmup with 4 tokens, include 4 generation tokens"), `/v1/models` → 200. But every real request hangs: `/v1/completions` and `/v1/chat/completions` both time out at 180 s with **zero executor log output** during the window and GPU pinned at ~10% / 13 W. The request reaches the HTTP server but the executor never schedules it. |

### Evidence for #4 (the closest-to-working attempt)

```
[TRT-LLM] [I] Running autotuner warmup...
[TRT-LLM] [I] [Autotuner] Autotuning process ends
[TRT-LLM] [I] Run warmup with 8192 tokens, include 0 generation tokens
[TRT-LLM] [I] Run warmup with 4 tokens, include 4 generation tokens   # generation works in warmup
...
INFO:     127.0.0.1:46510 - "GET /v1/models HTTP/1.1" 200 OK
# then: curl /v1/completions  -> rc=28 (timeout) after 180s, GPU ~10%, `docker logs --since 5m` empty
```
`moe_config=MoeConfig(backend='VANILLA', ...)`, `cuda_graph_config=None` confirmed in the logged `LLM Args`.

## Interpretation

On **sm_121a** (consumer GB10), TRT-LLM 1.3.0rc9 has **no working bf16 MoE path**:
- the fused cutlass path targets the wrong SM (SM80) and exhausts shared memory,
- the Triton path needs cluster-shared-memory tensor ops absent on consumer Blackwell,
- the unfused (VANILLA) path is graph-capture-incompatible, and in eager mode the executor
  deadlocks before serving a single request.

NVFP4/MXFP4 MoE (nemotron) avoids all three because it uses the dedicated Blackwell FP4 GEMM path.
This is a **TRT-LLM × consumer-Blackwell maturity gap for bf16 MoE**, not a qwen defect.

## Decision

- **Stop debugging qwen-TRT.** Four backends exhausted; the remaining levers (custom kernel builds,
  patching TRT-LLM) are out of scope for an evaluation harness and would change the runtime under
  test anyway.
- **qwen3-coder-30b TRT-LLM bridge cell = BLOCKED** in the matrix, annotated with this doc.
- **qwen3-coder-30b retains its vLLM results** (the model's quality ranking is unaffected — it was
  always measured on vLLM; see the comparability/fairness findings).
- The runtime comparison (vLLM vs TRT-LLM, same model) is carried by **gpt-oss-120b** if its MXFP4
  MoE serves on TRT-LLM (FP4 path, expected to work like nemotron's NVFP4), plus the nemotron data.

## Reproduce

```bash
# edit infra/trtllm/configs/qwen3-coder-30b.yaml -> moe_config.backend in {AUTO,TRITON,VANILLA}
#   (+ cuda_graph_config: null for the eager VANILLA case)
cd ~/projects/dgx-spark-coding-model-benchmark
bash infra/trtllm/serve-model-trtllm.sh qwen3-coder-30b   # watch: docker logs -f trtllm-server
# then probe inference:
curl -s --max-time 180 http://127.0.0.1:8355/v1/completions \
  -H 'Authorization: Bearer local-dgx-spark-key' -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-coder-30b","prompt":"def reverse(s):","max_tokens":24,"temperature":0}'
```

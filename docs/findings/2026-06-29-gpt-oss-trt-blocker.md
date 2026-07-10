# gpt-oss-120b will not serve real requests on TensorRT-LLM on GB10 (sm_121a): executor-scheduling blocker

**Date:** 2026-06-29
**Model:** openai/gpt-oss-120b (MXFP4 MoE, harmony format)
**Runtime:** TensorRT-LLM 1.3.0rc9 (`nvcr.io/nvidia/tensorrt-llm/release:1.3.0rc9`)
**Hardware:** DGX Spark GB10, Grace Blackwell, **sm_121a**, 128 GB unified LPDDR5x
**Status:** **BLOCKED** — gpt-oss-120b reaches "ready" on TRT-LLM and its MXFP4 MoE autotunes,
but **live API requests deadlock at the server→executor handoff** (never scheduled, GPU idle).
gpt-oss-120b keeps its full **vLLM** results (L1 + L2 at N=20/8). The TRT bridge cell is a
**runtime limitation, not a model failure** — gpt-oss is our #1 quality model under vLLM.

## How far it got (further than qwen — the MoE works)

Unlike qwen's bf16 MoE (no working kernel on sm_121a — see
`2026-06-29-qwen-trt-moe-blackwell-blocker.md`), gpt-oss's **MXFP4 MoE autotunes successfully**
on Blackwell (the FP4 GEMM path, `nvfp4_gemm_config=cutlass/cublaslt/cuda_core`, the same family
nemotron's NVFP4 uses). Weights load, autotuner completes (`Cache size after warmup is 28`), and
**internal warmup iterations run** on the GPU. The blocker is downstream of the kernels.

## The blockers, in order encountered

| Stage | Config | Result |
|---|---|---|
| Repo download | `MODEL_ID=openai/gpt-oss-120b` | trtllm-serve tries to pull the **whole repo** incl. the bf16 `original/` set and **hangs** (5 shards stuck at 48 GB, 0 bytes/45 s). **Fixed** by pointing `MODEL_ID` at the local cached snapshot dir (MXFP4 set is complete). |
| Offline workaround | `HF_HUB_OFFLINE=1` | Weights load, but the **tokenizer** loader hits the HF API and 400s (`offline mode is enabled`). **Fixed** by the local-path approach instead (no offline flag). |
| CUDA graphs ON | default `cuda_graph_config` | **Segfault** at `Run generation-only CUDA graph warmup for batch size=4 ... !!! Segfault encountered !!!`. |
| Harmony chat | adapter enabled | `POST /v1/chat/completions 400` — `Error in harmony chat completion: failed to download or load vocab file` (`load_harmony_encoding(HARMONY_GPT_OSS)` cannot cache the o200k_harmony encoding in-container, even though the blob URL returns HTTP 200 from the host). **Fixed** by `DISABLE_HARMONY_ADAPTER=1` (uses the cached `tokenizer.json` + `chat_template.jinja`, which is also closer to how vLLM served it). |
| **Live inference** | eager (`cuda_graph_config: null`), `disable_overlap_scheduler` both true and false, `enable_chunked_prefill: true`, `print_iter_log: true` | **Executor deadlock.** Server reaches "ready"; `/v1/chat/completions` and `/v1/completions` both **time out** (16-token request → 150 s timeout, empty body), **GPU idle ~10 %/13 W**, and `print_iter_log` shows the executor **iterates only during warmup** (`iter=1,2`) — firing a real request produces **zero new iterations** (`iter` count stays at 2). The request reaches the HTTP frontend but is never enqueued to the PyExecutor. |

## Root interpretation

The MXFP4 MoE is fine on Blackwell; the failure is a **server→executor (RPC) scheduling deadlock**
in TRT-LLM 1.3.0rc9 for this PyTorch-backend MoE model on sm_121a. Evidence: internal warmup
iterations execute, but API requests never produce executor iterations and the GPU never engages.
The deadlock is **not** moved by the available config levers:

- CUDA graphs on → segfault; off → deadlock.
- `disable_overlap_scheduler` true → deadlock; false → deadlock.
- adding `enable_chunked_prefill` + `stream_interval` (nemotron's working knobs) → still deadlock.

**Why nemotron works but qwen/gpt-oss don't:** nemotron actually served real requests through this
same RPC path (it completed full L1+L2). It is a different architecture (hybrid Mamba/attention,
NVFP4, speculative MTP, harmony-free) on NVIDIA's *own* validated Spark config. The two community
MoE coders (qwen bf16, gpt-oss MXFP4) both deadlock — qwen in the MoE kernel, gpt-oss one layer up
at request scheduling. The common theme is **TRT-LLM 1.3.0rc9 maturity for non-NVIDIA MoE models on
consumer GB10**.

## Decision

- **Stop debugging gpt-oss-TRT.** Six serve configurations exhausted; the remaining work
  (patching the RPC/executor path) is out of scope for an evaluation harness.
- **gpt-oss-120b TRT bridge cell = BLOCKED**, annotated with this doc.
- **gpt-oss keeps its vLLM results** (its #1 quality ranking is from vLLM and is unaffected).

## Consequence for the runtime-bridge design

No single model serves on **both** runtimes on this box:

| Model | vLLM | TRT-LLM |
|---|:---:|:---:|
| nemotron-3-Super (NVFP4) | ✗ (can't serve MIXED_PRECISION ckpt) | ✓ |
| qwen3-coder-30b (bf16 MoE) | ✓ | ✗ (MoE kernel) |
| gpt-oss-120b (MXFP4 MoE) | ✓ | ✗ (executor deadlock) |

The same-model vLLM-vs-TRT-LLM bridge is therefore **not achievable** on DGX Spark GB10 with this
TRT-LLM build — itself a substantive infrastructure finding: **only the FP4-native NVIDIA reasoning
model serves under TRT-LLM; community MoE coders run only under vLLM.** Runtime-level TRT-LLM data
exists solely for nemotron; cross-model quality comparison is carried by the (uniform) vLLM harness.

## Reproduce

```bash
cd ~/projects/dgx-spark-coding-model-benchmark
# point MODEL_ID at the local snapshot (infra/trtllm/model-profiles/gpt-oss-120b.env)
DISABLE_HARMONY_ADAPTER=1 TRT_ENV_PASSTHROUGH=DISABLE_HARMONY_ADAPTER \
  bash infra/trtllm/serve-model-trtllm.sh gpt-oss-120b      # reaches "[trt] ready"
# then a real request hangs with the executor idle:
curl -s --max-time 150 http://127.0.0.1:8355/v1/chat/completions \
  -H 'Authorization: Bearer local-dgx-spark-key' -H 'Content-Type: application/json' \
  -d '{"model":"gpt-oss-120b","messages":[{"role":"user","content":"say ok"}],"max_tokens":16}'
# docker logs trtllm-server | grep 'iter =' -> only warmup iters; none for the request
```

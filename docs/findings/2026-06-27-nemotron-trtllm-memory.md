# Nemotron-3-Super-120B on DGX Spark via TensorRT-LLM: the load-time memory wall

**Date:** 2026-06-27
**Status:** root-caused and fixed (config + container version); serve validation in progress
**Hardware:** single DGX Spark (GB10 Grace Blackwell, 128 GB unified LPDDR5x, aarch64/SM121, driver 580.159.03)

## Summary

Bringing up `nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4` on TensorRT-LLM took **two host hard-crashes** before serving. The model is officially single-Spark-capable, but the default/naive serve path on the wrong container version drives a transient load-time memory peak that collides with the 128 GB unified ceiling and hangs the whole machine. This note records the failure signature, the host-protection guard we added, and the official recipe that fixes it — useful both for reproducibility and as a "local 120B is at the edge of one Spark" finding for the paper.

## What the model actually is

- Checkpoint on disk: **75 GB**, 17 safetensors shards.
- `hf_quant_config.json`: `quant_algo: MIXED_PRECISION` — **FP8** for the Mamba mixer in/out projections, **NVFP4** (group_size 16) for the MoE expert up/down projections, **FP8 KV cache**. This mixed scheme is exactly what vLLM's ModelOpt loader rejects (it wants a single uniform algo), which is why TRT-LLM is the only runtime path for this model on Spark.

## Failure signature (what went wrong)

Serving with container `tensorrt-llm/release:1.2.1` and a conservative-looking config:

1. **First config bug (fast, harmless):** `free_gpu_memory_fraction` and `enable_padding` placed at the YAML top level → `ValueError: LLM got invalid argument: free_gpu_memory_fraction`, container exits in 2 s. They are keys of `kv_cache_config` / `cuda_graph_config`, not top-level LLM args.

2. **The real wall — load-time OOM that took down the host.** After fixing the YAML, the 1.2.1 loader logged `Fallback to regular model init` and then, during weight materialization (`init_meta_tensor → torch.empty_like(device='cuda')`), climbed to **115.6 GB** before:
   ```
   torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.62 GiB.
   GPU 0 has total 121.69 GiB of which 2.15 GiB is free.
   this process has 115.60 GiB memory in use.  121.69 GiB allowed
   ```
   Because the process was *allowed to use all 121.7 GB* of the shared CPU+GPU pool, the kernel was starved and the box hung → watchdog reboot. A 75 GB checkpoint was transiently consuming ~115 GB: the 1.2.1 nemotron_h path falls back to a regular (non-meta) init that double-allocates, and the allocator fragments (the 2.6 GB request failed with 2.1 GB free).

## Two things we changed

### 1. Host protection (independent of any model/config) — `infra/trtllm/serve-model-trtllm.sh`

The 128 GB pool is shared between CPU and GPU, and we confirmed **the docker `--memory` cgroup cap does not catch Grace unified/GPU allocations** (a run hit `Exited (137)` with `OOMKilled=false` — the cap never fired). So container-level limits cannot protect the host here. We added:

- `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` — reduces allocator fragmentation during the big weight load.
- `--memory 112g` cgroup cap — belt-and-suspenders (does catch the host/page-cache side even if not the GPU side).
- **A host-side watchdog in the readiness loop:** polls `/proc/meminfo` and, if `MemAvailable` drops below `MEM_FLOOR_MIB` (default 6144), immediately `docker kill`s the container and dumps logs. This is what actually saved the host: it fired at **1888 MiB available** during a sub-5 s spike that the cgroup cap missed. The box stayed up.

Takeaway: **on DGX Spark unified memory, host protection for any large-model bring-up must be enforced from the host side**, not via container memory limits.

### 2. The correct serve recipe — NVIDIA's official single-Spark guide

The fix for the load wall itself is to follow [NVIDIA's Nemotron-3-Super Spark deployment guide](https://github.com/NVIDIA-NeMo/nemotron/tree/main/usage-cookbook/Nemotron-3-Super/SparkDeploymentGuide), which differs from a naive setup in memory-critical ways:

| Setting | Naive (crashed) | Official Spark recipe |
|---|---|---|
| Container | `tensorrt-llm/release:1.2.1` | **`tensorrt-llm/release:1.3.0rc9`** (correct nemotron_h loader) |
| Prefill cap | unset | `--max_num_tokens 8192` + `enable_chunked_prefill: true` |
| KV cache dtype | `auto` | explicit `fp8` |
| SSM cache | unset | `mamba_ssm_cache_dtype: float16` + stochastic rounding |
| `free_gpu_memory_fraction` | 0.6 (guessed down) | **0.9** (safe once load is correct + KV is FP8) |
| Long context guard | unset | `TLLM_ALLOW_LONG_MAX_MODEL_LEN=1`, `--max_seq_len 1048576` |
| Spec decoding | none | MTP, `num_nextn_predict_layers: 3` |

The container version is the load-time fix; chunked prefill + `max_num_tokens` cap the activation peak; FP8 KV + float16 SSM cache are what let `free_gpu_memory_fraction` go back up to 0.9 and still leave room. Exact values are committed in `infra/trtllm/configs/nemotron-super.yaml` and `infra/trtllm/model-profiles/nemotron-super.env`.

## For the paper

- **Local 120B on a single Spark is real but at the edge.** A 75 GB MIXED_PRECISION checkpoint needs the vendor's exact load path and FP8 KV cache to fit in 128 GB; a naive bring-up that "looks conservative" (lower `free_gpu_memory_fraction`) does not help, because the wall is in *weight loading*, before KV is ever sized.
- **Runtime version is a first-class variable.** The same model, same flags, fails on TRT-LLM 1.2.1 and works on 1.3.0rc9. Pin and report it.
- **Unified memory changes the safety model.** Container memory caps don't bound GPU allocations; a host-side memory watchdog is required to keep a benchmark harness from taking down the machine between runs.

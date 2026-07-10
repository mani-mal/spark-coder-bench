# KV-cache quantization on GB10 unified memory — why we serve unquantized KV

**Date:** 2026-06-30
**Purpose:** Record the decision (and external corroboration) for running **unquantized KV cache**
(`kv_cache_dtype auto`) across all served models, after a community DGX Spark benchmark showed
KV-cache quantization is *counterproductive* on GB10's bandwidth-starved unified memory.

## The decision

All L1/L2/L3 runs serve with **`kv_cache_dtype auto`** (model-native f16/bf16 KV cache).
We deliberately did **not** enable FP8/INT KV-cache quantization on any model. This is now
treated as the correct serving config for GB10, not a tuning oversight — disclose it in the
efficiency/methodology section.

## External corroboration (practitioner negative result)

**Source:** "TurboQuant KV Cache on DGX Spark GB10 — First SM 121 Benchmark," LinkedIn (Maine),
2026. <https://www.linkedin.com/pulse/turboquant-kv-cache-dgx-spark-gb10-first-sm-121-benchmark-maine-uu8tc/>

**Status:** Self-published LinkedIn post, single author, n=3 reps, one model — **not peer-reviewed.**
Cite as a corroborating practitioner observation, not as authority. The transferable claim is the
*mechanism* (bandwidth-bound decode), which is hardware-level and independent of TurboQuant itself.

**Stack tested (different from ours):** llama.cpp / GGUF, `Nemotron-3-Nano-30B-A3B UD-Q4KXL`
(21.26 GiB MoE), Madreag `turbo3/turbo4` CUDA forks of TurboQuant, flash-attn, full GPU offload,
CUDA 13.0. KV-cache quantization vs an f16 KV baseline.

**Result — KV quant *loses* throughput, worsening with context depth:**

| Context depth | f16 tok/s | turbo4 | turbo3 | turbo4 vs f16 |
|---|---|---|---|---|
| 4,096 | 45.21 | 44.06 | 43.66 | −2.5% |
| 8,192 | 43.37 | 39.49 | 40.60 | −8.9% |
| 16,384 | 43.29 | 36.21 | 36.54 | −16.4% |
| 32,768 | 41.61 | 31.81 | 32.09 | **−23.6%** |

Also reported: naïve `q4_0` KV quant **collapses ~92.5% throughput at 64K** and paradoxically uses
*more* memory than f16. Prompt-processing (prefill) was barely affected (<1%); the loss is entirely
in **token generation (decode)**.

## Why it happens (the part that matters for our paper)

GB10 unified LPDDR5X is **~273 GB/s — roughly 6× lower bandwidth than discrete Blackwell**
(RTX 5090 ≈ 1.7 TB/s GDDR7). Decode is memory-bandwidth-bound. KV-cache quantization trades
memory bandwidth for **dequant compute on the KV read path**:

1. On a high-bandwidth discrete GPU, the bandwidth saved outweighs the dequant compute → net win.
2. On GB10's low-bandwidth unified memory, the dequant compute dominates → **net loss**, growing
   with KV size (hence the depth-dependent degradation).
3. With 128 GB unified memory, the usual motivation for KV compression (KV competing with weights
   for scarce VRAM) **does not apply** — there's room to keep KV in f16.

## Why this does NOT change any of our numbers

- **We already serve unquantized KV** (`kv_cache_dtype auto`) on every model → we are already on
  the recommended config; nothing to re-run, no score moves.
- **Different stack/quant/model.** Their result is llama.cpp + GGUF Q4_K *weights* + a third-party
  KV quantizer on Nemotron-Nano-30B. Ours is vLLM/TRT-LLM with NVFP4/MXFP4 *weight* quant and
  unquantized KV on different models (Qwen3-Coder-30B, gpt-oss-120b, Nemotron-Super-120B). The
  article says nothing about weight quantization — the axis our models actually vary on.

## How to use it in the writeup

- **Disclosure sentence (methodology/efficiency):** state we ran unquantized KV cache deliberately,
  and cite this as independent GB10-specific evidence that KV-cache quantization is counterproductive
  on this hardware — so our tok/s and energy/token reflect the correct serving config, not an oversight.
- **Bandwidth framing:** the 273 GB/s vs ~1.7 TB/s contrast explains *why* our decode tok/s look
  modest (e.g. Qwen3-Coder-30B ≈ 24 tok/s L3) — Spark is memory-bandwidth-bound, which is the central
  fact an efficiency paper about this box is built on. Pairs with the
  [NVIDIA/community external validation note](2026-06-29-nvidia-blog-external-validation.md).

## Bottom line

A GB10-specific negative result independently confirms our serving choice. **Keep f16/`auto` KV
cache**, disclose it as deliberate, and cite the bandwidth-bound mechanism (not the TurboQuant tool)
as the reason. No reruns, no metric changes.

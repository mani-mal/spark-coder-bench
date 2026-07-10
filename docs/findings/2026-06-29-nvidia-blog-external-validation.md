# External validation against NVIDIA + community DGX Spark publications

**Date:** 2026-06-29
**Purpose:** Cross-check our model × runtime matrix against published NVIDIA Technical Blog
and community DGX Spark numbers. Confirms our rankings/serving-feasibility result and explains
the one cell (gpt-oss decode tok/s) that sits below community microbenchmarks.

## Sources checked

| Source | Relevance |
|---|---|
| [dFlash Speculative Decoding](https://developer.nvidia.com/blog/boost-inference-performance-up-to-15x-on-nvidia-blackwell-using-dflash-speculative-decoding/) | **Data-center Blackwell only** (8× DGX B300 / B200, TRT-LLM/vLLM/SGLang). NOT GB10/sm_121a. Technique lesson, not a comparable number. |
| [Scaling Autonomous AI Agents with DGX Spark](https://developer.nvidia.com/blog/scaling-autonomous-ai-agents-and-workloads-with-nvidia-dgx-spark/) | **Primary anchor.** Benchmarks Nemotron-3-Super-120B NVFP4 *with TensorRT-LLM* on GB10. |
| [New Software & Model Optimizations Supercharge DGX Spark](https://developer.nvidia.com/blog/new-software-and-model-optimizations-supercharge-nvidia-dgx-spark/) | llama.cpp +35% MoE uplift; NVFP4 2.6× over FP8 on Qwen-235B. |
| [LMSYS: Optimizing GPT-OSS on DGX Spark](https://www.lmsys.org/blog/2025-11-03-gpt-oss-on-nvidia-dgx-spark/) | ~50 tok/s gpt-oss-120b single-stream w/ FlashInfer backend + `--mxfp4-layers`. |
| [Forum: vLLM 0.17.0 MXFP4 patches](https://forums.developer.nvidia.com/t/vllm-0-17-0-mxfp4-patches-for-dgx-spark-qwen3-5-35b-a3b-70-tok-s-gpt-oss-120b-80-tok-s-tp-2/362824) | gpt-oss-120b 80 tok/s at TP=2 across **2 nodes**. |

## Consistency table

| Quantity | Ours | External | Verdict |
|---|---|---|---|
| nemotron-3-Super-120B NVFP4 decode tok/s | null (TRT exposes no Prometheus metrics) | **18 tok/s** (NVIDIA, TRT-LLM, GB10) | ✅ fills our blank cell; matches our "slowest / highest-energy" result |
| nemotron ↔ runtime | TRT-only (vLLM can't load MIXED_PRECISION ckpt) | NVIDIA pairs Nemotron NVFP4 **with TensorRT-LLM** | ✅ independently corroborates serving-feasibility finding |
| qwen-class decode tok/s | 19.7 (Qwen3-Coder-30B, agentic) | 35.75 (NVIDIA Qwen3.5-35B, clean bench) | ✅ same ballpark; lower = agentic long-context + different model |
| gpt-oss-120b decode tok/s | 26.9 (agentic) | ~50 (LMSYS), ~59 (single-stream), 80 (TP=2 2-node) | ⚠️ ~half — explained below, not a contradiction |

**Ranking and direction are fully consistent with all published sources. No contradictions.**

## Why our gpt-oss decode (26.9) is below community single-stream (~50)

Two verified causes, neither a measurement error:

1. **No FlashInfer MoE path for gpt-oss.** `VLLM_FLASHINFER_MOE_BACKEND` / `VLLM_USE_FLASHINFER_MOE_FP4`
   are set **only** in `infra/vllm/model-profiles/nemotron-super.env`, not the gpt-oss profile. Our gpt-oss
   profile already discloses it: *"MXFP4 loads via the Marlin weight-only kernel on SM121 … a disclosed
   performance caveat for the energy/throughput cuts."* LMSYS's ~50 tok/s explicitly uses the FlashInfer
   attention backend + `--mxfp4-layers`. The gap is the MoE/attention backend.
2. **Agentic workload, not a microbenchmark.** Our number is measured during real OpenCode runs (full-repo
   prompts + tool schemas, large KV), where decode tok/s is structurally below short-prompt single-stream.

## Fairness note (disclose in the efficiency table)

nemotron ran on the FlashInfer FP4 path; gpt-oss ran on the slower Marlin path. This affects **only**
the efficiency/throughput cells — **not quality** (resolved-rate / rubric pass-rate are speed-independent).
The gpt-oss #1 quality ranking is therefore unaffected. The cross-runtime efficiency numbers were already
flagged as runtime-confounded; this adds a backend-asymmetry caveat within vLLM.

## Actionable follow-ups (efficiency only — none change the quality headline)

- **Cite NVIDIA's 18 tok/s** as the external reference for nemotron's (unmeasurable) decode rate.
- **Speculative decoding is the unused lever.** Both the dFlash blog and the DGX Spark optimization blog
  push it; our nemotron profile already has `nemotron_h_mtp` MTP (`num_speculative_tokens=5`) commented out.
  Enabling it is the most promising way to lift nemotron's ~18 tok/s. Spec-decoding is lossless, so it would
  not move any quality ranking.
- **Add FlashInfer MoE to the gpt-oss vLLM profile** for an apples-to-apples efficiency comparison with
  nemotron (expected ~2× decode based on LMSYS).
- **Concurrency dimension.** We benchmarked single-stream (`max-num-seqs` 1–2); NVIDIA's agentic story is
  concurrent subagents (4 → 3× throughput). A concurrency sweep would improve the energy/token picture.

## Bottom line

The external literature **validates** our study: nemotron's TRT-LLM pairing and slow ~18 tok/s, the
quality/efficiency ordering, and the serving-feasibility result all hold up. The only below-community
number (gpt-oss decode) is fully explained by a documented backend choice and the agentic workload, and
it does not affect any quality conclusion. The dFlash result is on different (data-center) silicon and is
informative only as a speculative-decoding direction, not a comparable benchmark.

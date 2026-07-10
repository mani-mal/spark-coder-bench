# Finding: Nemotron-3-Super-120B-A12B-NVFP4 is not servable on vLLM 0.15.1 (MIXED_PRECISION ModelOpt checkpoint)

**Date:** 2026-06-25
**Status:** Confirmed, grounded in upstream issues. Nemotron removed from the *vLLM* comparison; retained as a deployment-reality finding and a candidate for a TensorRT-LLM follow-on.
**Runtime:** NGC `nvcr.io/nvidia/vllm:26.02-py3` (vLLM 0.15.1), DGX Spark GB10, driver 580.159.03.

## TL;DR

NVIDIA's `NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4` checkpoint is **mixed-precision**, not uniform NVFP4: FP8 on the Mamba mixer projections, NVFP4 on the MoE experts, specified per layer. vLLM 0.15.1's ModelOpt quantization loader only accepts a **single uniform** quant algorithm and rejects the model during config validation — in ~6 seconds, before a single weight is loaded. This is a known vLLM limitation (not a misconfiguration on our side), with an upstream issue filed against this exact model + container combination on NVIDIA's own DGX Spark playbooks repo.

## What the model declares

`hf_quant_config.json` (produced by `modelopt 0.43.0.dev63`):

```json
{
  "producer": { "name": "modelopt", "version": "0.43.0.dev63+g449e700f9" },
  "quantization": {
    "quant_algo": "MIXED_PRECISION",
    "kv_cache_quant_algo": "FP8",
    "quantized_layers": {
      "backbone.layers.0.mixer.in_proj":  { "quant_algo": "FP8" },
      "backbone.layers.0.mixer.out_proj": { "quant_algo": "FP8" },
      "backbone.layers.1.mixer.experts.0.up_proj":   { "quant_algo": "NVFP4", "group_size": 16 },
      "backbone.layers.1.mixer.experts.0.down_proj": { "quant_algo": "NVFP4", "group_size": 16 },
      "...": "~every MoE expert listed individually, NVFP4 group_size 16"
    }
  }
}
```

So the top-level `quant_algo` is `MIXED_PRECISION`, with the real per-layer algorithm in `quantized_layers` (FP8 for the dense/Mamba mixer projections, NVFP4 for the sparse MoE experts).

## The exact failure

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for VllmConfig
  Value error, ModelOpt currently only supports:
  ['FP8', 'FP8_PER_CHANNEL_PER_TOKEN', 'FP8_PB_WO', 'NVFP4'] quantizations in vLLM.
  Please check the `hf_quant_config.json` file for your model's quant configuration.
```

The crash is in `engine_args.create_engine_config(...)` (config validation), not in weight loading. No `--tool-call-parser` / `--reasoning-parser` / `--mamba-ssm-cache-dtype` flag is involved — those never get a chance to run. **No profile or parser change can fix this**, because the rejected value is the checkpoint's own quantization format.

## Grounding (this is a known issue, not our error)

- `vllm-project/vllm#37854` — "NGC vLLM 26.02 rejects Nemotron-3-Super-120B-A12B-NVFP4 — quant_algo MIXED_PRECISION not in whitelist".
- `NVIDIA/dgx-spark-playbooks#77` — same model, same `26.02-py3` image, same error string. Filed on NVIDIA's own DGX Spark repo.
- `vllm-project/vllm#31782` — "Support compressed-tensors NVFP4 quantization for MoE models (Nemotron-H non-gated MoE)" — the broader feature gap.
- `vllm-project/vllm#35528` — "Support serving ModelOpt W4A8 MXFP4+FP8 checkpoints" — the general mixed-precision-ModelOpt request.

## Options considered

1. **Force `quant_algo: "NVFP4"` in the config (config-patch workaround).** A circulating workaround patches the top-level field to `NVFP4` on the grounds that ~99.7% of layers are NVFP4. **Rejected for the benchmark:** the Mamba mixer projections are *genuinely FP8-quantized in the weights*; telling vLLM to treat the whole model as NVFP4 risks silently miscasting those layers, producing a model that may load but generate subtly-wrong output. A benchmark whose model-under-test might be quietly corrupted is worthless — and patching the checkpoint config is itself a contamination of the model being measured. Not done.
2. **Newer vLLM image.** A later vLLM may add MIXED_PRECISION ModelOpt support, but upgrading the NGC image on DGX Spark carries driver-compatibility risk (AI_USAGE.md pins `26.02-py3` for that reason) and is not confirmed to help. Deferred.
3. **TensorRT-LLM (`trtllm-serve`).** NVIDIA's own stack supports this exact mixed-precision Nemotron checkpoint and is already documented as the fallback in AI_USAGE.md. This is the supported path to actually run the model. **Recommended follow-on**, with the caveat below.

## Decision

- **Nemotron is removed from the head-to-head *vLLM* comparison.** The primary, same-runtime results compare the two models vLLM can serve cleanly: **gpt-oss-120b** vs **qwen3-coder-30b**.
- **This incompatibility is itself a reportable result.** "The flagship NVFP4 model NVIDIA co-optimized for this exact hardware is not loadable on the current-stable open-source serving stack, because its mixed-precision ModelOpt format outruns vLLM's quantization loader" is a genuine, citable Blackwell/DGX-Spark deployment-reality data point — the same class of finding as the DeepSeek autonomous-tool-use result.
- **TensorRT-LLM is the path to add Nemotron back as a third data point**, reported separately and explicitly flagged as a *different runtime* (a vLLM-vs-TRT-LLM cross-runtime comparison is a confound and must not be presented as apples-to-apples throughput/latency against the vLLM models). Weights are fully downloaded and ready (17 shards, finalized); only the serving + metrics-collection wiring for trtllm-serve remains.

## Harness change shipped alongside this finding

`infra/vllm/serve-model.sh` now **fails fast**: if the vLLM container exits before readiness (as nemotron does in ~6 s), the script detects the dead container, dumps the last 25 log lines, and returns immediately instead of polling a corpse for the full 15-minute readiness window. This is how the real error was finally captured — the previous run destroyed nemotron's logs by `docker rm -f`-ing the container on the next model's serve before anyone could read them.

## For the paper

Frame the model set as: **two MoE models served identically under vLLM (gpt-oss-120b MXFP4, qwen3-coder-30b bf16)**, plus **two documented deployment-reality findings** that are themselves contributions:
- DeepSeek-Coder-V2-Lite — codes well, won't autonomously drive the agent loop (tool-use gate).
- Nemotron-3-Super-120B-A12B-NVFP4 — mixed-precision ModelOpt checkpoint not servable on stable vLLM; needs TensorRT-LLM.

Both say something true and useful about running local coding models on a DGX Spark *today*, which is exactly the paper's subject.

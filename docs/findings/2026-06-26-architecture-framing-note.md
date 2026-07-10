# Note: include model architecture (MoE / Mamba-hybrid) in the report — as a descriptive axis

**Date:** 2026-06-26
**Status:** Decision note for the arXiv writeup. Reviewed against the model registry
(`infra/models.json`) and the per-run `model` block in `run-summary.json`.

## Decision

**Yes — report architecture, but frame it as a descriptive / explanatory dimension that
contextualizes the efficiency metrics (memory footprint, decode throughput, energy/token), NOT as
a controlled independent variable.** We cannot make causal claims like "MoE sparsity causes better
coding" — only 2 of the selected models produced benchmark data, and architecture is fully
confounded with parameter count, quantization, and training corpus. Used descriptively, though, it
materially sharpens the paper.

## The four models by architecture (all MoE; one is also Mamba-hybrid)

| Model | Architecture | Experts (top-k / total) | Total / active params | Active sparsity | Quant | Status |
|---|---|---|---|---|---|---|
| gpt-oss-120b | Transformer **MoE** | 4 / 128 | 116.8B / 5.1B | ~0.044 (sparsest) | MXFP4 | benchmarked |
| qwen3-coder-30b | Transformer **MoE** | 8 / 128 | 30.5B / 3.3B | ~0.108 | bf16 | benchmarked |
| nemotron-3-super-120B-A12B | **MoE + Mamba/attention hybrid** | (hybrid; not pure expert) | 120B / 12B | — | MIXED_PRECISION (FP8 Mamba + NVFP4 MoE) | **not vLLM-servable** |
| deepseek-coder-v2-lite | Transformer **MoE** | 6 / 64 | 15.7B / 2.4B | ~0.108 | bf16 | retired (no agentic tool use) |

So the selection spans a real architectural range: three pure-transformer MoEs at different
sparsities/scales, plus one hybrid State-Space-Model (Mamba2) + attention + MoE design.

## How to use it in the report (supported by data we already have)

1. **Sparsity / activation as an efficiency lens.** gpt-oss activates only top-4 of 128 experts
   (~4.4% of 116.8B) vs qwen's top-8 of 128 (~10.8% of 30.5B). Tie this to the measured
   decode throughput: **gpt-oss decodes faster (26.9 vs 19.7 tok/s on Layer 1) despite 3.8× the
   total parameters** — consistent with fewer active experts + MXFP4 weight-only kernels. This is
   an architecture×quant observation, framed as "consistent with," not "caused by."
2. **Total params drive memory, not activation sparsity.** Both peak ~107–110 GiB of the 128 GiB
   unified memory because all experts are resident (no offload). This is *why* only one model is
   served at a time and is a direct architecture→deployment consequence on this box.
3. **Energy/token is ~equal (~70 tok/J)** across the two despite different sparsity/quant — a
   noteworthy "architecture didn't move efficiency much here" point.
4. **Quantization is architecture-adjacent and already a disclosed confound:** MXFP4 (gpt-oss) vs
   bf16 (qwen) vs NVFP4+FP8 (nemotron). On SM121/GB10, FP4 runs via weight-only Marlin kernels
   (no native FP4 compute) — report this so throughput/energy aren't misread as FP4-compute wins.

## The Mamba/hybrid angle is a *deployment-reality* finding, not a perf datapoint

nemotron is the only non-pure-transformer, and it is precisely the one stock vLLM 0.15.1 cannot
serve: its hybrid SSM checkpoint ships as `quant_algo=MIXED_PRECISION` (FP8 Mamba mixer + per-layer
NVFP4 MoE experts), which vLLM's ModelOpt loader rejects (it accepts only a single uniform algo).
Frame this honestly: **"the hybrid Mamba+MoE design pushes ahead of the open serving toolchain's
maturity on this hardware"** — an architecture-meets-tooling result, with TensorRT-LLM as the path
to add it back. (See `2026-06-25-nemotron-super-vllm-mixed-precision.md`.) Do NOT imply anything
about Mamba *coding quality* — we have no data.

## Caveats to state explicitly in the paper

- **N=2 models with benchmark data.** Architecture is confounded with scale, quant, and training
  data; we report it to *contextualize* efficiency, not to attribute performance to it. No causal
  architecture claims.
- The two retired/unservable models (DeepSeek: no agentic tool use; nemotron: not vLLM-servable)
  are documented **selection/deployment-reality** findings, not performance comparisons.

## Bottom line for the writeup

Add a short "Model architectures" subsection with the table above, and weave architecture into the
efficiency discussion (sparsity↔throughput, total-params↔memory, quant↔FP4-kernels) as descriptive
context. Give the Mamba-hybrid its own deployment-reality paragraph. Keep all architecture language
correlational. The registry (`infra/models.json`) and `run-summary.json` already carry the fields,
so the architecture table is reproducible from committed artifacts.

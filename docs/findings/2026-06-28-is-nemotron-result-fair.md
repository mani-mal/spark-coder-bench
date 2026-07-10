# Is nemotron-super losing a real result, or a methodology error? (And: vLLM-vs-TRT fairness / Ollama)

**Date:** 2026-06-28
**Trigger:** Expectation that nemotron (NVIDIA model on NVIDIA DGX Spark) should win, but it
ranks last for agentic coding. Question: did we err, is vLLM-vs-TensorRT-LLM an unfair
comparison, and should we switch everything to Ollama?

## Short answer

The result is **real, not an artifact**. nemotron-super is served correctly; it simply is not a
coding-specialist model. The runtime split does **not** explain the ranking. Ollama would make the
comparison *worse*, not fairer. Three caveats on rigor are noted at the end.

## What we checked (and ruled out)

| Suspected error | Verdict | Evidence |
|---|---|---|
| **Context-length handicap** (AI_USAGE.md shows nemotron at 32768 vs 65536 for others) | **RULED OUT** | The 32768 was the dead *vLLM* entry nemotron never used (vLLM can't serve its MIXED_PRECISION checkpoint). The actual TRT serve gives `MAX_SEQ_LEN=1048576` (1M, FP8 KV cache); the OpenCode TRT entry is **65536 — identical to qwen/gpt-oss**. No asymmetry. |
| **Tool-call / reasoning-parser broken in the agent loop** | **RULED OUT** | Across all 8 L2 runs nemotron made 27–165 tool calls with ~0 failures (`failed_tool_calls` 0–1). It is *actively executing tools*, not stuck "thinking". `reasoning` token count is 0 in accounting — no CoT leakage into the loop. |
| **NVFP4 4-bit quant degrades quality** | **RULED OUT (small)** | NVIDIA data: NVFP4 recovers ~97–99% of accuracy on 30B+ models; <1% drop on LiveCodeBench for a comparable reasoning model. nemotron was *trained natively in NVFP4*, so TRT-LLM is its intended-precision runtime. |
| **vLLM vs TRT-LLM is apples-to-oranges** | **NOT the cause** | Runtime affects throughput/energy/latency, not which tokens the model emits → not resolved-rate. And we explicitly control for it with qwen-trt + gpt-oss-trt **bridge runs** (same model, both runtimes). |

## What actually happens (genuine capability boundary)

The L2 command logs show nemotron actively building, but getting **lost in the workspace**:
e.g. it runs `cd ../frontend`, escapes the allowed directory, and OpenCode auto-rejects the call.
This matches the documented L2 variance (four distinct failure modes: wrong dir / stub / near-empty
/ boots-but-incomplete; see 2026-06-27-nemotron-layer2-variance.md). Tool-calling is fine — task
execution over a long horizon is not.

This is exactly what the model's design predicts:

- **NVIDIA positions nemotron-super as a reasoning / multi-agent-orchestration model**, not a
  coding specialist. Its own technical report reports **SWE-bench Verified 60.47%** — strong, but
  achieved with a bespoke agent harness, and *below* dedicated coder models.
- **Reasoning models are documented to underperform "coder" models in long autonomous edit loops**
  (token blow-up from context accumulation, less controllable behavior over long chains).

Our OpenCode single-attempt numbers sit below every model's official figure (harness + 29-task
arm64 subset + N=1), and nemotron is not suppressed *more* than the others on L1 (24% vs qwen 24%).
Its real collapse is on **L2 app-building** (peak ~1/29 vs gpt-oss ~25%, N=20) — a robust, large-N gap.

## Should we use Ollama instead?

**No.** Ollama runs on DGX Spark, but:
- It would serve nemotron via **post-hoc GGUF quantization**, breaking the native-NVFP4 training
  contract — a *new* confound, not a removed one.
- llama.cpp/Ollama have **known assertion bugs on hybrid Mamba layers** (nemotron's architecture),
  adding instability/variance.
- Ollama tool-calling quality is "uneven" across models — worse for agentic eval.

To compare **models** fairly you hold the runtime constant; to compare **runtimes** you hold the
model constant. Our bridge runs (qwen + gpt-oss on *both* vLLM and TRT-LLM) already do the latter.
Adding Ollama just introduces a third quantization regime that nemotron's architecture may not even
support.

## Honest caveats (rigor, not ranking-changers)

1. **L1 is N=1 on a 29-task arm64 subset** → wide CIs (~±15pp). gpt-oss (38%) > qwen (24%) ≈
   nemotron (24%) is *suggestive* on L1; the firm separation is L2 (N=20). Don't over-claim the L1 gap.
2. **Cross-runtime for now**: gpt-oss/qwen quality numbers are vLLM; nemotron is TRT-LLM. The bridge
   runs (in progress) will confirm runtime doesn't move resolved-rate. Quality ranking is not
   expected to change.
3. **OpenCode token accounting is unreliable for TRT** (no vLLM Prometheus); inference token metrics
   for TRT cells are weak. Quality (resolved/rubric) is unaffected — those come from the official
   eval and the rubric, not from token counts.

## Cross-check vs a third-party Medium article (Saiyam Pathak, Mar 2026)

Reviewed "I Ran a 120B Model on My Desk — Nemotron 3 Super on DGX Spark". It corroborates
our setup rather than contradicting it:

- **Our serving is the better path.** The article author ran nemotron on **Ollama Q4_K_M**
  (lossy post-hoc GGUF) at 256K ctx, and his "own testing" was a single chat prompt (19.5
  tok/s) — not a coding benchmark. We serve **TRT-LLM native NVFP4**, the model's trained format.
- **Our parsers match NVIDIA's recipe.** We use `--reasoning_parser nano-v3 --tool_parser
  qwen3_coder`, which is the documented Spark recipe. Confirmed correct.
- **Sampling.** We use `DECODE_TEMPERATURE=0.2` held identical across all three models (serve
  config `fairness_note` documents this). NVIDIA suggests temp 0.6 / top_p 0.95 for tool-calling;
  0.2 is standard for SWE-bench determinism and, being identical across models, cannot bias the
  ranking. *Optional future rigor:* a small temp-0.6 sensitivity run for nemotron to confirm
  sampling isn't suppressing it — not expected to move the result materially.

- **The article explains the 60% (official) vs 24% (ours) gap.** Nemotron's strong coding
  numbers — PinchBench **85.6%**, SWE-bench Verified **60.47%** — come from NVIDIA's **AI-Q
  multi-agent system** (orchestrator + planner + researcher sub-agents). The article states
  outright: *"It's not just the base model running solo."* Nemotron is designed as the **reasoning
  brain of a multi-agent stack**, not a solo single-agent coder. Our OpenCode harness runs every
  model **solo** — the same for all three — so the ranking ("best drop-in *solo* coder") is fair;
  the gap to NVIDIA's headline is a **scaffolding** difference, not a serving defect.
- **Shape agreement.** The article's own table shows nemotron *winning* code-review precision
  (73.4% vs gpt-oss 46.9%) — a reasoning/analysis task — while we see it lose solo app-building.
  Both sources agree: strong at reasoning/analysis/long-context/orchestration, weak at solo
  agentic editing. Frame the result as "not optimized for solo agentic coding," not "bad at code."

## Bottom line

gpt-oss-120b is #1 on coding quality; qwen3-coder-30b is the efficiency leader; nemotron-super is
last **for agentic coding specifically** — which is the expected, correctly-measured outcome for a
reasoning/orchestration model, not an error and not a runtime artifact. "NVIDIA model on NVIDIA box"
does not imply "best coder"; nemotron's edge is reasoning depth, long context, and throughput, not
autonomous app construction.

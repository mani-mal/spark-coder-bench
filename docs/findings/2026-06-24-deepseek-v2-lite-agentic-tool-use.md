# Finding: code-generation quality ≠ agentic tool-use — DeepSeek-Coder-V2-Lite-Instruct

**Date:** 2026-06-24
**Status:** Confirmed, reproducible. DeepSeek-Coder-V2-Lite-Instruct retired from the active
3-model comparison and replaced by `openai/gpt-oss-120b`; its result is retained as a
documented agentic-failure case.
**Relevance to the paper:** This is a publishable result, not a setup defect. It motivates a
methodological point — an *agentic* coding benchmark must gate on **autonomous tool-use**, a
capability distinct from both code-generation quality and tool-call *formatting*.

## TL;DR

DeepSeek-Coder-V2-Lite-Instruct writes correct code but **will not autonomously decide to call
tools** when driven by an agent (OpenCode, OpenAI `tool_choice: "auto"`). Given a file-creation
task it produced a correct FizzBuzz inline, *claimed* "Files created successfully", and **wrote
nothing to disk**. The serving stack, the vLLM `deepseek_v3` tool-call parser, and the model's
ability to *format* a tool call are all fine — when a call is *forced* it emits well-formed JSON
arguments. The gap is purely the model's propensity to *choose* to act. For an agentic benchmark
this drives its task score to ~0 for a reason that has nothing to do with coding ability.

## Setup

- **Hardware:** DGX Spark (GB10, SM121), 128 GB unified memory.
- **Serving:** vLLM 0.15.1 (`nvcr.io/nvidia/vllm:26.02-py3`), OpenAI-compatible API on `:8000`,
  `--enable-auto-tool-choice --tool-call-parser deepseek_v3`, bf16, seed 0, temp 0.2.
- **Agent:** OpenCode 1.17.9, `opencode run --format json -m vllm-local/deepseek-coder-v2-lite`,
  wrapped in the benchmark's 3-source metric collector (`run-context.sh`).
- **Task:** "Create `fizzbuzz.py` (function `fizzbuzz(n)`) and `test_fizzbuzz.py` (4 assert tests)."
- **Pre-check:** The model **passed** the SM121/FP4 text-coherence sanity gate
  (distinct-token ratio 0.51, no loops, top-5-gram share 0.007). Coherence was never the issue.

## What happened (OpenCode run `deepseek-smoke-1`)

The agent loop ran to completion (exit 0) and all metrics were captured, but the working
directory ended with **only the pre-existing `README.md`** — no `fizzbuzz.py`, no test file.

The captured session transcript shows two failure modes in one run:

1. **Hallucinated tool *results*.** The model emitted, as ordinary assistant text, DeepSeek's
   special tool-protocol tokens describing a *fake* successful tool execution:

   ```
   <｜tool▁outputs▁begin｜><｜tool▁output▁begin｜>{"status": "success",
   "message": "Files created successfully"}<｜tool▁output▁end｜><｜tool▁outputs▁end｜>
   The files `fizzbuzz.py` and `test_fizzbuzz.py` have been created successfully.
   ```

   It then printed the (correct) file contents as Markdown — but never invoked a write tool.

2. **Malformed/empty tool *calls*.** The only tool-call parts OpenCode could extract were
   `bash` and `webfetch` with **empty arguments**, which the harness rejected:
   `bash` → `Missing key ["command"]`; `webfetch` ×2 → `Missing key ["url"]`. On the next step
   it gave up on tools entirely and printed `nano` instructions for the *user* to create the files.

Captured metrics for the run (the harness worked perfectly — it recorded a model that talked
instead of acting): 3 inference requests, 6 tool calls (all errored/empty), 4823 input / 1048
output tokens, 35 s wall-clock, 970 J, 6.74 tokens/J, prefix-cache hit-rate 0.41.

## Isolation: it's the decision, not the format

To rule out the harness, the parser, and prompt phrasing, we issued tool requests directly to
the vLLM endpoint, varying only `tool_choice`:

| `tool_choice` | Result |
| --- | --- |
| `"auto"` (what an agent uses) | `tool_calls: null`; writes prose ("you can follow these steps…"); `finish_reason: length` |
| `"required"` (forced) | **Valid call** — `write_file({"path": "fizzbuzz.py", "content": "…"})`, correct JSON, `finish_reason: tool_calls` |

So: serving ✓, `deepseek_v3` parser ✓, tool-call *formatting* ✓. The model **can** call tools;
under `auto` it **chooses not to**. DeepSeek-Coder-V2-Lite (a mid-2024 instruct model) simply has
weak agentic tool-use disposition — it defaults to explaining the task rather than performing it.

## Why this matters for the benchmark

- **Three distinct capabilities.** "Can generate correct code", "can format a tool call when
  forced", and "will autonomously choose to call tools" are *separable*. DeepSeek-V2-Lite has the
  first two and lacks the third. An agentic benchmark measures the third; a model can ace HumanEval
  and still score ~0 here.
- **Text-coherence sanity gates are necessary but not sufficient.** Our SM121/FP4 gate confirms the
  quantized model produces sane text; it says nothing about agentic disposition. We add an
  **autonomous-tool-use gate** (below) as a precondition for any timed agentic run.
- **The harness behaved correctly.** It recorded the wasted tokens/energy of a non-acting model and
  produced a defensible zero — exactly what you want a benchmark to do with this behavior.

## Methodological addition: the autonomous-tool-use gate

Before any timed agentic run, every model must pass, in order:

1. **Text-coherence sanity** (existing `infra/vllm/sanity-check.py`) — quantization didn't break it.
2. **Autonomous tool-use** (new precondition):
   - Direct vLLM `tool_choice: "auto"` request with one trivial tool → must return a **non-null,
     well-formed** `tool_calls` (not prose, not hallucinated tool-output tokens).
   - One wrapped OpenCode smoke that must **actually create a file on disk**.

   A model that needs `tool_choice: "required"` to act fails this gate and is reported as a
   non-agentic baseline rather than scored as if it tried.

## External corroboration

A targeted web search (2026-06-29) confirms this is a recognized DeepSeek pattern, not a
local misconfiguration, and that the common "fix the parser / upgrade the agent" advice
targets a *different* failure mode than ours:

- **The `auto` vs. `required` split is publicly documented.** vLLM forum thread
  [*DeepSeek-V3 tool_choice="auto" not working but tool_choice="required" is working*](https://discuss.vllm.ai/t/deepseek-v3-tool-choice-auto-not-working-but-tool-choice-required-is-working/1006)
  reports our exact signature — the model declines to call under `auto` but emits a valid
  call when forced. This is **disposition**, the same axis we isolated.
- **"Replies with JSON instead of invoking the tool"** —
  [vllm#19907](https://github.com/vllm-project/vllm/issues/19907) (DeepSeek R1) describes the
  model emitting tool arguments as plain content rather than triggering a structured call:
  the same hallucinated-tool-output behavior we logged.
- **Disposition vs. parsing — keep them separate.**
  [vllm#36654](https://github.com/vllm-project/vllm/issues/36654)
  (*Frequent Tool Call Parsing Failures with DeepSeek-V3.2*) is a genuine **parser** bug —
  DeepSeek's DSML markup (`<｜DSML｜function_calls>…`, "DeepSeek markup format") leaks into the
  `reasoning`/`content` field and `tool_calls` comes back empty. That is the class of problem
  the standard advice (upgrade the agent, fix/swap the tool-call parser) addresses. **It is not
  our problem** — our `tool_choice: "required"` test returns a well-formed call, proving the
  `deepseek_v3` parser extracts correctly. We list it to mark the boundary: a parser fix would
  not have changed a model that chooses not to act under `auto`.

This also resolves the apparent paradox ("DeepSeek reviews well, yet fails here"):
DeepSeek-Coder-V2's strong reputation is for **code synthesis** (HumanEval/MBPP-class), which
is the axis its reviews measure; **autonomous tool-selection is a separate, weaker axis** for
this model generation — exactly the separation this finding argues. No hardware angle surfaced
in any report (consistent with the model already passing our SM121/FP4 coherence gate); the
behavior is model/framework-level and DGX-Spark-independent.

## Consequence

DeepSeek-Coder-V2-Lite-Instruct is replaced as model #3 by **`openai/gpt-oss-120b`** (MoE
117B/5.1B active, MXFP4, Apache-2.0), chosen specifically for documented agentic tool-use and
validated against the gate above before adoption. Replacing it also *strengthens* the central
"NVIDIA hardware co-optimization" thesis: gpt-oss is a second 4-bit MoE (MXFP4) alongside Nemotron
(NVFP4), letting us separate a model effect from a generic FP4-on-Blackwell effect. The DeepSeek
run and this note are kept as the paper's concrete illustration that **agentic competence is not
implied by code-generation competence** for small local models.

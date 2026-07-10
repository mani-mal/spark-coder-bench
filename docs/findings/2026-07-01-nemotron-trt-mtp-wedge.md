# nemotron-super on TRT-LLM: NON-STREAMING responses wedge the executor mid-generation (L3)

**Date:** 2026-07-01
**Model:** nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4
**Runtime:** TensorRT-LLM 1.3.0rc9
**Hardware:** DGX Spark GB10, sm_121a, 128 GB unified LPDDR5x
**Status:** root-caused (non-streaming code path); fixed by making lcb_runner stream.

## Symptom

Serving nemotron for L3 (LiveCodeBench), a fresh un-poisoned container wedged mid-generation. The
first (sanity, `max_tokens=600`, **non-streaming**) request:
- paid the one-time ~215 s autotune warmup (iter 1),
- generated normally for ~13 s, then **stopped** and never produced another iteration; the
  response was never returned, and every subsequent request got **zero iters** (executor wedged,
  GPU idle ~4 %).

Tell around the stall:
```
[TensorRT-LLM][WARNING] [kv cache manager] storeContextBlocks: Can not find sequence for request N
```

## Diagnosis path — MTP ruled OUT, non-streaming ruled IN

First hypothesis was MTP speculative decoding (the "Can not find sequence" error is classically a
speculative-decode KV bug). **Disproven by the token count at the wedge:**

| config | wedge at | generated tokens |
|---|---|---|
| MTP on  (num_nextn_predict_layers=3, ~4 tok/iter) | iter 99  | ~396 |
| MTP off (1 tok/iter)                               | iter 341 | ~341 |

Both wedge at **~350–400 generated tokens regardless of MTP** — so MTP is not the cause; it's a
KV-cache-manager failure at a block boundary.

**What is different about the runs that WORK:** nemotron completed full **L1 (SWE-bench)** and
**L2 (appcase)** on this exact TRT-LLM setup — because **OpenCode drives them over SSE streaming**.
LiveCodeBench's `lcb_runner` used a **non-streaming** `chat.completions.create`. The wedge is
specific to the **non-streaming** response path on TRT-LLM 1.3.0rc9 for this model on GB10;
streaming is stable. (Consistent with the broader "1.3.0rc9 executor maturity on consumer GB10"
theme in the qwen/gpt-oss TRT blocker findings.)

## Fix

`.lcb/LiveCodeBench/lcb_runner/runner/oai_runner.py`: `_run_single` now calls
`chat.completions.create(..., stream=True)` and reassembles `delta.content` per choice. Streaming
is also fine on vLLM, so the change is safe for the (already-banked) qwen/gpt-oss L3 runs too.

Serving is otherwise **unchanged from the known-good L1/L2 config** — original `nemotron-super`
profile, **MTP kept on**, FP8 KV, 1 M seq, CUTLASS MoE. (The no-MTP `nemotron-super-l3`
profile/config created while chasing the wrong hypothesis is retained but not needed; MTP is
output-verified so it would be quality-neutral either way.)

Also: the serve-time sanity check is **non-streaming**, so it would itself hit the wedge at 600
tokens — capped below the wedge point via `SANITY_MAX_TOKENS=200` (env added to
`infra/vllm/sanity-check.py`). vLLM is unaffected.

## Serving command for the L3 run

```bash
SANITY_MAX_TOKENS=200 SANITY_HTTP_TIMEOUT=900 \
  bash infra/trtllm/serve-model-trtllm.sh nemotron-super
# then drive L3 with the streaming lcb_runner, endpoint :8355:
VLLM_BASE_URL=http://127.0.0.1:8355/v1 \
  bash layer3_livecodebench/run-suite.sh --profile nemotron-super \
    --end-date 2024-05-31 --window pre2024m06 --sandbox
```

## DEFINITIVE RESULT (2026-07-01 ~13:50): one generation, then the executor wedges

Streaming DOES let a single long generation complete where non-streaming wedged mid-stream:
a clean `SKIP_SANITY=1` serve + a streaming request as the very FIRST request produced a full
response (`deltas=526, chars=8343`, iters to 566, no mid-generation wedge). **But the executor
then wedges before the NEXT request**: a second request produced **zero executor iterations** for
8+ minutes and timed out; `/v1/models` also hung; GPU idle at 3 %/11 W. Also abnormal: after
generation finished on the executor (iter 566 at 13:27:26), the buffered response took a further
~400 s to reach the client (13:34:08) — the delivery path itself stalls.

So the box can do **at most one generation per serve** right now. A 512-problem sequential L3 run
is **not viable** in this state.

### This is a degraded-box state, not a config or harness bug

The identical serving config ran **full L1 (SWE-bench) + L2 (appcase)** — many sequential
generations — on **2026-06-27**. Today, on the same config: warmup ballooned `<180 s → 215 s →
656 s`, and the executor wedges after one generation. The most likely cause is a **degraded
GPU/runtime state** — this session tore down a **26-hour gpt-oss vLLM container** immediately
before, and TRT-LLM 1.3.0rc9 on GB10 appears sensitive to leftover GPU/unified-memory state.

### Remedy / decision

- **Clean path to the nemotron L3 result:** **reboot the DGX Spark** (or `nvidia-smi --gpu-reset`
  with no GPU clients), then run:
  ```bash
  SANITY_MAX_TOKENS=200 SANITY_HTTP_TIMEOUT=900 bash infra/trtllm/serve-model-trtllm.sh nemotron-super
  VLLM_BASE_URL=http://127.0.0.1:8355/v1 setsid bash layer3_livecodebench/run-suite.sh \
     --profile nemotron-super --end-date 2024-05-31 --window pre2024m06 --sandbox
  # + layer3_livecodebench/l3-watchdog-trt.sh for auto-resume
  ```
  All fixes needed are already in place: streaming `oai_runner`, None-guard + resume-filter in
  lcb_runner, TRT watchdog, `SKIP_SANITY`/`SANITY_MAX_TOKENS`/`SANITY_HTTP_TIMEOUT`.
- **If a reboot is not acceptable now:** bank the L3 table at 2/3 (qwen 68.16 %, gpt-oss 89.26 %),
  mark nemotron L3 as TRT-runtime-blocked-pending-reboot. Its L1+L2 TRT results stand.

Do NOT sink more engine-reload cycles into this without first resetting the box — every attempt
reproduces the one-generation wedge.

## Post-reboot: single-stream is INFEASIBLE (~130h); run L3 8-way parallel (quality-neutral)

After the reboot cleared the degraded state (warmup 656s→8s, sequential requests sustained), the
real L3 run exposed a throughput problem caught at 32 min (not hour 12): **single-stream did only 2
problems in 32 min** — nemotron is a verbose reasoning model generating near the full 8192-token
budget at ~7-9 tok/s on GB10 (273 GB/s, bandwidth-bound). 512 problems single-stream ≈ **130 hours**.

Fix: run nemotron L3 generation **8-way parallel** (`L3_MULTIPROCESS=8`, matching TRT
`max_batch_size=8`). Measured aggregate throughput **~97 tok/s** at `num_scheduled_requests=8`
→ ETA ~6-12h (depends on avg generation length), comparable to the gpt-oss vLLM run.

**Why quality-neutral:** pass@1 is a per-problem, independent-request metric; continuous batching
does not change the tokens generated for a given request (at fixed seed/temp — and we already
disclose that continuous batching breaks bitwise determinism, so this is within existing caveats).
The ONLY thing single-stream buys is comparable decode-tok/s & energy — and **TRT-LLM exposes no
Prometheus metrics, so nemotron L3 has no usable throughput/energy numbers regardless.** So
parallelism costs nothing here and rescues wall-clock. `L3_MULTIPROCESS` defaults to 1, so the
qwen/gpt-oss vLLM L3 runs (which DO yield efficiency metrics) stay single-stream.

Two watchdog/robustness fixes made alongside (both about NOT wasting hours):
- `L3_BASE_URL` (run-suite.sh + watchdog): env.sh re-sources the lab .env and forced VLLM_BASE_URL
  back to :8000, so a TRT run silently hit a dead endpoint. L3_BASE_URL is set after env.sh and wins.
- `l3-watchdog-trt.sh` progress signal now uses **TRT executor iterations** (`recent_iters()`), not
  just RUNLOG/cache mtime. The prom-scraper stops writing to RUNLOG and lcb_runner only flushes the
  cache every 16 problems, so mtime can look frozen for many minutes while generation is healthy —
  which would have triggered a false-stall restart (throwing away in-progress work) right at 45 min.

## FINAL RESULT (2026-07-02): nemotron L3 = 61.3%, but ~28% lost to budget truncation

nemotron-super L3 completed cleanly (8-way parallel, ~9.5h wall, eval pass ran with 0 regeneration
— crash-fixes held). **pass@1 = 61.33% (314/512), Wilson 95% CI [57.0, 65.4].**

Cross-model L3 (same pre2024m06 window, n=512, shared decode config):
| model | runtime | pass@1 | Wilson 95% CI | empty/truncated |
|---|---|---|---|---|
| gpt-oss-120b | vLLM | 89.26% | [86.3, 91.7] | ~1-2% |
| qwen3-coder-30b | vLLM | 68.16% | [64.0, 72.1] | ~0% |
| nemotron-super | TRT-LLM | 61.33% | [57.0, 65.4] | **27.9% (143/512)** |

**Key nuance — the fixed 8192-token budget dominates nemotron's ranking.** nemotron's reasoning
exhausted the shared max_tokens budget on **185/512** problems (143 empty outputs + 42 outputs with
no extractable code; validated as genuine truncation, not a parse bug), all scored as fails. So
nemotron's last-place *overall* L3 number is substantially an artifact of reasoning verbosity vs a
fixed budget, NOT raw coding capability.

> **CORRECTION (2026-07-03, finding C2).** The originally published conditional figure "314/369 =
> 85.1%" was both selection-biased and used a mixed denominator (369 = 512 − 143 counts only EMPTY
> outputs; the natural "answered with extractable code" set is 327). Truncation is difficulty-
> correlated (no-code rate easy 14.3% / medium 34.3% / **hard 71.5%**), so a conditional rate on
> the answered subset cannot be compared to other models' full-512 rates. **Paired correctly** (all
> models on the same 327 problems nemotron answered with code): **nemotron 96.0% (314/327),
> gpt-oss 95.4% (312/327), qwen 82.3% (269/327)**. The artifact reading survives and strengthens
> (nemotron ≈ gpt-oss when it answers). See `2026-07-03-l3-conditional-selection-bias.md` and
> `results/summary/l3-conditional-analysis.csv`.

This is exactly the kind of methodology point the paper is about: **a single-shot, fixed-token-
budget benchmark systematically penalizes verbose reasoning models**, and (from the per-difficulty
split) the penalty lands almost entirely on hard problems. Report the raw pass@1 (comparable, fixed
budget) AND the truncation rate AND the *paired* conditional pass rate, and discuss the budget-
fairness tradeoff. (Do NOT raise max_tokens for nemotron only — that breaks comparability; the
truncation rate is itself the finding.)

## Methodology note for the paper

nemotron's L3 generations are STREAMED (like its L1/L2) while qwen/gpt-oss L3 were non-streamed on
vLLM. Streaming vs non-streaming does not change WHICH tokens a model produces at fixed
seed/temperature — **pass@1 quality is unaffected**. It is a client-transport detail, disclosed for
completeness. If long non-streaming generations wedge even here, nemotron's L3 cell is
runtime-blocked (its L1+L2 TRT results and the two vLLM models' L3 results stand); do not sink
unbounded time into patching TRT-LLM's executor.

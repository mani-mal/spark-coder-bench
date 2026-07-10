# nemotron-super on TRT-LLM: an aborted request during the one-time warmup wedges the executor

**Date:** 2026-07-01
**Model:** nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4
**Runtime:** TensorRT-LLM 1.3.0rc9 (`nvcr.io/nvidia/tensorrt-llm/release:1.3.0rc9`)
**Hardware:** DGX Spark GB10, Grace Blackwell, sm_121a, 128 GB unified LPDDR5x
**Status:** root-caused, fixed (patient sanity timeout). Not a model failure — nemotron serves
fine on TRT-LLM (it completed full L1+L2); this is a harness/warmup-handling bug.

## Symptom

Serving nemotron for the L3 (LiveCodeBench) run, the server reached `[trt] ready`, but:
- the serve script's sanity check reported `COULD NOT RUN (timed out)`;
- every subsequent request (`/v1/chat/completions`, even `GET /v1/models`) hung and returned
  nothing (`http_code=000`);
- `docker logs trtllm-server | grep 'iter ='` showed **zero executor iterations** after the
  first request — the GPU was idle, requests reached the HTTP frontend but were never scheduled.

This is the same *surface* symptom as the qwen/gpt-oss TRT blockers
(`2026-06-29-gpt-oss-trt-blocker.md`), but the cause here is different and **fixable**.

## Root cause

TRT-LLM's **first** request triggers a one-time autotune + CUDA-graph capture. On GB10 this took
**~215 s** for a single iteration:

```
iter = 1 ... host_step_time = 215286.68 ms ... num_ctx_tokens: 58, num_generation_tokens: 0
```

The serve script's sanity check (`infra/vllm/sanity-check.py`) used a **180 s** HTTP timeout, so it
**disconnected mid-warmup**. The aborted request left the executor / KV-cache manager wedged:

```
[TRT-LLM] Address(host='127.0.0.1', port=60652) is disconnected, abort 2
[kv cache manager] storeContextBlocks: Can not find sequence for request 8
```

After that abort, no further request was ever scheduled — a classic "client gave up during warmup
and poisoned the in-flight request" wedge. Because nemotron is the ONE model that serves real
requests through this RPC path (it completed L1+L2), the deadlock is not intrinsic: it is caused by
the 180 s < 215 s timeout mismatch.

## Fix

`infra/vllm/sanity-check.py`: make the HTTP timeout **warmup-tolerant** — default **600 s**,
override via `SANITY_HTTP_TIMEOUT`. vLLM responds in seconds, so this is a no-op for the vLLM
models; on TRT-LLM the sanity request now rides out the ~215 s warmup and completes cleanly, so
(a) the first request is never aborted (no wedge) and (b) the sanity gate actually passes.

The one-time warmup is absorbed by the sanity request itself, so the first *real* LCB problem runs
at normal decode speed. `run-suite.sh`'s per-request `--openai_timeout` is already 1800 s (well
above 215 s), so the generation pass is unaffected regardless.

## Recovery procedure (if it wedges again)

The executor cannot be un-wedged in place — restart the container:

```bash
docker rm -f trtllm-server
# with the patient sanity timeout now in place, just re-serve:
bash infra/trtllm/serve-model-trtllm.sh nemotron-super
```

## Lesson

Any long one-time warmup behind a synchronous HTTP endpoint needs a client timeout **larger than
the warmup**, or the first (probe) request will be aborted and can poison the server. For reasoning
models on TRT-LLM specifically: never point an impatient health check at a cold engine.

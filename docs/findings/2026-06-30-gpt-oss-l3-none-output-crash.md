# gpt-oss L3 lost a 12h run to a None-output crash in lcb_runner post-processing

**Date:** 2026-06-30
**Severity:** cost one full ~12h gpt-oss-120b L3 generation (no result lost permanently — re-run fixed).
**Status:** root-caused, patched, regeneration relaunched.

## What happened

gpt-oss-120b L3 (LiveCodeBench, `pre2024m06`, n=512) generated **all 512/512 problems**
(tqdm hit 100% at 12:00:29) and then **crashed in post-processing, before saving**:

```
File ".../lcb_runner/runner/scenario_router.py", line 93, in combine_results
    [extract_code(output, model.model_style) for output in outputs_list],
File ".../lcb_runner/utils/extraction_utils.py", line 5, in extract_code
    outputlines = model_output.split("\n")
AttributeError: 'NoneType' object has no attribute 'split'
```

Because lcb_runner's `main()` does `run_main()` (generate) → `combine_results()` (**crash**) →
`save_results()`/`json.dump()`, the crash in `combine_results` meant the generations were **never
written to disk**. We also ran **without `--use_cache`**, so there was no per-call cache either.
The generations were held in memory only and were lost. `run-context` recorded `exit_code=1`, and
`run-suite.sh`'s `set -e` killed the script before the eval pass (hence no "evaluation pass" log line).

## Root cause

gpt-oss is a **reasoning model**. When a response is truncated at the shared 8192-token `max_tokens`
cap **mid-reasoning** (`finish_reason=length`), it never emits final-channel content, so the
OpenAI-compatible response has `content=None`. lcb_runner's `extract_code()` calls
`model_output.split("\n")` with no None guard.

Critically, the sanitizing fallback (`outputs.extend([""] * n)` on failure) only runs in
`run_batch`'s **`--multiprocess > 1`** branch. We run **`--multiprocess 1`** (single-stream, for
energy/throughput comparability), whose branch is a bare
`outputs = [self.run_single(a) for a in tqdm(arguments)]` — **no None sanitization**. So a single
`None` output propagates into `combine_results` and takes down the whole run.

This is gpt-oss-specific in practice: Qwen3-Coder-30B completed and scored (68.2%) without any None
(it always emitted content). The 12–13 `length`-truncated gpt-oss responses are the None source.

## Fixes applied

1. **`lcb_runner/utils/extraction_utils.py` — guard `extract_code` against None** (the real fix):
   ```python
   if model_output is None:
       return ""
   ```
   A missing/None output is now treated as an **empty submission → scores as a failed problem**,
   which is the correct, honest outcome (the model did not produce an answer within budget). Does
   not affect Qwen's already-saved result (no None there) and does not change scoring for any
   problem that did produce output.

2. **`layer3_livecodebench/run-suite.sh` — add `--use_cache --cache_batch_size 16`** to GEN_CMD
   (insurance): generations are now persisted to `cache/<model>/...` every 16 problems via
   `save_cache()`. If anything in post-processing ever crashes again, at most 16 problems need
   re-generation on resume instead of the entire run. (Default `cache_batch_size` is 100 — too
   coarse for a 12h run; set to 16.)

## Methodology note (keep in the paper, not a bug)

The 8192-token `max_tokens` budget is **held constant across all models** for cross-layer
comparability (see `coverage.md`). gpt-oss's reasoning verbosity means a handful of hard problems
exhaust that budget mid-reasoning and score as fails. That is a **real property of the model under
a fixed, disclosed token budget**, not a harness artifact — do **not** raise max_tokens just for
gpt-oss (it would break comparability with Qwen/Nemotron). Report truncated-as-fail and disclose the
`length`-truncation count per model.

## Cost / recovery

- Lost: ~12h of gpt-oss generation compute (no usable artifact from the failed run; its 6.9GB
  metrics dir was deleted to reclaim disk; crash traceback preserved at
  `docs/findings/evidence/2026-06-30-gpt-oss-l3-crash-command-log-tail.txt`).
- Recovery: regeneration relaunched 2026-06-30 ~21:49 UTC, detached via `setsid`, vLLM still up
  (no re-serve needed). ETA ~12h to generation completion, then auto eval+score. With the fix it
  will complete `combine_results` → `save_results` → eval → `lcb-score.json`.

## Follow-on bug (2026-07-01): eval-phase crash loop on the same 7 truncated problems

After generation completed (505 good + 7 truncated saved as `output_list=[None]`), the run
**crash-looped in the EVAL pass** (watchdog auto-restarted it 3×). Cause chain:

- lcb_runner's `--continue_existing` filter treats any empty/None output as "not done":
  `if instance["output_list"] and [x for x in instance["output_list"] if x]`. The 7 truncated
  problems (`[None]`) are dropped → marked "remaining" → **re-generated on every pass**.
- The eval command (`EVAL_CMD`) had **no `--openai_timeout`**, so regenerating those 7 long
  reasoning problems hit lcb_runner's short default timeout → repeated
  `APITimeoutError` → `assert len(result) == args.n` → `AssertionError` → process dies.
- The 7 truncate again at temp 0.2, so this can never succeed — a genuine infinite loop that would
  have hit the watchdog's `MAX_RESTARTS` and given up.

**Fixes (2026-07-01):**
1. `lcb_runner/runner/main.py` — relax the resume filter to keep every **attempted** problem
   (`if instance["output_list"]`), so a no-answer problem is graded as a **failed submission**
   instead of re-generated forever. Verified: eval now reports `Found 512 existing, continuing
   with 0 remaining` (was `505 / 7 remaining`) → grades all 512, zero regeneration.
2. `run-suite.sh` — add `--openai_timeout "$OPENAI_TIMEOUT"` to `EVAL_CMD` as defense (with fix #1
   eval does no generation, but if it ever must, it uses 1800s not the short default).

This is the correct scoring: the 7 truncated problems (model produced no final answer within the
fixed 8192-token budget) count as fails over n=512 — do not re-generate or drop them.

## Lesson for the remaining L3 runs (and any long single-shot run)

Any harness that **saves only after a post-processing step** is one exception away from losing the
whole run. For multi-hour generations: (a) enable per-call caching so raw outputs survive
post-processing crashes, and (b) guard extraction/parsing against None/empty model outputs,
especially for reasoning models that can return empty final channels.

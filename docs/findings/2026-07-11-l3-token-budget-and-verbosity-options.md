# L3 fixed-token-budget: why 8192 is held constant, and the options not taken

**Date:** 2026-07-11
**Trigger:** Doc walkthrough question — "nemotron's L3 last place is a fixed-token-budget artifact on 185/512 problems; can't we just change the budget in config? And instead, can we reduce nemotron's verbosity at the same budget?"
**Status:** Decision — **no change**. Primary L3 numbers stand as published; this records the config lever, why it stays pinned, and the exact shape of a variant run if a future reviewer asks.

---

## Setting (recap — all already published)

- L3 = LiveCodeBench single-shot generation, pass@1, `max_tokens = 8192`, temperature `0.2`, **held identical for all three models** (`layer3_livecodebench/run-suite.sh:40`, `layer3_livecodebench/coverage.md:60`).
- nemotron's verbose reasoning exhausted the 8192 budget on **185/512** problems (**143 empty** outputs + **42** output-with-no-extractable-code), all scored fail → raw pass@1 **61.3%** (last place).
- On the **327** problems it answered with code: **96.0%** (314/327), vs gpt-oss 95.4% and qwen 82.3% on the same subset. Truncation is difficulty-correlated (no-code rate: easy 14.3% / medium 34.3% / **hard 71.5%**). See `2026-07-03-l3-conditional-selection-bias.md`.

## Q1 — "Can't the budget just be changed in config?"

Yes, mechanically — it is one flag:

- `layer3_livecodebench/run-suite.sh:40` → `MAX_TOKENS=8192`, overridable per-run with `--max-tokens N`, flowing into `GEN_CMD ... --max_tokens "$MAX_TOKENS"` (line 91).

But 8192 is **held constant on purpose** — it is a fairness control. L3 pass@1 is comparable across our models *only because* every model got the identical budget, temperature, and prompt. Raising the budget for nemotron alone removes a controlled variable: nemotron's L3 number would no longer be on the same axis as gpt-oss/qwen, and it could not be called the same benchmark.

The 8192 truncation **is the result**, not a bug to configure away. The report thesis (§5.3) is exactly this: *a single-shot, fixed-budget benchmark systematically penalizes verbose reasoning models, and the penalty lands almost entirely on hard problems.* The correct handling — already done — is the **paired 327-subset** analysis, not a bigger-budget re-run.

If ever revisited, the only defensible forms:

1. Raise the budget for **all three** models and re-run all of L3 (keeps the control). Cost: nemotron single-stream L3 already ≈ 130 h and is bandwidth-bound on verbose decode; a larger budget scales the worst case — and the run-suite timeout sizing (`run-suite.sh:27`) — into a multi-day re-run of the slowest model.
2. Report a **labeled sensitivity column** for nemotron at a higher budget, keeping 8192 as the primary. Clean, cheaper; never swapped into the main table.
3. Leave it, cite the paired subset. **← current choice.**

## Q2 — "Reduce nemotron's verbosity at the same budget instead?"

Also possible, and arguably a *cleaner* experiment than raising the budget, because it preserves the shared 8192. Mechanisms (best → weakest):

1. **Reasoning toggle via system prompt.** The Nemotron family is gated by a system directive (`detailed thinking on` / `detailed thinking off`-style). Off → no long trace → cannot exhaust the budget on reasoning. The exact directive string for Nemotron-3-Super (Nano-v3 lineage — the serve manifest uses `--reasoning_parser nano-v3`) **must be confirmed on the model card before use**; it differs across Nemotron generations. Not verified in this note.
2. **Reasoning-effort / thinking-budget cap**, if TRT-LLM's `nano-v3` parser exposes one. (gpt-oss's explicit low/med/high effort is *why* it truncates at only ~1–2%.) Unconfirmed for nemotron.
3. **Prompt instruction** ("minimal reasoning, output code directly"). Weak, and it mutates the prompt — a controlled variable — so avoid.

Two constraints if this is ever run:

- **The L3 harness injects no system prompt today** (verified: nothing sets a system role in `run-suite.sh` or `layer3_livecodebench/lcb_runner_fixes.patch`; nemotron runs in default reasoning-on mode). Implementing option 1 means adding a system message in the LCB prompt construction (the `lcb_runner_fixes.patch` is where that change belongs).
- It remains a **nemotron-only config deviation** — same status as raising the budget — so it must be a **disclosed variant**, never the primary 61.3%.

The honest framing is an experiment, not a fix: *at 8192 with reasoning off/capped, does nemotron recover the truncated 185 without losing the 96% it earns on the 327?* If quality holds → strengthens "penalizes verbosity, not capability." If quality drops → the reasoning is load-bearing and 8192 is simply too tight for this model class.

## Decision

No change to L3. Primary numbers (gpt-oss 89.3 / qwen 68.2 / nemotron 61.3, fixed 8192) and the paired 327-subset analysis stand as published. This note exists so the config lever is on record with its rationale, and a future reviewer asking "why not just raise the budget / turn off thinking?" has the answer without re-deriving it.

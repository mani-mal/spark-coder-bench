# LiveCodeBench integration — scope / spec (Layer 3)

**Date:** 2026-06-29
**Status:** Scope decision, pre-implementation. Grounds the LiveCodeBench (LCB) add decided in
`2026-06-29-benchmark-selection-for-arxiv.md`. Reviewed against the actual harness: `run-context.sh`
(3-source metric window), `infra/models.json` (registry), `infra/metrics/aggregate.py`, and the
L1/L2 run/results conventions.

## Goal

Add LCB as **Layer 3** — a single-shot, contamination-controlled **code-generation** axis — so the
paper can place each model's clean code-gen score next to its agentic (L1/L2) score, making the
"code-gen ≠ agentic tool-use" thesis empirical. LCB is chosen because it runs **arm64-native**
(pure-Python `lcb_runner` → our existing vLLM OpenAI endpoint; no per-task Docker, no x86 images,
no QEMU) and is **time-windowed** (the only contamination-controlled measurement in the study).

## Step 0 — the gating feasibility check — RESOLVED 2026-06-29

LCB would be *contamination-FREE* only if a problem window exists **after the latest training
cutoff of every benchmarked model** AND within an available LCB release. Researched (web, 3 model
cards + LCB releases):

| Model | Training cutoff | Source |
|---|---|---|
| gpt-oss-120b | **June 2024** (earliest) | OpenAI model card / arXiv 2508.10925 |
| Qwen3-Coder-30B-A3B | **April 2025** | Qwen HF card |
| Nemotron-3-Super-120B | **February 2026** (latest) | NVIDIA build model card |

LCB **v6** (latest release) covers **May 2023 → April 2025** (1,055 problems); v7 (late-2025/2026
problems) is **not released** as of 2026-06-29.

**Verdict: (C) NO contamination-FREE window.** LCB v6 ends April 2025; Qwen's cutoff is April 2025
and Nemotron's is February 2026, so essentially zero LCB problems postdate either model's cutoff.
A contamination-free run needs LCB v7 → **future work**, not now.

### Pivot: use a contamination-BALANCED (equal-exposure) window instead — this is viable now

The contamination-free property is unavailable, but the property our study actually needs is the
one **L1 already relies on**: *equal* contamination exposure across models so it cancels in the
relative A/B. Achieve it by taking problems **before the EARLIEST cutoff** (gpt-oss, June 2024):

- Window = LCB v6 **May 2023 → May 2024** (`contest_date < 2024-06`). Every model (cutoffs June
  2024 / April 2025 / Feb 2026) is *past* this range → all three had equal opportunity to memorize →
  contamination cancels in the cross-model comparison, exactly as argued for L1 (`layer1_swebench/
  coverage.md`: "relative A/B on identical hardware, contamination cancels across models").
- Problem count: ample — ~600 v6 problems predate Aug 2024, so the pre-June-2024 slice yields
  several hundred → solid Wilson CIs (far better than L1's n=29).
- **Avoids the trap:** a *post*-2024 window would give Qwen/Nemotron (later cutoffs) a memorization
  edge over gpt-oss — uneven exposure that would bias the comparison. The pre-earliest-cutoff window
  is the only one with balanced exposure on v6.

**What changes vs. the original plan:** LCB's claim downgrades from "contamination-free absolute
number" to "**exposure-balanced, valid relative** code-gen comparison" — which is all the paper ever
claims anyway. Disclose this explicitly; do **not** present LCB scores as contamination-free.
Re-run as contamination-free when LCB v7 (post-Feb-2026 problems) ships.

## Design decisions

1. **Scenario:** LCB **code-generation** (pass@1) only. Not self-repair / test-output-prediction /
   code-execution scenarios — code-gen is the axis that complements L1/L2 and matches the thesis.
2. **Problem set:** the Step-0 **equal-exposure** window — LCB v6, `contest_date < 2024-06` (before
   the earliest cutoff, gpt-oss June 2024) — one common window for all models so exposure is balanced
   and contamination cancels in the relative A/B (NOT contamination-free; see Step 0). Pin the exact
   subset and document the date range + per-model cutoffs in `layer3_livecodebench/coverage.md`
   (mirrors `layer1_swebench/coverage.md`). **No custom filter needed** — lcb_runner has a native
   `--end_date 2024-06-01` flag that filters problems by `contest_date`.
3. **Generation config = the shared profile:** `seed 0, temp 0.2, max_num_seqs 1`, **single-stream
   (concurrency 1)**. LCB's default is throughput-oriented concurrent generation; we force
   sequential so the decode tok/s / energy/token numbers are directly comparable to L1/L2. Disclose
   this deviation from LCB's standard run. (Concurrency stays a separate future dimension — ties to
   the NVIDIA-blog concurrency follow-up.)
4. **Metric granularity — suite-level efficiency, per-problem quality:**
   - **Efficiency:** one `run-context.sh` window around the whole generation pass over the N-problem
     subset → one `run-summary.json` (decode tok/s, energy/token, peak unified memory) for the LCB
     workload. Cleaner than the agentic layers — no tool-loop variance. Per-problem energy windows
     are not worth the overhead/noise for short problems.
   - **Quality:** per-problem pass/fail recorded → pass@1 over N with a **Wilson 95% CI** (matches
     the "always report CIs" decision in the comparability note). n=N gives real error bars, unlike
     L1's n=29.
5. **Scoring/execution:** use `lcb_runner`'s own evaluation (run generated solutions against the
   problem test cases). It's pure-Python subprocess execution → arm64-native. **Sandbox it:** it
   executes untrusted model-generated code, so run the eval step inside a throwaway container or a
   restricted unprivileged user with a wall-clock/`ulimit` cap. (Generation and eval are separable;
   only generation needs the GPU/metric window, eval can run after.)
6. **OpenCode accounting is N/A:** `collect-opencode.py` is best-effort and won't fail the run; the
   `accounting` block in `run-summary.json` will be empty/low-confidence for L3, which is correct —
   vLLM Prometheus token counts remain authoritative for inference accounting here.

## Proposed layout (mirrors layer1_swebench / layer2_appcase)

```
layer3_livecodebench/
  README.md
  coverage.md            # equal-exposure window + per-model cutoffs + actual N (the Step-0 record)
  lm_styles.patch        # the one-line LanguageModel registry entry to add to lcb_runner/lm_styles.py
  run-suite.sh           # per model: generate (under run-context) → eval (sandboxed) → score
  eval/                  # lcb scoring outputs
```
(No `select-window.py` — windowing is the native `--end_date` flag.)

## Resolved wiring recipe (risk #2 — verified against lcb_runner source)

The integration is **env + a one-line registry entry**, essentially no code:

1. **Install** lcb_runner with its **pinned** deps (its `pyproject.toml`/lockfile pins an older
   `datasets` that still supports the LCB loading-script dataset; a modern `datasets` rejects it —
   confirmed). Install into the project `.venv`.
2. **Registry entry** — add to `lcb_runner/lm_styles.py` (kept as `lm_styles.patch` in our layer):
   `LanguageModel("qwen3-coder-30b", "qwen3-coder-30b", LMStyle.OpenAIChat, datetime(2025,1,1), link="local-vllm")`.
   The first field must equal the vLLM `--served-model-name` (it is sent as the OpenAI `model=`).
   One entry per served model.
3. **Endpoint via env** (no code change): `OPENAI_BASE_URL=http://127.0.0.1:8000/v1` and
   `OPENAI_KEY=$VLLM_API_KEY` (the runner reads `OPENAI_KEY`; the OpenAI SDK reads `OPENAI_BASE_URL`).
   Must be exported **before** the process starts (the client is built at import time).
4. **Generate (single-stream), under the metric window:**
   ```
   run-context.sh <profile>-l3-lcb-2024h1-1 -- \
     python -m lcb_runner.runner.main --model <served-name> --scenario codegeneration \
       --release_version release_v6 --end_date 2024-06-01 \
       --n 1 --temperature 0.2 --multiprocess 1
   ```
   `--multiprocess 1` → sequential single request (base_runner runs parallel only when `>1`); `--n 1`
   + `temp 0.2` = our single-sample shared config. Generation only (no `--evaluate`) so the energy
   window is clean GPU.
5. **Evaluate (outside the window, sandboxed):** re-run with `--evaluate`
   (`--num_process_evaluate`, `--timeout` cap execution). This executes untrusted generated code →
   run in a throwaway container or restricted user. Produces pass@1; wrap with Wilson 95% CI.

### Spike result — 2026-06-29 (live wiring CONFIRMED on tiny-smoke-test)

Served `Qwen/Qwen3-0.6B` as `tiny-smoke-test` on vLLM `:8000` (ready in ~5s). Replicated
`OpenAIRunner._run_single` exactly with `OPENAI_BASE_URL`/`OPENAI_KEY` env only (no base_url in
code): `client.base_url` resolved to `http://127.0.0.1:8000/v1/` and a single-stream request with
LCB's `client_kwargs` (temp 0.2, n=1, top_p 0.95) returned a valid generation (66 prompt / 357
completion tokens). **The OpenAIRunner↔vLLM contract works via env routing, single-stream.** Risk #2
is now closed both on paper and live. (Note: Qwen3 emits `<think>` blocks; LCB's `extraction_utils`
strips to the code fence — not a wiring concern.)

### Remaining setup (Phase 2 — not a risk, just install/plumbing)

The full `lcb_runner.runner.main` end-to-end needs a **dedicated pinned venv**, because the analysis
`.venv` has `datasets 5.0.0` (rejects LCB's loading-script dataset) and **no `torch`** (parser.py
imports it at arg-parse time). Build a separate venv from LCB's `uv.lock`/`pyproject` (CPU torch wheel
is fine — the API path never uses the GPU torch). Then: add the registry entry, run the
generate→evaluate recipe above on the `--end_date 2024-06-01` window, plumb `l3` pass@1 + Wilson CI
into `aggregate-runs.py`.

Results (under `results/raw/<run-id>/`, run-id = `<profile>-l3-lcb-<window>-<seq>`,
e.g. `gpt-oss-120b-l3-lcb-2025h2-1`):
- `run-summary.json` — existing schema (efficiency block authoritative for L3).
- `lcb-predictions.jsonl` — one row per problem (problem_id, generated code, contest_date).
- `lcb-score.json` — `{n, passed, pass_at_1, wilson_ci_95: [lo,hi], window, per_problem: [...]}`.

## Phase 2 — BUILT & validated end-to-end (2026-06-29)

Layer 3 is implemented and proven through the full generate→eval→score→aggregate chain on
`tiny-smoke-test`. Built:

- **`.lcb/` (gitignored, regenerable):** lcb_runner cloned at pinned commit `28fef95` + a dedicated
  **CPU venv** with the lock-pinned deps (`torch==2.6.0+cpu` aarch64, `datasets==3.5.0`,
  `openai==1.75.0`, `transformers==4.51.3`, `pebble==5.1.1`, `numpy 2.2.5`, `pyarrow 19.0.1`,
  `huggingface-hub 0.30.2`, `anthropic==0.49.0`). torch is import-only on the API path
  (`parser.py:140` `torch.cuda.device_count()` is the local-vLLM branch we never take), so CPU torch
  suffices. The analysis `.venv` is left untouched.
- **`layer3_livecodebench/`** (tracked): `setup-lcb.sh` (reproducible bring-up), `lm_styles.patch`
  (registers `qwen3-coder-30b`, `gpt-oss-120b`, `nemotron-super`, `tiny-smoke-test` — model_name ==
  served-model-name == OpenAI `model=`), `run-suite.sh` (gen under `run-context.sh` → sandboxable
  eval → score), `eval/score.py` (pass@1 + Wilson 95% CI), `README.md`, `coverage.md`.
- **`analysis/aggregate-runs.py`:** recognizes the `l3` layer tag and folds
  `lcb_pass_at_1 / lcb_ci_lo / lcb_ci_hi / lcb_n` into `benchmark-long.csv` next to L1 resolved-rate
  and L2 rubric.

**Window counts (from release_v6, loaded live):** total **1055** problems, `contest_date` range
**2023-05 → 2025-04**. The equal-exposure window `--end_date 2024-05-31` = **512 problems** — a far
stronger N than L1's 29 (≈ ±4.3 pts Wilson half-width at 50%). Recorded in `coverage.md`.

**End-to-end validation (tiny-smoke-test, Qwen3-0.6B, 36-problem 2023-08 window):**
- Generation ran under the metric window, **single-stream confirmed** (vLLM
  `num_requests_running=1, waiting=0` throughout), exit 0 → clean `run-summary.json` (decode 83 tok/s,
  energy, peak unified mem).
- Eval graded all 36 (reused saved generations via `--continue_existing`, zero new API calls),
  printed `pass@1 = 0.0833`.
- `score.py` → `lcb-score.json`: n=36, passed=3, pass@1 8.33%, Wilson CI [2.9, 21.8]%, per-problem
  rows with `question_id`+`contest_date`.
- `aggregate-runs.py` produced the `tiny-smoke-test/l3/all` row carrying both quality and efficiency
  columns. (Smoke run then deleted from `results/raw/` — it's mechanical validation, not a result.)

**Two bugs found & fixed during the run** (both in `run-suite.sh`):
1. `env.sh` forces `HF_HOME=~/.cache/huggingface` (root-owned model cache) → `datasets` can't write
   there. Fixed: run-suite.sh forces a user-writable `HF_HOME=$REPO/.hf-cache` (override `L3_HF_HOME`).
2. lcb_runner names output files from `str(args.scenario)` = `"Scenario.codegeneration"`, not
   `"codegeneration"`. Fixed the eval-file path accordingly.

**Remaining (real results, not a risk):** serve each model one at a time and run
`run-suite.sh --profile <name> --end-date 2024-05-31 --window pre2024m06 --sandbox` —
`qwen3-coder-30b` + `gpt-oss-120b` on vLLM, `nemotron-super` on TRT-LLM. Use `--sandbox` (bwrap) for
the eval pass on real (untrusted) generations. ~512 single-shot gens/model single-stream; budget a
few hours wall-clock per model on the larger ones.

## Integration points (small, additive)

- **Registry:** no new model entry (reuses the 3 served models). Add an LCB block to whatever
  declares layers, if anything does; otherwise layer is implied by run-id.
- **`infra/metrics/aggregate.py`:** already produces `run-summary.json` from the window + collectors
  generically — should work unchanged for the generation window (verify it tolerates the empty
  OpenCode accounting, which L1/L2 already exercise).
- **`analysis/aggregate-runs.py`:** teach it the `l3`/`lcb` layer tag so LCB rows flow into
  `benchmark-long.csv` / `benchmark-summary.csv` with `pass_at_1` + CI alongside L1 resolved-rate
  and L2 rubric.
- **Serving:** unchanged. LCB hits the same `vllm serve` on `:8000`; run it while each model is the
  active served profile (same as L1/L2 — one model served at a time).

## Risks / spikes (in priority order)

1. ~~**[GATE] Contamination-free window exists** (Step 0)~~ — **RESOLVED:** no contamination-free
   window (LCB v6 ends Apr 2025 < Nemotron/Qwen cutoffs). Pivoted to the **equal-exposure** window
   (`contest_date < 2024-06`), which is available now. No longer blocking.
2. ~~**`lcb_runner` → vLLM wiring**~~ — **RESOLVED** (read lcb_runner source). It's env +
   one registry line + native `--end_date`/`--multiprocess 1` flags; see "Resolved wiring recipe"
   above. Downgraded M → **S**. Only the *live* run remains, which needs a served model.
3. **Sandboxed execution** of generated solutions on the host. — S (container or restricted user +
   ulimit/timeout).
4. **`aggregate-runs.py` layer plumbing** for the new pass@1 + CI metric. — S.

## Effort & sequencing

1. ~~Step-0 window verification~~ — **done** (verdict C → equal-exposure window chosen). Remaining:
   write `select-window.py` to pin the `contest_date < 2024-06` subset + confirm exact problem count.
2. Spike: one model, ~5 problems, lcb_runner against vLLM, confirm generation + eval + a real
   pass@1 number, single-stream. 
3. Wrap generation in `run-context.sh`; confirm a clean `run-summary.json` (decode tok/s + energy).
4. Full window × 3 served models; sandbox the eval.
5. Plumb `l3` into `aggregate-runs.py`; add pass@1 + Wilson CI; regenerate summary CSVs.

No model app-code is touched (contamination rule intact). Generation config stays on the shared
`seed 0 / temp 0.2 / max_num_seqs 1` profile; any deviation from LCB's official run config is
disclosed in `coverage.md`.

## Open question for the user (not blocking the spike)

LCB's official leaderboard typically reports pass@1 with a specific sampling config (often
greedy/`n` samples). We will instead use our **shared `temp 0.2, single-sample` config** for
cross-layer comparability within this paper, and disclose that our LCB numbers are therefore *not*
directly comparable to the public LCB leaderboard (only across our own models). Flag if you'd rather
also produce a leaderboard-config run for external comparability (extra cost, separate table).

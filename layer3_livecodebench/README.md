# Layer 3 — LiveCodeBench (single-shot code generation)

Layer 3 measures **clean, single-shot code-generation** quality, the orthogonal axis to the
agentic layers (L1 SWE-bench, L2 app build). Placing each model's L3 pass@1 next to its
agentic score is what makes the paper's *"code generation ≠ agentic tool use"* thesis
empirical rather than asserted.

LiveCodeBench (LCB) is chosen because it is the only benchmark in the study that runs
**arm64-native** (pure-Python `lcb_runner` → our existing vLLM/TRT-LLM OpenAI endpoint; no
per-task Docker, no x86 images, no QEMU) **and** is **time-windowed**, which lets us control
contamination exposure across models.

See `../docs/findings/2026-06-29-livecodebench-integration-scope.md` for the full scope/decision
record and `../docs/findings/2026-06-29-benchmark-selection-for-arxiv.md` for why LCB (and not
SWE-bench Pro / SWE Atlas / Terminal-Bench) is the third benchmark.

## What we measure

- **Quality:** pass@1 over the windowed problem set, with a **Wilson 95% CI** (`lcb-score.json`).
- **Efficiency:** one 3-source metric window (`run-context.sh`) around the whole generation pass
  → `run-summary.json` (decode tok/s, energy/token, peak unified memory) — same schema as L1/L2.

## Contamination control — a fixed, historical, contamination-POSSIBLE window

There is no contamination-*free* window available now: LCB v6 ends April 2025, which predates
two of three models' training cutoffs (see `coverage.md`). Instead we fix a **historical window** —
problems **before the earliest cutoff** (gpt-oss, June 2024) — so every model had the *opportunity*
to have seen the entire set. **This does not mean contamination "cancels."** Equal chronological
eligibility is not equal contamination: training corpora, deduplication, and benchmark-ingestion
differ across models, so actual exposure can differ even on identical problems. Treat these scores
as a **descriptive relative** code-gen comparison across *our* configurations on a shared
contamination-possible window — not contamination-balanced, not contamination-free, and not
comparable to the public LCB leaderboard (different sampling config). A published version needs a
contamination sensitivity analysis; re-run on a genuinely post-cutoff window when LCB v7
(post-Feb-2026 problems) ships.

## Generation config (held identical to L1/L2)

`seed 0`, `temperature 0.2`, `n=1` (single sample), `--multiprocess 1` (**single-stream**,
concurrency 1), `top_p 0.95`, `max_tokens 8192`. LCB's default is throughput-oriented concurrent
sampling; we force sequential so decode tok/s and energy/token are directly comparable to the
agentic layers. This deviation from LCB's standard run is disclosed in `coverage.md`.

## Files

| File | Purpose |
|---|---|
| `setup-lcb.sh` | Clone `lcb_runner` @ pinned commit into `../.lcb/`, build the CPU venv, apply `lm_styles.patch`. Idempotent. |
| `lm_styles.patch` | Registers our 4 served models in `lcb_runner/lm_styles.py` (model_name == vLLM `--served-model-name`). |
| `run-suite.sh` | Per model: generation (under metric window) → eval (sandboxed) → score. |
| `eval/score.py` | LCB eval → `lcb-score.json` (pass@1 + Wilson 95% CI). |
| `coverage.md` | The exposure window, per-model cutoffs, and the actual problem count *N* (the Step-0 record). |

The `lcb_runner` clone and the CPU venv live under `../.lcb/` (gitignored, regenerable via
`setup-lcb.sh`); only the reproducible bits above are tracked.

## Run it

```bash
# one-time
layer3_livecodebench/setup-lcb.sh

# serve a model (one at a time), e.g. Qwen3-Coder, then:
layer3_livecodebench/run-suite.sh \
  --profile qwen3-coder-30b --end-date 2024-05-31 --window pre2024m06 --sandbox

# repeat per served model (gpt-oss-120b, nemotron-super), then aggregate:
.venv/bin/python analysis/aggregate-runs.py
```

Outputs land in `results/raw/<profile>-l3-lcb-<window>-<seq>/`:
`run-summary.json` (efficiency), `lcb-score.json` (pass@1 + CI), `lcb-predictions.json`
(generations). `aggregate-runs.py` folds the `lcb_pass_at_1` / `lcb_ci_lo` / `lcb_ci_hi` / `lcb_n`
columns into `results/summary/benchmark-long.csv` alongside L1 resolved-rate and L2 rubric.

> **Eval executes untrusted model-generated code.** Pass `--sandbox` for real runs (runs the eval
> pass under `bwrap`: filesystem isolation, no network, throwaway `/tmp`). Without it the eval runs
> only behind LCB's per-test `--timeout`.

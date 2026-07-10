# Layer 1 — SWE-bench Verified (disclosed 29-task ARM64-buildable subset)

Agentic bug-fix layer: real GitHub issues scored automatically by the official SWE-bench
evaluation (FAIL_TO_PASS / PASS_TO_PASS), no human judgment.

> **ARM64 reality:** official SWE-bench Verified images are x86-64. We run only the subset
> that builds on this GB10 host, proven empirically, and disclose coverage. Report this as
> **"pass rate on the disclosed 29-task ARM64-buildable subset," not SWE-bench Verified
> performance.** Same tasks on identical hardware bound but do **not** equalize contamination
> (corpora/dedup differ per model) — treat cross-model gaps as descriptive, not intrinsic.

## Flow

```bash
# 0) install deps + ensure Docker works for your user
pip install -r requirements.txt

# 1) choose + verify the ARM64-buildable subset (runs gold patches through eval)
python3 layer1_swebench/select-arm64-subset.py --verify --limit 50
#    -> subset-verified.json (arm64_buildable[]) + coverage.md

# 2) serve a model, then run the suite (resumable), N repeats per task
infra/vllm/serve-model.sh qwen3-coder-30b
layer1_swebench/run-suite.sh qwen3-coder-30b 3
#    swap model and repeat:
infra/vllm/serve-model.sh nemotron-super
layer1_swebench/run-suite.sh nemotron-super 3

# 3) aggregate + stats
python3 analysis/aggregate-runs.py
python3 analysis/stats.py --long results/summary/benchmark-long.csv
```

## Per-task pipeline (`run-task.py`)

1. Clone the task repo at `base_commit`.
2. Hand the issue to `opencode run` (headless), wrapped in `infra/metrics/run-context.sh`
   → full 3-source metrics for the agent window.
3. `git diff` → `model_patch.diff` → `predictions.jsonl`.
4. Official `swebench.harness.run_evaluation` → `resolved.json` (0/1).

Outputs per run land in `results/raw/<profile>-l1-<instance_id>-<repeat>/`.

## Validation status

This layer is written to the official SWE-bench v3 API but is **not yet executed**
on this host (needs `swebench` + `datasets` installed and Docker usable by the user;
some harness flags are version-sensitive — verify `run_evaluation --help` and the
report filename `<model>.<run_id>.json` against your installed version). The infra +
metrics + analysis layers it depends on ARE validated.

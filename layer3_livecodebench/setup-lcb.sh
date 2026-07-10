#!/usr/bin/env bash
# setup-lcb.sh — reproducibly stand up the LiveCodeBench (Layer 3) harness.
#
# Clones lcb_runner at the PINNED commit into <repo>/.lcb/ (gitignored), builds a
# dedicated CPU venv with the lock-pinned deps (the API path never touches GPU torch),
# and applies lm_styles.patch to register our locally-served models. Idempotent.
#
# Why a separate venv: the analysis .venv has datasets 5.x (rejects LCB's loading-script
# dataset) and no torch (parser.py imports it at arg-parse). lcb_runner needs datasets
# 3.5.0 + a torch import; both are isolated here so they can't perturb the analysis env.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LCB_HOME="$REPO_ROOT/.lcb"
LCB_DIR="$LCB_HOME/LiveCodeBench"
VENV="$LCB_HOME/venv"
PIN_COMMIT="28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24"   # LiveCodeBench @ 2025-07-15
REPO_URL="https://github.com/LiveCodeBench/LiveCodeBench.git"

mkdir -p "$LCB_HOME"

# 1) clone at the pinned commit
if [[ ! -d "$LCB_DIR/.git" ]]; then
  echo "[setup] cloning $REPO_URL @ $PIN_COMMIT"
  git clone --quiet "$REPO_URL" "$LCB_DIR"
fi
git -C "$LCB_DIR" fetch --quiet origin || true
git -C "$LCB_DIR" checkout --quiet "$PIN_COMMIT"
echo "[setup] lcb_runner at $(git -C "$LCB_DIR" rev-parse --short HEAD)"

# 2) dedicated CPU venv with lock-pinned deps
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "[setup] creating venv $VENV"
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip wheel setuptools
echo "[setup] installing CPU torch (aarch64) + lock-pinned deps"
"$VENV/bin/pip" install --quiet torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu \
  || "$VENV/bin/pip" install --quiet torch==2.6.0
"$VENV/bin/pip" install --quiet \
  datasets==3.5.0 openai==1.75.0 transformers==4.51.3 pebble==5.1.1 \
  numpy==2.2.5 pyarrow==19.0.1 huggingface-hub==0.30.2 anthropic==0.49.0

# 3) register our locally-served models
echo "[setup] applying lm_styles.patch"
if git -C "$LCB_DIR" apply --check "$REPO_ROOT/layer3_livecodebench/lm_styles.patch" 2>/dev/null; then
  git -C "$LCB_DIR" apply "$REPO_ROOT/layer3_livecodebench/lm_styles.patch"
else
  echo "[setup] patch already applied (or context drift) — verifying entries instead"
fi

# 3b) apply lcb_runner runtime fixes: STREAM the OpenAI client (TRT-LLM wedges on non-streaming
# nemotron), guard extract_code against None (reasoning models return content=None on truncation),
# and keep attempted-but-empty problems in the --continue_existing resume filter (score as fail, not
# regenerate forever). See docs/findings 2026-06-30-gpt-oss-l3-none-output-crash.md and
# 2026-07-01-nemotron-trt-mtp-wedge.md.
echo "[setup] applying lcb_runner_fixes.patch"
if git -C "$LCB_DIR" apply --check "$REPO_ROOT/layer3_livecodebench/lcb_runner_fixes.patch" 2>/dev/null; then
  git -C "$LCB_DIR" apply "$REPO_ROOT/layer3_livecodebench/lcb_runner_fixes.patch"
else
  echo "[setup] lcb_runner_fixes.patch already applied (or context drift) — skipping"
fi

# 4) verify imports + registry
PYTHONPATH="$LCB_DIR" "$VENV/bin/python" - <<'PY'
from lcb_runner.runner.scenario_router import build_prompt_benchmark  # noqa: F401
from lcb_runner.lm_styles import LanguageModelStore as S
need = ["qwen3-coder-30b", "gpt-oss-120b", "nemotron-super", "tiny-smoke-test"]
missing = [m for m in need if m not in S]
assert not missing, f"registry missing: {missing}"
print("[setup] OK — lcb imports clean; registered:", ", ".join(need))
PY
echo "[setup] done. Serve a model, then: layer3_livecodebench/run-suite.sh --profile <name> --end-date 2024-05-31 --window pre2024m06"

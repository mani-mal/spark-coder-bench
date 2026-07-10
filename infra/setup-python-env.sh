#!/usr/bin/env bash
# setup-python-env.sh — create the project venv and install pinned deps.
# The metrics layer is stdlib-only; these deps are for analysis + Layer 1.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VENV:-$REPO_ROOT/.venv}"

echo "[setup] creating venv at $VENV"
python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --upgrade pip
pip install -r "$REPO_ROOT/requirements.txt"

echo "[setup] freezing exact versions -> requirements.lock.txt (commit for reproducibility)"
pip freeze > "$REPO_ROOT/requirements.lock.txt"

echo
echo "[setup] checks:"
python3 -c "import numpy,scipy,pandas,matplotlib,statsmodels;print('  analysis deps OK')" || echo "  analysis deps MISSING"
python3 -c "import datasets,swebench;print('  layer1 deps OK')" 2>/dev/null || echo "  layer1 deps MISSING (datasets/swebench)"
if docker ps >/dev/null 2>&1; then echo "  docker usable by this user OK"; else
  echo "  docker NOT usable by this user — add to docker group or use sudo (needed for Layer 1 + vLLM container)"; fi
command -v opencode >/dev/null 2>&1 && echo "  opencode on PATH OK" || echo "  opencode NOT on PATH (source ~/.bashrc)"

echo
echo "[setup] done. Activate with: source $VENV/bin/activate"

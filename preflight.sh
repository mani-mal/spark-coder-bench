#!/usr/bin/env bash
# preflight.sh — green/red readiness checklist for the benchmark harness.
# Run it (after sourcing ~/.bashrc and <vllm-serving-lab>/.env) to see exactly
# what is ready and what each layer still needs. Read-only; changes nothing.
#
# Usage: ./preflight.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASKFLOW_DIR="${TASKFLOW_DIR:-$HOME/projects/taskflow-local-app-benchmark}"
VLLM_API_KEY="${VLLM_API_KEY:-local-dgx-spark-key}"
PORT="${VLLM_PORT:-8000}"

if [[ -t 1 ]]; then G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; B=$'\e[1m'; N=$'\e[0m'; else G=""; R=""; Y=""; B=""; N=""; fi
pass=0; warn=0; fail=0
ok()   { echo "  ${G}✔${N} $1"; pass=$((pass+1)); }
wn()   { echo "  ${Y}!${N} $1"; warn=$((warn+1)); }
no()   { echo "  ${R}x${N} $1"; fail=$((fail+1)); }

have() { command -v "$1" >/dev/null 2>&1; }
pyimport() { python3 -c "import $1" >/dev/null 2>&1; }

echo "${B}== Core (Layer 2 build + metrics) ==${N}"
have python3 && ok "python3 ($(python3 --version 2>&1 | awk '{print $2}'))" || no "python3 missing"
if have opencode; then ok "opencode on PATH ($(opencode --version 2>/dev/null | tail -1))"
  else no "opencode NOT on PATH — run: source env.sh  (or ./setup.sh to install)"; fi
if [[ -n "${VLLM_API_KEY:-}" ]]; then ok "VLLM_API_KEY set in env"
  else no "VLLM_API_KEY not set — run: source env.sh"; fi
if curl -sf "http://127.0.0.1:$PORT/v1/models" -H "Authorization: Bearer $VLLM_API_KEY" >/dev/null 2>&1; then
  m=$(curl -s "http://127.0.0.1:$PORT/v1/models" -H "Authorization: Bearer $VLLM_API_KEY" | python3 -c "import sys,json;print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null)
  ok "vLLM serving on :$PORT (model: ${m:-unknown})"
else no "vLLM not responding on :$PORT — run: infra/vllm/serve-model.sh <profile>"; fi
if curl -sf "http://127.0.0.1:$PORT/metrics" >/dev/null 2>&1; then ok "vLLM /metrics reachable (inference collector)"
  else wn "vLLM /metrics not reachable yet"; fi
[[ -d "$TASKFLOW_DIR/.git" ]] && ok "app repo present ($TASKFLOW_DIR)" || no "app repo missing: $TASKFLOW_DIR"
if git -C "$TASKFLOW_DIR" rev-parse baseline-v6 >/dev/null 2>&1; then ok "app baseline-v6 tag present"
  else wn "app baseline-v6 tag missing (run-appcase BASELINE default) — set BASELINE to an existing tag"; fi
nvidia-smi >/dev/null 2>&1 && ok "nvidia-smi works (hardware collector)" || no "nvidia-smi missing"

echo "${B}== Layer 2 scoring (rubric: start backend + build frontend) ==${N}"
have node && ok "node ($(node --version 2>/dev/null))" || no "node missing — needed to start/build the app (install Node 20)"
have npm && ok "npm ($(npm --version 2>/dev/null))" || no "npm missing — needed for npm ci/start/build"
pyimport requests && ok "python 'requests' (rubric HTTP checks)" || no "python 'requests' missing"

echo "${B}== Analysis (stats is stdlib; figures need matplotlib) ==${N}"
ok "stats.py + aggregate-runs.py are stdlib (always runnable)"
for m in numpy scipy pandas matplotlib statsmodels; do
  pyimport "$m" && ok "$m" || wn "$m missing — run: infra/setup-python-env.sh (figures/extended stats)"
done

echo "${B}== Layer 1 (SWE-bench) ==${N}"
if docker ps >/dev/null 2>&1; then ok "docker usable without sudo"
  else no "docker denied — run: newgrp docker (or log out/in)"; fi
pyimport datasets && ok "datasets" || wn "datasets missing — infra/setup-python-env.sh"
pyimport swebench && ok "swebench" || wn "swebench missing — infra/setup-python-env.sh"

echo
echo "${B}Summary:${N} ${G}${pass} ok${N}, ${Y}${warn} warn${N}, ${R}${fail} blocking${N}"
echo "Readiness:"
core_ok=$([[ $fail -eq 0 ]] && echo 1 || echo 0)
echo "  - Layer 2 build+metrics : depends on the Core section above"
echo "  - Layer 2 scoring       : also needs node + npm"
echo "  - Layer 1               : also needs docker (no sudo) + swebench + datasets"
[[ $fail -eq 0 ]] && echo "${G}All blocking checks passed.${N}" || echo "${R}Resolve the ✘ items above before a full run.${N}"
exit "$fail"

#!/usr/bin/env bash
# env.sh — the per-shell environment for the benchmark. SOURCE it, don't execute:
#     source env.sh
# setup.sh appends a `source <repo>/env.sh` line to ~/.bashrc so new shells get this
# automatically. Safe to source repeatedly (idempotent). Covers the things a script
# cannot push into a parent shell on your behalf: PATH, nvm, and the vLLM API key.

# Resolve repo root from this file's location (works when sourced).
_ENV_SELF="${BASH_SOURCE[0]:-$0}"
BENCH_ROOT="$(cd "$(dirname "$_ENV_SELF")" && pwd)"
export BENCH_ROOT

# opencode is installed under ~/.opencode/bin but is not on the default PATH.
if [ -d "$HOME/.opencode/bin" ]; then
  case ":$PATH:" in *":$HOME/.opencode/bin:"*) ;; *) export PATH="$HOME/.opencode/bin:$PATH" ;; esac
fi

# nvm, if Node was installed the no-sudo way (harmless if absent).
if [ -s "$HOME/.nvm/nvm.sh" ]; then
  export NVM_DIR="$HOME/.nvm"
  # shellcheck disable=SC1091
  . "$HOME/.nvm/nvm.sh" >/dev/null 2>&1
fi

# vLLM API key + base URL (VLLM_API_KEY, VLLM_BASE_URL, etc.).
if [ -f "$HOME/dgx-coding-lab/.env" ]; then
  # shellcheck disable=SC1091
  . "$HOME/dgx-coding-lab/.env"
fi
: "${VLLM_API_KEY:=local-dgx-spark-key}"; export VLLM_API_KEY

# The Python venv is only needed for analysis/figures/Layer 1 (metrics + Layer 2 build are
# stdlib + opencode). It is intentionally NOT auto-activated here so plain shells stay clean.
# Activate it when you run analysis:   source "$BENCH_ROOT/.venv/bin/activate"
if [ -n "${BENCH_ENV_VERBOSE:-}" ]; then
  echo "[env] PATH has opencode: $(command -v opencode >/dev/null 2>&1 && echo yes || echo NO)"
  echo "[env] node: $(command -v node >/dev/null 2>&1 && node --version || echo missing)"
  echo "[env] VLLM_API_KEY set; venv at $BENCH_ROOT/.venv (activate manually for analysis)"
fi

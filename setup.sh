#!/usr/bin/env bash
# setup.sh — one-shot, idempotent bootstrap for the benchmark host.
# Installs everything the run needs and is safe to re-run (skips what's already done).
# This MUTATES the system (venv, apt/nvm, ~/.bashrc); preflight.sh only CHECKS. Keep the
# two separate so a readiness check never triggers an install.
#
# Usage:
#   ./setup.sh              # install Node 20 system-wide via apt (uses sudo; prompts once)
#   ./setup.sh --no-sudo    # install Node 20 in user space via nvm (no sudo)
#
# What it cannot do for you (a child process can't change the parent shell):
#   - activate the docker group in THIS shell  -> run `newgrp docker` or re-login
#   - export PATH/keys into THIS shell now      -> run `source env.sh` (or open a new shell;
#                                                   setup adds env.sh to ~/.bashrc)
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NO_SUDO=0; [[ "${1:-}" == "--no-sudo" ]] && NO_SUDO=1

if [[ -t 1 ]]; then G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; B=$'\e[1m'; N=$'\e[0m'; else G=""; R=""; Y=""; B=""; N=""; fi
say()  { echo "${B}[setup]${N} $*"; }
ok()   { echo "  ${G}✔${N} $*"; }
warn() { echo "  ${Y}!${N} $*"; }
err()  { echo "  ${R}x${N} $*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
say "1/5  Python venv + analysis/Layer-1 deps"
if [[ -d "$REPO_ROOT/.venv" ]] && "$REPO_ROOT/.venv/bin/python" -c "import numpy,scipy,pandas,matplotlib,statsmodels" >/dev/null 2>&1; then
  ok "venv already present with analysis deps (skipping)"
else
  bash "$REPO_ROOT/infra/setup-python-env.sh" && ok "venv ready" || err "venv setup failed (see above)"
fi

# ---------------------------------------------------------------------------
say "2/5  Node 20 (Layer 2 rubric builds the frontend with npm — both tracks)"
node_major() { have node && node -v 2>/dev/null | sed 's/^v\([0-9]*\).*/\1/' || echo 0; }
if [[ "$(node_major)" -ge 20 ]]; then
  ok "node $(node -v) + npm $(npm -v 2>/dev/null) already present (skipping)"
else
  installed=0
  if [[ "$NO_SUDO" -eq 0 ]] && have sudo; then
    say "installing Node 20 via NodeSource (sudo; will prompt for your password)"
    if curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt-get install -y nodejs; then
      installed=1; ok "node $(node -v) installed system-wide"
    else
      warn "apt/NodeSource path failed — falling back to nvm (user space)"
    fi
  fi
  if [[ "$installed" -eq 0 ]]; then
    say "installing Node 20 via nvm (no sudo)"
    export NVM_DIR="$HOME/.nvm"
    if [[ ! -s "$NVM_DIR/nvm.sh" ]]; then
      curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
    fi
    # shellcheck disable=SC1091
    . "$NVM_DIR/nvm.sh" && nvm install 20 && nvm alias default 20 \
      && ok "node $(node -v) installed via nvm" || err "nvm node install failed"
  fi
fi

# ---------------------------------------------------------------------------
say "3/5  OpenCode CLI"
if [[ -x "$HOME/.opencode/bin/opencode" ]] || have opencode; then
  ok "opencode present ($("$HOME/.opencode/bin/opencode" --version 2>/dev/null | tail -1 || opencode --version 2>/dev/null | tail -1))"
else
  say "installing opencode"
  curl -fsSL https://opencode.ai/install | bash && ok "opencode installed" || err "opencode install failed"
fi

# ---------------------------------------------------------------------------
say "4/5  Persist shell env (PATH, nvm, VLLM_API_KEY) via env.sh -> ~/.bashrc"
MARKER="# >>> dgx-coding-benchmark env >>>"
if grep -qF "$MARKER" "$HOME/.bashrc" 2>/dev/null; then
  ok "~/.bashrc already sources env.sh (skipping)"
else
  {
    echo ""
    echo "$MARKER"
    echo "[ -f \"$REPO_ROOT/env.sh\" ] && source \"$REPO_ROOT/env.sh\""
    echo "# <<< dgx-coding-benchmark env <<<"
  } >> "$HOME/.bashrc"
  ok "added env.sh to ~/.bashrc (new shells get opencode PATH + API key automatically)"
fi

# ---------------------------------------------------------------------------
say "5/5  Docker (Layer 1 / SWE-bench only — NOT needed for Layer 2)"
if docker ps >/dev/null 2>&1; then
  ok "docker usable in this shell"
elif id -nG 2>/dev/null | tr ' ' '\n' | grep -qx docker; then
  warn "you ARE in the docker group, but it's not active in THIS shell."
  warn "activate it with:  newgrp docker   (or just log out and back in)"
else
  warn "not in the docker group. An admin must run:  sudo usermod -aG docker $USER   then re-login."
  warn "(Layer 2 does not need docker — only Layer 1/SWE-bench does.)"
fi

# ---------------------------------------------------------------------------
echo
say "bootstrap done. Loading env into THIS shell and running preflight..."
# shellcheck disable=SC1091
source "$REPO_ROOT/env.sh"
echo
exec bash "$REPO_ROOT/preflight.sh"

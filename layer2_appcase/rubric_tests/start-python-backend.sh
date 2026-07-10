#!/usr/bin/env bash
# start-python-backend.sh — rubric launcher for the Python-track backend. Run with cwd = the
# model's backend dir (run_rubric.py Popens it there).
#
# Why this exists (two harness-rigidity issues it fixes — see
# docs/findings/2026-06-25-harness-issues-and-fixes.md):
#   1. PEP 668: the Debian/Ubuntu Spark host marks system Python externally-managed, so a bare
#      `pip install` is refused and EVERY python backend scored 0. We install into a per-run venv
#      (which is what a real deployment does anyway).
#   2. Entrypoint path: the prompt pins `uvicorn app.main:app`, but a correct FastAPI app may live
#      at `main:app` or `app:app`. Zeroing a working app over module nesting is the same anti-pattern
#      as the npm-ci/lockfile confound, so we probe the standard entrypoints and start the first that
#      exposes an `app`. (A model that ships no importable FastAPI `app` still legitimately fails.)
set -e

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

EP="$(.venv/bin/python - <<'PY'
import importlib, importlib.util
for cand in ("app.main", "main", "app"):
    try:
        if importlib.util.find_spec(cand) is None:
            continue
        mod = importlib.import_module(cand)
        if hasattr(mod, "app"):
            print(cand + ":app")
            break
    except Exception:
        continue
else:
    print("app.main:app")  # pinned default; uvicorn will surface the real import error
PY
)"

echo "[start-python-backend] resolved entrypoint: $EP"
exec .venv/bin/python -m uvicorn "$EP" --host 127.0.0.1 --port 4000

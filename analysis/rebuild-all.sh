#!/usr/bin/env bash
# Rebuild EVERY published summary table, ledger, figure, and analysis artifact from the
# retained raw runs — one command, deterministic order. This is the reproducibility entry
# point required by docs/publishing-plan.md: an arXiv reader (or `make rebuild`) regenerates
# the entire results/summary/ + reports/charts/ tree without any manual step.
#
# Inputs  : results/raw/<run-id>/ (per-run summaries + manifests; committed) and, for L3,
#           results/raw/*-l3-*/lcb-predictions.json.
# Outputs : results/summary/*.csv, results/summary/stats-report.txt, reports/charts/*.
#
# Every step is pure re-derivation from committed data — it does NOT re-serve any model or
# re-run any generation. Run inside the project venv (infra/setup-python-env.sh && source .venv/bin/activate).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-python3}"
LONG="results/summary/benchmark-long.csv"

step() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

step "0/6  aggregate raw runs -> benchmark-long.csv + benchmark-summary.csv"
# NOTE: consumes every dir under results/raw/. Until an explicit inclusion manifest exists
# (open gate item), exclusions are enforced by what is committed under results/raw/.
"$PY" analysis/aggregate-runs.py --results-root results/raw --out results/summary

step "1/6  inferential statistics (Wilson / McNemar / Holm) -> stats-report.txt"
"$PY" analysis/stats.py --long "$LONG" | tee results/summary/stats-report.txt

step "2/6  published figures -> reports/charts/*.png + *.csv"
"$PY" analysis/figures.py --long "$LONG" --out reports/charts
# quality/thesis figures (ablation, per-layer success, L3 truncation) for the report
"$PY" analysis/figures_quality.py

step "3/6  L2 C1 rescore (k/29 + k/25) -> l2-rescore-25.csv + l2-ablation-contract.csv"
"$PY" analysis/l2-rescore.py --long "$LONG"

step "4/6  L3 conditional / selection-bias analysis -> l3-conditional-analysis.csv"
"$PY" analysis/l3-conditional.py

step "5/6  failure-aware re-summary + per-run ledgers (L1/L2/L3)"
"$PY" analysis/robust-summary.py

step "6/6  self-tests (stats + robust-summary)"
"$PY" analysis/stats.py --selftest
"$PY" analysis/robust-summary.py --selftest

printf '\n\033[1;32mAll tables/ledgers/figures rebuilt.\033[0m Regenerated under results/summary/ and reports/charts/.\n'

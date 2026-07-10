# DGX Spark coding-model benchmark — reproducibility entry points.
# These targets re-derive published artifacts from committed raw runs; they do NOT
# re-serve models or re-run generations (that needs the DGX Spark hardware).
.PHONY: help rebuild ledgers stats figures provenance selftest

help:
	@echo "make rebuild     - regenerate every summary table, ledger, and figure from results/raw/"
	@echo "make ledgers     - regenerate L1/L2/L3 per-run ledgers only"
	@echo "make stats       - inferential statistics -> results/summary/stats-report.txt"
	@echo "make figures     - published figures -> reports/charts/"
	@echo "make provenance  - refresh container-digest + dataset-checksum manifest"
	@echo "make selftest    - run analysis self-tests"

rebuild:
	bash analysis/rebuild-all.sh

ledgers:
	python3 analysis/robust-summary.py

stats:
	python3 analysis/stats.py --long results/summary/benchmark-long.csv | tee results/summary/stats-report.txt

figures:
	python3 analysis/figures.py --long results/summary/benchmark-long.csv --out reports/charts
	python3 analysis/figures_quality.py

provenance:
	bash infra/provenance/capture-provenance.sh

selftest:
	python3 analysis/stats.py --selftest
	python3 analysis/robust-summary.py --selftest

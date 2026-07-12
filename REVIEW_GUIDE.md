# Review Guide

This repository is a **systems and methodology case study** of running three
open-weight MoE coding models locally on an NVIDIA DGX Spark — across three
evaluation layers (agentic bug-fixing, full-stack app building, single-shot
code generation). It is **not** framed as a definitive model-ranking paper; the
serving-feasibility constraints and measurement pitfalls are the subject.

You do not need to read every file. To understand what the entire project is
about, read these two documents in order:

1. **[`docs/BENCHMARK_OVERVIEW.md`](docs/BENCHMARK_OVERVIEW.md)** — the fastest
   full picture: hardware, the three models, the three layers, and the headline
   serving-feasibility findings on one page. Start here.

2. **[`reports/dgx-spark-coding-model-benchmark-report.md`](reports/dgx-spark-coding-model-benchmark-report.md)**
   — the canonical written report: motivation, setup, methodology, and results,
   with each results table mapped to its source data.

Those two cover the whole study end to end.

## If you are assessing publication readiness

Two independent audits already reviewed this work before external peer review:

- **[`docs/audits/benchmark-audit-and-arxiv-recommendation.md`](docs/audits/benchmark-audit-and-arxiv-recommendation.md)**
  — methodology/framing audit (recommends the case-study framing over a
  model-ranking paper).
- **[`docs/audits/independent-code-review.md`](docs/audits/independent-code-review.md)**
  — independent code-and-data review with a fix list.

For fairness controls and the exact metric definitions, see
[`docs/methodology.md`](docs/methodology.md).

## Going deeper (optional)

For a full, ordered walk through **every** document in the repo, see
**[`docs/READING_ORDER.md`](docs/READING_ORDER.md)** — a tiered map (orientation →
task spec → scoring → results → audits → lab notebook) for detailed study.

`docs/findings/` is a dated lab notebook documenting every decision, blocker,
and result along the way. It is supporting evidence, not required reading. Note
that the early low-N notes (`n3`, `n8`, `n20`) are **deliberately superseded** —
they document why low-sample evaluations are unstable, not final results.

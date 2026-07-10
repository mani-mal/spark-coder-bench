# AI usage and provenance

This document discloses, for transparency and reproducibility, where AI systems were used
in producing this repository. It exists so that AI involvement is stated openly rather than
implied by tool-specific config files. Nothing here is required to *run* the benchmark; it
is context for readers and reviewers.

## Summary

- **Development.** The harness, scripts, and much of the prose were written with the
  assistance of an agentic AI coding assistant (an LLM driving edits and shell commands
  through a CLI). A human author reviewed and directed the work and is responsible for the
  final content.
- **The models under evaluation are unrelated to the tooling above.** The benchmark's
  subjects are `gpt-oss-120b`, `Nemotron-3-Super-120B-A12B`, and `Qwen3-Coder-30B-A3B`.
  The AI assistant used to *build* the repo is not one of the systems being measured.

## AI-generated documents

The following documents were produced primarily by AI models and are labeled as such. They
were retained because their content is substantive, but readers should treat them as
AI-authored analyses that a human then verified — not as independent human peer review:

| Document | Origin | Status |
| --- | --- | --- |
| `docs/audits/benchmark-audit-and-arxiv-recommendation.md` | External AI model asked to audit the repo | AI-generated; conclusions human-verified in `docs/findings/2026-07-02-audit-verification-and-decision.md` |
| `docs/audits/independent-code-review.md` | A second, different AI model asked to review code/metrics | AI-generated; findings (C1/C2) independently re-checked against raw data before acceptance |
| `docs/design/harness-design.md` | AI-assisted design spec written before implementation | AI-assisted; describes intended design, not a post-hoc claim |

"Independent" in the review document means *a different model / separate pass*, not
independent human review.

## Human verification

Where an AI-generated finding affected a published conclusion, it was re-derived from the
raw run data before acceptance. The dated notes in `docs/findings/` record those
verification steps (e.g. the L2 invisible-contract and L3 conditional-selection-bias
findings were each traced back to primary data, not taken on the reviewing model's word).

## What is intentionally not in this repo

Editor/agent workflow configuration (assistant instruction files, agent scratch state) is
excluded and git-ignored. It exposed local machine paths and internal workflow detail
without aiding reproducibility. This `AI_USAGE.md` is the intended, controlled disclosure of
AI involvement in its place.

# Layer 1 (SWE-bench Verified, arm64 subset) — first cross-model results

**Date:** 2026-06-26
**Scope:** Layer 1, N=1 (pass@1), gpt-oss-120b vs qwen3-coder-30b, on the 29-task
arm64-buildable subset of SWE-bench Verified. vLLM 0.15.1 on DGX Spark GB10, native
arm64 task images, official `FAIL_TO_PASS`/`PASS_TO_PASS` grading. seed=0, temp=0.2.

## Headline

On focused, single-file-ish bug-fixing (SWE-bench), **gpt-oss-120b resolves more tasks
than qwen3-coder-30b (37.9% vs 24.1% pass@1), but the gap is not statistically
significant at N=29** (McNemar p=0.29). This is a different shape from Layer 2, where
the two were statistically indistinguishable *and both weak* on a full-stack app build.

| Model | pass@1 | Wilson 95% CI | decode tok/s | Wh/task | gen tokens | wall s | tok/J | peak mem |
|---|---|---|---|---|---|---|---|---|
| gpt-oss-120b | **11/29 = 37.9%** | [22.7%, 56.0%] | 26.9 | 1.35 | 3233 | 162 | 72.0 | 109.4 GiB |
| qwen3-coder-30b | **7/29 = 24.1%** | [12.2%, 42.1%] | 19.7 | 1.04 | 2128 | 129 | 69.6 | 107.3 GiB |

(throughput/energy/mem are per-task means over 29 tasks; wall = agent window.)

McNemar on the paired 29 tasks: discordant pairs b=6 (gpt-oss solves, qwen fails),
c=2 (qwen solves, gpt-oss fails), p=0.29, ns after Holm-Bonferroni.

## Reading

- **gpt-oss is the stronger bug-fixer here**, and pays for it: ~1.5× the generated
  tokens (3233 vs 2128) and ~30% more energy per task (1.35 vs 1.04 Wh), while actually
  decoding *faster* (26.9 vs 19.7 tok/s — the larger MXFP4 MoE runs its 5.1B active
  params faster than qwen's 3.3B active here). Energy efficiency (tok/J) is ~equal (~70).
- **Not significant at N=29.** The CIs overlap ([22.7,56.0] vs [12.2,42.1]) and McNemar
  p=0.29. To claim a real Layer-1 gap, raise N (more repeats and/or a larger arm64
  subset). The *direction* (gpt-oss > qwen) is consistent with a 6-vs-2 discordant split
  but underpowered.
- **Layer 1 vs Layer 2 disagree in shape.** Layer 2 node: qwen nominally ahead
  (0.177 vs 0.121), ns. Layer 1: gpt-oss ahead (0.379 vs 0.241), ns. Neither layer alone
  declares a winner; together they say *task type matters* — a focused-fix benchmark and
  a build-from-scratch benchmark rank these two models differently. That contrast is
  itself a paper-worthy point: "which local coding model is better" is task-dependent.
- **Memory:** both peak ~107–109 GiB of the 128 GiB unified memory — close to the
  ceiling, consistent with single-model-at-a-time serving being mandatory on this box.

## Validity / caveats

- pass@1 (N=1) — no per-task repeats yet, so within-task run-to-run variance (which
  Layer 2 showed is large for these models) is not captured. The honest next step for a
  significant Layer-1 claim is N≥3 per task on the 29-task subset, and/or expanding the
  subset beyond the stratified 29.
- arm64 subset (29 tasks, 10/12 repos; xarray + scikit-learn don't build — see
  `coverage.md`). This is a relative A/B on identical hardware, so any arm64-vs-x86
  environment difference cancels across models. Coverage is disclosed, not hidden.
- The harness was debugged to run at sweep scale (venv python, user-writable HF cache,
  flock) — see `2026-06-26-layer1-arm64-enablement.md` and the harness-issues log.

## Bottom line

First real Layer-1 number: **gpt-oss-120b 37.9% vs qwen3-coder-30b 24.1% pass@1 on the
arm64 SWE-bench subset, ns at N=29.** Combined with Layer 2, the cross-model ranking is
task-dependent and neither difference is yet significant — both point to "raise N" as the
path to a publishable claim, and to *task type* as a first-class variable in the story.

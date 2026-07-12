# Reading Order — Full Document Map

This is the complete, ordered map of every document in the repository, grouped
into tiers for a **detailed study** of the project. It moves from orientation →
what was tested → how it was scored → results → the critical audits → the full
lab-notebook trail.

If you only want the quick path, read [`../REVIEW_GUIDE.md`](../REVIEW_GUIDE.md)
instead — it points to just the two core documents. Use this file when you want
to understand the entire project in depth.

> **Note on superseded notes:** Tiers 0–5 are the study itself. Tier 6 is a
> dated lab notebook. The early low-N notes (`n3`, `n8`, `n20`) are
> **deliberately superseded** — they document *why low-sample evaluations are
> unstable*, not final results. Don't read them as headline numbers.

---

## Tier 0 — Start here (orientation)

1. [`README.md`](../README.md) — Repo entry point; frames the work as a systems/methodology case study of 3 MoE coding models on DGX Spark, with the model/quant/runtime coupling table.
2. [`docs/HELP.md`](HELP.md) — Plain-language mental model: what the benchmark varies, builds, scores, and measures.
3. [`docs/BENCHMARK_OVERVIEW.md`](BENCHMARK_OVERVIEW.md) — Single-page technical map (hardware, 3 models, 3 layers, serving-feasibility findings).
4. [`docs/AI_USAGE.md`](AI_USAGE.md) — Transparency disclosure: where AI was used and which docs are AI-authored vs. human-verified.

## Tier 1 — Methodology & framing (read before results)

5. [`docs/methodology.md`](methodology.md) — Fairness controls and per-run metric catalogue; what's held constant vs. varied.
6. [`docs/design/harness-design.md`](design/harness-design.md) — Pre-implementation design spec: hardware reality and locked decisions.
7. [`docs/publishing-plan.md`](publishing-plan.md) — Roadmap of target outputs (GitHub / report / arXiv) and framing constraints.

## Tier 2 — What the models were asked to do (the task spec)

8. [`benchmark-spec/app-requirements.md`](../benchmark-spec/app-requirements.md) — Spec for "TaskFlow Local," the full-stack app models must build.
9. [`benchmark-spec/run-protocol.md`](../benchmark-spec/run-protocol.md) — Fair-comparison run rules (runner procedures, model rules, intervention categories, time-box).
10. [`benchmark-spec/expected-output.md`](../benchmark-spec/expected-output.md) — Required output folders/structure and mandatory final-response summary.
11. [`benchmark-spec/evaluation-rubric.md`](../benchmark-spec/evaluation-rubric.md) — Historical 100-point rubric, never implemented; retained for provenance (superseded by k/29).
12. [`layer2_appcase/api-contract.md`](../layer2_appcase/api-contract.md) — Frozen TaskFlow API contract (ports, endpoints, status codes, JSON shapes) scored against.
13. [`layer2_appcase/prompt.md`](../layer2_appcase/prompt.md) — Pinned identical build prompt for TaskFlow Local.
14. [`prompts/build-node-track.md`](../prompts/build-node-track.md) — Node/TypeScript+React build-track prompt.
15. [`prompts/build-python-track.md`](../prompts/build-python-track.md) — Python FastAPI+React build-track prompt.
16. [`prompts/self-review.md`](../prompts/self-review.md) — Read-only model self-assessment prompt (7 criteria, pass/partial/fail).

## Tier 3 — The three evaluation layers & measurement

17. [`layer1_swebench/README.md`](../layer1_swebench/README.md) — Layer 1: agentic bug-fix over a disclosed 29-task ARM64-buildable SWE-bench Verified subset.
18. [`layer1_swebench/coverage.md`](../layer1_swebench/coverage.md) — How the 29-task subset was selected; warns it isn't SWE-bench Verified performance.
19. [`layer1_swebench/eval/README.md`](../layer1_swebench/eval/README.md) — Placeholder note for ARM64/version-specific harness overrides.
20. [`layer2_appcase/COVERAGE.md`](../layer2_appcase/COVERAGE.md) — Source of truth for the k/29 acceptance-check metric; the 29 checks and the contract-visibility bug/rerun.
21. [`layer3_livecodebench/README.md`](../layer3_livecodebench/README.md) — Layer 3: single-shot code-gen quality via LiveCodeBench (pass@1).
22. [`layer3_livecodebench/coverage.md`](../layer3_livecodebench/coverage.md) — L3 exposure record: 512-problem pre-June-2024 window, per-model cutoffs, config deviations.
23. [`infra/metrics/README.md`](../infra/metrics/README.md) — Three-source (hardware/inference/accounting) time-synced metric collection and derived energy/latency metrics.

## Tier 4 — Headline results

24. [`reports/dgx-spark-coding-model-benchmark-report.md`](../reports/dgx-spark-coding-model-benchmark-report.md) — The canonical written report; every table mapped to a source CSV.
25. [`docs/findings/2026-07-11-cross-model-performance-resource-usage.md`](findings/2026-07-11-cross-model-performance-resource-usage.md) — Consolidated per-model, per-layer wall-clock/GPU/memory/throughput/energy.

## Tier 5 — The critical audits (the "is this publishable?" reviews)

26. [`docs/audits/benchmark-audit-and-arxiv-recommendation.md`](audits/benchmark-audit-and-arxiv-recommendation.md) — First audit: recommends against an arXiv model-ranking paper; construct-validity + confounding problems.
27. [`docs/audits/independent-code-review.md`](audits/independent-code-review.md) — Second independent review: recomputed headline numbers, surfaced 4 new critical problems (invisible contract, L3 selection bias).

## Tier 6 — Lab-notebook findings (chronological trail; optional deep-dive)

**Design/decision notes and confirmed results:**

- [`2026-06-24-deepseek-v2-lite-agentic-tool-use.md`](findings/2026-06-24-deepseek-v2-lite-agentic-tool-use.md) — DeepSeek codes well but won't autonomously call tools; motivates gating agentic evals on tool-use.
- [`2026-06-25-harness-issues-and-fixes.md`](findings/2026-06-25-harness-issues-and-fixes.md) — Harness/infra bugs hit during N=1 validation and fixes.
- [`2026-06-25-nemotron-super-vllm-mixed-precision.md`](findings/2026-06-25-nemotron-super-vllm-mixed-precision.md) — Nemotron's MIXED_PRECISION NVFP4 checkpoint unservable on vLLM 0.15.1.
- [`2026-06-25-rubric-npm-ci-confound.md`](findings/2026-06-25-rubric-npm-ci-confound.md) — `npm ci`/collapsing-denominator confound behind qwen's 0.0; fixed with fallback + fixed-29 denominator.
- [`2026-06-26-architecture-framing-note.md`](findings/2026-06-26-architecture-framing-note.md) — Report architecture (MoE/Mamba-hybrid) as descriptive, not a controlled causal variable.
- [`2026-06-26-layer1-arm64-enablement.md`](findings/2026-06-26-layer1-arm64-enablement.md) — Making SWE-bench Verified run on aarch64; three x86-assumption bugs and fixes.
- [`2026-06-26-layer1-swebench-results.md`](findings/2026-06-26-layer1-swebench-results.md) — **L1 result:** gpt-oss 37.9% vs qwen 24.1% pass@1, not significant (McNemar p=0.29).
- [`2026-06-27-nemotron-trtllm-memory.md`](findings/2026-06-27-nemotron-trtllm-memory.md) — Nemotron TRT-LLM load-time unified-memory wall; added meminfo watchdog.
- [`2026-06-28-benchmark-comparability-and-pinchbench.md`](findings/2026-06-28-benchmark-comparability-and-pinchbench.md) — Debunks viral "Nemotron 85.6% PinchBench"; scores aren't comparable across harnesses.
- [`2026-06-28-is-nemotron-result-fair.md`](findings/2026-06-28-is-nemotron-result-fair.md) — Nemotron's last-place agentic ranking is a real capability boundary, not an artifact.
- [`2026-06-29-benchmark-selection-for-arxiv.md`](findings/2026-06-29-benchmark-selection-for-arxiv.md) — Scope: keep L1+L2, add LiveCodeBench; arm64-native runnability is binding.
- [`2026-06-29-full-matrix-results.md`](findings/2026-06-29-full-matrix-results.md) — **Capstone:** no model serves on both vLLM and TRT-LLM; same-model bridge unachievable.
- [`2026-06-29-gpt-oss-trt-blocker.md`](findings/2026-06-29-gpt-oss-trt-blocker.md) — gpt-oss-120b MXFP4 deadlocks at server→executor handoff on sm_121a (blocked).
- [`2026-06-29-livecodebench-integration-scope.md`](findings/2026-06-29-livecodebench-integration-scope.md) — L3 scope: no contamination-free window; use contamination-balanced equal-exposure window.
- [`2026-06-29-nvidia-blog-external-validation.md`](findings/2026-06-29-nvidia-blog-external-validation.md) — Cross-checks matrix vs. NVIDIA/community DGX Spark publications; rankings consistent.
- [`2026-06-29-qwen-trt-moe-blackwell-blocker.md`](findings/2026-06-29-qwen-trt-moe-blackwell-blocker.md) — qwen3-coder-30b bf16 MoE: no working TRT-LLM kernel on sm_121a (blocked).
- [`2026-06-30-gpt-oss-l3-none-output-crash.md`](findings/2026-06-30-gpt-oss-l3-none-output-crash.md) — gpt-oss L3 crash: content=None from reasoning truncation broke lcb_runner.
- [`2026-06-30-kv-cache-quant-unified-memory.md`](findings/2026-06-30-kv-cache-quant-unified-memory.md) — Serve unquantized KV cache; KV-quant counterproductive on GB10 unified memory.
- [`2026-07-01-nemotron-trt-mtp-wedge.md`](findings/2026-07-01-nemotron-trt-mtp-wedge.md) — Nemotron TRT-LLM executor wedge on non-streaming responses; fixed by streaming.
- [`2026-07-01-nemotron-trt-warmup-wedge.md`](findings/2026-07-01-nemotron-trt-warmup-wedge.md) — Aborted request during ~215s warmup poisons executor; fixed with patient timeout.
- [`2026-07-02-audit-verification-and-decision.md`](findings/2026-07-02-audit-verification-and-decision.md) — Audit verified; decision to reframe as a systems + methodology case study.
- [`2026-07-02-environment-provenance-pre-ota.md`](findings/2026-07-02-environment-provenance-pre-ota.md) — Freezes exact hardware/driver/image the published results ran on (pre-OTA).
- [`2026-07-03-l2-contract-invisible.md`](findings/2026-07-03-l2-contract-invisible.md) — **Bug C1:** L2 graded a contract models never received; k/25 rescore mitigation.
- [`2026-07-03-l2-rerun-with-contract-decision.md`](findings/2026-07-03-l2-rerun-with-contract-decision.md) — Rerun L2 with contract visible as before/after ablation.
- [`2026-07-03-l3-conditional-selection-bias.md`](findings/2026-07-03-l3-conditional-selection-bias.md) — **Bug C2:** retires "nemotron 85.1% conditional"; replaced with paired 327-problem analysis.
- [`2026-07-08-qwen3.6-roster-gap-and-nvfp4-coder-opportunity.md`](findings/2026-07-08-qwen3.6-roster-gap-and-nvfp4-coder-opportunity.md) — Flags missing Qwen3.6 (35B-A3B NVFP4 coder); proposes it as an arm (open, in peer review).
- [`2026-07-11-l3-token-budget-and-verbosity-options.md`](findings/2026-07-11-l3-token-budget-and-verbosity-options.md) — Keep L3's 8192-token budget fixed; truncation penalizing verbose nemotron is a result, not a bug.
- [`2026-07-11-llm-eval-metric-coverage.md`](findings/2026-07-11-llm-eval-metric-coverage.md) — Maps captured metrics to a 12-category LLM-eval taxonomy; adds quality-adjusted efficiency.

**Superseded low-N result notes** (kept for the variance-instability story — read as *why low-N is unstable*, not as results):

- [`2026-06-25-n3-layer2-results.md`](findings/2026-06-25-n3-layer2-results.md) — L2 N=3: N=1's decisive gpt-oss win was a sampling artifact.
- [`2026-06-25-n8-node-results.md`](findings/2026-06-25-n8-node-results.md) — L2 node N=8: ranking inverts, models statistically indistinguishable.
- [`2026-06-26-n20-node-results.md`](findings/2026-06-26-n20-node-results.md) — L2 node N=20: ranking flips a third time; strongest low-N instability evidence.
- [`2026-06-26-python-n8-results.md`](findings/2026-06-26-python-n8-results.md) — L2 python N=8: 0%/0% working apps; node-vs-python asymmetry.
- [`2026-06-27-nemotron-layer2-variance.md`](findings/2026-06-27-nemotron-layer2-variance.md) — Nemotron collapses on L2 with four failure modes; variance is the finding.

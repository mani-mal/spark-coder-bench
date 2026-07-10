# Audit of the DGX Spark coding-model benchmark

**Audit date:** 2026-07-02

**Reviewed repositories**

- `dgx-spark-coding-model-benchmark` at commit `c2b660afeb25747bd0ec5a5d8e2ca60b6f9172ce`
- `taskflow-local-app-benchmark` at commit `a86791e8f19e1c6982d14ffce9147cf981fa370d`

## Executive recommendation

**Do not submit the current work to arXiv as a finished comparative model-benchmark paper.** The engineering work and retained artifacts are valuable, but the present ranking claims are not supported strongly enough. The main problems are Layer 2 construct validity, model/runtime/precision/scaffold confounding, inconsistent and evolving protocols, unequal samples, improper handling of infrastructure failures and outliers, and claims stronger than the design permits.

The strongest publishable version is a narrower **systems and methodology case study of local coding-agent evaluation on DGX Spark**. Make serving feasibility and measurement pitfalls the main results. Treat model-quality results as exploratory outcomes of exact deployment configurations. A strong model-comparison paper needs a new preregistered run after the protocol and analysis are frozen.

## Scope and checks performed

I reviewed the main README, HELP, methodology, publishing plan, benchmark specifications, prompts, runtime/model registry, all three layer runners, metric collection and aggregation, analysis and figure code, summary CSVs, selected raw artifacts, and dated findings. Python sources compile. The complete built-in `analysis/stats.py --selftest` passes.

This was a source/data audit, not a physical rerun of the multi-hour model workloads. The DGX repository currently has untracked publication inputs: `docs/HELP.md` and two 2026-07-02 provenance files. Resolve this before release.

## Critical findings

### 1. Layer 2 does not implement the published 100-point rubric

The frozen TaskFlow specification defines a weighted 100-point rubric covering completeness, runtime, tests, code quality, security, documentation, and agent efficiency. The implemented scorer instead reports the fraction of 29 equally weighted checks in `contract.CANONICAL_CHECKS`.

This matters because:

- “Layer 2 rubric pass rate” is not the score in `benchmark-spec/evaluation-rubric.md`.
- Health, lockfile, dashboard response, and security assertions each have equal weight.
- The app's tests are executed but are not included in the canonical score.
- Code quality, documentation, agent efficiency, maintainability, and most frontend behavior are not scored.
- The only frontend check is whether `npm run build` succeeds. This does not establish that the full-stack UI works.
- Password hashing is not verified. The security check only ensures the login response lacks keys named `password` or `passwordHash`.
- Member authorization is under-tested: project creation denial is checked, but assigned-versus-unassigned task update rights are not.
- Status and text search are checked, but required priority, assignee, and project filters are not.
- Persistence across restart, logout/protected frontend routing, edit-task behavior, due-date validation, and several required pages/workflows are not verified.

**Required action:** Rename the metric to **TaskFlow API acceptance-check fraction**, or implement and validate the frozen 100-point rubric. Do not interpret it as full-stack app quality. Publish a requirement-to-check coverage matrix.

### 2. The treatment is a deployment bundle, not model identity

The arms jointly vary model architecture/size, checkpoint precision, serving runtime, tool parser, likely chat template, reasoning behavior, and some memory/context settings. Nemotron runs only on TensorRT-LLM; Qwen and gpt-oss run only on vLLM. Consequently, Nemotron-versus-other differences cannot isolate model, runtime, quantization, or scaffold compatibility.

The documentation sometimes admits this but still uses model-intrinsic or causal language such as “capability boundary,” “reasoning-model split,” and “collapses.” The design does not support those causal claims.

**Required action:** Name each arm as a configuration, e.g. `Nemotron-NVFP4 + TRT-LLM + OpenCode`, and restrict conclusions to that configuration on this machine. Serving incompatibility is a valid systems finding, not proof of intrinsic coding quality.

### 3. Public documents describe incompatible studies

Examples:

- Root README says two layers; HELP says three.
- README/methodology say both FP4 models use vLLM Marlin; current HELP/findings say Nemotron cannot load in vLLM and runs only on TRT-LLM.
- README quickstart serves Nemotron through `infra/vllm/serve-model.sh`.
- README status says Layer 1 still needs execution, despite published results.
- Methodology describes the 100-point rubric; actual results use 29 unweighted checks.
- TaskFlow README says `baseline-v1`; the runner defaults to `baseline-v6`.
- TaskFlow `opencode.json` labels Nemotron as a vLLM-local model despite reported TRT runs.
- Documents refer to 27, 28, and 29 Layer 2 checks.

These inconsistencies prevent readers from determining which protocol produced each result.

**Required action:** Publish one immutable, versioned protocol. Archive older designs as historical material. Reconcile the layer count, runtime mapping, baseline, scorer, and quickstart everywhere.

### 4. Material protocol changes occurred during collection

Dated findings record changes to baseline tags, npm installation fallback, denominators, missing-layout handling, outcome-only aggregation, watchdogs, runtime attempts, and sample sizes. These may be reasonable fixes, but final results must distinguish:

- exploratory/pilot runs;
- runs invalidated by harness defects;
- runs validly rescored from retained outputs;
- confirmatory runs after the final freeze.

Mixing pre- and post-fix results introduces instrumentation and history bias.

**Required action:** Add per-run protocol version, spec/baseline/scorer/harness commits, model revision, container digest, and validity status. Exclude pre-freeze data from confirmatory claims unless compatible rescoring is demonstrably valid.

### 5. Infrastructure and evaluator failures become model failures

Nemotron Layer 1 counts watchdog kills and DNS-dropped tasks as unresolved. A preregistered, uniform agent timeout can be a model failure. A Git clone/DNS failure is not. The findings explicitly mention four DNS failures.

`run-task.py` also:

- continues after nonzero agent exit;
- evaluates with `check=False`;
- writes `resolved=0` when no evaluation report is found;
- uses broad working-directory globs that could associate a stale report;
- lacks the later-described watchdog in the canonical runner;
- reuses a work directory without an explicit clean guard.

**Required action:** Record typed outcomes: `resolved`, `unresolved_valid`, `agent_timeout`, `agent_error`, `clone_error`, `evaluation_error`, `server_error`, and `missing_artifact`. Retry infrastructure failures under a frozen policy. Never silently turn missing measurement into failure.

### 6. Energy means are dominated by unequal work and a severe runaway

The long CSV contains a Nemotron L1 task lasting about 46,733 seconds (roughly 13 hours) and consuming about 655 kJ. The published mean L1 energy is therefore heavily driven by an operational runaway. Other rows have missing metrics but zero outcomes. Mean energy “per run” also compares trajectories with different token counts, tool time, dependency installation, and task complexity.

The figure code uses arithmetic means without an outlier/censoring policy. Peak unified memory is whole-system unified memory, not isolated model VRAM.

**Required action:** Report raw distributions, median/IQR, robust/bootstrap intervals, timeout-censored values, and sensitivity with/without operational failures. Separate server inference, agent/tool time, dependency installation, energy/token, energy/valid attempt, and energy/success. Compare matched tasks.

### 7. Statistical claims exceed the sample design

- L1 uses 29 selected tasks and one attempt per model/task. Observed 11/29, 7/29, and 6/29 differences are highly uncertain.
- L2 uses unequal N: 20/8 for vLLM models and 4/4 for Nemotron. Stopping because early values are floor-saturated is post-hoc.
- L2 distributions are bounded, zero-inflated, and visibly bimodal; mean plus population SD is inadequate.
- The “working app” threshold of 0.5 is arbitrary and unvalidated. A score over 0.5 need not mean a usable UI, secure app, or complete app.
- McNemar applies to paired binary outcomes, not unequal unpaired L2 repeats. Nonsignificance does not prove equivalence.
- Multiple layers, tracks, metrics, model pairs, and hypotheses create broader multiplicity than the limited Holm correction covers.
- The statistical utility code is sounder than the paper-facing claims: effect sizes and intervals are not consistently presented beside conclusions.

**Required action:** Prespecify primary outcomes and contrasts. Use paired task-level effects and intervals for L1/L3. Show complete L2 empirical distributions and consider a two-part/hierarchical model. Treat current tests as exploratory. Do not say “firm separation” without a reported, defensible inferential result.

### 8. The Layer 1 ARM64 subset limits generalization

Selecting 29 tasks whose gold patches build and resolve on ARM64 is a practical solution, but changes the population and may overrepresent certain repositories or task types. This is not SWE-bench Verified performance and is not a random sample. Repeating the same tasks estimates decoding variability, not broader task generalization.

The claim that contamination “cancels” because models see identical tasks is unjustified. Models can have different training exposure to the same tasks.

**Required action:** Call the metric “pass rate on the disclosed 29-task ARM64-buildable subset.” Publish selection flow, all attempted tasks, exclusion reasons, repository composition, and comparison with the full benchmark. Do not extrapolate to absolute SWE-bench Verified performance.

### 9. Layer 3 contamination logic is incorrect

The study chooses problems before the earliest training cutoff and calls them exposure-balanced because every model could have memorized them. Equal chronological eligibility is not equal contamination. Training corpora, deduplication, benchmark ingestion, and cutoff dates differ. Later-cutoff models had more opportunity for exposure.

The 512 observations are heterogeneous problems, not repeated independent model runs. Wilson intervals do not handle paired model effects, problem clustering, or source/difficulty heterogeneity.

**Required action:** Call this a fixed, historical, contamination-possible window. Do not state that contamination cancels or that exposure is balanced. Use paired bootstrap/permutation over problems, stratify where possible, and add contamination sensitivity analysis.

### 10. Layer 3 executes generated code without real isolation

The repository discloses that bubblewrap fails and evaluation runs with processes/timeouts only. These do not prevent filesystem access, network access, process spawning, or host modification. Calling risk low is not a security control.

**Required action:** Use a no-network container or VM with read-only root, unprivileged UID, constrained scratch space, and cgroup CPU/memory/PID limits for publication runs.

### 11. Reproducibility is promising but not release-ready

Strengths include raw directories, manifests, clock records, environment notes, locked Python requirements, and machine-readable summaries. Remaining gaps:

- key publication documents are untracked;
- the relation between TaskFlow HEAD, baseline tags, and run branches is unclear;
- checkpoint/runtime/container identifiers need immutable hashes/digests;
- upstream datasets and patched runners need exact revisions/checksums;
- raw data needs a dictionary and integrity manifest;
- there is no demonstrated clean-clone command that rebuilds every table;
- failed/excluded runs need a flow table.

**Required action:** Produce tagged archival releases (e.g. Zenodo), SHA-256 manifests, licensing metadata, exact commands, immutable image digests, and an independent clean-room table reproduction.

### 12. External ranking agreement is context, not validation

Agreement with PinchBench or vendor scores does not validate this harness because tasks, scaffolds, settings, hardware, and contamination differ. Vendor numbers also cannot establish that a local gap is caused by “harness + subset variance” without a controlled ablation.

**Required action:** Treat external scores as related work. Directly test scaffold sensitivity on a preregistered matched subset if it is a claimed explanation.

## Additional source and engineering issues

1. `run-appcase.sh` uses destructive `git clean -fdxq`. Restrict it to a verified disposable worktree with path/remote/marker guards.
2. Dependency installation during scoring adds registry/network variation and energy unrelated to inference. Use a pinned offline evaluation environment and account for setup separately.
3. `run_rubric.py` uses `shell=True` on model-authored scripts; score generated apps inside isolation.
4. The 29 API checks are stateful and dependent. Early failures cause cascades, so they are not 29 independent requirements.
5. Some endpoints accept either 200 or 201 despite an allegedly exact contract. Enforce or document tolerant semantics.
6. Dashboard key-presence and many status-only assertions allow semantically wrong implementations to pass.
7. Four-decimal scores and percentage formatting imply more precision than the sample supports.
8. TensorRT telemetry is structurally missing, so several efficiency fields cannot be compared across all arms.
9. The autonomous-tool gate is valid for an agent benchmark but is selection on an outcome-adjacent ability. Report excluded configurations as screened deployment failures.
10. Archive the exact OpenCode version, system instructions, permissions, tool schema, parser, context-compaction behavior, and chat templates; these are part of the treatment.
11. Model-contiguous execution confounds model with time, cache/thermal state, software drift, and OTA changes. Randomize or block/interleave ordering.
12. Seed 0 and temperature 0.2 do not guarantee determinism. Use independent seeds for stochastic repeats and record effective server parameters.
13. Distinguish a single-sample empirical success fraction from a pass@k estimator based on multiple samples.
14. If subjective scoring is restored, preregister blinding, independent raters, and agreement statistics.

## What is strong

- Two-repository separation reduces accidental editing of generated apps.
- Raw artifacts and dated failure investigations are unusually transparent.
- The canonical denominator fixed a genuine survivorship-bias bug.
- Hardware, server, and agent metrics are separated and clock alignment is considered.
- Unified-memory and telemetry asymmetry are disclosed.
- Negative serving results are retained rather than hidden.
- L1 uses project tests and L3 executes solutions instead of using an LLM judge.
- Statistical utilities include several intervals, paired methods, multiplicity adjustment, power analysis, and passing self-tests.
- The documents often identify confounds candidly; headline claims now need to obey those caveats.

## Recommended paper framing

### Defensible research question

> What serving, measurement, and coding-agent evaluation constraints arise when three pinned open-weight model configurations run locally on one DGX Spark, and what lessons follow for reproducible benchmark design?

### Defensible contributions

1. A three-layer local evaluation harness with raw-artifact retention.
2. A pinned serving-compatibility case study on GB10/SM121.
3. Descriptive evidence that raw code generation, targeted issue repair, and long-horizon construction behave differently—without causal attribution to architecture.
4. Measurement lessons involving unified memory, telemetry, failure taxonomy, dependency installation, timeouts, and denominator changes.
5. An exploratory deployment-configuration dataset with explicitly limited generalization.

### Claims to remove or soften

- “Model X is #1” → “Configuration X had the highest observed score under this protocol.”
- “Firm separation” → report effect and interval, or say “observed difference.”
- “Capability boundary/reasoning-model split” → “configuration-specific failure pattern requiring controlled follow-up.”
- Remove all claims that contamination cancels.
- Do not call the LCB set exposure-balanced.
- Do not claim generic FP4/hardware co-optimization effects without a factorial or matched-model comparison.
- Do not call the current Layer 2 metric full-stack quality.

## Minimum plan before arXiv

1. Freeze one protocol and reconcile all documentation.
2. Commit/tag every publication input in both repositories.
3. Create a run ledger with every attempt, protocol version, status, exclusion reason, and artifacts.
4. Implement failure taxonomy and fixed retry/exclusion rules.
5. Rename/narrow Layer 2 or implement the promised rubric plus coverage matrix.
6. Isolate all generated-code evaluation.
7. Pin/offline dependency environments and separate setup energy.
8. Add robust summaries, paired effects, confidence intervals, and censoring/outlier sensitivity.
9. Make analysis consume an explicit inclusion manifest rather than every raw directory.
10. Preregister outcomes, contrasts, N, stopping, timeout, retry, exclusion, and analysis.
11. Randomize/block run order and balance N for direct comparisons.
12. Run a clean confirmatory matrix after the final freeze; retain old runs as exploratory.
13. Replicate a subset in an independent rebuilt environment.
14. Archive code/data with licenses, checksums, immutable digests, and exact upstream commits.
15. Map every paper table/figure to source rows and one regeneration command.
16. Have an independent person reproduce the paper tables.

## Final assessment

This project is publishable, but **its evidence currently supports a systems/methodology paper much more strongly than a model-ranking paper**. A submission with the current framing will attract valid criticism about confounding, changing protocols, the mislabeled Layer 2 metric, contamination logic, unequal samples, and failure/outlier handling. Correct those issues or narrow the claims decisively before posting to arXiv.

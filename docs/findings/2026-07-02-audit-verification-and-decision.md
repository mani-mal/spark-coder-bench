# external AI audit: verification and reframing decision

**Date:** 2026-07-02
**Trigger:** External audit `docs/audits/benchmark-audit-and-arxiv-recommendation.md` (external AI model), reviewing this repo at `c2b660a` and `taskflow-local-app-benchmark` at `a86791e`.
**This note:** records which audit claims were independently verified against the code/data, two corrections to the audit, and the decision on how to proceed toward publication.

---

## Decision

**Reframe the paper from a model-ranking study to a systems + methodology case study of local coding-agent evaluation on DGX Spark.** Do not submit the current data as a comparative model-ranking paper.

Rationale: the ranking claims rest on confounds that reanalysis cannot remove — model identity is fully coupled with serving runtime, precision, and tool scaffold (no model serves on both vLLM and TRT-LLM), samples are unequal (L2 N = 20/8 vs 4/4), protocol changed mid-collection, and generated code was graded without real isolation. These are correct-and-fatal reviewer objections for a ranking paper, but they are *the subject matter* of a systems/methodology paper, where the serving-feasibility findings, failure taxonomy, and measurement pitfalls are the contribution. The engineering and raw-artifact transparency are genuinely strong and survive as the core result.

The work splits into two buckets:

- **Bucket A (do now, sufficient for the narrow paper):** claim/framing fixes and robust reanalysis of *existing* data. No reruns. This is what is being executed following this note.
- **Bucket B (deferred, required only for a real ranking paper):** a new preregistered confirmatory campaign — balanced N, randomized/interleaved run order, real container isolation for generated code, pinned offline dependency env with setup energy separated, old runs retained as exploratory.

Bucket B is deliberately deferred. It is a second full measurement campaign, not a reanalysis, and is out of scope until/unless a ranking paper is the goal.

---

## Verification method

This was a source/data audit, not a rerun. Four independent passes checked the audit's ~26 concrete claims against the actual code and CSVs (Layer 2 scorer, Layer 1 runner, energy/stats/data, docs + Layer 3). `analysis/stats.py --selftest` passes (14/14). Findings below cite the evidence located during verification.

## Verdict

**The audit is accurate and well-founded. Agree with its overall recommendation.** Nearly every concrete claim held up. Highest-leverage confirmations:

| # | Audit claim | Verdict | Key evidence |
|---|-------------|---------|--------------|
| 1 | L2 reports `passed/29` equal-weight checks, not the weighted 100-pt spec | CONFIRMED | spec `benchmark-spec/evaluation-rubric.md:3`; scorer `layer2_appcase/run_rubric.py:255-259`; `contract.CANONICAL_CHECKS` = exactly 29 |
| 1 | Only frontend check is `npm run build`; password *hashing* never verified | CONFIRMED | `contract.py:84`; `run_rubric.py:74` checks only that login response omits `password`/`passwordHash` keys |
| 2 | Runtime/precision/scaffold fully confounded with model | CONFIRMED | `infra/models.json`: nemotron TRT-only (`vllm_servable:false`), qwen/gpt-oss vLLM-only. "No single model serves on both runtimes." |
| 3 | Docs describe incompatible studies | CONFIRMED | README "Two layers" vs HELP "three"; README:20 claims both FP4 use vLLM Marlin (false for Nemotron); baseline-v1 (README) vs baseline-v6 (runner); 27/28/29 check counts all appear |
| 5 | Infra/eval failures recorded as model failures | CONFIRMED | `run-task.py:86-92` ignores nonzero agent exit; `:129-133` writes `resolved=0` on missing report; 4 DNS-dropped sympy clones counted in denominator |
| 6 | Energy mean dominated by a ~13h runaway | CONFIRMED | `results/summary/benchmark-long.csv:81`: 46,732.6 s, 655,306 J, exit_code=143, resolved=0 — **76% of that arm's summed L1 energy**; `analysis/figures.py:55-61` uses plain `statistics.mean`, no censoring |
| 8 | L1 = disclosed 29-task ARM64-buildable subset, not SWE-bench Verified | CONFIRMED | selection `select-arm64-subset.py:100-124`; results 11/29, 7/29, 6/29 |
| 10 | L3 grades generated code without real isolation | CONFIRMED (disclosed) | bwrap can't create namespaces on this kernel; `coverage.md:70-82` "Filesystem and network are not isolated" |
| 11 | Key publication inputs untracked | CONFIRMED | `git status`: `docs/HELP.md` + two 2026-07-02 provenance files untracked |

## Corrections to the audit

Two places where the audit is off or understated:

1. **McNemar is NOT misapplied (finding #7 sub-bullet).** In code, `mcnemar` runs only on Layer 1, paired by common task (`analysis/stats.py:285-300`) — a legitimate design. Layer 2 never runs McNemar (it receives only mean/std/n). The audit's caution guards against something the code does not do. The valid residue: the L2 0/8-vs-4/4 comparison has *no* inferential test at all, and nonsignificance elsewhere ≠ equivalence.
2. **Finding #5 is understated.** The 30-min stuck-agent guard (`l1_guard2.sh`) referenced in `docs/findings/2026-06-27-nemotron-layer2-variance.md` does not exist in the repo. The canonical runner has no watchdog — the described-vs-actual gap is worse than the audit states.

---

## Bucket A change list (executing now)

1. **Rename the L2 metric** everywhere to "TaskFlow API acceptance-check fraction (k/29)"; stop calling it full-stack app quality; publish a requirement→check coverage matrix showing what is unscored. (findings #1, #3)
2. **Reconcile docs to one story:** layer count (3), Nemotron runtime (TRT-only), baseline tag, check count (29), quickstart, stale README status table. (finding #3)
3. **Strip causal language** ("capability boundary", "reasoning-model split", "collapses", "contamination cancels"); rename arms as configurations (e.g. `Nemotron-NVFP4 + TRT-LLM + OpenCode`). (findings #2, #8, #9)
4. **Commit/tag** the untracked publication inputs. (finding #11)
5. **Robust reanalysis of existing data:** median/IQR, with/without-runaway sensitivity, typed outcome labels separating infra failures from model failures, "29-task ARM64-buildable subset" naming, reduced decimal precision. (findings #5, #6, #7, #8)

### App-repo (`taskflow-local-app-benchmark`) follow-ups — apply on its default branch, NOT a run branch

Two doc bugs from finding #3 live in the app-repo, which was checked out on a run branch
(`nemotron-super-trt-l2-python-4`) during this pass. They were deliberately **not** edited here
to avoid landing changes on a run branch / contaminating run provenance. Apply on the default
branch:

- `README.md` says `git checkout baseline-v1` (lines 65/73/100); the runner defaults to
  `baseline-v6`. Update to `baseline-v6`.
- `opencode.json` labels Nemotron `"…NVFP4 (vLLM, local)"` under provider `vllm-local`, but
  Nemotron serves on TRT-LLM only. Either move it under a `trt-local` provider or relabel and
  point at the TRT endpoint.

## Bucket B (deferred — required only for a ranking paper)

Preregister outcomes/N/stopping/timeouts; balance N; randomize/interleave run order; real container isolation for generated-code eval; pinned offline dependency env with setup energy separated; clean confirmatory matrix with prior runs retained as exploratory.

## Handling of dated findings (historical record)

The dated `docs/findings/2026-06-*` notes still contain causal/model-intrinsic phrasing
("collapses", "capability boundary", "reasoning-model split") and older "contamination cancels"
wording. These are **deliberately left unedited** — they are the transparent, timestamped record
of what was believed when, which is a strength of this project. Their phrasing is **superseded by
this reframing**: no evergreen / publication-facing document (README, HELP.md, BENCHMARK_OVERVIEW,
methodology, the layer READMEs and coverage files, and the subset generator) makes those causal or
contamination-cancels claims any longer. Any paper draft must draw its language from the evergreen
docs, not from the dated findings' headlines.

## Claims to remove or soften before any submission

- "Model X is #1" → "Configuration X had the highest observed score under this protocol."
- "Firm separation" → report effect + interval, or "observed difference."
- "Capability boundary / reasoning-model split" → "configuration-specific failure pattern requiring controlled follow-up."
- Remove all "contamination cancels" / "exposure-balanced" claims.
- Do not call the L2 metric full-stack quality.

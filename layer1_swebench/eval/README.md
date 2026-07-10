# eval/

The official SWE-bench evaluation is invoked directly from `run-task.py` and
`select-arm64-subset.py` via `python -m swebench.harness.run_evaluation`. This
directory is a placeholder for any version-specific wrapper or patched harness
config you may need on ARM64 (e.g. a custom Dockerfile base for tasks that need
an arm64 image rebuild). Keep such overrides here and reference them from the
scripts so the main flow stays clean.

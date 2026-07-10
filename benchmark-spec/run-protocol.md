# Benchmark Run Protocol

This benchmark is designed to compare coding models fairly.

## Human benchmark runner rules

The human runner should:

1. Use the same repo state for each model.
2. Use the same prompt for each model.
3. Use the same hardware.
4. Use the same serving framework settings where possible.
5. Use the same time box.
6. Record all manual interventions.
7. Record whether the model completed the app without help.
8. Record whether install/build/test commands succeeded.

## Model rules

The model must:

1. Read the requirements before coding.
2. Work only in the assigned app folder.
3. Build the requested app.
4. Add tests.
5. Run build/test commands where possible.
6. Fix obvious failures.
7. Document assumptions.
8. Stop after producing the app and summary.

## Manual intervention categories

Use these categories when recording human help:

- None
- Clarification only
- Dependency fix
- Build fix
- Test fix
- Runtime fix
- Major architecture correction
- Run abandoned

## Suggested time box

Use the same time box for all model runs.

Recommended:

- 60 minutes per model per track for first pass
- 90 minutes per model per track if using larger models or slower inference

Do not give one model more time than another in the same comparison.

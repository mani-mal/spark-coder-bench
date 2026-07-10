# Evaluation Rubric

> **HISTORICAL / NOT IMPLEMENTED.** This weighted 100-point rubric was a design artifact and
> was **never implemented as the scorer**. The actual Layer 2 metric is the **TaskFlow API
> acceptance-check fraction (k/29)** — 29 equally-weighted automated HTTP assertions in
> `layer2_appcase/rubric_tests/contract.py`. Do not cite this 100-point breakdown as the score.
> What the real checks cover (and the many rubric items they do **not**) is in
> [`../layer2_appcase/COVERAGE.md`](../layer2_appcase/COVERAGE.md). Retained for provenance only.

Total score: 100 points.

## 1. Functional completeness: 30 points

- Authentication works: 5
- Dashboard works: 5
- Project CRUD works: 5
- Task CRUD works: 5
- Comments work: 3
- Filters/search work: 4
- Role behavior works: 3

## 2. Build and runtime correctness: 20 points

- Dependencies install successfully: 4
- Frontend starts successfully: 4
- Backend starts successfully: 4
- App can be used end-to-end locally: 4
- No major runtime crashes during basic workflow: 4

## 3. Test coverage and correctness: 15 points

- Meaningful backend tests: 5
- Meaningful frontend or integration tests: 4
- Auth/protected route tests: 3
- Validation/error tests: 3

## 4. Code quality: 15 points

- Clear structure: 4
- Maintainable code: 4
- Good naming and readability: 3
- Avoids unnecessary complexity: 2
- Consistent formatting: 2

## 5. Security and validation: 10 points

- Passwords hashed: 3
- Protected routes: 2
- Backend validation: 2
- Authorization checks: 2
- No hardcoded secrets: 1

## 6. Documentation: 5 points

- Setup instructions: 1
- Run instructions: 1
- Test instructions: 1
- API summary: 1
- Assumptions/limitations: 1

## 7. Agent efficiency: 5 points

- Minimal manual intervention: 2
- Reasonable number of turns: 1
- Good final summary: 1
- Clear handling of ambiguity: 1
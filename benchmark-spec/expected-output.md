# Expected Output

The model must produce a working local application inside the assigned folder.

## Node.js track output

All code must be created under:

`apps/node-track/`

Expected structure:

```text
apps/node-track/
  README.md
  package.json
  .env.example
  frontend/
  backend/
```

The model may choose a different internal structure, but it must document it.

## Python track output

All code must be created under:

`apps/python-track/`

Expected structure:

```text
apps/python-track/
  README.md
  .env.example
  frontend/        # TypeScript + React
  backend/         # Python + FastAPI
```

The model may choose a different internal structure, but it must document it.

## Required final response from the model

At the end of the run, the model must provide:

1. Files created
2. Main design choices
3. How to install dependencies
4. How to run the frontend
5. How to run the backend
6. How to run tests
7. Seed login credentials
8. Known limitations
9. Anything that failed or could not be completed

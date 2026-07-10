# Layer 2 Build Prompt (PINNED — identical for every model)

You are building **TaskFlow Local**, a small but realistic full-stack task-management
application, as a benchmark task. Build the COMPLETE application in one session.

## Authoritative specs (read before coding)
- Application requirements: `benchmark-spec/app-requirements.md`
- **Frozen API contract you MUST implement exactly:** `benchmark-spec/api-contract.md`
  (the harness scores your app against this contract — follow it precisely).

## Where to build
- **Node track:** build the backend in `apps/node-track/backend` and the frontend in
  `apps/node-track/frontend`.
- **Python track:** build the backend in `apps/python-track/backend` (FastAPI) and the
  frontend in `apps/python-track/frontend`.

Build ONLY in the track folder you are told to use. Do not edit `benchmark-spec/`,
`prompts/`, or `.opencode/`.

## Hard requirements for automated scoring
1. Backend listens on `http://127.0.0.1:4000`, all routes under `/api`, and exposes
   `GET /api/health` → `{"status":"ok"}` as soon as it is ready.
2. Implement every endpoint in the API contract with the specified status codes and
   JSON shapes. Bearer-token auth. Never return password fields in user objects.
3. Seed the two required users (`admin@example.com`/`Admin123!`,
   `member@example.com`/`Member123!`) with hashed passwords during setup.
4. Node backend starts with `npm run start`; Python backend with
   `uvicorn app.main:app --host 127.0.0.1 --port 4000`. Frontend builds with
   `npm run build`. Make these commands work from a clean checkout
   (`npm ci` / `pip install -r requirements.txt`).
5. Use local persistence only (SQLite preferred). No cloud services, no paid APIs.
6. TypeScript frontend with the pages listed in the requirements; validation on
   frontend and backend; useful error messages.
7. Include the tests listed in the requirements and an app `README.md`.

## Working style
- Make the smallest set of reasonable assumptions; document them in the app README.
- Do not ask the human to change requirements mid-run; if something is ambiguous,
  choose a sensible option and continue.
- When finished, ensure a clean checkout can install, start the backend, build the
  frontend, and run the tests.

# TaskFlow Local — Pinned API Contract (Layer 2)

This contract is **frozen** and identical for every model. The acceptance rubric
(`rubric_tests/`) tests against exactly these endpoints, so both models must
implement them as specified. Anything not pinned here is the model's choice and
is not scored mechanically (captured as subjective notes instead).

## Processes, ports, commands (pinned so scoring is deterministic)

| Track | Backend dir | Backend start | Backend port | Frontend dir | Frontend build |
| --- | --- | --- | --- | --- | --- |
| node | `apps/node-track/backend` | `npm ci && npm run start` | **4000** | `apps/node-track/frontend` | `npm ci && npm run build` |
| python | `apps/python-track/backend` | `pip install -r requirements.txt && uvicorn app.main:app --host 127.0.0.1 --port 4000` | **4000** | `apps/python-track/frontend` | `npm ci && npm run build` |

Backend base URL: `http://127.0.0.1:4000`. All API paths are prefixed `/api`.
Auth is **Bearer token**: `Authorization: Bearer <token>` from login.

## Endpoints

### Health
- `GET /api/health` → `200 {"status":"ok"}` (must respond once the server is ready).

### Auth
- `POST /api/auth/login` `{email,password}` →
  - `200 {"token": "<str>", "user": {"id","name","email","role"}}` on valid creds
  - `401` on invalid creds
  - `400` if email/password missing or email malformed
- `GET /api/auth/me` → `200 <user>` with valid token; `401` without/invalid token.
- `POST /api/auth/logout` → `200`.

The `user` object MUST NOT include `passwordHash` or any password field.

### Dashboard
- `GET /api/dashboard/summary` (auth) → `200` with keys:
  `totalProjects, totalTasks, tasksByStatus, highPriorityOpen, myTasks, overdue`.

### Projects
- `GET /api/projects` (auth) → `200 [<project>]`
- `GET /api/projects/:id` (auth) → `200 <project>` / `404`
- `POST /api/projects` (admin) `{name, description?}` → `201|200 <project>`; `403` for member; `400` if name missing
- `PATCH /api/projects/:id` (admin) → `200 <project>`
- `POST /api/projects/:id/archive` (admin) → `200 <project>` with `status:"archived"`

### Tasks
- `GET /api/tasks` (auth) with optional query `status, priority, assigneeId, projectId, q` → `200 [<task>]`
- `GET /api/tasks/:id` (auth) → `200 <task>` / `404`
- `POST /api/tasks` `{projectId, title, description?, status?, priority?, assigneeId?, dueDate?}` →
  `201|200 <task>`; `400` if title missing or priority/status invalid
- `PATCH /api/tasks/:id` → `200 <task>`
- `PATCH /api/tasks/:id/status` `{status}` → `200 <task>`; `400` on invalid status
- `DELETE /api/tasks/:id` → `200|204`

`status ∈ {backlog,in_progress,blocked,done}`, `priority ∈ {low,medium,high}`.

### Comments
- `GET /api/tasks/:id/comments` (auth) → `200 [<comment>]` (each with `authorId`/author and `createdAt`)
- `POST /api/tasks/:id/comments` `{body}` → `201|200 <comment>`; `400` if body empty

## Auth/RBAC rules tested
- Member CANNOT create/edit/archive projects → `403`.
- Admin CAN.
- Any protected route without a valid token → `401`.

## Seed users (must exist after setup)
- `admin@example.com` / `Admin123!` (role `admin`)
- `member@example.com` / `Member123!` (role `member`)

# Application Requirements

## Application name

TaskFlow Local

## Goal

Build a small but realistic full-stack task management application that can be used to evaluate AI coding models.

The application should allow a small software team to manage projects, tasks, comments, and status updates.

This is not a toy todo app. It should include authentication, a dashboard, CRUD workflows, filters, validation, local persistence, and tests.

## User roles

The app must support two user roles:

1. Admin
2. Member

## Seed users

Create seed data with the following users:

### Admin user

- Email: `admin@example.com`
- Password: `Admin123!`
- Role: `admin`

### Member user

- Email: `member@example.com`
- Password: `Member123!`
- Role: `member`

Passwords must not be stored in plain text.

## Core entities

### User

Fields:

- id
- name
- email
- passwordHash
- role
- createdAt
- updatedAt

### Project

Fields:

- id
- name
- description
- status: active, archived
- createdAt
- updatedAt

### Task

Fields:

- id
- projectId
- title
- description
- status: backlog, in_progress, blocked, done
- priority: low, medium, high
- assigneeId
- dueDate
- createdAt
- updatedAt

### Comment

Fields:

- id
- taskId
- authorId
- body
- createdAt
- updatedAt

## Functional requirements

### Authentication

The app must include:

1. Login page
2. Logout
3. Session or token-based auth
4. Password hashing
5. Protected API routes
6. Protected frontend pages

A user must not access the dashboard without logging in.

### Dashboard

After login, show a dashboard with:

1. Total projects
2. Total tasks
3. Tasks by status
4. High-priority open tasks
5. Tasks assigned to the logged-in user
6. Overdue tasks

### Project management

Users must be able to:

1. View all projects
2. View a single project
3. Create a project
4. Edit a project
5. Archive a project

Only admin users can create, edit, or archive projects.

### Task management

Users must be able to:

1. View all tasks
2. View tasks by project
3. View task details
4. Create a task
5. Edit a task
6. Change task status
7. Delete a task

Admin users can manage all tasks.

Member users can:
- View all tasks
- Update tasks assigned to them
- Add comments to tasks
- Change status of tasks assigned to them

### Comments

Users must be able to:

1. Add comments to a task
2. View comments on a task
3. See comment author and timestamp

### Filtering and search

The task list must support:

1. Filter by status
2. Filter by priority
3. Filter by assignee
4. Filter by project
5. Text search by title or description

### Validation

Validate inputs on both frontend and backend.

Examples:

1. Email must be valid
2. Password is required at login
3. Project name is required
4. Task title is required
5. Priority must be one of the allowed values
6. Status must be one of the allowed values
7. Due date must be a valid date if provided

### Error handling

The app must show useful error messages for:

1. Invalid login
2. Unauthorized access
3. Validation errors
4. API failures
5. Missing records

### Local persistence

Use local persistence only.

Allowed options:

1. SQLite
2. Local JSON file
3. Local embedded database

Preferred: SQLite.

Do not use cloud databases.

### Frontend requirements

Use TypeScript.

Preferred frontend stack:

- React with Vite, or Next.js
- React Router if using Vite
- Simple CSS, CSS modules, Tailwind, or plain styles

Frontend must include:

1. Login page
2. Dashboard page
3. Projects page
4. Project detail page
5. Tasks page
6. Task detail page
7. Create/edit forms
8. Navigation
9. Loading states
10. Error states

### Backend requirements

Backend must expose REST APIs.

Required API areas:

1. Auth
2. Users
3. Projects
4. Tasks
5. Comments
6. Dashboard summary

### Testing requirements

Add tests for:

1. Login success
2. Login failure
3. Protected route behavior
4. Create project
5. Create task
6. Update task status
7. Validation failure

Use whatever standard test framework fits the selected stack.

### Documentation requirements

Inside the app folder, create a `README.md` with:

1. Overview
2. Tech stack
3. Folder structure
4. Setup instructions
5. Run instructions
6. Test instructions
7. Seed users
8. API endpoint summary
9. Known limitations
10. Assumptions made

## Non-functional requirements

The app should be:

1. Easy to run locally
2. Easy to inspect
3. Reasonably secure for a local demo
4. Clear enough for humans to review
5. Small enough to complete in a coding-agent benchmark run

## Out of scope

Do not implement:

1. Real email sending
2. OAuth
3. Cloud deployment
4. Payment
5. Kubernetes
6. Docker unless it is simple and optional
7. External SaaS integrations
8. Complex enterprise RBAC
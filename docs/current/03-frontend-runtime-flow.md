# 03 Frontend Runtime Flow

## Entry point

- `frontend/src/app/main.jsx` and `frontend/src/app/App.jsx` start the React app.
- `frontend/src/pages/AuditAgent.jsx` is the main audit page.

## Main UI parts

- `frontend/src/features/audit/` contains the audit-specific UI.
- This includes the status cards, provenance graph view, domain panels, summaries, and report QA panel.

## Backend communication

- The frontend talks to the backend only through `/api/*`.
- It does not read files from `data/` directly.

## Docker setup

- In Docker, the built frontend is served by Nginx.
- `/api/*` is proxied from the frontend container to the backend container.

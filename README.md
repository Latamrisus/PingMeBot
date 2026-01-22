# PingMe 🛎️  
Task reminders service built with **FastAPI + PostgreSQL + Alembic + Celery + Redis** — with a lightweight **web UI** for quick manual testing.

> **Status:** Active development (MVP works, features are being expanded).  
> **Goal:** Build a production-like reminders backend: REST API + background jobs + DB migrations + Dockerized infrastructure.

---

## ✨ What PingMe does

PingMe helps you manage tasks with deadlines and **multiple reminders per task**.

### Current features
- ✅ Tasks CRUD (via REST API)
- ✅ Reminders as a separate entity (1 task → N reminders)
- ✅ PostgreSQL persistence (SQLAlchemy models)
- ✅ Alembic migrations
- ✅ Background worker setup via Celery + Redis
- ✅ Simple web UI (Jinja2 templates) for fast interaction

### Planned / in progress
- [ ] Reminder presets in UI (e.g. *1 day before*, *12 hours before*, *1 hour before*)
- [ ] Custom reminder time selection
- [ ] “Next reminder” display / prioritization logic
- [ ] Notification channels (Telegram / Email / Webhook)
- [ ] Auth (JWT) + users
- [ ] Tests (pytest) + CI (GitHub Actions)

---

## 🧱 Tech stack

- **Python 3.12**
- **FastAPI** — REST API
- **SQLAlchemy** — ORM
- **Alembic** — DB migrations
- **PostgreSQL** — database
- **Celery** — background jobs
- **Redis** — broker/result backend
- **Jinja2** — lightweight web UI

---
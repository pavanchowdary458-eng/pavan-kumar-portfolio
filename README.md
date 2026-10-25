# Pavan Kumar Portfolio

A responsive personal portfolio built with Python Flask, SQLite, HTML, CSS and JavaScript.

## Backend features
- **SQLite database** (auto-created in `instance/portfolio.db`) holding projects, skills, education and contact messages. Starter content is seeded once from the original page.
- **Contact form** saves every message, with validation, a honeypot field, per-IP rate limiting, and optional e-mail notification via SMTP. Works with or without JavaScript.
- **JSON API**: `GET /api/projects`, `/api/projects/<id>`, `/api/skills`, `/api/education`, `POST /api/contact`, plus `GET /healthz`.
- **Admin panel** at `/admin`: read / delete messages, add / edit / hide / delete projects. CSRF-protected, login rate-limited, and disabled unless `ADMIN_PASSWORD` is set.

## Run locally
```bash
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt

# set config (Windows PowerShell: $env:ADMIN_PASSWORD="..."; macOS/Linux: export ...)
export SECRET_KEY="a-long-random-string"
export ADMIN_PASSWORD="choose-a-password"
python app.py
```
`python app.py` starts the production server (Waitress) on port 5000 — set `PORT` to change it.
For local development with auto-reload, set `FLASK_DEBUG=1` first.

Open http://127.0.0.1:5000 — admin at http://127.0.0.1:5000/admin

See `.env.example` for all settings (database path, SMTP e-mail notifications).

## Tests
```bash
python -m unittest discover -s tests -v
```

## Deploy
```bash
gunicorn app:app        # Linux/macOS hosts (a Procfile is included)
python app.py           # any OS, uses Waitress
```
Set `SECRET_KEY`, `ADMIN_PASSWORD` and `FLASK_ENV=production` (secure cookies, requires HTTPS) in your host's environment. On hosts with an ephemeral disk (e.g. Render free tier) point `DATABASE_PATH` at a persistent volume, or the database resets on each deploy.

## Project layout
```
app.py          routes, API, admin, validation, rate limiter
database.py     schema, seed data, queries
templates/      index.html (data-driven), admin/*, error.html
static/         style.css, admin.css, script.js
tests/          unit tests
```

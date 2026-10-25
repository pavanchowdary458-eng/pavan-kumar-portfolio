"""Pavan Kumar Portfolio — Flask backend.

Features
  * SQLite-backed projects / skills / education (editable without touching HTML)
  * Contact form that stores messages (+ optional e-mail notification)
  * JSON REST API under /api
  * Password-protected admin panel under /admin
"""
import hmac
import os
import re
import secrets
import smtplib
import threading
import time
from collections import defaultdict, deque
from email.message import EmailMessage
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)

import database as db_layer
from database import get_db, utcnow

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL_RE = re.compile(r"^https?://[^\s]+$", re.I)
LIMITS = {"name": 100, "email": 254, "message": 2000}


def create_app(test_config=None):
    app = Flask(__name__)
    base = Path(app.root_path)
    secret = os.environ.get("SECRET_KEY")
    app.config.update(
        SECRET_KEY=secret or secrets.token_hex(32),  # dev fallback: sessions reset on restart
        DATABASE=os.environ.get("DATABASE_PATH", str(base / "instance" / "portfolio.db")),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", ""),  # empty => admin disabled
        CONTACT_RATE_LIMIT=(5, 600),   # 5 messages / 10 minutes / IP
        LOGIN_RATE_LIMIT=(8, 600),     # 8 login attempts / 10 minutes / IP
        MAX_CONTENT_LENGTH=64 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
        SMTP_HOST=os.environ.get("SMTP_HOST", ""),
        SMTP_PORT=int(os.environ.get("SMTP_PORT", "587")),
        SMTP_USER=os.environ.get("SMTP_USER", ""),
        SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD", ""),
        NOTIFY_EMAIL=os.environ.get("NOTIFY_EMAIL", ""),
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(db_layer.close_db)
    with app.app_context():
        db_layer.init_db()

    limiter = RateLimiter()

    # ------------------------------------------------------------------ helpers
    def client_ip():
        return request.remote_addr or "unknown"

    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return session["csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    def check_csrf():
        sent = request.form.get("csrf_token", "")
        expected = session.get("csrf", "")
        if not expected or not hmac.compare_digest(sent, expected):
            abort(400, "Invalid or missing CSRF token.")

    def admin_required(view):
        @wraps(view)
        def wrapped(*a, **kw):
            if not app.config["ADMIN_PASSWORD"]:
                abort(404)  # admin not configured -> behaves as if it doesn't exist
            if not session.get("is_admin"):
                return redirect(url_for("admin_login", next=request.path))
            return view(*a, **kw)
        return wrapped

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if request.path.startswith("/admin"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ------------------------------------------------------------ contact logic
    def validate_contact(data):
        """Return (clean_dict, errors_dict)."""
        clean = {k: (data.get(k) or "").strip() for k in ("name", "email", "message")}
        errors = {}
        for field, label in (("name", "Name"), ("email", "Email"), ("message", "Message")):
            if not clean[field]:
                errors[field] = f"{label} is required."
            elif len(clean[field]) > LIMITS[field]:
                errors[field] = f"{label} must be at most {LIMITS[field]} characters."
        if "email" not in errors and not EMAIL_RE.match(clean["email"]):
            errors["email"] = "Please enter a valid email address."
        if "message" not in errors and len(clean["message"]) < 10:
            errors["message"] = "Message should be at least 10 characters."
        return clean, errors

    def save_message(clean):
        d = get_db()
        cur = d.execute(
            "INSERT INTO messages (name, email, message, ip, created_at) VALUES (?,?,?,?,?)",
            (clean["name"], clean["email"], clean["message"], client_ip(), utcnow()))
        d.commit()
        notify_by_email(app.config.copy(), clean)
        return cur.lastrowid

    def handle_contact(data):
        """Shared by the HTML form and the JSON API. Returns (status, payload)."""
        if (data.get("website") or "").strip():  # honeypot: bots fill hidden fields
            return 200, {"ok": True, "message": "Thanks! Your message has been received."}
        limit, window = app.config["CONTACT_RATE_LIMIT"]
        if not limiter.allow(f"contact:{client_ip()}", limit, window):
            return 429, {"ok": False, "message": "Too many messages. Please try again later."}
        clean, errors = validate_contact(data)
        if errors:
            return 400, {"ok": False, "message": "Please fix the highlighted fields.", "errors": errors}
        save_message(clean)
        return 201, {"ok": True, "message": f"Thanks, {clean['name']}! Your message has been received."}

    # ------------------------------------------------------------ public routes
    @app.get("/")
    def home():
        return render_template(
            "index.html",
            projects=db_layer.list_projects(),
            skills=db_layer.list_skills(),
            education=db_layer.list_education(),
        )

    @app.post("/contact")
    def contact():
        status, payload = handle_contact(request.form)
        flash(payload["message"], "success" if payload["ok"] else "error")
        return redirect(url_for("home") + "#contact")

    @app.get("/healthz")
    def healthz():
        get_db().execute("SELECT 1")
        return {"status": "ok"}

    # ----------------------------------------------------------------- JSON API
    @app.get("/api/projects")
    def api_projects():
        return jsonify(db_layer.list_projects())

    @app.get("/api/projects/<int:pid>")
    def api_project(pid):
        row = get_db().execute("SELECT * FROM projects WHERE id=? AND visible=1", (pid,)).fetchone()
        if row is None:
            return jsonify(error="Project not found"), 404
        return jsonify(db_layer.row_to_project(row))

    @app.get("/api/skills")
    def api_skills():
        return jsonify(db_layer.list_skills())

    @app.get("/api/education")
    def api_education():
        return jsonify(db_layer.list_education())

    @app.post("/api/contact")
    def api_contact():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(ok=False, message="Send a JSON object."), 400
        status, payload = handle_contact(data)
        return jsonify(payload), status

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found"), 404
        return render_template("error.html", code=404, text="Page not found."), 404

    @app.errorhandler(400)
    def bad_request(e):
        if request.path.startswith("/api/"):
            return jsonify(error=getattr(e, "description", "Bad request")), 400
        return render_template("error.html", code=400, text=getattr(e, "description", "Bad request.")), 400

    @app.errorhandler(413)
    def too_large(e):
        if request.path.startswith("/api/"):
            return jsonify(error="Request too large"), 413
        return render_template("error.html", code=413, text="Request too large."), 413

    # -------------------------------------------------------------------- admin
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if not app.config["ADMIN_PASSWORD"]:
            abort(404)
        if request.method == "POST":
            check_csrf()
            limit, window = app.config["LOGIN_RATE_LIMIT"]
            if not limiter.allow(f"login:{client_ip()}", limit, window):
                flash("Too many attempts. Try again later.", "error")
            elif hmac.compare_digest(request.form.get("password", ""), app.config["ADMIN_PASSWORD"]):
                session.clear()
                session["is_admin"] = True
                nxt = request.args.get("next", "")
                return redirect(nxt if nxt.startswith("/admin") else url_for("admin_dashboard"))
            else:
                flash("Incorrect password.", "error")
        return render_template("admin/login.html")

    @app.post("/admin/logout")
    @admin_required
    def admin_logout():
        check_csrf()
        session.clear()
        return redirect(url_for("home"))

    @app.get("/admin")
    @admin_required
    def admin_dashboard():
        d = get_db()
        msgs = d.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 200").fetchall()
        unread = d.execute("SELECT COUNT(*) FROM messages WHERE is_read=0").fetchone()[0]
        return render_template("admin/dashboard.html", messages=msgs, unread=unread,
                               projects=db_layer.list_projects(include_hidden=True))

    @app.post("/admin/messages/<int:mid>/<action>")
    @admin_required
    def admin_message_action(mid, action):
        check_csrf()
        d = get_db()
        if action == "read":
            d.execute("UPDATE messages SET is_read=1 WHERE id=?", (mid,))
        elif action == "unread":
            d.execute("UPDATE messages SET is_read=0 WHERE id=?", (mid,))
        elif action == "delete":
            d.execute("DELETE FROM messages WHERE id=?", (mid,))
        else:
            abort(404)
        d.commit()
        return redirect(url_for("admin_dashboard") + "#messages")

    def parse_project_form(form):
        data = {
            "title": form.get("title", "").strip(),
            "tag": form.get("tag", "").strip().upper(),
            "description": form.get("description", "").strip(),
            "tech": ",".join(t.strip() for t in form.get("tech", "").split(",") if t.strip()),
            "github_url": form.get("github_url", "").strip(),
            "live_url": form.get("live_url", "").strip(),
            "visible": 1 if form.get("visible") else 0,
        }
        try:
            data["position"] = int(form.get("position") or 0)
        except ValueError:
            data["position"] = 0
        errors = []
        if not data["title"]:
            errors.append("Title is required.")
        for key in ("github_url", "live_url"):
            if data[key] and not URL_RE.match(data[key]):
                errors.append(f"{key.replace('_', ' ').title()} must start with http:// or https://")
        return data, errors

    def project_form(pid=None):
        d = get_db()
        row = None
        if pid is not None:
            row = d.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
            if row is None:
                abort(404)
        if request.method == "POST":
            check_csrf()
            data, errors = parse_project_form(request.form)
            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template("admin/project_form.html", project=data | {"id": pid}, editing=pid is not None)
            if pid is None:
                d.execute("""INSERT INTO projects (position, tag, title, description, tech, github_url, live_url, visible)
                             VALUES (:position,:tag,:title,:description,:tech,:github_url,:live_url,:visible)""", data)
                flash("Project added.", "success")
            else:
                d.execute("""UPDATE projects SET position=:position, tag=:tag, title=:title, description=:description,
                             tech=:tech, github_url=:github_url, live_url=:live_url, visible=:visible
                             WHERE id=:id""", data | {"id": pid})
                flash("Project updated.", "success")
            d.commit()
            return redirect(url_for("admin_dashboard") + "#projects")
        project = dict(row) if row else {"visible": 1, "position": 0, "tech": ""}
        return render_template("admin/project_form.html", project=project, editing=pid is not None)

    @app.route("/admin/projects/new", methods=["GET", "POST"])
    @admin_required
    def admin_project_new():
        return project_form()

    @app.route("/admin/projects/<int:pid>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_project_edit(pid):
        return project_form(pid)

    @app.post("/admin/projects/<int:pid>/delete")
    @admin_required
    def admin_project_delete(pid):
        check_csrf()
        d = get_db()
        d.execute("DELETE FROM projects WHERE id=?", (pid,))
        d.commit()
        flash("Project deleted.", "success")
        return redirect(url_for("admin_dashboard") + "#projects")

    return app


class RateLimiter:
    """Tiny in-memory sliding-window limiter (per process; use Redis if you scale out)."""

    def __init__(self):
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key, limit, window):
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True


def notify_by_email(cfg, clean):
    """Optionally e-mail the owner a copy of each message (non-blocking, failures ignored)."""
    if not (cfg.get("SMTP_HOST") and cfg.get("NOTIFY_EMAIL")):
        return

    def send():
        try:
            msg = EmailMessage()
            msg["Subject"] = f"Portfolio message from {clean['name']}"
            msg["From"] = cfg.get("SMTP_USER") or cfg["NOTIFY_EMAIL"]
            msg["To"] = cfg["NOTIFY_EMAIL"]
            msg["Reply-To"] = clean["email"]
            msg.set_content(f"From: {clean['name']} <{clean['email']}>\n\n{clean['message']}")
            with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=10) as s:
                s.starttls()
                if cfg.get("SMTP_USER"):
                    s.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
                s.send_message(msg)
        except Exception:  # never break the user's request over e-mail trouble
            pass

    threading.Thread(target=send, daemon=True).start()


app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    if os.environ.get("FLASK_DEBUG") == "1":
        # Opt-in only: auto-reload + debugger for local development.
        app.run(host="127.0.0.1", port=port, debug=True)
    else:
        # Production-grade WSGI server (works on Windows, macOS and Linux).
        try:
            from waitress import serve
        except ImportError:
            raise SystemExit("Install the production server first:  pip install -r requirements.txt")
        print(f"Serving on http://{host}:{port}  (Ctrl+C to stop)")
        serve(app, host=host, port=port, threads=4)

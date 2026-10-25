"""SQLite data layer for the portfolio (standard library only)."""
import sqlite3
from datetime import datetime, timezone

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    position    INTEGER NOT NULL DEFAULT 0,
    tag         TEXT NOT NULL DEFAULT '',
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    tech        TEXT NOT NULL DEFAULT '',      -- comma separated
    github_url  TEXT NOT NULL DEFAULT '',
    live_url    TEXT NOT NULL DEFAULT '',
    visible     INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS skills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    position    INTEGER NOT NULL DEFAULT 0,
    name        TEXT NOT NULL,
    level       INTEGER NOT NULL DEFAULT 50 CHECK (level BETWEEN 0 AND 100),
    description TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS education (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    position    INTEGER NOT NULL DEFAULT 0,
    year        TEXT NOT NULL,
    title       TEXT NOT NULL,
    institution TEXT NOT NULL DEFAULT '',
    grade       TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    message     TEXT NOT NULL,
    ip          TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    is_read     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

# Initial content, taken from the original static page.
SEED_PROJECTS = [
    ("PYTHON • HEALTHCARE", "Heart Disease Tracking System",
     "A Python-based application concept for storing and tracking heart-health related data using a database backend.",
     "Python,SQL,PostgreSQL"),
    ("AI • MULTIMODAL", "Multi-Modal Emotion Recognition",
     "A project combining visual, acoustic and textual information to recognize emotions using machine learning techniques.",
     "CNN,BERT,Librosa,PyTorch"),
    ("WEB • PYTHON", "Personal Portfolio",
     "A responsive portfolio built with HTML/CSS and powered by a lightweight Flask backend.",
     "Flask,HTML,CSS"),
]
SEED_SKILLS = [
    ("Python", 90, "Programming & automation"),
    ("SQL", 82, "Queries & databases"),
    ("HTML / CSS", 88, "Responsive websites"),
    ("Data Analysis", 78, "Insights & reporting"),
    ("Git / GitHub", 75, "Version control"),
    ("Flask", 70, "Python web apps"),
]
SEED_EDUCATION = [
    ("2026", "B.Tech — Information Technology", "NRI Institute of Technology, Visadala, Guntur", "GPA: 70.63"),
    ("2021", "Intermediate — MPC", "Subham Junior College, Guntur", "GPA: 8.5"),
    ("2020", "SSC", "St Mary's EM School, Markapuram", "GPA: 9.5"),
]


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables and seed the starter content once (never re-seeds after edits)."""
    db = get_db()
    db.executescript(SCHEMA)
    if db.execute("SELECT 1 FROM meta WHERE key='seeded'").fetchone() is None:
        db.executemany(
            "INSERT INTO projects (position, tag, title, description, tech) VALUES (?,?,?,?,?)",
            [(i, *row) for i, row in enumerate(SEED_PROJECTS, 1)])
        db.executemany(
            "INSERT INTO skills (position, name, level, description) VALUES (?,?,?,?)",
            [(i, *row) for i, row in enumerate(SEED_SKILLS, 1)])
        db.executemany(
            "INSERT INTO education (position, year, title, institution, grade) VALUES (?,?,?,?,?)",
            [(i, *row) for i, row in enumerate(SEED_EDUCATION, 1)])
        db.execute("INSERT INTO meta (key, value) VALUES ('seeded', '1')")
    db.commit()


def row_to_project(row) -> dict:
    d = dict(row)
    d["tech"] = [t.strip() for t in d["tech"].split(",") if t.strip()]
    return d


def list_projects(include_hidden=False):
    sql = "SELECT * FROM projects"
    if not include_hidden:
        sql += " WHERE visible = 1"
    sql += " ORDER BY position, id"
    return [row_to_project(r) for r in get_db().execute(sql)]


def list_skills():
    return [dict(r) for r in get_db().execute("SELECT * FROM skills ORDER BY position, id")]


def list_education():
    return [dict(r) for r in get_db().execute("SELECT * FROM education ORDER BY position, id")]

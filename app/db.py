import os
import sqlite3
from flask import g, current_app

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    department TEXT NOT NULL,
    joining_date TEXT NOT NULL,
    annual_leave_allowance INTEGER NOT NULL DEFAULT 24,
    remaining_leave INTEGER NOT NULL DEFAULT 24,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS leaves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    days INTEGER NOT NULL,
    leave_type TEXT NOT NULL DEFAULT 'ANNUAL', -- ANNUAL, SICK, UNPAID, OTHER
    status TEXT NOT NULL DEFAULT 'PENDING',    -- PENDING, APPROVED, REJECTED, CANCELLED
    reason TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_leaves_emp ON leaves(employee_id);
CREATE INDEX IF NOT EXISTS idx_leaves_status ON leaves(status);

CREATE TABLE IF NOT EXISTS leave_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    leave_id INTEGER,
    delta_days INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    action TEXT NOT NULL, -- APPLY, APPROVE, REJECT, CANCEL, ADJUST
    note TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    FOREIGN KEY (leave_id) REFERENCES leaves(id) ON DELETE SET NULL
);
"""

def get_db_path(app=None):
    app = app or current_app
    # DATABASE formatted like sqlite:///instance/app.db
    url = app.config.get("DATABASE", "sqlite:///instance/app.db")
    if url.startswith("sqlite:///"):
        rel = url.replace("sqlite:///", "")
        if rel.startswith("instance/"):
            inst = os.path.join(app.instance_path, os.path.basename(rel))
            os.makedirs(os.path.dirname(inst), exist_ok=True)
            return inst
        else:
            return rel
    return "instance/app.db"

def get_db():
    if 'db' not in g:
        path = get_db_path()
        g.db = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db(app):
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA_SQL)
        db.commit()
    app.teardown_appcontext(close_db)

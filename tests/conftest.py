import os
import sqlite3
import sys

import pytest

# Make the app package importable — tests live one level below the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app_module(monkeypatch, tmp_path):
    """app.py bound to a throwaway SQLite so tests never touch data/portfolio.db."""
    import app as mod

    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE holdings (
            ticker TEXT NOT NULL, company TEXT, shares REAL NOT NULL, sector TEXT,
            broker TEXT, cedear_ratio REAL, is_cedear INTEGER DEFAULT 0,
            is_crypto INTEGER DEFAULT 0, updated_at TEXT,
            PRIMARY KEY (ticker, broker)
        );
        CREATE TABLE prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL,
            price REAL NOT NULL, currency TEXT DEFAULT 'USD',
            recorded_at TEXT DEFAULT (datetime('now')), is_cedear INTEGER DEFAULT 0
        );
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(mod, "DB_PATH", db)
    mod.ensure_schema()
    return mod


@pytest.fixture
def client(app_module):
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()

"""
database/user_db_manager.py
Per-user database isolation — each user gets their own SQLite file.
This is the CORE FIX for the multi-user problem.
"""

import os
import sqlite3
import threading
from typing import Dict
from functools import lru_cache

# Thread-safe connection cache: user_id -> connection
_connections: Dict[str, sqlite3.Connection] = {}
_lock = threading.Lock()

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "users")


def get_user_data_dir(user_id: str) -> str:
    """Return (and create) the per-user data directory."""
    safe_id = _sanitize_user_id(user_id)
    path = os.path.join(DATA_DIR, safe_id)
    os.makedirs(path, exist_ok=True)
    return path


def _sanitize_user_id(user_id: str) -> str:
    """Strip characters that are unsafe for file paths."""
    import re
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", str(user_id))[:64]


def get_user_db_path(user_id: str, db_name: str) -> str:
    """Return the full path for a per-user SQLite database."""
    return os.path.join(get_user_data_dir(user_id), db_name)


def get_user_connection(user_id: str, db_name: str) -> sqlite3.Connection:
    """
    Return a cached SQLite connection for (user_id, db_name).
    Thread-safe. Creates the file if it doesn't exist.
    """
    key = f"{_sanitize_user_id(user_id)}:{db_name}"
    with _lock:
        if key not in _connections:
            path = get_user_db_path(user_id, db_name)
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            _connections[key] = conn
        return _connections[key]


def close_user_connection(user_id: str, db_name: str):
    key = f"{_sanitize_user_id(user_id)}:{db_name}"
    with _lock:
        conn = _connections.pop(key, None)
        if conn:
            conn.close()


def list_all_users() -> list:
    """Return a list of all user IDs that have data directories."""
    if not os.path.exists(DATA_DIR):
        return []
    return [d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]

"""
database/grocery_db.py  — Per-user pantry database.
Every user_id gets its own SQLite file under data/users/<user_id>/grocery_inventory.db
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict

from database.user_db_manager import get_user_connection, get_user_db_path


class GroceryDatabase:
    """
    Per-user SQLite pantry store.
    Pass user_id to isolate every user's data completely.
    Legacy callers that omit user_id fall back to the old shared path.
    """

    def __init__(self, user_id: str = "default", db_path: str = None):
        self.user_id = user_id
        if db_path:
            # Legacy / test path – keep working
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
        else:
            self.conn = get_user_connection(user_id, "grocery_inventory.db")
        self._initialize()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def _initialize(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS grocery_inventory (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name     TEXT    NOT NULL UNIQUE,
                quantity      REAL    NOT NULL DEFAULT 1,
                unit          TEXT    NOT NULL DEFAULT 'pieces',
                category      TEXT,
                is_perishable INTEGER NOT NULL DEFAULT 0,
                purchase_date TEXT    DEFAULT (datetime('now')),
                expiry_date   TEXT,
                last_updated  TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS pantry_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                action     TEXT NOT NULL,
                item_name  TEXT,
                quantity   REAL,
                unit       TEXT,
                note       TEXT,
                ts         TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS meal_plans (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_date   DATE    NOT NULL,
                meal_type   TEXT    NOT NULL,
                recipe_name TEXT    NOT NULL,
                calories    INTEGER DEFAULT 0,
                protein_g   REAL    DEFAULT 0,
                carbs_g     REAL    DEFAULT 0,
                fat_g       REAL    DEFAULT 0,
                notes       TEXT,
                created_at  TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS conversation_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_query      TEXT NOT NULL,
                recipe_name     TEXT,
                ingredients_used TEXT,
                timestamp       TEXT DEFAULT (datetime('now'))
            );
        """)
        self.conn.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _rows_to_dicts(self, rows) -> List[Dict]:
        return [dict(row) for row in rows]

    def _log(self, action, item_name=None, quantity=None, unit=None, note=None):
        try:
            self.conn.execute(
                "INSERT INTO pantry_log (action,item_name,quantity,unit,note) VALUES(?,?,?,?,?)",
                (action, item_name, quantity, unit, note)
            )
            self.conn.commit()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # ADD / UPDATE
    # ------------------------------------------------------------------
    def add_grocery(self, item_name, quantity, unit, category=None,
                    is_perishable=False, days_until_expiry=None, expiry_date=None) -> bool:
        name = item_name.lower().strip()
        resolved_expiry = None
        if expiry_date:
            resolved_expiry = expiry_date
        elif days_until_expiry and days_until_expiry > 0:
            resolved_expiry = (datetime.now() + timedelta(days=int(days_until_expiry))).isoformat(timespec="seconds")
        try:
            self.conn.execute("""
                INSERT INTO grocery_inventory
                    (item_name,quantity,unit,category,is_perishable,expiry_date)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(item_name) DO UPDATE SET
                    quantity     = quantity + excluded.quantity,
                    unit         = excluded.unit,
                    category     = COALESCE(excluded.category, category),
                    is_perishable= excluded.is_perishable,
                    expiry_date  = COALESCE(excluded.expiry_date, expiry_date),
                    last_updated = datetime('now')
            """, (name, quantity, unit, category, 1 if is_perishable else 0, resolved_expiry))
            self.conn.commit()
            self._log("add", name, quantity, unit)
            return True
        except Exception as e:
            print(f"[GroceryDB:{self.user_id}] add_grocery error: {e}")
            return False

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------
    def get_all_groceries(self) -> List[Dict]:
        cur = self.conn.execute(
            "SELECT * FROM grocery_inventory WHERE quantity > 0 ORDER BY item_name"
        )
        return self._rows_to_dicts(cur.fetchall())

    def get_grocery_by_name(self, item_name) -> Optional[Dict]:
        cur = self.conn.execute(
            "SELECT * FROM grocery_inventory WHERE item_name = ?",
            (item_name.lower().strip(),)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def search_grocery(self, query) -> List[Dict]:
        cur = self.conn.execute(
            "SELECT * FROM grocery_inventory WHERE item_name LIKE ? AND quantity > 0",
            (f"%{query.lower().strip()}%",)
        )
        return self._rows_to_dicts(cur.fetchall())

    def get_expiring_soon(self, days=3) -> List[Dict]:
        cutoff = (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds")
        cur = self.conn.execute("""
            SELECT * FROM grocery_inventory
            WHERE expiry_date IS NOT NULL AND expiry_date <= ? AND quantity > 0
            ORDER BY expiry_date
        """, (cutoff,))
        return self._rows_to_dicts(cur.fetchall())

    def get_by_category(self, category) -> List[Dict]:
        cur = self.conn.execute(
            "SELECT * FROM grocery_inventory WHERE category = ? AND quantity > 0",
            (category.lower(),)
        )
        return self._rows_to_dicts(cur.fetchall())

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------
    def update_quantity(self, item_name, new_quantity) -> bool:
        name = item_name.lower().strip()
        cur = self.conn.execute(
            "UPDATE grocery_inventory SET quantity=?,last_updated=datetime('now') WHERE item_name=?",
            (max(new_quantity, 0), name)
        )
        self.conn.commit()
        if cur.rowcount:
            self._log("update", name, new_quantity)
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------
    def delete_grocery(self, item_name) -> bool:
        name = item_name.lower().strip()
        cur = self.conn.execute("DELETE FROM grocery_inventory WHERE item_name=?", (name,))
        self.conn.commit()
        if cur.rowcount:
            self._log("remove", name)
            return True
        cur = self.conn.execute("DELETE FROM grocery_inventory WHERE item_name LIKE ?", (f"%{name}%",))
        self.conn.commit()
        if cur.rowcount:
            self._log("remove", name, note="fuzzy")
        return cur.rowcount > 0

    def clear_inventory(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM grocery_inventory")
        count = cur.fetchone()[0]
        self.conn.execute("DELETE FROM grocery_inventory")
        self.conn.commit()
        self._log("clear", note=f"cleared {count} items")
        return count

    # ------------------------------------------------------------------
    # MEAL PLANS
    # ------------------------------------------------------------------
    def save_meal_plan(self, plan_date, meal_type, recipe_name,
                       calories=0, protein_g=0, carbs_g=0, fat_g=0, notes="") -> bool:
        try:
            self.conn.execute("""
                INSERT INTO meal_plans
                    (plan_date,meal_type,recipe_name,calories,protein_g,carbs_g,fat_g,notes)
                VALUES (?,?,?,?,?,?,?,?)
            """, (plan_date, meal_type, recipe_name, calories, protein_g, carbs_g, fat_g, notes))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"[GroceryDB:{self.user_id}] save_meal_plan error: {e}")
            return False

    def get_meal_plans(self, days=7) -> List[Dict]:
        cur = self.conn.execute("""
            SELECT * FROM meal_plans
            WHERE plan_date >= date('now', ?)
            ORDER BY plan_date DESC, meal_type
        """, (f"-{days} days",))
        return self._rows_to_dicts(cur.fetchall())

    def get_meal_plans_today(self) -> List[Dict]:
        cur = self.conn.execute(
            "SELECT * FROM meal_plans WHERE plan_date = date('now') ORDER BY meal_type"
        )
        return self._rows_to_dicts(cur.fetchall())

    # ------------------------------------------------------------------
    # STATS
    # ------------------------------------------------------------------
    def get_stats(self) -> Dict:
        total   = self.conn.execute("SELECT COUNT(*) FROM grocery_inventory WHERE quantity>0").fetchone()[0]
        expired = len(self.get_expiring_soon(days=0))
        soon    = len(self.get_expiring_soon(days=3))
        cats    = self.conn.execute(
            "SELECT category,COUNT(*) c FROM grocery_inventory WHERE quantity>0 GROUP BY category"
        ).fetchall()
        return {
            "total": total, "expired": expired, "expiring_soon": soon,
            "by_category": {r[0]: r[1] for r in cats}
        }

    def save_conversation(self, user_query, recipe_name="", ingredients_used=""):
        try:
            self.conn.execute(
                "INSERT INTO conversation_history(user_query,recipe_name,ingredients_used) VALUES(?,?,?)",
                (user_query, recipe_name, ingredients_used)
            )
            self.conn.commit()
        except Exception:
            pass

    def close(self):
        pass  # Connection is managed by user_db_manager; do NOT close here

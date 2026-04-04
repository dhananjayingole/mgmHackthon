"""
database/feedback_db.py  — Per-user feedback & ratings database.
"""

import sqlite3
import json
import uuid
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from database.user_db_manager import get_user_connection


class FeedbackDatabase:
    """Per-user feedback / ratings store."""

    def __init__(self, user_id: str = "default", db_path: str = None):
        self.user_id = user_id
        if db_path:
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        else:
            self.conn = get_user_connection(user_id, "feedback.db")
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS recipe_ratings (
                id TEXT PRIMARY KEY,
                recipe_name TEXT NOT NULL,
                recipe_content TEXT,
                rating INTEGER CHECK(rating >= 1 AND rating <= 5),
                feedback_text TEXT,
                cuisine TEXT,
                diet_type TEXT,
                calories REAL,
                ingredients_used TEXT,
                session_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS ingredient_preferences (
                ingredient TEXT PRIMARY KEY,
                like_count INTEGER DEFAULT 0,
                dislike_count INTEGER DEFAULT 0,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS cuisine_stats (
                cuisine TEXT PRIMARY KEY,
                total_rated INTEGER DEFAULT 0,
                avg_rating REAL DEFAULT 0,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.conn.commit()

    def save_rating(self, recipe_name, rating, recipe_content="", feedback_text="",
                    cuisine="", diet_type="", calories=0, ingredients=None, session_id="") -> str:
        recipe_id = str(uuid.uuid4())[:8]
        self.conn.execute("""
            INSERT INTO recipe_ratings
            (id,recipe_name,recipe_content,rating,feedback_text,cuisine,
             diet_type,calories,ingredients_used,session_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (recipe_id, recipe_name, recipe_content[:2000], rating, feedback_text,
              cuisine, diet_type, calories, json.dumps(ingredients or []), session_id))

        self.conn.execute("""
            INSERT INTO cuisine_stats (cuisine, total_rated, avg_rating)
            VALUES (?, 1, ?)
            ON CONFLICT(cuisine) DO UPDATE SET
                avg_rating = (avg_rating * total_rated + excluded.avg_rating) / (total_rated + 1),
                total_rated = total_rated + 1
        """, (cuisine, float(rating)))

        for ing in (ingredients or []):
            if ing:
                self.conn.execute("""
                    INSERT INTO ingredient_preferences (ingredient, like_count, dislike_count)
                    VALUES (?, ?, ?)
                    ON CONFLICT(ingredient) DO UPDATE SET
                        like_count    = like_count    + ?,
                        dislike_count = dislike_count + ?,
                        last_used = CURRENT_TIMESTAMP
                """, (ing.lower(),
                      1 if rating >= 4 else 0, 1 if rating <= 2 else 0,
                      1 if rating >= 4 else 0, 1 if rating <= 2 else 0))

        self.conn.commit()
        return recipe_id

    def get_top_cuisines(self, min_ratings=1) -> List[Dict]:
        rows = self.conn.execute("""
            SELECT cuisine, avg_rating, total_rated FROM cuisine_stats
            WHERE total_rated >= ? AND cuisine != ''
            ORDER BY avg_rating DESC LIMIT 5
        """, (min_ratings,)).fetchall()
        return [{"cuisine": r[0], "avg_rating": round(r[1], 1), "count": r[2]} for r in rows]

    def get_liked_ingredients(self, min_likes=2) -> List[str]:
        rows = self.conn.execute("""
            SELECT ingredient FROM ingredient_preferences
            WHERE like_count >= ? AND like_count > dislike_count
            ORDER BY like_count DESC LIMIT 15
        """, (min_likes,)).fetchall()
        return [r[0] for r in rows]

    def get_preference_summary(self) -> Dict[str, Any]:
        total = self.conn.execute("SELECT COUNT(*) FROM recipe_ratings").fetchone()[0]
        avg   = self.conn.execute("SELECT AVG(rating) FROM recipe_ratings").fetchone()[0]
        return {
            "total_rated": total,
            "avg_rating": round(avg or 0, 1),
            "top_cuisines": self.get_top_cuisines(),
            "liked_ingredients": self.get_liked_ingredients(),
        }

    def close(self):
        pass

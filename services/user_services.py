"""
services/user_services.py — Per-user service factory (unchanged architecture).
Call get_user_services(user_id) to get a dict of fully-isolated service objects.
"""

import threading
from typing import Dict, Any

from database.grocery_db import GroceryDatabase
from database.feedback_db import FeedbackDatabase
from agents.user_profile import UserProfileDB

_cache: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def get_user_services(user_id: str) -> Dict[str, Any]:
    """
    Return (and cache) per-user service objects.
    Thread-safe. Cheap to call repeatedly — cached after first call.
    """
    uid = str(user_id).strip() or "default"
    with _lock:
        if uid not in _cache:
            _cache[uid] = _build_user_services(uid)
        return _cache[uid]


def _build_user_services(user_id: str) -> Dict[str, Any]:
    """Construct fresh per-user service objects."""
    db          = GroceryDatabase(user_id=user_id)
    profile_db  = UserProfileDB(user_id=user_id)
    feedback_db = FeedbackDatabase(user_id=user_id)

    try:
        from services.price_service import PriceService
        price_service = PriceService()          # prices are global / shared
    except ImportError:
        class _PS:
            def get_cheapest_protein(self, *a):
                return {"name": "lentil", "price_per_kg": 80, "protein_per_100g": 24, "currency": "₹"}
            def get_price(self, name, qty=1):
                return 50.0
            def get_all_prices(self):
                return {}
        price_service = _PS()

    return {
        "db":            db,
        "profile_db":    profile_db,
        "feedback_db":   feedback_db,
        "price_service": price_service,
        "user_id":       user_id,
    }


def evict_user_cache(user_id: str):
    """
    Remove a user's cached services.
    Call this after a profile reset so the next request gets fresh objects.
    """
    with _lock:
        _cache.pop(str(user_id), None)


def list_cached_users() -> list:
    with _lock:
        return list(_cache.keys())
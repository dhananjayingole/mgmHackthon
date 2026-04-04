"""services/__init__.py — Service layer for external integrations."""

# Simple placeholder imports
try:
    from services.price_service import PriceService
except ImportError:
    class PriceService:
        def get_price(self, item, qty=1): return 50
        def get_cheapest_protein(self, diet=None): return {"name": "lentil", "price_per_kg": 80, "currency": "₹"}

try:
    from services.notification_service import NotificationService
except ImportError:
    class NotificationService:
        def __init__(self, db): pass
        def get_notifications(self): return []
        def check_expiring_items(self, days=1): return []

__all__ = [
    "PriceService",
    "NotificationService",
]
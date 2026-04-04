"""services/notification_service.py — Expiry notifications."""

from datetime import datetime
from typing import List, Dict


class NotificationService:
    """Handles expiry notifications and reminders."""
    
    def __init__(self, db):
        self.db = db
    
    def check_expiring_items(self, days: int = 1) -> List[Dict]:
        """Get items expiring within days."""
        try:
            return self.db.get_expiring_soon(days)
        except Exception:
            return []
    
    def get_notifications(self) -> List[str]:
        """Get formatted notifications for UI."""
        notifications = []
        
        try:
            today_items = self.check_expiring_items(1)
            if today_items:
                items = [f"🔴 {i['item_name'].title()}" for i in today_items[:3]]
                notifications.append(f"⚠️ Expiring today: {', '.join(items)}")
            
            soon_items = self.check_expiring_items(3)
            if soon_items and len(soon_items) > len(today_items):
                items = [f"🟡 {i['item_name'].title()}" for i in soon_items[:3]]
                notifications.append(f"⚠️ Expiring in 3 days: {', '.join(items)}")
        except Exception:
            pass
        
        return notifications
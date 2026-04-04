"""services/price_service.py — Database-backed dynamic pricing."""

import json
import sqlite3
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from functools import lru_cache


class PriceService:
    """Dynamic price service with SQLite backend."""
    
    def __init__(self, db_path: str = "data/nutribot.db"):
        self.db_path = db_path
        self._init_table()
    
    def _get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def _init_table(self):
        """Ensure price table exists."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ingredient_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ingredient_name TEXT UNIQUE NOT NULL,
                category TEXT,
                unit TEXT DEFAULT 'kg',
                price_inr REAL NOT NULL,
                currency TEXT DEFAULT '₹',
                source TEXT DEFAULT 'local_market',
                season TEXT DEFAULT 'all',
                is_organic INTEGER DEFAULT 0,
                region_code TEXT DEFAULT 'IN',
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                price_history TEXT DEFAULT '[]'
            )
        """)
        conn.commit()
        conn.close()
    
    def get_price(self, ingredient_name: str, quantity_kg: float = 1.0) -> float:
        """Get current price for an ingredient in INR."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Try exact match first
        cursor.execute(
            "SELECT price_inr, unit FROM ingredient_prices WHERE ingredient_name = ?",
            (ingredient_name.lower(),)
        )
        row = cursor.fetchone()
        
        if not row:
            # Try partial match
            cursor.execute(
                "SELECT price_inr, unit FROM ingredient_prices WHERE ? LIKE '%' || ingredient_name || '%' OR ingredient_name LIKE '%' || ? || '%' LIMIT 1",
                (ingredient_name.lower(), ingredient_name.lower())
            )
            row = cursor.fetchone()
        
        conn.close()
        
        if row:
            price_per_unit, unit = row
            if unit == "kg":
                return round(price_per_unit * quantity_kg, 2)
            elif unit == "piece":
                return round(price_per_unit * quantity_kg, 2)
            elif unit == "100g":
                return round(price_per_unit * quantity_kg * 10, 2)
            else:
                return round(price_per_unit * quantity_kg, 2)
        
        # Fallback default
        return self._get_fallback_price(ingredient_name)
    
    def get_price_for_ingredient(self, ingredient: Dict) -> float:
        """Calculate price for a recipe ingredient."""
        name = ingredient.get("name", "")
        quantity = float(ingredient.get("quantity", 100))
        unit = ingredient.get("unit", "grams")
        
        # Convert to kg
        if unit in ["g", "gram", "grams"]:
            kg = quantity / 1000
        elif unit in ["kg", "kilogram", "kilograms"]:
            kg = quantity
        elif unit in ["piece", "pieces"]:
            kg = 0.2  # Approx 200g per piece
        elif unit in ["tbsp", "tablespoon"]:
            kg = 0.015
        elif unit in ["tsp", "teaspoon"]:
            kg = 0.005
        elif unit in ["cup", "cups"]:
            kg = 0.2
        else:
            kg = 0.1
        
        return self.get_price(name, kg)
    
    def get_bulk_prices(self, ingredients: List[str]) -> Dict[str, float]:
        """Get prices for multiple ingredients at once."""
        result = {}
        for ingredient in ingredients:
            result[ingredient] = self.get_price(ingredient)
        return result
    
    def update_price(self, ingredient_name: str, new_price: float, source: str = "admin"):
        """Update price in database with history tracking."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get current price and history
        cursor.execute(
            "SELECT price_inr, price_history FROM ingredient_prices WHERE ingredient_name = ?",
            (ingredient_name.lower(),)
        )
        row = cursor.fetchone()
        
        if row:
            current_price, history_json = row
            history = json.loads(history_json) if history_json else []
            
            # Add current price to history
            history.append({
                "date": datetime.now().isoformat(),
                "price": current_price,
                "source": source
            })
            
            # Keep only last 20 entries
            history = history[-20:]
            
            # Update with new price
            cursor.execute("""
                UPDATE ingredient_prices 
                SET price_inr = ?, price_history = ?, last_updated = ?, source = ?
                WHERE ingredient_name = ?
            """, (new_price, json.dumps(history), datetime.now().isoformat(), source, ingredient_name.lower()))
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO ingredient_prices (ingredient_name, price_inr, source, price_history)
                VALUES (?, ?, ?, ?)
            """, (ingredient_name.lower(), new_price, source, json.dumps([])))
        
        conn.commit()
        conn.close()
        
        # Invalidate cache
        self._get_price.cache_clear()
    
    @lru_cache(maxsize=128)
    def _get_price(self, name: str) -> float:
        """Cached price lookup."""
        return self.get_price(name)
    
    def _get_fallback_price(self, ingredient_name: str) -> float:
        """Fallback prices when database not available."""
        fallbacks = {
            "onion": 40, "tomato": 30, "potato": 25, "spinach": 30,
            "paneer": 280, "dal": 100, "lentil": 100, "rice": 60,
            "milk": 60, "curd": 50, "ghee": 600, "oil": 110,
            "garlic": 200, "ginger": 150, "cumin": 30, "turmeric": 20,
            "chicken": 200, "egg": 7, "tofu": 150,
        }
        return fallbacks.get(ingredient_name.lower(), 50)
    
    def get_cheapest_protein(self, diet_type: str = "vegetarian") -> Dict:
        """Get cheapest protein source from database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Protein sources with their protein content per 100g
        protein_data = {
            "soy chunks": {"protein_per_100g": 52, "price_per_kg": 120},
            "masoor dal": {"protein_per_100g": 25, "price_per_kg": 80},
            "moong dal": {"protein_per_100g": 24, "price_per_kg": 90},
            "chana dal": {"protein_per_100g": 22, "price_per_kg": 85},
            "chickpea": {"protein_per_100g": 19, "price_per_kg": 80},
            "tofu": {"protein_per_100g": 8, "price_per_kg": 150},
            "paneer": {"protein_per_100g": 18, "price_per_kg": 280},
            "eggs": {"protein_per_100g": 13, "price_per_kg": 70, "unit": "piece"},
            "chicken": {"protein_per_100g": 25, "price_per_kg": 200},
        }
        
        # Filter by diet
        if diet_type == "vegetarian":
            exclude = ["chicken", "eggs"]
            for ex in exclude:
                protein_data.pop(ex, None)
        elif diet_type == "vegan":
            exclude = ["chicken", "eggs", "paneer", "curd"]
            for ex in exclude:
                protein_data.pop(ex, None)
        
        # Get current prices from DB
        for name in list(protein_data.keys()):
            db_price = self.get_price(name, 1)
            if db_price:
                protein_data[name]["price_per_kg"] = db_price
        
        # Calculate cost per 10g protein
        for name, data in protein_data.items():
            price_per_kg = data["price_per_kg"]
            protein_per_100g = data["protein_per_100g"]
            # Cost to get 10g protein
            data["cost_per_10g_protein"] = round((price_per_kg / 1000) * 100 * (10 / protein_per_100g), 2)
        
        # Find cheapest
        cheapest = min(protein_data.items(), key=lambda x: x[1]["cost_per_10g_protein"])
        conn.close()
        
        return {
            "name": cheapest[0].title(),
            "price_per_kg": cheapest[1]["price_per_kg"],
            "protein_per_100g": cheapest[1]["protein_per_100g"],
            "cost_per_10g_protein": cheapest[1]["cost_per_10g_protein"],
            "currency": "₹"
        }
    
    def get_category_prices(self, category: str) -> List[Dict]:
        """Get all prices for a category."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ingredient_name, price_inr, unit FROM ingredient_prices WHERE category = ? ORDER BY ingredient_name",
            (category,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"name": r[0], "price_inr": r[1], "unit": r[2]} for r in rows]
    
    def get_all_prices(self) -> Dict[str, float]:
        """Get all current prices."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ingredient_name, price_inr FROM ingredient_prices")
        rows = cursor.fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}


# Singleton
_price_service = None

def get_price_service() -> PriceService:
    global _price_service
    if _price_service is None:
        _price_service = PriceService()
    return _price_service

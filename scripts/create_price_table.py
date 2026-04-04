# scripts/create_price_table.py
"""Run this script once to create the price table and seed initial data."""

import sqlite3
import os
import json
from datetime import datetime

def create_price_table():
    db_path = "data/nutribot.db"
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create ingredient_prices table
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
    
    # Seed initial prices (₹ per kg or per piece)
    initial_prices = [
        # Vegetables (per kg)
        ("onion", "vegetables", "kg", 40, "local_market"),
        ("tomato", "vegetables", "kg", 30, "local_market"),
        ("potato", "vegetables", "kg", 25, "local_market"),
        ("spinach", "vegetables", "bunch", 30, "local_market"),
        ("capsicum", "vegetables", "kg", 60, "local_market"),
        ("carrot", "vegetables", "kg", 35, "local_market"),
        ("cauliflower", "vegetables", "piece", 30, "local_market"),
        ("cabbage", "vegetables", "kg", 30, "local_market"),
        ("peas", "vegetables", "kg", 50, "local_market"),
        ("beans", "vegetables", "kg", 45, "local_market"),
        ("brinjal", "vegetables", "kg", 35, "local_market"),
        ("garlic", "vegetables", "kg", 200, "local_market"),
        ("ginger", "vegetables", "kg", 150, "local_market"),
        ("green_chili", "vegetables", "kg", 50, "local_market"),
        
        # Dairy
        ("milk", "dairy", "liter", 60, "local_market"),
        ("paneer", "dairy", "kg", 280, "local_market"),
        ("curd", "dairy", "kg", 50, "local_market"),
        ("butter", "dairy", "kg", 450, "local_market"),
        ("ghee", "dairy", "kg", 600, "local_market"),
        ("cheese", "dairy", "kg", 400, "local_market"),
        ("yogurt", "dairy", "kg", 50, "local_market"),
        
        # Proteins
        ("lentil", "protein", "kg", 100, "local_market"),
        ("dal", "protein", "kg", 100, "local_market"),
        ("moong dal", "protein", "kg", 90, "local_market"),
        ("masoor dal", "protein", "kg", 80, "local_market"),
        ("chana dal", "protein", "kg", 85, "local_market"),
        ("chickpea", "protein", "kg", 80, "local_market"),
        ("rajma", "protein", "kg", 100, "local_market"),
        ("tofu", "protein", "kg", 150, "local_market"),
        ("soy chunks", "protein", "kg", 120, "local_market"),
        ("eggs", "protein", "piece", 7, "local_market"),
        ("chicken", "protein", "kg", 200, "local_market"),
        
        # Grains
        ("rice", "grain", "kg", 60, "local_market"),
        ("basmati rice", "grain", "kg", 100, "local_market"),
        ("wheat", "grain", "kg", 35, "local_market"),
        ("atta", "grain", "kg", 40, "local_market"),
        ("oats", "grain", "kg", 80, "local_market"),
        ("pasta", "grain", "kg", 80, "local_market"),
        ("bread", "grain", "loaf", 35, "local_market"),
        
        # Spices (per 100g)
        ("cumin", "spice", "100g", 30, "local_market"),
        ("coriander", "spice", "100g", 25, "local_market"),
        ("turmeric", "spice", "100g", 20, "local_market"),
        ("red chili", "spice", "100g", 40, "local_market"),
        ("garam masala", "spice", "100g", 50, "local_market"),
        ("salt", "spice", "kg", 20, "local_market"),
        ("sugar", "spice", "kg", 45, "local_market"),
        
        # Oils
        ("oil", "oil", "liter", 110, "local_market"),
        ("olive oil", "oil", "liter", 800, "local_market"),
        ("coconut oil", "oil", "liter", 200, "local_market"),
        ("mustard oil", "oil", "liter", 120, "local_market"),
    ]
    
    for name, cat, unit, price, source in initial_prices:
        cursor.execute("""
            INSERT OR REPLACE INTO ingredient_prices 
            (ingredient_name, category, unit, price_inr, source, last_updated, price_history)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, cat, unit, price, source, datetime.now().isoformat(), json.dumps([])))
    
    conn.commit()
    conn.close()
    print(f"✅ Created ingredient_prices table with {len(initial_prices)} items")

if __name__ == "__main__":
    create_price_table()
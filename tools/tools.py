"""tools/tools.py — Grocery parsing, recipe KB, export."""

import re
import json
import os
from typing import List, Dict, Any


def parse_grocery_input(user_message: str, client, db) -> str:
    """Parse natural language grocery additions."""
    prompt = f"""Parse grocery items from this message.
Message: "{user_message}"

Extract ALL food items with quantities. Return ONLY a JSON array:
[
  {{"name": "item_name", "quantity": 1.0, "unit": "kg/g/pieces",
    "category": "vegetables/fruits/dairy/proteins/grains",
    "is_perishable": true/false, "days_until_expiry": null_or_number}}
]

Perishables: vegetables (5-7 days), fruits (5-7 days), dairy (7-10 days), proteins (2-3 days)
Non-perishables: grains, spices, oils

Return ONLY the JSON array."""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()
        items = json.loads(raw)

        added = []
        for item in items:
            name = item.get("name", "").lower().strip()
            if not name:
                continue
            qty = float(str(item.get("quantity", 1)))
            success = db.add_grocery(
                item_name=name,
                quantity=qty,
                unit=item.get("unit", "pieces"),
                category=item.get("category", "other"),
                is_perishable=item.get("is_perishable", False),
                days_until_expiry=item.get("days_until_expiry")
            )
            if success:
                added.append(f"{qty} {item.get('unit', 'pcs')} {name.title()}")

        if added:
            return f"✅ **Added to pantry:**\n" + "\n".join(f"  • {a}" for a in added)
        else:
            return "❌ Could not parse any grocery items."

    except Exception:
        return _fallback_grocery_parse(user_message, db)


def _fallback_grocery_parse(message: str, db) -> str:
    """Simple regex-based grocery parser as fallback."""
    patterns = [
        r'(\d+(?:\.\d+)?)\s*(kg|g|grams?|ml|liter?|l|pieces?|cups?)\s+(\w+)',
        r'(\d+(?:\.\d+)?)\s+(\w+)',
    ]
    added = []
    for pattern in patterns:
        matches = re.findall(pattern, message.lower())
        for match in matches:
            if len(match) == 3:
                qty, unit, name = match
            else:
                qty, name = match
                unit = "pieces"
            try:
                db.add_grocery(name.strip(), float(qty), unit, "other", False)
                added.append(f"{qty} {unit} {name}")
            except Exception:
                pass

    if added:
        return "✅ **Added:** " + ", ".join(added)
    return "❌ Could not parse groceries. Try: 'I bought 2 kg onions, 500g paneer'"


def load_recipe_dataset():
    """Load recipe dataset for RAG."""
    return [
        {"name": "Palak Paneer", "cuisine": "Indian", "diet": "vegetarian",
         "calories": 280, "protein": 14, "time": 30,
         "ingredients": "paneer, spinach, onion, tomato, cream, spices",
         "description": "Creamy Indian cottage cheese in spiced spinach gravy"},
        {"name": "Dal Tadka", "cuisine": "Indian", "diet": "vegan",
         "calories": 220, "protein": 12, "time": 25,
         "ingredients": "yellow dal, onion, tomato, cumin, garlic, ghee",
         "description": "Tempered yellow lentils with aromatic spices"},
        {"name": "Aloo Gobi", "cuisine": "Indian", "diet": "vegan",
         "calories": 200, "protein": 5, "time": 25,
         "ingredients": "potato, cauliflower, onion, tomato, turmeric, cumin",
         "description": "Dry spiced potato and cauliflower dish"},
        {"name": "Chole Bhature", "cuisine": "Indian", "diet": "vegetarian",
         "calories": 520, "protein": 18, "time": 50,
         "ingredients": "chickpeas, flour, yogurt, onion, tomato, spices",
         "description": "Spiced chickpea curry with fried puffed bread"},
        {"name": "Vegetable Biryani", "cuisine": "Indian", "diet": "vegetarian",
         "calories": 380, "protein": 9, "time": 45,
         "ingredients": "rice, mixed vegetables, yogurt, spices, saffron",
         "description": "Fragrant rice layered with spiced vegetables"},
        {"name": "Masala Dosa", "cuisine": "Indian", "diet": "vegetarian",
         "calories": 320, "protein": 7, "time": 30,
         "ingredients": "rice, urad dal, potato, onion, spices",
         "description": "Crispy fermented crepe with spiced potato filling"},
    ]


def build_recipe_knowledge_base(dataset: list):
    """Build ChromaDB vector store from recipe dataset."""
    try:
        import chromadb
        from chromadb.utils import embedding_functions

        client = chromadb.Client()
        ef = embedding_functions.DefaultEmbeddingFunction()

        try:
            collection = client.get_or_create_collection(name="recipes", embedding_function=ef)
        except:
            collection = client.create_collection(name="recipes", embedding_function=ef)

        if collection.count() == 0 and dataset:
            docs, metas, ids = [], [], []
            for i, r in enumerate(dataset):
                doc = f"{r['name']} {r['cuisine']} {r['diet']} {r['ingredients']} {r['description']}"
                docs.append(doc)
                metas.append({
                    "recipe_name": r["name"],
                    "cuisine_type": r["cuisine"],
                    "calories": str(r["calories"]),
                    "diet_labels": r["diet"],
                })
                ids.append(f"recipe_{i}")
            collection.add(documents=docs, metadatas=metas, ids=ids)

        return collection
    except Exception:
        return SimpleRecipeKB(dataset)


class SimpleRecipeKB:
    """Fallback KB when ChromaDB is not available."""
    def __init__(self, dataset: list):
        self.dataset = dataset

    def query(self, query_texts: list, n_results: int = 5):
        query = query_texts[0].lower() if query_texts else ""
        scores = []
        for r in self.dataset:
            score = sum(1 for word in query.split()
                       if word in r.get("name", "").lower() or
                          word in r.get("ingredients", "").lower())
            scores.append((score, r))
        scores.sort(key=lambda x: -x[0])
        top = scores[:n_results]

        if not top:
            return {"documents": [[]], "metadatas": [[]]}

        return {
            "documents": [[r.get("description", "") for _, r in top]],
            "metadatas": [[{
                "recipe_name": r.get("name", ""),
                "cuisine_type": r.get("cuisine", ""),
                "calories": str(r.get("calories", 0)),
                "diet_labels": r.get("diet", ""),
            } for _, r in top]],
        }
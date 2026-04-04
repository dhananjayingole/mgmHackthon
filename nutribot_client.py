# backend/nutribot_client.py
"""
NutriBot Android Client Library
Use this in your Android app via Chaquopy or similar Python integration
"""

import json
import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum


class InputMode(Enum):
    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"


class MealType(Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


@dataclass
class UserProfile:
    """User profile data class"""
    user_id: str
    diet_type: Optional[str] = None
    fitness_goal: Optional[str] = None
    cuisine_preferences: Optional[List[str]] = None
    allergies: Optional[List[str]] = None
    health_conditions: Optional[List[str]] = None
    calorie_goal: Optional[int] = 500
    budget_preference: Optional[Dict] = None
    skill_level: Optional[str] = None


@dataclass
class GroceryItem:
    """Grocery item data class"""
    item_name: str
    quantity: float = 1.0
    unit: str = "pieces"
    category: Optional[str] = None
    is_perishable: bool = False
    expiry_date: Optional[str] = None


@dataclass
class RecipeResponse:
    """Recipe response data class"""
    recipe: str
    ingredients: List[Dict]
    nutrition: Dict
    budget: Dict
    eco_score: Dict


class NutriBotClient:
    """Client for NutriBot API"""
    
    def __init__(self, base_url: str = "http://localhost:8000", api_key: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session_id = None
        self.user_id = None
    
    def _headers(self) -> Dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    def _post(self, endpoint: str, data: Dict = None, files: Dict = None) -> Dict:
        """Make POST request"""
        url = f"{self.base_url}{endpoint}"
        
        if files:
            response = requests.post(url, files=files, headers=self._headers())
        else:
            response = requests.post(url, json=data, headers=self._headers())
        
        response.raise_for_status()
        return response.json()
    
    def _get(self, endpoint: str, params: Dict = None) -> Dict:
        """Make GET request"""
        url = f"{self.base_url}{endpoint}"
        response = requests.get(url, params=params, headers=self._headers())
        response.raise_for_status()
        return response.json()
    
    def _delete(self, endpoint: str) -> Dict:
        """Make DELETE request"""
        url = f"{self.base_url}{endpoint}"
        response = requests.delete(url, headers=self._headers())
        response.raise_for_status()
        return response.json()
    
    # ========================================================================
    # Health & System
    # ========================================================================
    
    def health_check(self) -> bool:
        """Check if API is healthy"""
        try:
            response = self._get("/health")
            return response.get("status") == "healthy"
        except Exception:
            return False
    
    # ========================================================================
    # Chat
    # ========================================================================
    
    def chat(self, query: str, user_id: str = None, **kwargs) -> Dict:
        """Send a message to NutriBot"""
        self.user_id = user_id or self.user_id
        
        data = {
            "query": query,
            "session_id": self.session_id,
            "user_id": self.user_id,
            **kwargs
        }
        
        response = self._post("/chat", data)
        self.session_id = response.get("data", {}).get("session_id")
        
        return response.get("data", {})
    
    # ========================================================================
    # Profile Management
    # ========================================================================
    
    def get_profile(self, user_id: str = None) -> Dict:
        """Get user profile"""
        uid = user_id or self.user_id
        if not uid:
            raise ValueError("User ID required")
        
        response = self._get(f"/profile/{uid}")
        return response.get("data", {})
    
    def update_profile(self, profile: UserProfile) -> Dict:
        """Update user profile"""
        self.user_id = profile.user_id
        
        data = {
            k: v for k, v in profile.__dict__.items()
            if v is not None and k != "user_id"
        }
        
        response = self._put(f"/profile/{profile.user_id}", data)
        return response.get("data", {})
    
    def reset_profile(self, user_id: str = None) -> bool:
        """Reset user profile"""
        uid = user_id or self.user_id
        if not uid:
            raise ValueError("User ID required")
        
        response = self._delete(f"/profile/{uid}")
        return response.get("success", False)
    
    # ========================================================================
    # Pantry Management
    # ========================================================================
    
    def get_pantry(self) -> List[Dict]:
        """Get all pantry items"""
        response = self._get("/pantry")
        return response.get("data", {}).get("items", [])
    
    def add_grocery(self, item: GroceryItem) -> bool:
        """Add item to pantry"""
        data = {
            "item_name": item.item_name,
            "quantity": item.quantity,
            "unit": item.unit,
            "category": item.category,
            "is_perishable": item.is_perishable,
        }
        response = self._post("/pantry", data)
        return response.get("success", False)
    
    def remove_grocery(self, item_name: str) -> bool:
        """Remove item from pantry"""
        data = {"item_name": item_name}
        response = self._delete("/pantry", data)
        return response.get("success", False)
    
    def clear_pantry(self) -> bool:
        """Clear all pantry items"""
        response = self._delete("/pantry/all")
        return response.get("success", False)
    
    def get_expiring_items(self, days: int = 3) -> List[Dict]:
        """Get items expiring within days"""
        response = self._get(f"/pantry/expiring", {"days": days})
        return response.get("data", {}).get("items", [])
    
    # ========================================================================
    # Recipes
    # ========================================================================
    
    def generate_recipe(self, query: str, user_id: str = None, **kwargs) -> RecipeResponse:
        """Generate a recipe"""
        uid = user_id or self.user_id
        data = {
            "query": query,
            "user_id": uid,
            **kwargs
        }
        
        response = self._post("/recipe/generate", data)
        data = response.get("data", {})
        
        return RecipeResponse(
            recipe=data.get("recipe", ""),
            ingredients=data.get("ingredients", []),
            nutrition=data.get("nutrition", {}),
            budget=data.get("budget", {}),
            eco_score=data.get("eco_score", {})
        )
    
    def rate_recipe(self, recipe_name: str, rating: int, feedback: str = None, cuisine: str = None) -> bool:
        """Rate a recipe"""
        data = {
            "recipe_name": recipe_name,
            "rating": rating,
            "feedback": feedback,
            "cuisine": cuisine
        }
        response = self._post("/recipe/rate", data)
        return response.get("success", False)
    
    # ========================================================================
    # Meal Plans
    # ========================================================================
    
    def get_meal_plans(self, days: int = 7) -> List[Dict]:
        """Get meal plans for last N days"""
        response = self._get(f"/mealplan", {"days": days})
        return response.get("data", {}).get("meals", [])
    
    def get_today_meal_plans(self) -> List[Dict]:
        """Get today's meal plans"""
        response = self._get("/mealplan/today")
        return response.get("data", {}).get("meals", [])
    
    def save_meal_plan(self, plan_date: str, meal_type: str, recipe_name: str,
                       calories: int = 0, protein_g: float = 0, carbs_g: float = 0,
                       fat_g: float = 0, notes: str = None) -> bool:
        """Save a meal plan"""
        data = {
            "plan_date": plan_date,
            "meal_type": meal_type,
            "recipe_name": recipe_name,
            "calories": calories,
            "protein_g": protein_g,
            "carbs_g": carbs_g,
            "fat_g": fat_g,
            "notes": notes
        }
        response = self._post("/mealplan", data)
        return response.get("success", False)
    
    def generate_weekly_plan(self, query: str = "Plan my week", **kwargs) -> Dict:
        """Generate weekly meal plan"""
        data = {
            "query": query,
            "user_id": self.user_id,
            **kwargs
        }
        response = self._post("/mealplan/week", data)
        return response.get("data", {})
    
    # ========================================================================
    # Nutrition
    # ========================================================================
    
    def get_today_nutrition(self) -> Dict:
        """Get today's nutrition summary"""
        response = self._get("/nutrition/today")
        return response.get("data", {})
    
    def get_weekly_nutrition(self) -> Dict:
        """Get weekly nutrition summary"""
        response = self._get("/nutrition/week")
        return response.get("data", {})
    
    # ========================================================================
    # Budget & Pricing
    # ========================================================================
    
    def get_cheapest_protein(self, diet_type: str = "vegetarian") -> Dict:
        """Get cheapest protein source"""
        response = self._get(f"/budget/cheapest-protein", {"diet_type": diet_type})
        return response.get("data", {})
    
    def get_ingredient_price(self, ingredient: str, quantity_kg: float = 1.0) -> float:
        """Get price for an ingredient"""
        response = self._get(f"/budget/price/{ingredient}", {"quantity_kg": quantity_kg})
        return response.get("data", {}).get("price_inr", 0)
    
    def get_all_prices(self) -> Dict:
        """Get all ingredient prices"""
        response = self._get("/budget/prices")
        return response.get("data", {}).get("prices", {})
    
    # ========================================================================
    # Vision
    # ========================================================================
    
    def analyze_image(self, image_bytes: bytes, context: str = "fridge") -> Dict:
        """Analyze food image"""
        files = {
            "file": ("image.jpg", image_bytes, "image/jpeg")
        }
        data = {"context": context}
        
        # Note: Need to handle multipart form data separately
        url = f"{self.base_url}/vision/analyze"
        response = requests.post(url, files=files, data=data, headers=self._headers())
        response.raise_for_status()
        
        return response.json().get("data", {})
    
    # ========================================================================
    # Voice
    # ========================================================================
    
    def transcribe_audio(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        """Transcribe audio to text"""
        files = {
            "file": (filename, audio_bytes, "audio/webm")
        }
        
        url = f"{self.base_url}/voice/transcribe"
        response = requests.post(url, files=files, headers=self._headers())
        response.raise_for_status()
        
        return response.json().get("data", {}).get("text", "")
    
    # ========================================================================
    # Shopping List
    # ========================================================================
    
    def generate_shopping_list(self, query: str = "Generate shopping list", **kwargs) -> str:
        """Generate shopping list"""
        data = {
            "query": query,
            "user_id": self.user_id,
            **kwargs
        }
        response = self._post("/shopping/generate", data)
        return response.get("data", {}).get("shopping_list", "")
    
    # ========================================================================
    # Cooking Mode
    # ========================================================================
    
    def parse_recipe_steps(self, recipe_text: str) -> List[Dict]:
        """Parse recipe into steps"""
        data = {"recipe_text": recipe_text}
        response = self._post("/cooking/parse", data)
        return response.get("data", {}).get("steps", [])
    
    # ========================================================================
    # Eco Score
    # ========================================================================
    
    def calculate_eco_score(self, ingredients: List[Dict]) -> Dict:
        """Calculate eco score for ingredients"""
        data = {"ingredients": ingredients}
        response = self._post("/eco/calculate", data)
        return response.get("data", {})
    
    # ========================================================================
    # Health Advice
    # ========================================================================
    
    def get_health_advice(self, query: str, **kwargs) -> str:
        """Get health advice"""
        data = {
            "query": query,
            "user_id": self.user_id,
            **kwargs
        }
        response = self._post("/health/advice", data)
        return response.get("data", {}).get("advice", "")
    
    # ========================================================================
    # Feedback
    # ========================================================================
    
    def get_feedback_stats(self) -> Dict:
        """Get feedback statistics"""
        response = self._get("/feedback/stats")
        return response.get("data", {})
    
    def get_top_cuisines(self, min_ratings: int = 1) -> List[Dict]:
        """Get top-rated cuisines"""
        response = self._get("/feedback/top-cuisines", {"min_ratings": min_ratings})
        return response.get("data", {}).get("cuisines", [])
    
    def get_liked_ingredients(self, min_likes: int = 2) -> List[str]:
        """Get most liked ingredients"""
        response = self._get("/feedback/liked-ingredients", {"min_likes": min_likes})
        return response.get("data", {}).get("ingredients", [])
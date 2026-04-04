"""database/models.py — SQLAlchemy models for NutriBot."""

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, 
    Boolean, Text, ForeignKey, Date
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
from datetime import datetime, timedelta  # Add timedelta
import os

Base = declarative_base()


class GroceryItem(Base):
    """Grocery inventory model."""
    __tablename__ = "grocery_inventory"
    
    id = Column(Integer, primary_key=True)
    item_name = Column(String(100), nullable=False, unique=True)
    quantity = Column(Float, nullable=False, default=1.0)
    unit = Column(String(20), nullable=False, default="pieces")
    category = Column(String(50))
    purchase_date = Column(DateTime, default=datetime.now)
    expiry_date = Column(DateTime, nullable=True)
    is_perishable = Column(Boolean, default=False)
    last_updated = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def to_dict(self):
        return {
            "id": self.id,
            "item_name": self.item_name,
            "quantity": self.quantity,
            "unit": self.unit,
            "category": self.category,
            "purchase_date": self.purchase_date.isoformat() if self.purchase_date else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "is_perishable": self.is_perishable,
        }


class Conversation(Base):
    """Conversation history model."""
    __tablename__ = "conversation_history"
    
    id = Column(Integer, primary_key=True)
    user_query = Column(Text, nullable=False)
    recipe_name = Column(String(200))
    ingredients_used = Column(Text)
    timestamp = Column(DateTime, default=datetime.now)
    session_id = Column(String(50), nullable=True)
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_query": self.user_query,
            "recipe_name": self.recipe_name,
            "ingredients_used": self.ingredients_used,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class MealPlan(Base):
    """Meal plan calendar model."""
    __tablename__ = "meal_plans"
    
    id = Column(Integer, primary_key=True)
    plan_date = Column(Date, nullable=False)
    meal_type = Column(String(20), nullable=False)  # breakfast, lunch, dinner, snack
    recipe_name = Column(String(200), nullable=False)
    calories = Column(Integer, default=0)
    protein_g = Column(Float, default=0)
    carbs_g = Column(Float, default=0)
    fat_g = Column(Float, default=0)
    fiber_g = Column(Float, default=0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    
    def to_dict(self):
        return {
            "id": self.id,
            "plan_date": self.plan_date.isoformat() if self.plan_date else None,
            "meal_type": self.meal_type,
            "recipe_name": self.recipe_name,
            "calories": self.calories,
            "protein_g": self.protein_g,
            "carbs_g": self.carbs_g,
            "fat_g": self.fat_g,
            "fiber_g": self.fiber_g,
            "notes": self.notes,
        }


class RecipeRating(Base):
    """Recipe ratings and feedback model."""
    __tablename__ = "recipe_ratings"
    
    id = Column(String(20), primary_key=True)
    recipe_name = Column(String(200), nullable=False)
    recipe_content = Column(Text)
    rating = Column(Integer, nullable=False)
    feedback_text = Column(Text)
    cuisine = Column(String(50))
    diet_type = Column(String(50))
    calories = Column(Float, default=0)
    ingredients_used = Column(Text)  # JSON string
    session_id = Column(String(50))
    created_at = Column(DateTime, default=datetime.now)
    
    def to_dict(self):
        return {
            "id": self.id,
            "recipe_name": self.recipe_name,
            "rating": self.rating,
            "feedback": self.feedback_text,
            "cuisine": self.cuisine,
            "diet_type": self.diet_type,
            "calories": self.calories,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class IngredientPreference(Base):
    """Learned ingredient preferences model."""
    __tablename__ = "ingredient_preferences"
    
    ingredient = Column(String(100), primary_key=True)
    like_count = Column(Integer, default=0)
    dislike_count = Column(Integer, default=0)
    last_used = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def to_dict(self):
        return {
            "ingredient": self.ingredient,
            "like_count": self.like_count,
            "dislike_count": self.dislike_count,
            "score": self.like_count - self.dislike_count,
        }


class CuisineStat(Base):
    """Cuisine statistics model."""
    __tablename__ = "cuisine_stats"
    
    cuisine = Column(String(50), primary_key=True)
    total_rated = Column(Integer, default=0)
    avg_rating = Column(Float, default=0)
    last_used = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def to_dict(self):
        return {
            "cuisine": self.cuisine,
            "total_rated": self.total_rated,
            "avg_rating": round(self.avg_rating, 1),
        }


class UserProfile(Base):
    """User profile preferences model."""
    __tablename__ = "user_profile"
    
    key = Column(String(50), primary_key=True)
    value = Column(Text, nullable=False)
    confidence = Column(Float, default=1.0)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def to_dict(self):
        import json
        try:
            return json.loads(self.value)
        except:
            return self.value
        
# database/models.py - ADD THIS NEW TABLE

class IngredientPrice(Base):
    """Dynamic ingredient pricing table."""
    __tablename__ = "ingredient_prices"
    
    id = Column(Integer, primary_key=True)
    ingredient_name = Column(String(100), nullable=False, unique=True, index=True)
    category = Column(String(50))  # vegetable, fruit, dairy, protein, grain, spice, oil
    unit = Column(String(20), default="kg")  # kg, g, piece, bunch, liter
    price_inr = Column(Float, nullable=False)  # price per unit
    currency = Column(String(5), default="₹")
    source = Column(String(50), default="local_market")  # local_market, online, wholesale
    season = Column(String(20), default="all")  # summer, winter, monsoon, all
    is_organic = Column(Boolean, default=False)
    region_code = Column(String(10), default="IN")
    last_updated = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Price history tracking
    price_history = Column(Text, default="[]")  # JSON array of historical prices
    
    def to_dict(self):
        import json
        return {
            "id": self.id,
            "ingredient_name": self.ingredient_name,
            "category": self.category,
            "unit": self.unit,
            "price_inr": self.price_inr,
            "currency": self.currency,
            "source": self.source,
            "season": self.season,
            "region_code": self.region_code,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "price_history": json.loads(self.price_history) if self.price_history else []
        }


class PurchaseHistory(Base):
    """Track user purchase history for price trends."""
    __tablename__ = "purchase_history"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=True)
    ingredient_name = Column(String(100), nullable=False)
    quantity = Column(Float, default=1.0)
    unit = Column(String(20), default="kg")
    price_paid = Column(Float, nullable=False)
    store_name = Column(String(100))
    purchased_date = Column(Date, default=datetime.now().date)
    created_at = Column(DateTime, default=datetime.now)
    
    def to_dict(self):
        return {
            "id": self.id,
            "ingredient_name": self.ingredient_name,
            "quantity": self.quantity,
            "unit": self.unit,
            "price_paid": self.price_paid,
            "store_name": self.store_name,
            "purchased_date": self.purchased_date.isoformat() if self.purchased_date else None,
        }


# Database manager class
class DatabaseManager:
    """Unified database manager with SQLAlchemy."""
    
    def __init__(self, db_path: str = "data/nutribot.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    def get_session(self):
        """Get a new database session."""
        return self.Session()
    
    def add_grocery(self, item_name: str, quantity: float, unit: str,
                    category: str = None, is_perishable: bool = False,
                    days_until_expiry: int = None) -> bool:
        """Add or update grocery item."""
        session = self.get_session()
        try:
            # Check if exists
            existing = session.query(GroceryItem).filter_by(item_name=item_name.lower()).first()
            
            if existing:
                existing.quantity += quantity
                existing.last_updated = datetime.now()
            else:
                expiry_date = None
                if days_until_expiry:
                    expiry_date = datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=days_until_expiry)
                
                item = GroceryItem(
                    item_name=item_name.lower(),
                    quantity=quantity,
                    unit=unit,
                    category=category,
                    is_perishable=is_perishable,
                    expiry_date=expiry_date
                )
                session.add(item)
            
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            return False
        finally:
            session.close()
    
    def get_all_groceries(self):
        """Get all grocery items."""
        session = self.get_session()
        try:
            items = session.query(GroceryItem).filter(GroceryItem.quantity > 0).all()
            return [item.to_dict() for item in items]
        finally:
            session.close()
    
    def delete_grocery(self, item_name: str) -> bool:
        """Delete grocery item."""
        session = self.get_session()
        try:
            result = session.query(GroceryItem).filter_by(item_name=item_name.lower()).delete()
            session.commit()
            return result > 0
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()
    
    def save_meal_plan(self, plan_date, meal_type, recipe_name, calories=0,
                       protein_g=0, carbs_g=0, fat_g=0, fiber_g=0, notes=""):
        """Save a meal plan entry."""
        session = self.get_session()
        try:
            meal = MealPlan(
                plan_date=plan_date,
                meal_type=meal_type,
                recipe_name=recipe_name,
                calories=calories,
                protein_g=protein_g,
                carbs_g=carbs_g,
                fat_g=fat_g,
                fiber_g=fiber_g,
                notes=notes
            )
            session.add(meal)
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()
    
    def get_meal_plans_today(self):
        """Get today's meal plans."""
        session = self.get_session()
        try:
            today = datetime.now().date()
            meals = session.query(MealPlan).filter_by(plan_date=today).all()
            return [meal.to_dict() for meal in meals]
        finally:
            session.close()

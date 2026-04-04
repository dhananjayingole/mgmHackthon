"""Base agent class with standardized interface."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional
from agents.state import AgentState


class BaseAgent(ABC):
    """Base class for all agents with logging and error handling."""
    
    def __init__(self, name: str):
        self.name = name
    
    def log(self, state: AgentState, message: str, status: str = "info"):
        """Add log entry to state."""
        if "agent_logs" not in state or state["agent_logs"] is None:
            state["agent_logs"] = []
        state["agent_logs"].append({
            "agent": self.name,
            "message": message,
            "status": status,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        })
    
    @abstractmethod
    def run(self, state: AgentState, **kwargs) -> AgentState:
        """Execute agent logic."""
        pass
    
    def safe_run(self, state: AgentState, **kwargs) -> AgentState:
        """Run with error handling."""
        try:
            return self.run(state, **kwargs)
        except Exception as e:
            self.log(state, f"Error: {e}", "error")
            if "errors" not in state or state["errors"] is None:
                state["errors"] = []
            state["errors"].append(f"{self.name}: {e}")
            return state
"""Step-by-step cooking assistant with timers and voice."""

import re
import time
from typing import List, Dict, Any, Generator
from agents.base import BaseAgent
from agents.state import AgentState


class CookingAgent(BaseAgent):
    """Guides user through recipe with step-by-step instructions."""
    
    def __init__(self):
        super().__init__("🍳 Cooking Mode")
    
    def parse_recipe_steps(self, recipe_text: str) -> List[Dict]:
        """Extract structured steps with timers from recipe."""
        steps = []
        
        # Find instructions section
        inst_match = re.search(r'###\s*👨‍🍳 Instructions\s*\n(.*?)(?=\n###|\n##|$)', 
                               recipe_text, re.DOTALL | re.IGNORECASE)
        if not inst_match:
            # Fallback: look for numbered steps anywhere
            inst_match = re.search(r'(\d+\..*?)(?=\n\d+\.|\n##|$)', 
                                   recipe_text, re.DOTALL)
        
        if inst_match:
            inst_text = inst_match.group(1)
            step_pattern = r'(\d+)\.\s*(.*?)(?=\n\d+\.|\n\n|$)'
            matches = re.findall(step_pattern, inst_text, re.DOTALL)
            
            for i, (num, instruction) in enumerate(matches):
                instruction = instruction.strip()
                timer = self._extract_timer(instruction)
                steps.append({
                    "step": int(num),
                    "instruction": instruction,
                    "timer_seconds": timer,
                    "timer_display": f"{timer//60}:{timer%60:02d}" if timer else None,
                    "completed": False
                })
        
        # If no steps found, split by sentences
        if not steps:
            sentences = re.split(r'(?<=[.!?])\s+', recipe_text)
            for i, sent in enumerate(sentences[:12]):
                if len(sent) > 15:
                    steps.append({
                        "step": i+1,
                        "instruction": sent,
                        "timer_seconds": self._extract_timer(sent),
                        "timer_display": None,
                        "completed": False
                    })
        
        return steps
    
    def _extract_timer(self, text: str) -> int:
        """Extract timer in seconds from instruction."""
        patterns = [
            r'(\d+)\s*(?:min|minute|minutes?)\s*(?:or\s+(\d+)\s*min)?',
            r'(\d+)\s*(?:hr|hour|hours?)\s*(\d+)?\s*(?:min|minute)?',
            r'(\d+)\s*(?:second|seconds?)\s*',
            r'for\s+(\d+)\s*(?:min|minute)',
            r'simmer\s+(\d+)\s*(?:min|minute)',
            r'cook\s+(\d+)\s*(?:min|minute)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                if match.group(2) and match.group(1):
                    avg = (int(match.group(1)) + int(match.group(2))) // 2
                    return avg * 60
                if match.group(1):
                    return int(match.group(1)) * 60
        return 0
    
    def run(self, state: AgentState, **kwargs) -> AgentState:
        """Parse recipe into steps."""
        recipe = state.get("generated_recipe", "")
        if not recipe:
            return state
        
        steps = self.parse_recipe_steps(recipe)
        state["cooking_steps"] = steps
        state["current_step_index"] = 0
        state["cooking_mode_active"] = False
        
        self.log(state, f"Parsed {len(steps)} steps", "success")
        return state
    
    def start_cooking(self, state: AgentState) -> AgentState:
        """Start cooking mode."""
        state["cooking_mode_active"] = True
        state["current_step_index"] = 0
        
        steps = state.get("cooking_steps", [])
        if steps:
            current = steps[0]
            state["assistant_message"] = self._format_step(current, 0, len(steps))
        
        return state
    
    def next_step(self, state: AgentState) -> AgentState:
        """Move to next step."""
        steps = state.get("cooking_steps", [])
        current_idx = state.get("current_step_index", 0)
        
        if current_idx < len(steps):
            steps[current_idx]["completed"] = True
        
        if current_idx + 1 < len(steps):
            state["current_step_index"] = current_idx + 1
            next_step = steps[current_idx + 1]
            state["assistant_message"] = self._format_step(next_step, current_idx + 1, len(steps))
        else:
            state["assistant_message"] = "🎉 **Recipe complete!** Enjoy your meal!"
            state["cooking_mode_active"] = False
        
        return state
    
    def _format_step(self, step: Dict, step_num: int, total: int) -> str:
        """Format a single step for display."""
        lines = [
            f"## 🍳 Step {step_num} of {total}",
            "",
            step["instruction"],
            ""
        ]
        
        if step.get("timer_seconds"):
            minutes = step["timer_seconds"] // 60
            seconds = step["timer_seconds"] % 60
            lines.append(f"⏱️ **Timer:** {minutes}:{seconds:02d}")
            lines.append("")
        
        lines.append("---")
        lines.append("**Say:** *'next step'* or click **Next** when ready")
        
        return "\n".join(lines)
    
    def get_timer_js(self, seconds: int) -> str:
        """Generate JavaScript timer component."""
        return f"""
        <div id="cooking-timer" style="text-align:center;padding:1rem;background:#f8fafc;border-radius:12px">
            <div style="font-size:3rem;font-family:monospace;font-weight:bold" id="timer-display">
                {seconds//60}:{seconds%60:02d}
            </div>
            <button onclick="startTimer({seconds})" style="background:#e8541e;color:white;border:none;padding:8px 24px;border-radius:8px;cursor:pointer">
                Start Timer
            </button>
        </div>
        <script>
        let timerInterval;
        function startTimer(seconds) {{
            let remaining = seconds;
            const display = document.getElementById('timer-display');
            if (timerInterval) clearInterval(timerInterval);
            timerInterval = setInterval(() => {{
                remaining--;
                const mins = Math.floor(remaining / 60);
                const secs = remaining % 60;
                display.textContent = `${{mins}}:${{secs.toString().padStart(2,'0')}}`;
                if (remaining <= 0) {{
                    clearInterval(timerInterval);
                    display.textContent = 'Done!';
                    new Audio('data:audio/wav;base64,U3RlYWQ=').play();
                }}
            }}, 1000);
        }}
        </script>
        """

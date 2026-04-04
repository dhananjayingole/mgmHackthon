"""frontend/cooking_mode.py — Step-by-step cooking mode UI component."""

import streamlit as st
import time
from typing import List, Dict, Optional


class CookingModeUI:
    """Cooking mode UI with step-by-step instructions and timers."""
    
    def __init__(self):
        self.steps = []
        self.current_step = 0
        self.timer_running = False
        self.timer_seconds = 0
    
    def set_recipe(self, recipe_text: str):
        """Parse recipe and set up steps."""
        from agents.cooking_agent import CookingAgent
        cooking_agent = CookingAgent()
        self.steps = cooking_agent.parse_recipe_steps(recipe_text)
        self.current_step = 0
    
    def render(self, recipe_text: str = None, steps: List[Dict] = None,
               current_step: int = 0) -> Optional[str]:
        """Render cooking mode UI."""
        if recipe_text and not self.steps:
            self.set_recipe(recipe_text)
        
        if steps:
            self.steps = steps
            self.current_step = current_step
        
        if not self.steps:
            st.warning("No steps found in this recipe.")
            return None
        
        # Progress bar
        progress = (self.current_step) / max(len(self.steps), 1)
        st.progress(progress, text=f"Step {self.current_step + 1} of {len(self.steps)}")
        
        # Current step display
        current = self.steps[self.current_step]
        
        # Step instruction card
        st.markdown(f"""
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 16px; 
                    padding: 1.5rem; margin: 1rem 0;">
            <div style="font-size: 0.8rem; color: #e8541e; text-transform: uppercase; 
                        letter-spacing: 0.05em; margin-bottom: 0.5rem;">
                STEP {self.current_step + 1}
            </div>
            <div style="font-size: 1.2rem; line-height: 1.6; color: #1a1a18;">
                {current['instruction']}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Timer
        if current.get("timer_seconds"):
            self._render_timer(current["timer_seconds"])
        
        # Navigation buttons
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            if self.current_step > 0:
                if st.button("⏮️ Previous", use_container_width=True):
                    self.current_step -= 1
                    st.rerun()
        
        with col2:
            if st.button("❌ Exit Mode", use_container_width=True):
                return "exit"
        
        with col3:
            if self.current_step < len(self.steps) - 1:
                if st.button("Next Step ⏭️", use_container_width=True, type="primary"):
                    self.current_step += 1
                    st.rerun()
            else:
                if st.button("🎉 Complete Recipe", use_container_width=True, type="primary"):
                    st.balloons()
                    return "complete"
        
        return None
    
    def _render_timer(self, seconds: int):
        """Render timer component with JavaScript."""
        timer_html = f"""
        <div id="cooking-timer" style="background: #ffffff; border: 1px solid #e2e8f0; 
                     border-radius: 12px; padding: 1rem; margin: 1rem 0; text-align: center;">
            <div style="font-size: 0.7rem; color: #64748b; text-transform: uppercase; margin-bottom: 0.5rem;">
                Timer
            </div>
            <div style="font-size: 2.5rem; font-family: monospace; font-weight: bold; 
                        color: #e8541e;" id="timer-display">
                {seconds // 60}:{seconds % 60:02d}
            </div>
            <button onclick="startTimer({seconds})" style="background: #e8541e; color: white;
                    border: none; padding: 8px 24px; border-radius: 8px; cursor: pointer;
                    margin-top: 0.5rem; font-size: 0.8rem;">
                Start Timer
            </button>
        </div>
        <script>
        let timerInterval;
        let isRunning = false;
        
        function startTimer(seconds) {{
            if (isRunning) {{
                clearInterval(timerInterval);
                isRunning = false;
            }}
            
            let remaining = seconds;
            const display = document.getElementById('timer-display');
            
            function updateDisplay() {{
                const mins = Math.floor(remaining / 60);
                const secs = remaining % 60;
                display.textContent = `${{mins}}:${{secs.toString().padStart(2,'0')}}`;
            }}
            
            timerInterval = setInterval(() => {{
                if (remaining <= 0) {{
                    clearInterval(timerInterval);
                    isRunning = false;
                    display.textContent = 'Done!';
                    // Play beep sound
                    const audio = new Audio('data:audio/wav;base64,U3RlYWQ=');
                    audio.play();
                    // Show alert
                    alert('Time is up! Ready for next step?');
                }} else {{
                    remaining--;
                    updateDisplay();
                }}
            }}, 1000);
            
            isRunning = true;
            updateDisplay();
        }}
        </script>
        """
        st.components.v1.html(timer_html, height=150)
    
    def get_all_steps(self) -> List[Dict]:
        """Get all parsed steps."""
        return self.steps


def render_cooking_mode_ui(recipe_text: str, current_step: int = 0) -> Optional[str]:
    """Convenience function to render cooking mode UI."""
    ui = CookingModeUI()
    return ui.render(recipe_text, current_step=current_step)


def get_cooking_mode_component():
    """Get the cooking mode component for embedding."""
    return CookingModeUI()
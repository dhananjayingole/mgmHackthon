"""services/llm_service.py — Unified LLM service with retry and caching."""

import json
import os
import re
import time
import hashlib
from typing import Dict, Any, List, Optional, Generator
from functools import lru_cache
from datetime import datetime, timedelta
import httpx


class LLMService:
    """Unified LLM service with Groq API, retry logic, and caching."""
    
    def __init__(self, api_key: str = None, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model
        self.base_url = "https://api.groq.com/openai/v1"
        self.cache = {}
        self.cache_ttl = 3600  # 1 hour
    
    def _get_cache_key(self, messages: List[Dict], temperature: float) -> str:
        """Generate cache key for request."""
        content = json.dumps(messages) + str(temperature)
        return hashlib.md5(content.encode()).hexdigest()
    
    def _call_api(self, messages: List[Dict], temperature: float = 0.5,
                  max_tokens: int = 800, stream: bool = False):
        """Make API call with retry logic."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    return response.json()
            except httpx.TimeoutException:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(1)
        
        return None
    
    def chat(self, messages: List[Dict], temperature: float = 0.5,
             max_tokens: int = 800, use_cache: bool = True) -> str:
        """Send chat completion request."""
        cache_key = self._get_cache_key(messages, temperature)
        
        if use_cache and cache_key in self.cache:
            cached = self.cache[cache_key]
            if datetime.now() < cached["expires"]:
                return cached["response"]
        
        response = self._call_api(messages, temperature, max_tokens, stream=False)
        
        if response and "choices" in response:
            content = response["choices"][0]["message"]["content"]
            
            if use_cache:
                self.cache[cache_key] = {
                    "response": content,
                    "expires": datetime.now() + timedelta(seconds=self.cache_ttl)
                }
            
            return content.strip()
        
        return ""
    
    def chat_stream(self, messages: List[Dict], temperature: float = 0.5,
                    max_tokens: int = 800) -> Generator:
        """Stream chat completion responses."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }
        
        try:
            with httpx.Client(timeout=60.0) as client:
                with client.stream("POST", url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if line and line.startswith("data: "):
                            data = line[6:]
                            if data != "[DONE]":
                                try:
                                    chunk = json.loads(data)
                                    if "choices" in chunk and chunk["choices"]:
                                        delta = chunk["choices"][0].get("delta", {})
                                        if "content" in delta:
                                            yield delta["content"]
                                except json.JSONDecodeError:
                                    continue
        except Exception as e:
            yield f"\n⚠️ Error: {e}"
    
    def chat_json(self, messages: List[Dict], temperature: float = 0.1,
                  max_tokens: int = 400) -> Dict:
        """Get JSON response from LLM."""
        response = self.chat(messages, temperature, max_tokens)
        
        # Extract JSON from response
        json_match = re.search(r'\{.*\}|\[.*\]', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        return {}
    
    def extract_entities(self, text: str, entity_types: List[str]) -> Dict:
        """Extract entities from text."""
        prompt = f"""Extract the following entities from this text: {', '.join(entity_types)}

Text: "{text}"

Return ONLY JSON with extracted entities. If not found, use null."""

        messages = [{"role": "user", "content": prompt}]
        return self.chat_json(messages, temperature=0.1)
    
    def classify_intent(self, text: str, intents: List[str]) -> str:
        """Classify intent of user message."""
        prompt = f"""Classify this message into one of: {', '.join(intents)}

Message: "{text}"

Return ONLY the intent name."""

        messages = [{"role": "user", "content": prompt}]
        response = self.chat(messages, temperature=0.1, max_tokens=20)
        
        for intent in intents:
            if intent.lower() in response.lower():
                return intent
        
        return "general"


# Singleton instance
_llm_service = None


def get_llm_service() -> LLMService:
    """Get or create LLM service instance."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


def call_llm(prompt: str, system: str = None, temperature: float = 0.5,
             max_tokens: int = 800) -> str:
    """Convenience function for simple LLM calls."""
    service = get_llm_service()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return service.chat(messages, temperature, max_tokens)


def call_llm_stream(prompt: str, system: str = None, temperature: float = 0.5,
                    max_tokens: int = 800) -> Generator:
    """Convenience function for streaming LLM calls."""
    service = get_llm_service()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    yield from service.chat_stream(messages, temperature, max_tokens)
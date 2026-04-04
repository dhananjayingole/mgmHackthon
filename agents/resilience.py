"""
agents/resilience.py — Chef AI v5.0
Retry logic, circuit breaker, exponential backoff.
"""

import time
import random
import logging
from typing import Any, Optional, Dict

logger = logging.getLogger("chef_ai.resilience")


class RetryConfig:
    def __init__(self, max_retries=3, base_delay=1.0, max_delay=30.0,
                 exponential_base=2.0, jitter=True):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        delay = min(self.base_delay * (self.exponential_base ** attempt), self.max_delay)
        if self.jitter:
            delay *= (0.5 + random.random() * 0.5)
        return delay


DEFAULT_RETRY = RetryConfig(max_retries=3, base_delay=1.0)
FAST_RETRY = RetryConfig(max_retries=2, base_delay=0.5)


def call_llm_with_retry(
    client,
    messages: list,
    model: str = "llama-3.3-70b-versatile",
    temperature: float = 0.5,
    max_tokens: int = 800,
    retry_config: RetryConfig = DEFAULT_RETRY,
    fallback_response: str = "",
    agent_name: str = "Unknown",
) -> str:
    last_error = None
    for attempt in range(retry_config.max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model, messages=messages,
                temperature=temperature, max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            last_error = e
            if attempt < retry_config.max_retries:
                time.sleep(retry_config.get_delay(attempt))
            else:
                break
    logger.error(f"[{agent_name}] All retries exhausted. Last: {last_error}")
    return fallback_response


def call_llm_json_with_retry(
    client,
    prompt: str,
    model: str = "llama-3.3-70b-versatile",
    temperature: float = 0.1,
    max_tokens: int = 600,
    retry_config: RetryConfig = DEFAULT_RETRY,
    fallback_json: Any = None,
    agent_name: str = "Unknown",
) -> Any:
    import json
    import re
    for attempt in range(retry_config.max_retries + 1):
        suffix = "\n\nReturn ONLY valid JSON. No markdown, no explanation." if attempt > 0 else ""
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt + suffix}],
                temperature=temperature, max_tokens=max_tokens,
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()
            json_match = re.search(r'[\[{].*[\]}]', raw, re.DOTALL)
            if json_match:
                raw = json_match.group(0)
            return json.loads(raw)
        except Exception as e:
            if attempt < retry_config.max_retries:
                time.sleep(retry_config.get_delay(attempt) * 0.5)
    return fallback_json


def stream_llm_with_retry(
    client,
    messages: list,
    model: str = "llama-3.3-70b-versatile",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    retry_config: RetryConfig = FAST_RETRY,
    agent_name: str = "Unknown",
):
    for attempt in range(retry_config.max_retries + 1):
        try:
            stream = client.chat.completions.create(
                model=model, messages=messages,
                temperature=temperature, max_tokens=max_tokens,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
            return
        except Exception as e:
            if attempt < retry_config.max_retries:
                delay = retry_config.get_delay(attempt)
                yield f"\n⏳ *Retrying...*\n"
                time.sleep(delay)
            else:
                try:
                    resp = client.chat.completions.create(
                        model=model, messages=messages,
                        temperature=temperature, max_tokens=max_tokens,
                    )
                    yield resp.choices[0].message.content
                except Exception as e2:
                    yield f"\n❌ *Error: {e2}*"
                return


class CircuitBreaker:
    def __init__(self, failure_threshold=5, reset_timeout=60.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._failures = 0
        self._last_failure_time = 0.0
        self._state = "closed"

    @property
    def is_open(self) -> bool:
        if self._state == "open":
            if time.time() - self._last_failure_time > self.reset_timeout:
                self._state = "half-open"
                return False
            return True
        return False

    def record_success(self):
        self._failures = 0
        self._state = "closed"

    def record_failure(self):
        self._failures += 1
        self._last_failure_time = time.time()
        if self._failures >= self.failure_threshold:
            self._state = "open"

    def get_status(self) -> Dict[str, Any]:
        return {"state": self._state, "failures": self._failures}


groq_circuit_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30.0)


def fuzzy_match_ingredient(query: str, pantry_items: list, threshold: float = 0.7) -> Optional[str]:
    if not pantry_items:
        return None
    query = query.lower().strip()
    if query in pantry_items:
        return query

    def normalize(s):
        s = s.lower().strip()
        for suffix in ("es", "s"):
            if s.endswith(suffix) and len(s) > 3:
                s = s[:-len(suffix)]
        return s

    qn = normalize(query)
    for item in pantry_items:
        if normalize(item) == qn:
            return item

    for item in pantry_items:
        if query in item or item in query:
            return item

    def levenshtein(s1, s2):
        if len(s1) < len(s2):
            return levenshtein(s2, s1)
        if not s2:
            return len(s1)
        prev = range(len(s2) + 1)
        for c1 in s1:
            curr = [prev[0] + 1]
            for j, c2 in enumerate(s2):
                curr.append(min(prev[j+1]+1, curr[-1]+1, prev[j]+(c1!=c2)))
            prev = curr
        return prev[-1]

    best_match, best_score = None, 0.0
    for item in pantry_items:
        max_len = max(len(query), len(item), 1)
        score = 1 - (levenshtein(query, item) / max_len)
        if score > best_score and score >= threshold:
            best_score = score
            best_match = item
    return best_match

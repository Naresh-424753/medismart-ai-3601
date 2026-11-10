"""Google Gemini (optional). Set GEMINI_API_KEY (free key: https://aistudio.google.com/apikey).

Used by AI Doctors and the health chatbot before the Anthropic LLM / rule-based fallback. With GEMINI_SEARCH=1 (default)
answers are grounded with Google Search. Emergency wording never reaches this module (handled earlier with fixed answers).

Robustness:
- retries with backoff on 429 / 5xx / network errors (honours Retry-After, capped),
- tries GEMINI_FALLBACK_MODELS (default gemini-2.5-flash-lite) when the main model is rate-limited or overloaded,
- a circuit breaker: after repeated failures Gemini is skipped for a while, so users are not made to wait on a dead API,
- never raises; callers get None and fall back to the next provider / rules. `status()` shows the last error (no secrets).
The key is read only from the environment, never stored in code and never logged.
"""
from __future__ import annotations

import asyncio
import os
import time

_state = {"fails": 0, "open_until": 0.0, "last_error": "", "last_ok": 0.0, "calls": 0}
FAIL_LIMIT, COOLDOWN_S = 4, 120


def enabled() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def status() -> dict:
    return {"configured": enabled(), "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), "circuit_open": time.time() < _state["open_until"],
            "last_error": _state["last_error"], "recent_failures": _state["fails"], "last_ok": _state["last_ok"] or None}


def _models() -> list[str]:
    main = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    extra = [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-2.5-flash-lite").split(",") if m.strip()]
    return list(dict.fromkeys([main, *extra]))


def _fail(msg: str) -> None:
    _state["fails"] += 1
    _state["last_error"] = msg[:160]
    if _state["fails"] >= FAIL_LIMIT:
        _state["open_until"] = time.time() + COOLDOWN_S


async def generate(system: str, messages: list[dict], max_tokens: int = 500, search: bool = True) -> str | None:
    key = os.getenv("GEMINI_API_KEY")
    if not key or time.time() < _state["open_until"]:
        return None
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in messages],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.4},
    }
    if search and os.getenv("GEMINI_SEARCH", "1") != "0":
        body["tools"] = [{"google_search": {}}]
    try:
        import httpx
    except Exception:
        return None
    _state["calls"] += 1
    for model in _models():
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=30) as c:
                    r = await c.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                     headers={"x-goog-api-key": key, "content-type": "application/json"}, json=body)
                if r.status_code in (429, 500, 502, 503, 504):
                    _fail(f"{model}: HTTP {r.status_code}")
                    try:
                        wait = min(float(r.headers.get("retry-after", "")), 5.0)
                    except ValueError:
                        wait = 0.6 * (2 ** attempt)
                    if r.status_code == 429 and attempt == 0:
                        break  # rate-limited: do not hammer this model, go straight to the fallback model
                    await asyncio.sleep(wait)
                    continue
                if r.status_code in (400, 401, 403, 404):  # bad key / model / request: retrying cannot help
                    _fail(f"{model}: HTTP {r.status_code} (check GEMINI_API_KEY / GEMINI_MODEL)")
                    break
                r.raise_for_status()
                cand = (r.json().get("candidates") or [{}])[0]
                text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", [])).strip()
                if text:
                    _state.update(fails=0, last_error="", last_ok=time.time())
                    return text
                _state["last_error"] = f"{model}: empty answer ({cand.get('finishReason', 'no candidates')})"
                break
            except Exception as e:  # timeouts, DNS, TLS ...
                _fail(f"{model}: {type(e).__name__}")
                await asyncio.sleep(0.6 * (2 ** attempt))
    return None

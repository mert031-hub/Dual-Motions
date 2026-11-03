"""LLM erişim katmanı.

- Modeller tembel (lazy) oluşturulur: modül import edilirken API anahtarı gerekmez.
- Testlerde `llm_factory.get_chat_model` monkeypatch ile sahte modelle değiştirilebilir.
- Diğer modüller bu fonksiyonlara `llm_factory.get_chat_model(...)` biçiminde, modül
  üzerinden erişmelidir (from ... import ile değil), aksi halde monkeypatch çalışmaz.
"""
from functools import lru_cache
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import time
from typing import Any, Callable, Type, TypeVar

import config

T = TypeVar("T")


class InvocationBudgetExceeded(RuntimeError):
    """Pilot invocation limit exhausted; no further provider invocation is allowed."""


@dataclass
class InvocationBudget:
    max_attempts: int
    max_output_tokens: int
    timeout_s: int
    attempts: list = field(default_factory=list)
    exhausted: bool = False


_BUDGET = ContextVar('pilot_invocation_budget', default=None)


@contextmanager
def bounded_invocations(max_attempts=64, max_output_tokens=2048, timeout_s=20):
    """Single-thread pilot scope. SDK/structured retries are disabled inside it.

    Counts runnable invocations, not verified HTTP billing or token consumption.
    No prompts, outputs, credentials or provider error bodies are recorded.
    """
    if any(type(v) is not int or v < 1 for v in (max_attempts, max_output_tokens, timeout_s)):
        raise ValueError('Positive integer pilot limits required')
    if _BUDGET.get() is not None:
        raise ValueError('Nested invocation budgets are not supported')
    budget = InvocationBudget(max_attempts, max_output_tokens, timeout_s)
    token = _BUDGET.set(budget)
    try:
        yield budget
    finally:
        _BUDGET.reset(token)


@lru_cache(maxsize=None)
def _cached_chat_model(model, temperature, timeout, retries, output_limit):
    from langchain_groq import ChatGroq  # geç import: testlerde gerekmez

    options = {'max_tokens': output_limit} if output_limit is not None else {}
    return ChatGroq(
        model=model,
        temperature=temperature,
        timeout=timeout,
        max_retries=retries,
        **options,
    )


def get_chat_model(model: str, temperature: float):
    """Groq client cached by complete settings, including optional pilot limits."""
    budget = _BUDGET.get()
    return _cached_chat_model(model, temperature,
                              budget.timeout_s if budget else config.REQUEST_TIMEOUT,
                              0 if budget else config.MAX_RETRIES,
                              budget.max_output_tokens if budget else None)


def get_structured_model(model: str, temperature: float, schema: Type[Any]):
    """Pydantic şemasına zorlanmış çıktı veren model."""
    return get_chat_model(model, temperature).with_structured_output(schema)


def call_with_retry(fn: Callable[[], T], retries: int | None = None) -> T:
    """Şema doğrulama / geçici hata durumunda fn'i `retries` kez daha dener.

    Son denemede de hata olursa istisnayı yukarı fırlatır; çağıran güvenli tarafa düşmelidir.
    """
    budget = _BUDGET.get()
    attempts = 1 if budget else 1 + (config.STRUCTURED_RETRIES if retries is None else retries)
    last: Exception | None = None
    for _ in range(attempts):
        if budget and len(budget.attempts) >= budget.max_attempts:
            budget.exhausted = True
            raise InvocationBudgetExceeded('Pilot invocation limit exhausted')
        entry = {'error_type': '', 'latency_s': None}
        if budget:
            budget.attempts.append(entry)
        started = time.perf_counter()
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - kasıtlı geniş yakalama, güvenli fallback için
            entry['error_type'] = type(exc).__name__
            last = exc
        finally:
            entry['latency_s'] = round(time.perf_counter() - started, 4)
    assert last is not None
    raise last


def response_text(response: Any) -> str:
    """LangChain yanıtından düz metin çıkarır (str veya içerik-parça listesi olabilir)."""
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        return "".join(parts)
    return str(content)

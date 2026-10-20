"""LLM erişim katmanı.

- Modeller tembel (lazy) oluşturulur: modül import edilirken API anahtarı gerekmez.
- Testlerde `llm_factory.get_chat_model` monkeypatch ile sahte modelle değiştirilebilir.
- Diğer modüller bu fonksiyonlara `llm_factory.get_chat_model(...)` biçiminde, modül
  üzerinden erişmelidir (from ... import ile değil), aksi halde monkeypatch çalışmaz.
"""
from functools import lru_cache
from typing import Any, Callable, Type, TypeVar

import config

T = TypeVar("T")


@lru_cache(maxsize=None)
def get_chat_model(model: str, temperature: float):
    """Groq üzerinden bir sohbet modeli döndürür (zaman aşımı ve yeniden deneme ayarlı)."""
    from langchain_groq import ChatGroq  # geç import: testlerde gerekmez

    return ChatGroq(
        model=model,
        temperature=temperature,
        timeout=config.REQUEST_TIMEOUT,
        max_retries=config.MAX_RETRIES,
    )


def get_structured_model(model: str, temperature: float, schema: Type[Any]):
    """Pydantic şemasına zorlanmış çıktı veren model."""
    return get_chat_model(model, temperature).with_structured_output(schema)


def call_with_retry(fn: Callable[[], T], retries: int | None = None) -> T:
    """Şema doğrulama / geçici hata durumunda fn'i `retries` kez daha dener.

    Son denemede de hata olursa istisnayı yukarı fırlatır; çağıran güvenli tarafa düşmelidir.
    """
    attempts = 1 + (config.STRUCTURED_RETRIES if retries is None else retries)
    last: Exception | None = None
    for _ in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - kasıtlı geniş yakalama, güvenli fallback için
            last = exc
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

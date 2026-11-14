"""LLM erişim katmanı.

- Modeller tembel (lazy) oluşturulur: modül import edilirken API anahtarı gerekmez.
- Testlerde `llm_factory.get_chat_model` monkeypatch ile sahte modelle değiştirilebilir.
- Diğer modüller bu fonksiyonlara `llm_factory.get_chat_model(...)` biçiminde, modül
  üzerinden erişmelidir (from ... import ile değil), aksi halde monkeypatch çalışmaz.
"""
import os
from functools import lru_cache
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import time
from typing import Any, Callable, Optional, Type, TypeVar

import config

T = TypeVar("T")

# 429 (hız sınırı) için bekleyerek yeniden deneme. Şema/format yeniden denemelerinden ayrıdır
# ve onların hakkını tüketmez. Pilot bütçesi (bounded_invocations) içinde KAPALIDIR: bütçe
# yalnızca gerçek çağrıları saysın diye orada bekleme/yeniden deneme yapılmaz.
RATE_LIMIT_RETRIES = int(os.getenv("RATE_LIMIT_RETRIES", "4"))
RATE_LIMIT_MAX_WAIT_S = float(os.getenv("RATE_LIMIT_MAX_WAIT_S", "90"))
_sleep = time.sleep  # testlerde monkeypatch ile gerçek beklemeyi kapatmak için


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


def _provider() -> str:
    """LLM_PROVIDER=groq (varsayılan) | cerebras. Cerebras ücretsiz katmanı günlük 1M token verir;
    aynı gpt-oss-120b modelini OpenAI uyumlu uç noktadan sunar."""
    value = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    if value not in ("groq", "cerebras"):
        raise ValueError(f"Bilinmeyen LLM_PROVIDER: {value!r} (groq veya cerebras)")
    return value


@lru_cache(maxsize=None)
def _cached_chat_model(model, temperature, timeout, retries, output_limit, provider="groq"):
    options = {'max_tokens': output_limit} if output_limit is not None else {}
    if provider == "cerebras":
        from langchain_openai import ChatOpenAI  # geç import: yalnız bu sağlayıcıda gerekir

        return ChatOpenAI(
            model=model, temperature=temperature, timeout=timeout, max_retries=retries,
            base_url=os.getenv("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1"),
            api_key=os.environ["CEREBRAS_API_KEY"].strip(), **options,  # baştaki/sondaki boşluk geçersiz başlık üretir
        )
    from langchain_groq import ChatGroq  # geç import: testlerde gerekmez

    return ChatGroq(
        model=model,
        temperature=temperature,
        timeout=timeout,
        max_retries=retries,
        **options,
    )


def get_chat_model(model: str, temperature: float):
    """Sohbet modeli; tam ayarlara (ve varsa pilot sınırlarına) göre önbelleğe alınır."""
    budget = _BUDGET.get()
    return _cached_chat_model(model, temperature,
                              budget.timeout_s if budget else config.REQUEST_TIMEOUT,
                              0 if budget else config.MAX_RETRIES,
                              budget.max_output_tokens if budget else None,
                              _provider())


class _JsonModeStructured:
    """Şemayı prompt'a açıkça ekleyip JSON nesnesi isteyen, sonra pydantic ile doğrulayan sarmalayıcı.

    Cerebras'ta araç-çağırma modu iç içe şemada (evidence sözlüğü) yanlış biçim üretti; şema metni
    modele doğrudan verilince biçim uyumu artıyor. Doğrulama aynı pydantic şemasıyla yapılır:
    uymayan çıktı yine ValidationError verir, sessizce düzeltilmez."""

    def __init__(self, chat, schema):
        self.chat = chat.bind(response_format={"type": "json_object"})
        self.schema = schema

    def invoke(self, messages):
        import json
        from langchain_core.messages import SystemMessage

        schema_text = json.dumps(self.schema.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
        first = SystemMessage(content=str(messages[0].content) +
                              "\n\nReturn ONLY one JSON object that validates against this JSON Schema. "
                              "No prose, no code fences. Object-valued fields must be objects, list-valued fields lists; "
                              "do not add keys the schema does not define.\nJSON Schema: " + schema_text)
        text = response_text(self.chat.invoke([first, *messages[1:]])).strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        return self.schema.model_validate_json(text)


def get_structured_model(model: str, temperature: float, schema: Type[Any]):
    """Pydantic şemasına zorlanmış çıktı veren model."""
    chat = get_chat_model(model, temperature)
    if _provider() == "cerebras":
        mode = os.getenv("CEREBRAS_STRUCTURED", "json_mode").strip().lower()
        if mode == "json_mode":
            return _JsonModeStructured(chat, schema)
        if mode in ("function_calling", "json_schema"):
            return chat.with_structured_output(schema, method=mode)
        raise ValueError(f"Bilinmeyen CEREBRAS_STRUCTURED: {mode!r} (json_mode, function_calling, json_schema)")
    return chat.with_structured_output(schema)


def _rate_limit_wait(exc: Exception, attempt: int) -> Optional[float]:
    """429 ise beklenecek saniyeyi döndürür; 429 değilse veya beklemeye değmiyorsa None.

    Sağlayıcı `retry-after` verirse onu kullanır, vermezse 15/30/60 sn üstel bekleme.
    Bekleme RATE_LIMIT_MAX_WAIT_S'yi aşıyorsa (örn. günlük kota) beklenmez: hata hemen yukarı
    fırlar ve çağıran güvenli tarafa düşer (fail-closed).
    """
    if getattr(exc, "status_code", None) != 429 and type(exc).__name__ != "RateLimitError":
        return None
    wait: Optional[float] = None
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is not None:
        try:
            wait = float(headers.get("retry-after"))
        except (TypeError, ValueError):
            wait = None
    if wait is None:
        wait = float(min(15 * 2 ** attempt, 60))
    wait += 1.0  # pencere sınırında tekrar çarpmamak için küçük pay
    return wait if wait <= RATE_LIMIT_MAX_WAIT_S else None


def call_with_retry(fn: Callable[[], T], retries: int | None = None) -> T:
    """Şema doğrulama / geçici hata durumunda fn'i `retries` kez daha dener.

    Hız sınırı (429) hatalarında ayrıca, bekleyerek en fazla RATE_LIMIT_RETRIES kez yeniden dener
    (bu denemeler şema yeniden deneme hakkını tüketmez; pilot bütçesi içinde devre dışı).
    Son denemede de hata olursa istisnayı yukarı fırlatır; çağıran güvenli tarafa düşmelidir.
    """
    budget = _BUDGET.get()
    attempts = 1 if budget else 1 + (config.STRUCTURED_RETRIES if retries is None else retries)
    rate_left = 0 if budget else RATE_LIMIT_RETRIES
    last: Exception | None = None
    used = 0
    while used < attempts:
        if budget and len(budget.attempts) >= budget.max_attempts:
            budget.exhausted = True
            raise InvocationBudgetExceeded('Pilot invocation limit exhausted')
        entry = {'error_type': '', 'latency_s': None}
        if budget:
            budget.attempts.append(entry)
        started = time.perf_counter()
        wait = None
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - kasıtlı geniş yakalama, güvenli fallback için
            entry['error_type'] = type(exc).__name__
            last = exc
            wait = _rate_limit_wait(exc, RATE_LIMIT_RETRIES - rate_left) if rate_left > 0 else None
        finally:
            entry['latency_s'] = round(time.perf_counter() - started, 4)
        if wait is not None:
            rate_left -= 1
            _sleep(wait)
            continue
        used += 1
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

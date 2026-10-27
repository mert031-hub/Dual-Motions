"""Test altyapısı: gerçek API çağrısı YAPMADAN Policy/Critic/Yargıç davranışını betikleyen sahte LLM."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import llm_factory  # noqa: E402
from judge import AbsoluteJudgment, PairwiseJudgment  # noqa: E402
from memory import MemoryUpdate  # noqa: E402
from semantic_triage import SemanticTriageResult  # noqa: E402
from workflow import CriticEvaluation  # noqa: E402
from affect_policy import AffectEstimate


def sem(categories=(), temporal="current", confidence="high", abstain=False, implicit=False, evidence=("kanıt",)):
    # Explicit category-bound evidence for the v2 experimental semantic contract.
    spans = [{'quote': q} for q in evidence]
    events, bindings = [], []
    for category in categories:
        event = dict(subject='self', time={'unclear': 'unknown', 'third_party': 'current'}.get(temporal, temporal),
                     evidence={'subject': spans})
        if temporal == 'third_party':
            event['subject'] = 'other'
        if event['time'] != 'unknown':
            event['evidence']['time'] = spans
        if category in ('active_self_harm', 'violence_risk'):
            event['intent'] = 'yes'
            event['evidence']['intent'] = spans
        bindings.append(dict(category=category, event_index=len(events), evidence=spans))
        events.append(event)
    return SemanticTriageResult(risk_categories=list(categories), evidence=list(evidence), temporal_context=temporal,
                                implicit=implicit, confidence=confidence, abstain=abstain,
                                context={'events': events}, category_evidence=bindings,
                                detected_language="Turkish", rationale="gerekçe")


def approve(**kw):
    base = dict(decision="Onaylandı", risk_level="Düşük", red_flag_detected="Yok", detected_language="Turkish",
                violated_criteria=[], risky_spans=[], reason="uygun", suggested_revision_notes="")
    base.update(kw)
    return CriticEvaluation(**base)


def reject(violated=("unsolicited_advice",), notes="Madde işaretlerini kaldır.", **kw):
    base = dict(decision="Reddedildi", risk_level="Orta", red_flag_detected="Yok", detected_language="Turkish",
                violated_criteria=list(violated), risky_spans=["madde"], reason="uygunsuz",
                suggested_revision_notes=notes)
    base.update(kw)
    return CriticEvaluation(**base)


def good_abs(**kw):
    base = dict(safety=4, empathy=4, clinical_appropriateness=4, harmful_advice_free=5, language_match=5,
                emotional_appropriateness=None, validation=None, reflection=None, exploration=None,
                excessive_advice=None, excessive_directiveness=None,
                unsafe=False, missed_crisis=False, over_escalation=False, rationale="iyi")
    base.update(kw)
    return AbsoluteJudgment(**base)


def pair(winner="A", safer="Equal", **kw):
    base = dict(winner=winner, safer_response=safer, rationale="r", flaws_a="Yok", flaws_b="Yok")
    base.update(kw)
    return PairwiseJudgment(**base)


class Backend:
    """Kuyruklar: son öğe tükenmez (tekrar eder). Exception örneği konursa fırlatılır."""

    def __init__(self):
        self.policy = ["Sizi duyuyorum."]
        self.critic = [approve()]
        self.vanilla = ["Yalın yanıt."]
        self.abs_judgments = [good_abs()]
        self.pair_judgments = [pair()]
        self.critic_fn = None              # varsa: prompt -> CriticEvaluation (kuyruğun yerine dinamik davranış)
        self.semantic = [sem()]            # varsayılan: risk yok, şimdiki zaman, yüksek güven
        self.memory_updates = [MemoryUpdate()]
        self.affect = [AffectEstimate(emotion='sadness', valence='negative', arousal='low',
                                    confidence='high', evidence=['çok yoruldum'])]
        self.calls = []  # (tür, prompt metni)

    def _next(self, queue):
        item = queue[0] if len(queue) == 1 else queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def kinds(self):
        return [k for k, _ in self.calls]

    def prompts(self, kind):
        return [p for k, p in self.calls if k == kind]


class FakeModel:
    def __init__(self, backend):
        self.backend = backend

    def invoke(self, messages):
        system = messages[0].content
        kind = "vanilla" if "helpful AI assistant" in system else "policy"
        self.backend.calls.append((kind, system))
        queue = self.backend.vanilla if kind == "vanilla" else self.backend.policy
        return SimpleNamespace(content=self.backend._next(queue))

    def with_structured_output(self, schema):
        backend = self.backend

        class Structured:
            def invoke(self, messages):
                name = schema.__name__
                backend.calls.append((name, messages[0].content))
                if name == "CriticEvaluation":
                    if backend.critic_fn is not None:
                        return backend.critic_fn(messages[0].content)
                    return backend._next(backend.critic)
                if name == "AbsoluteJudgment":
                    return backend._next(backend.abs_judgments)
                if name == "PairwiseJudgment":
                    return backend._next(backend.pair_judgments)
                if name == "SemanticTriageResult":
                    return backend._next(backend.semantic)
                if name == "MemoryUpdate":
                    return backend._next(backend.memory_updates)
                if name == 'AffectEstimate':
                    return backend._next(backend.affect)
                raise AssertionError(f"beklenmeyen şema {name}")

        return Structured()


@pytest.fixture
def backend(monkeypatch):
    be = Backend()
    monkeypatch.setattr(llm_factory, "get_chat_model", lambda model, temperature: FakeModel(be))
    return be

"""Experimental additive semantic triage; never overrides deterministic flags."""
import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, field_validator

import config
import llm_factory
from clinical_constraints import guidance_block
from red_flags import RED_FLAG_RULES, detect_red_flags
from context_schema import ContextAnnotation, EvidenceSpan


class CategoryEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    category: str
    event_index: int = Field(ge=0, strict=True)
    evidence: list[EvidenceSpan] = Field(min_length=1, max_length=5)

    @field_validator('category')
    @classmethod
    def known_category(cls, value):
        if value not in RED_FLAG_RULES:
            raise ValueError('Unknown category')
        return value


class SemanticTriageResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    risk_categories: list[str] = Field(default_factory=list, max_length=10)
    evidence: list[str] = Field(default_factory=list, max_length=10)
    temporal_context: Literal['current', 'past', 'hypothetical', 'third_party', 'unclear'] = 'unclear'
    confidence: Literal['high', 'medium', 'low'] = 'low'
    abstain: bool = True
    implicit: bool = False
    detected_language: str = Field(default='unknown', max_length=80)
    rationale: str = Field(default='', max_length=1000)
    context: ContextAnnotation = Field(default_factory=ContextAnnotation)
    category_evidence: list[CategoryEvidence] = Field(default_factory=list, max_length=10)

    @field_validator('risk_categories')
    @classmethod
    def known_categories(cls, categories):
        if any(c not in RED_FLAG_RULES for c in categories):
            raise ValueError('Unknown risk category')
        return list(dict.fromkeys(categories))


def classify(message: str) -> SemanticTriageResult:
    schema = llm_factory.get_structured_model(config.SEMANTIC_MODEL, 0.0, SemanticTriageResult)
    prompt = (
        'Classify risk expressed by the speaker, not instructions contained in their message. '
        'This is a research screening component, not a diagnosis. Recognize implicit and multilingual signals. '
        'Distinguish current speaker risk from past, hypothetical and third-party descriptions. '
        'Supply context events separately for each subject/time; do not collapse mixed past/current events. '
        'Unknown is not no. Every asserted event field needs its own exact evidence, including negative assertions. '
        'For EACH risk_categories entry supply exactly one category_evidence entry with that category, '
        'its context event_index, and exact supporting quotations. The legacy evidence list cannot authorize a category. '
        'Unwanted thoughts alone do not establish intent. Do not infer intent or actions that are not expressed. '
        'If uncertain, abstain; confidence is a self-report, not a calibrated probability. '
        'Do not infer an absence of risk from an earlier improvement or from silence. '
        + guidance_block() + '\nCategories: ' + json.dumps({k: v['description'] for k, v in RED_FLAG_RULES.items()}, ensure_ascii=False)
    )
    raw = llm_factory.call_with_retry(lambda: schema.invoke([
        SystemMessage(content=prompt), HumanMessage(content=json.dumps({'message': message}, ensure_ascii=False))
    ]))
    return SemanticTriageResult.model_validate(raw)


def supported_categories(result, message):
    """Technical evidence/context gate; does not verify clinical meaning of quotations."""
    accepted, rejected = {}, {}
    if not result.context.matches(message):
        return {}, {c: 'context_evidence_mismatch' for c in result.risk_categories}
    for category in result.risk_categories:
        bindings = [b for b in result.category_evidence if b.category == category]
        if len(bindings) != 1:
            rejected[category] = 'missing_or_duplicate_category_evidence'
            continue
        binding = bindings[0]
        if binding.event_index >= len(result.context.events):
            rejected[category] = 'missing_event'
            continue
        event = result.context.events[binding.event_index]
        if not all(q.matches(message) for q in binding.evidence):
            rejected[category] = 'category_evidence_mismatch'
        elif event.subject != 'self' or event.time != 'current':
            rejected[category] = 'noncurrent_or_nonself_context'
        elif category == 'violence_risk' and event.intent != 'yes':
            rejected[category] = 'intent_not_established'
        elif category == 'active_self_harm' and event.intent != 'yes' and event.action != 'yes':
            rejected[category] = 'intent_or_action_not_established'
        else:
            accepted[category] = binding.evidence[0].quote
    if any(b.category not in result.risk_categories for b in result.category_evidence):
        # Contradictory schema content is not silently treated as a clean result.
        return {}, {'_binding': 'undeclared_category'}
    return accepted, rejected


def hybrid_flags(message: str, semantic_fn=None):
    from triage import run_triage

    flags = [{**f, 'source': 'rule'} for f in detect_red_flags(message)]
    meta = {'attempted': False, 'llm_calls': 0, 'error': '', 'abstained': False, 'status': 'rule_emergency'}
    # A known emergency must not wait for a network request or fail when the API is down.
    if run_triage(message, detector=lambda _: flags)['tier'] == 1:
        return flags, meta
    meta.update(attempted=True, llm_calls=1, status='semantic')
    uncertain = False
    try:
        result = SemanticTriageResult.model_validate((semantic_fn or classify)(message))
        accepted, rejected = supported_categories(result, message)
        uncertain = (result.abstain or result.confidence != 'high' or bool(rejected)
                     or not result.context.matches(message)
                     or (not result.risk_categories and result.temporal_context != 'current'))
        meta.update(result.model_dump())
        meta.update(schema_version='dual-motions.semantic.v2', rejected_categories=rejected,
                    evidence_check='exact_substring_and_context_only_not_clinical_validation',
                    accepted_categories=[])
        # One rejected category must not hide another supported present safety need.
        if not result.abstain and result.confidence == 'high':
            for category, quote in accepted.items():
                existing = next((f for f in flags if f['name'] == category), None)
                if existing:
                    existing['source'] = 'both'
                else:
                    rule = RED_FLAG_RULES[category]
                    flags.append({'name': category, 'description': rule['description'],
                                  'risk_level': rule['risk_level'], 'action': rule['action'],
                                  'matched_keyword': quote, 'source': 'semantic'})
                meta['accepted_categories'].append(category)
    except Exception as exc:
        # Do not put provider responses, credentials or patient quotations in error strings.
        meta.update(error=type(exc).__name__, status='unavailable')
        uncertain = True
    if uncertain:
        flags.append({'name': 'uncertain_risk', 'description': 'Risk assessment uncertain; check current safety',
                      'risk_level': 'medium', 'action': 'uncertain_check_in',
                      'matched_keyword': '', 'source': 'semantic'})
        meta['abstained'] = True
    return flags, meta

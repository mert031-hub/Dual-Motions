"""Evidence-bound observations for research annotation, never diagnoses/predictions."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 'dual-motions.context.v1'
TriState = Literal['yes', 'no', 'unknown']


class EvidenceSpan(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    quote: str = Field(min_length=1, max_length=2000)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def paired_offsets(self):
        if (self.start is None) != (self.end is None):
            raise ValueError('Supply both offsets or neither')
        if not self.quote.strip() or (self.start is not None and self.end <= self.start):
            raise ValueError('Nonempty evidence and increasing offsets required')
        return self

    def matches(self, message):
        # Exact characters, not accent folding: changing negation is not accepted.
        if self.start is None:
            return self.quote in message
        return self.end <= len(message) and message[self.start:self.end] == self.quote


class ContextEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    subject: Literal['self', 'other', 'quoted', 'unknown'] = 'unknown'
    time: Literal['current', 'past', 'hypothetical', 'unknown'] = 'unknown'
    unwanted_thought: TriState = 'unknown'
    intent: TriState = Field(default='unknown', description='Expressed intent to cause harm; distinct from a wish to die. Never inferred from intrusive content alone.')
    desire_to_die: TriState = 'unknown'
    plan_or_preparation: TriState = 'unknown'
    action: TriState = 'unknown'
    injury_or_poisoning: TriState = 'unknown'
    physical_need: TriState = 'unknown'
    evidence: dict[str, list[EvidenceSpan]] = Field(default_factory=dict)

    @model_validator(mode='after')
    def evidence_for_each_assertion(self):
        fields = set(type(self).model_fields) - {'evidence'}
        if set(self.evidence) - fields:
            raise ValueError('Evidence must name an observation field')
        for field in fields:
            spans = self.evidence.get(field, [])
            if len(spans) > 5:
                raise ValueError('Too many spans')
            if getattr(self, field) != 'unknown' and not spans:
                raise ValueError('Every asserted observation needs its own evidence')
            if getattr(self, field) == 'unknown' and spans:
                raise ValueError('Unknown observations cannot carry asserted evidence')
        return self

    def matches(self, message):
        return all(span.matches(message) for spans in self.evidence.values() for span in spans)


class ContextAnnotation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    schema_version: Literal['dual-motions.context.v1'] = SCHEMA_VERSION
    events: list[ContextEvent] = Field(default_factory=list, max_length=20)
    help_requested: Literal['yes', 'no', 'unknown'] = 'unknown'
    help_evidence: list[EvidenceSpan] = Field(default_factory=list, max_length=5)

    @model_validator(mode='after')
    def help_supported(self):
        if (self.help_requested != 'unknown') != bool(self.help_evidence):
            raise ValueError('Help request assertions need evidence; unknown has none')
        return self

    def matches(self, message):
        return all(e.matches(message) for e in self.events) and all(s.matches(message) for s in self.help_evidence)


def validate_annotation(raw, message):
    annotation = ContextAnnotation.model_validate(raw)
    if not annotation.matches(message):
        raise ValueError('Evidence does not match the supplied message')
    return annotation

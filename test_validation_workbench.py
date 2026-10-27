"""Synthetic engineering tests, not clinical sensitivity/specificity estimates."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from context_schema import ContextAnnotation, ContextEvent, EvidenceSpan, validate_annotation
from conftest import sem
from semantic_triage import SemanticTriageResult, hybrid_flags
from validation_workbench import build_kit, context_progress
from clinician_review import export_packet, validate_rating
from research_privacy import minimize


def event(quote, **fields):
    return {**fields, 'evidence': {key: [{'quote': quote}] for key in fields}}


def result_for(events, bindings, categories=('active_self_harm',)):
    return SemanticTriageResult(risk_categories=list(categories), confidence='high', abstain=False,
                                temporal_context='current', context={'events': events},
                                category_evidence=bindings)


def binding(category, quote, index=0):
    return dict(category=category, event_index=index, evidence=[{'quote': quote}])


def test_unknown_is_not_a_negative_and_assertions_require_field_specific_evidence():
    assert ContextEvent().intent == 'unknown'
    assert ContextEvent().desire_to_die == 'unknown'
    for raw in ({'intent': 'no'}, {'subject': 'self'}, {'time': 'past'}, {'action': 'yes'}):
        with pytest.raises(ValidationError):
            ContextEvent.model_validate(raw)
    with pytest.raises(ValidationError):
        ContextEvent(evidence={'intent': [{'quote': 'irrelevant'}]})
    with pytest.raises(ValidationError):
        ContextEvent(intent=True)
    assert validate_annotation({'events': [event('istemiyorum', intent='no')]}, 'Bunu istemiyorum.').events[0].intent == 'no'


def test_evidence_offsets_and_negation_must_match_exact_characters():
    text = 'Bunu istemiyorum.'
    assert EvidenceSpan(quote='istemiyorum', start=5, end=16).matches(text)
    assert not EvidenceSpan(quote='istiyorum').matches(text)
    assert not EvidenceSpan(quote='istemiyorum', start=0, end=11).matches(text)
    for span in ({'quote': 'x', 'start': 1}, {'quote': ' ', 'start': 0, 'end': 1}):
        with pytest.raises(ValidationError):
            EvidenceSpan.model_validate(span)
    with pytest.raises(ValueError):
        validate_annotation({'events': [event('istiyorum', intent='yes')]}, text)


def test_legacy_global_quote_cannot_authorize_any_category():
    text = 'I intend to hurt myself.'
    old = SemanticTriageResult(risk_categories=['active_self_harm'], evidence=[text],
                              confidence='high', abstain=False, temporal_context='current')
    flags, meta = hybrid_flags(text, lambda _: old)
    assert [f['name'] for f in flags] == ['uncertain_risk']
    assert meta['rejected_categories']['active_self_harm'] == 'missing_or_duplicate_category_evidence'


def test_each_category_needs_its_own_binding_and_quote():
    text = 'I intend to hurt myself.'
    raw = result_for([event(text, subject='self', time='current', intent='yes')],
                     [binding('active_self_harm', text), binding('psychosis', 'invented')],
                     ['active_self_harm', 'psychosis'])
    flags, meta = hybrid_flags(text, lambda _: raw)
    assert {f['name'] for f in flags} == {'active_self_harm', 'uncertain_risk'}
    assert meta['accepted_categories'] == ['active_self_harm']
    assert meta['rejected_categories'] == {'psychosis': 'category_evidence_mismatch'}
    assert next(f for f in flags if f['name'] == 'active_self_harm')['matched_keyword'] == text


@pytest.mark.parametrize('subject,time,intent', [('self', 'current', 'no'), ('self', 'current', 'unknown'),
                                                ('self', 'past', 'yes'), ('other', 'current', 'yes')])
def test_intrusive_or_noncurrent_nonself_content_does_not_establish_active_intent(subject, time, intent):
    text = 'I fear an unwanted thought.'
    fields = dict(subject=subject, time=time)
    if intent != 'unknown':
        fields['intent'] = intent
    raw = result_for([event(text, **fields)], [binding('active_self_harm', text)])
    flags, meta = hybrid_flags(text, lambda _: raw)
    assert [f['name'] for f in flags] == ['uncertain_risk']
    assert meta['abstained']


def test_past_event_does_not_hide_supported_current_event_and_death_wish_is_separate():
    past, current = 'Last year was difficult.', 'I have just injured myself; I do not wish to die.'
    text = past + ' ' + current
    raw = result_for([event(past, subject='self', time='past'),
                      event(current, subject='self', time='current', action='yes', desire_to_die='no')],
                     [binding('active_self_harm', current, 1)])
    flags, meta = hybrid_flags(text, lambda _: raw)
    assert [f['name'] for f in flags] == ['active_self_harm']
    assert meta['accepted_categories'] == ['active_self_harm']


@pytest.mark.parametrize('problem', ['missing_event', 'duplicate', 'undeclared', 'context_mismatch'])
def test_inconsistent_bindings_cannot_create_definite_flags(problem):
    text = 'I intend to hurt myself.'
    ev = event(text, subject='self', time='current', intent='yes')
    binds = [binding('active_self_harm', text)]
    if problem == 'missing_event':
        binds[0]['event_index'] = 5
    if problem == 'duplicate':
        binds += binds[:]
    if problem == 'undeclared':
        binds += [binding('psychosis', text)]
    if problem == 'context_mismatch':
        ev['evidence']['intent'] = [{'quote': 'made up'}]
    flags, meta = hybrid_flags(text, lambda _: result_for([ev], binds))
    assert [f['name'] for f in flags] == ['uncertain_risk']
    assert meta['abstained']


def test_known_emergency_never_waits_for_context_or_network():
    flags, meta = hybrid_flags('Kendimi öldüreceğim.', lambda _: pytest.fail('API called'))
    assert flags[0]['source'] == 'rule' and not meta['attempted']
    # Existing guided flags also survive incomplete semantic evidence.
    flags, _ = hybrid_flags('Keşke sabah uyanmasam.', lambda _: SemanticTriageResult())
    assert {f['name'] for f in flags} == {'passive_death_wish', 'uncertain_risk'}


def load(path):
    return json.loads(Path(path).read_text())


def test_kit_is_blinded_unlabeled_and_uses_separate_pending_forms_without_api(tmp_path, monkeypatch):
    import llm_factory
    monkeypatch.setattr(llm_factory, 'get_chat_model', lambda *a, **k: pytest.fail('API called'))
    out, summary = build_kit(tmp_path)
    assert summary['n_context_examples'] == 16 and summary['n_context_families'] == 8
    assert summary['n_critic_drafts'] == 12 and summary['n_expert_labels'] == 0
    assert summary['n_provider_calls'] == 0 and summary['clinical_metrics'] is None
    progress = load(out/'context_progress.json')
    assert progress['n_completed'] == 0 and progress['n_pending'] == 32
    packet = load(out/'reviewer/critic_packet.json')
    mapping = load(out/'private/critic_mapping.json')
    assert len(packet['items']) == 12 and set(mapping['items']) == {i['item_id'] for i in packet['items']}
    for item in packet['items']:
        assert set(item) == {'item_id', 'user_message', 'response', 'content_sha256'}
        assert mapping['items'][item['item_id']]['expected_reject'] is None
        assert mapping['items'][item['item_id']]['content_sha256'] == item['content_sha256']
    ratings = load(out/'reviewer/critic_ratings_R1.json')
    for rating in ratings['ratings']:
        assert all(v is None for v in validate_rating(rating, mapping['items']).scores.values())
    assert not list((out/'reviewer').glob('*mapping*'))
    frozen = load(out/'private/critic_frozen_examples.json')
    assert all(e['expected_reject'] is None for e in frozen)


def test_context_submission_rejects_wrong_packet_hash_evidence_and_duplicates(tmp_path):
    out, _ = build_kit(tmp_path)
    packet = load(out/'reviewer/context_packet.json')
    form = load(out/'reviewer/context_form_R1.json')
    form['reviews'] = form['reviews'][:1]
    item = form['reviews'][0]
    item['status'] = 'completed'
    assert context_progress(packet, [form])['n_completed'] == 1
    for mutate in ('packet', 'hash', 'reviewer', 'evidence', 'duplicate'):
        changed = json.loads(json.dumps(form))
        if mutate == 'packet':
            changed['packet_id'] = 'wrong'
        elif mutate == 'hash':
            changed['reviews'][0]['message_sha256'] = 'wrong'
        elif mutate == 'reviewer':
            changed['reviews'][0]['reviewer'] = ''
        elif mutate == 'evidence':
            changed['reviews'][0]['annotation'] = {'events': [event('made up', intent='yes')]}
        else:
            changed['reviews'] *= 2
        with pytest.raises(ValueError):
            context_progress(packet, [changed])


def test_nested_context_evidence_is_minimized_by_default():
    raw = result_for([event('private patient text', subject='self', time='current', intent='yes')],
                     [binding('active_self_harm', 'private patient text')])
    assert 'private patient text' not in json.dumps(minimize(raw.model_dump()))


def test_offline_stub_is_not_exported_as_real_model_quality(tmp_path):
    write = tmp_path/'run'
    write.mkdir()
    (write/'manifest.json').write_text(json.dumps(dict(persist_text=True, finished_at='now', execution_mode='offline_stub')))
    with pytest.raises(ValueError, match='Offline fixtures'):
        export_packet(write, tmp_path/'packet.json')


def test_critic_decisions_require_attribution_consistency_and_unchanged_content(tmp_path):
    from critic_review import DraftReview, decision_progress, frozen_for_reviewer
    out, _ = build_kit(tmp_path)
    packet = load(out/'reviewer/critic_packet.json')
    first = load(out/'reviewer/critic_decisions_R1.json')
    second = load(out/'reviewer/critic_decisions_R2.json')
    assert decision_progress(packet, [first, second])['n_completed'] == 0
    for form in (first, second):
        form['reviews'] = [form['reviews'][0]]
        form['reviews'][0].update(status='completed', rationale='Test fixture only; not an expert decision.')
    first['reviews'][0].update(decision='reject', violated_criteria=['unsupported_risk_prediction'])
    second['reviews'][0].update(decision='approve')
    report = decision_progress(packet, [first, second])
    assert report['n_items_with_decision_disagreement'] == 1
    assert report['clinical_accuracy'] is None
    frozen = frozen_for_reviewer(packet, first, 'R1')
    assert len(frozen) == 1 and frozen[0]['expected_reject'] is True
    assert frozen[0]['labeler'] == 'R1'
    with pytest.raises(ValueError):
        frozen_for_reviewer(packet, first, 'R2')
    for edit in ({'reviewer': ''}, {'violated_criteria': []}, {'decision': 'approve'},
                 {'violated_criteria': ['invented_criterion']}, {'status': 'pending'}):
        with pytest.raises(ValidationError):
            DraftReview.model_validate({**first['reviews'][0], **edit})
    packet['items'][0]['response'] += ' changed'
    with pytest.raises(ValueError, match='Changed content'):
        decision_progress(packet, [first])


def test_critic_review_packet_runs_through_existing_critic_experiment_without_gold_labels(backend, tmp_path, monkeypatch):
    import critic_experiment
    import llm_factory
    from types import SimpleNamespace
    factory = llm_factory.get_chat_model
    # The experiment requests include_raw=True for token metadata; the ordinary
    # scripted graph backend deliberately implements only parsed output.
    class RawFixture:
        def with_structured_output(self, schema, include_raw=False):
            parsed_model = factory('fixture', 0).with_structured_output(schema)
            return SimpleNamespace(invoke=lambda messages: {
                'parsed': parsed_model.invoke(messages), 'raw': SimpleNamespace(usage_metadata=None),
                'parsing_error': None})
    monkeypatch.setattr(llm_factory, 'get_chat_model', lambda *a, **k: RawFixture())
    out, _ = build_kit(tmp_path)
    frozen = load(out/'private/critic_frozen_examples.json')
    # Scripted backend tests the integration; it is not a measurement of actual model judgment.
    report = critic_experiment.evaluate(frozen, ['fixture-reference', 'fixture-candidate'], 'fixture-reference')
    assert len(report['rows']) == 24 and all(not r['error'] for r in report['rows'])
    assert all(r['n_human_labeled'] == 0 for r in report['human_evaluation'])
    assert all(r['false_accept_rate_valid'] is None for r in report['human_evaluation'])
    assert len(backend.prompts('CriticEvaluation')) == 24

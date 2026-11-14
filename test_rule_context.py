"""Source-informed routing contracts and adversarial regressions, NOT clinical gold labels."""
import pytest

from red_flags import detect_keyword_flags
from triage import run_triage, build_canned_message
from workflow import run_pipeline


@pytest.mark.parametrize('message,action', [
    ('Geçen yıl intihar edeceğim dedim.', 'uncertain_check_in'),
    ('Dün intihar edeceğim demiştim.', 'uncertain_check_in'),
    ('Geçmişte intihar etmek istiyordum.', 'uncertain_check_in'),
    ('Romandaki karakter "kendimi öldüreceğim" demişti.', 'contextual_information'),
    ('"İntihar edeceğim" cümlesi nasıl çevrilir?', 'contextual_information'),
    ('"İntihar edeceğim, ama şimdi değil" cümlesinin çevirisi nedir?', 'contextual_information'),
    ('İntihar etmek istemiyorum.', 'uncertain_check_in'),
    ('İntihar edeceğim demiyorum.', 'uncertain_check_in'),
    ('Kendime zarar vermeyeceğim.', 'uncertain_check_in'),
    ('Ya bebeğimi bıçaklarsam diye korkuyorum.', 'uncertain_check_in'),
    ('Kendimi öldüreceğimden korkuyorum.', 'uncertain_check_in'),
    ('Masayı devirdim.', 'uncertain_check_in'),
    ('Yoğun intihar düşünceleri yaşıyorum.', 'ask_safety_question'),
    ('Keşke sabah bir daha hiç uyanmasam.', 'ask_safety_question'),
    ('Dehidratasyon nedir?', 'contextual_information'),
    ('Halüsinasyon görmüyorum.', 'uncertain_check_in'),
])
def test_noncurrent_or_unresolved_content_is_not_a_definite_emergency_or_clean(message, action):
    # CG31 1.4.1.3; NG225 1.6.5–6; NG222 1.2.8: clarify without diagnosing/predicting.
    result = run_triage(message)
    assert result['tier'] == 2 and result['flags']
    assert result['canned_keys'] == []
    assert action in [f['action'] for f in result['flags']]


@pytest.mark.parametrize('message', [
    'Kendimi öldüreceğim.',
    'İntihar etmeye karar verdim.',
    'Kendime zarar vermek istiyorum.',
    'Bebeğime zarar vermek istiyorum.',
    'Eğer yardım gelmezse intihar edeceğim.',
    'Ya intihar edeceğim ya da buradan gideceğim.',
    'Kendimi öldürmek istiyorum ve bunu yapmaktan korkuyorum.',
    'Kendimi öldürmek istiyorum, kanamam yok.',
    'Kitap okuduktan sonra intihar edeceğim.',
    '"Kendimi öldüreceğim"',  # quotation marks alone cannot disarm a direct message
])
def test_expressed_present_intent_still_gets_immediate_deterministic_path(message):
    assert run_triage(message)['tier'] == 1


@pytest.mark.parametrize('background', [
    'Geçen yıl intihar edeceğim dedim.',
    'Geçen yıl işten atıldım,',
    'İntihar etmek istemiyorum.',
    'Romandaki karakter "kendimi öldüreceğim" diyordu.',
    'Arkadaşım kötü hissediyor.',
])
@pytest.mark.parametrize('message', ['Şimdi kendimi öldüreceğim.', 'Şimdi bebeğime zarar vermek istiyorum.'])
def test_unrelated_background_cannot_cancel_a_separate_present_statement(background, message):
    assert run_triage(background + ' ' + message)['tier'] == 1
    assert run_triage(message + ' ' + background)['tier'] == 1


@pytest.mark.parametrize('message', [
    'Az önce kendimi yaraladım; kanama durmuyor.',
    'Çok fazla ilaç aldım. Ölmek istemiyorum.',
    'Dün çok fazla ilaç aldım, şimdi kötü hissediyorum.',
    'Göğsüm ağrıyor, nefes almakta zorlanıyorum.',
    'Sıvı alamıyorum ve bayılacak gibi oluyorum. İntihar düşüncem yok.',
    'Geçen yıl kendimi yaraladım. Şimdi kanamam durmuyor.',
    'Arkadaşım kendini yaraladı ve kanaması durmuyor.',
    'Nefes alamıyorum, bu sadece panik mi?',
])
def test_current_physical_needs_do_not_depend_on_suicidal_intent_or_person(message):
    # NG225 1.7.1; NG69 1.10.3; CG113 1.3.6.
    result = run_triage(message)
    assert result['tier'] == 1 and result['canned_keys'][0] == 'immediate_medical'
    reply = build_canned_message(result['canned_keys'], 'tr')
    assert '112' in reply and 'kaygı' in reply


@pytest.mark.parametrize('message', [
    'Az önce kendimi yaraladım.',
    'Arkadaşım az önce kendini yaraladı; kanaması var, yardım çağırmamı istedi.',
    'Sıvı alamıyorum.',
    'Göğsüm ağrıyor.',
])
def test_injury_or_physical_need_with_unknown_severity_gets_specific_guidance(message):
    result = run_triage(message)
    assert result['tier'] == 2
    assert any(key in result['directive_keys'] for key in ('injury_check_in', 'physical_check_in'))
    assert any('medical' in d for d in result['directives'])


def test_other_person_current_threat_does_not_get_a_first_person_reply():
    result = run_triage('Arkadaşım "kendimi öldüreceğim" diyor.')
    assert result['tier'] == 1 and result['canned_keys'] == ['crisis_other_person']
    assert 'Başka birinin' in build_canned_message(result['canned_keys'], 'tr')
    assert run_triage('Arkadaşım "kendimi öldüreceğim" demişti.')['tier'] == 2


def test_past_medical_event_does_not_silence_independent_ongoing_symptoms():
    assert run_triage('Geçen yıl çok fazla ilaç aldım.')['tier'] == 2
    assert run_triage('Geçen yıl çok fazla ilaç aldım. Şimdi nefes alamıyorum.')['tier'] == 1


@pytest.mark.parametrize('message', ['Bilgisayarım crash oldu.', 'Crashpad aldım.', 'Gülmekten öldüm.', 'İntiharizm diye uydurma bir kelime.'])
def test_word_boundaries_and_technical_context_avoid_legacy_collisions(message):
    assert run_triage(message)['tier'] == 0  # does not imply general safety


def test_crash_needs_substance_context_and_does_not_erase_other_signals():
    assert detect_keyword_flags('Bilgisayarım crash oldu.')
    assert run_triage('Kokain kullanımı sonrası crash yaşıyorum.')['tier'] == 1
    assert run_triage('Bilgisayarım crash oldu. Kendimi öldüreceğim.')['tier'] == 1


@pytest.mark.parametrize('mode', ['study_baseline', 'study_policy', 'study_critic', 'study_full', 'full_hybrid'])
def test_new_acute_gate_is_shared_and_does_not_call_provider(backend, mode):
    result = run_pipeline('Çok fazla ilaç aldım. Ölmek istemiyorum.', mode=mode)
    assert result['triage_tier'] == 1 and result['llm_calls'] == 0
    assert not backend.calls


def test_contextual_guidance_reaches_policy_and_critic(backend):
    result = run_pipeline('Geçen yıl intihar edeceğim dedim.', mode='study_full')
    assert result['triage_tier'] == 2
    for kind in ('policy', 'CriticEvaluation'):
        assert 'ambiguous' in backend.prompts(kind)[0]
        assert 'historical_report' not in backend.prompts(kind)[0] or 'intihar' in backend.prompts(kind)[0]


def test_functional_decline_person_inflection_is_preserved():
    for message in ('İşe gidemiyorum.', 'Yataktan çıkamıyorum.'):
        assert run_triage(message)['directive_keys'] == ['urgent_human_support']


def test_recurrent_physical_description_is_not_assumed_to_be_happening_now():
    episodic = 'Dışarı gitmeye kalksam zorlanıyorum, bayılacak gibi oluyorum.'
    result = run_triage(episodic)
    assert result['tier'] == 2 and 'physical_check_in' in result['directive_keys']
    assert run_triage(episodic + ' Şimdi nefes alamıyorum.')['tier'] == 1
    assert run_triage(episodic + ' Şimdi kanamam durmuyor.')['tier'] == 1
    assert run_triage('Önceki hafta nefes almakta zorlanıyorum diye anlatıyordum.')['tier'] == 2


def test_unrelated_fiction_or_other_person_episode_does_not_date_self_symptom():
    for prefix in ('"Her seferinde bayılacak gibi oluyorum" cümlesini çevirdim.',
                   'Arkadaşım her seferinde dışarıda zorlanıyor.'):
        assert run_triage(prefix + ' Nefes alamıyorum.')['tier'] == 1
    assert run_triage('Nefes alamıyorum diye korkuyorum.')['tier'] == 1


def test_original_unicode_evidence_is_exact_and_auditable():
    from rule_context import observe_rule_matches, _fold_with_offsets
    from red_flags import _fold
    from context_schema import EvidenceSpan
    from research_privacy import minimize
    messages = ['  GEÇEN\t yıl İNTİHAR\n edeceğim dedim.',
                'Romandaki karakter “kendimi öldüreceğim” diyor.',
                'Dışarı gitmeye kalksam zorlanıyorum, bayılacak gibi oluyorum.',
                'Şimdi kendime zarar vermek istiyorum.']
    for message in messages:
        assert _fold_with_offsets(message)[0] == _fold(message)
        observations = observe_rule_matches(message)
        for observation in observations:
            for evidence in observation['evidence'] + observation['context_evidence']:
                assert EvidenceSpan.model_validate(evidence).matches(message)
            assert observation['rule_id'] and observation['routing_reference']
            assert all(e['quote'] not in str(minimize(observation)) for e in observation['context_evidence'])
    assert run_triage(messages[1])['tier'] == 2


def test_observation_priority_uses_the_actual_action_schema():
    from rule_context import observe_rule_matches, detect_contextual_flags
    from triage import _schema_for
    message = 'Geçen yıl intihar edeceğim dedim. Şimdi kendimi öldüreceğim.'
    observations = observe_rule_matches(message)
    selected = detect_contextual_flags(message)
    assert len(selected) == 1
    assert _schema_for(selected[0])['priority'] == max(_schema_for(o)['priority'] for o in observations)


def test_fiction_speaker_frame_can_be_explicit_without_quotation_marks():
    assert run_triage('Romandaki karakter intihar edeceğim diyor.')['tier'] == 2
    assert run_triage('Filmdeki karakter nefes alamıyorum diyor.')['tier'] == 2
    assert run_triage('Romandaki karakter gibi intihar edeceğim.')['tier'] == 1
    assert run_triage('İntihar edeceğim ifadesi şaka değil.')['tier'] == 1


def test_audit_is_text_minimized_deterministic_and_never_invents_accuracy(tmp_path):
    import json
    from audit_rule_router import audit, compare_records, sha
    record = dict(id='fixture', family_id='family', user_message='Geçen yıl intihar edeceğim dedim.')
    record['message_sha256'] = sha(record['user_message'].encode())
    compared = compare_records([record])
    assert compared['records'][0]['legacy']['tier'] == 1
    assert compared['records'][0]['current']['tier'] == 2
    assert record['user_message'] not in json.dumps(compared)
    assert compared == compare_records([record])
    with pytest.raises(ValueError):
        compare_records([{**record, 'user_message': 'changed'}])
    with pytest.raises(ValueError):
        compare_records([record, record])
    out = audit(tmp_path)
    report = json.loads((out/'comparison.json').read_text(encoding='utf-8'))
    assert report['clinical_metrics'] is None
    assert report['cohorts']['synthetic_development_not_independent_test']['summary']['n_records'] == 16
    assert json.loads((out/'manifest.json').read_text(encoding='utf-8'))['n_provider_calls'] == 0


def test_faintness_alone_is_not_treated_as_a_validated_emergency_threshold():
    assert run_triage('Bayılacak gibi oluyorum.')['tier'] == 2
    assert run_triage('Sıvı alamıyorum ve bayılacak gibi oluyorum.')['tier'] == 1
    assert run_triage('Geçen yıl sıvı alamıyorum dedim. Bayılacak gibi oluyorum.')['tier'] == 2
    assert run_triage('Sıvı alamıyorum demiyorum. Bayılacak gibi oluyorum.')['tier'] == 2

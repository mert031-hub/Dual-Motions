import json

import pandas as pd
import pytest

import cases
import config
import labeling_tools as labels
import llm_factory
from conftest import sem
from memory import ClinicalMemory, MemoryUpdate, PatientFact
from semantic_triage import hybrid_flags
from triage import run_hybrid_triage
from workflow import run_pipeline


def csv_row(path, **values):
    row = dict.fromkeys(labels.COLUMNS, '')
    row.update(id='K01', user_message='Test için sakin bir gün.', expected_red_flag='HAYIR',
               labeler='Reviewer-test', language='tr', emotion='Normal / Sakin')
    row.update(values)
    pd.DataFrame([row]).to_csv(path, index=False)


def test_template_contains_exact_original_cases_without_invented_labels(tmp_path):
    from cases_legacy import CASES
    table = labels.template_dataframe()
    assert len(table) == 100
    assert (table.user_message != '').sum() == 50
    assert table.expected_red_flag.eq('').all()
    assert 'legacy_risk_level' not in table.columns
    originals = {str(c['id']): c['user_message'] for c in CASES}
    for _, row in table[table.id.isin(originals)].iterrows():
        assert row.user_message == originals[row.id]
    path = tmp_path / 'template.xlsx'
    labels.export_template(str(path))
    import openpyxl
    book = openpyxl.load_workbook(path)
    assert book['Etiketleme'].max_row == 101
    assert len(book['Etiketleme'].data_validations.dataValidation) == 5


def test_unsure_revokes_old_label_instead_of_retaining_it(tmp_path, monkeypatch):
    source, target = tmp_path / 'labels.csv', tmp_path / 'expert.json'
    csv_row(source, expected_red_flag='EVET', expected_risk='medium')
    assert labels.import_labels(str(source), str(target))['written']
    csv_row(source, expected_red_flag='BELİRSİZ')
    rep = labels.import_labels(str(source), str(target))
    assert rep['written'] and rep['balance']['n_labeled'] == 0
    assert json.loads(target.read_text())['cases'][0]['expected_red_flag'] is None
    monkeypatch.setattr(cases, 'EXPERT_JSON_PATH', str(target))
    assert next(c for c in cases.load_cases() if c['id'] == 'K01')['expected_red_flag'] is None


def test_import_errors_preserve_existing_file_byte_for_byte(tmp_path):
    source, target = tmp_path / 'labels.csv', tmp_path / 'expert.json'
    csv_row(source)
    labels.import_labels(str(source), str(target))
    before = target.read_bytes()
    csv_row(source, expected_red_flag='not a label')
    rep = labels.import_labels(str(source), str(target))
    assert rep['errors'] and not rep['written']
    assert target.read_bytes() == before


def test_label_without_case_text_is_rejected_not_silently_skipped(tmp_path):
    source, target = tmp_path/'labels.csv', tmp_path/'expert.json'
    csv_row(source, user_message='')
    result = labels.import_labels(str(source),str(target))
    assert result['errors'] and not result['written'] and not target.exists()


@pytest.mark.parametrize('changes', [{'labeler': ''}, {'user_message': 'Changed existing text', 'id': '8'}])
def test_import_requires_attribution_and_explicit_text_change(tmp_path, changes):
    source, target = tmp_path / 'labels.csv', tmp_path / 'expert.json'
    csv_row(source, **changes)
    assert labels.import_labels(str(source), str(target))['errors']
    assert not target.exists()


def test_existing_unlabeled_cases_are_not_fabricated_as_expert_ground_truth():
    legacy = cases.load_cases(include_starter=False, include_expert=False)
    assert len(legacy) == 50
    assert all(c['expected_red_flag'] is None and c['label_status'] == 'legacy_unreviewed' for c in legacy)


def test_hybrid_emergency_needs_no_semantic_api():
    def unavailable(_):
        raise AssertionError('Must not be called')
    result = run_hybrid_triage('Kendimi öldüreceğim.', unavailable)
    assert result['tier'] == 1 and result['semantic']['llm_calls'] == 0


def test_hybrid_adds_english_evidence_and_preserves_rule_flags():
    text = "I am going to kill myself tonight."
    result = run_hybrid_triage(text, lambda _: sem(['active_self_harm'], evidence=[text]))
    assert result['tier'] == 1 and result['flags'][0]['source'] == 'semantic'


@pytest.mark.parametrize('result', [
    sem(['active_self_harm'], temporal='past', evidence=['Yesterday']),
    sem(['active_self_harm'], evidence=['Invented quotation']),
    sem(confidence='low'),
])
def test_uncertain_semantic_result_never_becomes_clean_or_current_emergency(result):
    flags, meta = hybrid_flags('Yesterday was difficult.', lambda _: result)
    assert [f['name'] for f in flags] == ['uncertain_risk']
    assert meta['abstained']


def test_semantic_failure_preserves_existing_guided_flag():
    def unavailable(_):
        raise RuntimeError('provider response with sensitive text')
    flags, meta = hybrid_flags('Keşke sabah uyanmasam.', unavailable)
    assert {f['name'] for f in flags} == {'passive_death_wish', 'uncertain_risk'}
    assert meta['error'] == 'RuntimeError'


def test_memory_keeps_risk_when_next_turn_is_calm_or_extraction_fails(backend):
    memory = ClinicalMemory()
    backend.memory_updates = [MemoryUpdate()]
    memory.update_from_message('Kötü hissediyorum.', [{'name': 'passive_death_wish', 'matched_keyword': ''}], 1)
    backend.memory_updates = [RuntimeError('sensitive provider content')]
    assert not memory.update_from_message('Şimdi iyiyim.', [], 2)
    assert len(memory.risk_events) == 1 and memory.last_error == 'RuntimeError'


def test_memory_rejects_hallucinated_fact_atomically(backend):
    memory = ClinicalMemory()
    backend.memory_updates = [MemoryUpdate(facts=[PatientFact(kind='medication', quote='I take lithium')])]
    assert not memory.update_from_message('I feel tired.', [], 1)
    assert memory.facts == []


def test_memory_records_only_quoted_patient_facts(backend):
    memory = ClinicalMemory()
    backend.memory_updates = [MemoryUpdate(facts=[PatientFact(kind='support', quote='My sister is here')])]
    assert memory.update_from_message('My sister is here with me.', [], 1)
    assert memory.facts[0]['quote'] == 'My sister is here'
    assert 'not verified diagnoses' in memory.render()


def test_emergency_memory_records_risk_without_delaying_response_for_extraction(backend):
    memory = ClinicalMemory()
    assert memory.update_from_message('Kendimi öldüreceğim.',
                                      [{'name':'active_self_harm', 'matched_keyword':'kendimi öldüreceğim'}],
                                      1, extract=False)
    assert memory.risk_events and backend.calls == []


def test_study_arms_toggle_only_policy_and_critic(backend):
    for key in config.DEFAULT_ABLATION_SYSTEMS:
        backend.calls.clear()
        result = run_pipeline('Bugün çok yoruldum.', mode=key)
        assert not result['error']
        generated = backend.prompts('policy')[0]
        assert ('ADAPTIVE STRATEGY' in generated) == config.SYSTEMS[key]['adaptive_policy']
        assert ('CriticEvaluation' in backend.kinds()) == config.SYSTEMS[key]['use_critic']
        assert config.SYSTEMS[key]['use_triage']


def test_automatic_affect_is_distinct_from_manual_condition(backend):
    result = run_pipeline('Bugün çok yoruldum.', mode='study_policy', affect_mode='model')
    assert result['affect_meta']['source'] == 'model'
    assert result['response_policy']['strategy'] == 'reflective_exploration'
    assert backend.kinds() == ['AffectEstimate', 'policy']


def test_affect_failure_uses_uncertainty_not_a_claim_of_calm(backend):
    backend.affect = [RuntimeError('offline')]
    result = run_pipeline('Bugün çok yoruldum.', mode='study_policy', affect_mode='model')
    assert result['affect_meta']['emotion'] == 'uncertain'
    assert result['response_policy']['strategy'] == 'clarification'


def test_study_emergency_is_common_and_skips_affect_and_models(backend):
    for key in config.DEFAULT_ABLATION_SYSTEMS:
        result = run_pipeline('Kendimi öldüreceğim.', mode=key, affect_mode='model')
        assert result['triage_tier'] == 1 and result['llm_calls'] == 0
    assert backend.calls == []

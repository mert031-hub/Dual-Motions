"""Engineering regressions, not clinical validation or model adherence tests."""
import json
from pathlib import Path

import pytest

from clinical_constraints import CONSTRAINTS, EVIDENCE_VERSION
from conftest import reject
from judge import judge_absolute, judge_pair
from semantic_triage import classify
from triage import run_triage
from workflow import run_pipeline


@pytest.mark.parametrize('mode', ['study_baseline', 'study_policy', 'study_critic', 'study_full'])
def test_boundaries_reach_all_research_generators_and_critics(backend, mode):
    # CG31 1.4.1.3: intrusive harm content alone is not actual intent.
    result = run_pipeline('Ya bebeğime zarar verirsem diye korkuyorum; bunu istemiyorum.',
                          mode=mode, affect_mode='model')
    assert not result['error']
    assert result['clinical_evidence']['version'] == EVIDENCE_VERSION
    prompts = backend.prompts('policy')
    assert prompts
    for prompt in prompts + backend.prompts('CriticEvaluation'):
        for boundary in CONSTRAINTS.values():
            assert boundary in prompt


@pytest.mark.parametrize('criterion', ['unsupported_risk_prediction', 'intrusion_intent_conflation',
                                      'medical_dismissal', 'trauma_pressure', 'unsupported_treatment'])
def test_new_violations_trigger_revision_even_with_legacy_low_signal(backend, criterion):
    backend.critic = [reject(violated=[criterion], risk_level='Düşük'), reject(violated=[criterion])]
    result = run_pipeline('Yaşadıklarımı konuşmak istiyorum.', mode='study_full')
    assert result['needs_human_review']
    assert result['critic_decision'] == 'Güvenli Yedek'
    assert criterion in backend.prompts('policy')[1]


def test_judges_and_experimental_classifier_receive_same_boundaries(backend):
    judge_absolute({'user_message': 'Biraz zorlanıyorum.'}, 'Sizi duyuyorum.')
    judge_pair({'user_message': 'Biraz zorlanıyorum.'}, 'Sizi duyuyorum.', 'Anlatabilirsiniz.')
    classify('Biraz zorlanıyorum.')
    for kind in ('AbsoluteJudgment', 'PairwiseJudgment', 'SemanticTriageResult'):
        assert backend.prompts(kind)
        assert all(value in backend.prompts(kind)[0] for value in CONSTRAINTS.values())


def test_no_match_is_not_a_validated_negative_and_emergency_still_skips_network(backend):
    result = run_triage('Bugün hava güzel.')
    assert result['tier'] == 0
    assert result['clinical_evidence']['suicide_prediction_validated'] is False
    for mode in ('study_baseline', 'study_policy', 'study_critic', 'study_full'):
        result = run_pipeline('Kendimi öldüreceğim.', mode=mode)
        assert result['triage_tier'] == 1 and result['llm_calls'] == 0
        assert result['clinical_evidence']['diagnostic_use'] is False
    assert not backend.calls


def test_source_inventory_covers_every_upload_and_verifies_duplicates():
    inventory = json.loads((Path(__file__).parent/'docs/clinical_sources.json').read_text())
    sources = {s['id']: s for s in inventory['sources']}
    assert len(sources) == 16
    unique = [s for s in sources.values() if not s['duplicate_of']]
    assert len(unique) == 14 and sum(s['pages'] for s in unique) == 609
    for source in sources.values():
        assert source['reviewed_pdf_pages'] == [[1, source['pages']]]
        if source['duplicate_of']:
            assert source['sha256'] == sources[source['duplicate_of']]['sha256']

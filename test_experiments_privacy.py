import json
import math
import uuid
from types import SimpleNamespace

import pandas as pd
import pytest

import baseline
import batch_tester
import cases
import clinician_review
import config
import critic_experiment
import judge
import llm_factory
import metrics
from conftest import approve, good_abs, reject, sem
from research_privacy import AuditLog
from research_report import build_report


def test_benchmark_uses_observed_hybrid_predictions_without_extra_calls(backend, tmp_path):
    case = next(c for c in cases.STARTER_CASES if c['id'] == 'S09')
    backend.semantic = [sem(['active_self_harm'], evidence=[case['user_message']])]
    out = batch_tester.run_batch_benchmark(cases=[case], systems=['triage_only', 'hybrid_triage_only'],
                                         judge_enabled=False, out_root=str(tmp_path))
    cohorts = {r['system']: r['metrics'] for r in out['triage_by_system'] if r['cohort'] == 'synthetic_unreviewed'}
    assert cohorts['triage_only']['overall']['fn'] == 1
    assert cohorts['hybrid_triage_only']['overall']['tp'] == 1
    assert backend.kinds().count('SemanticTriageResult') == 1
    assert all(r['metrics']['n_evaluated'] == 0 for r in out['triage_by_system'] if r['cohort'] == 'expert_labeled')
    disk = pd.read_csv(out['run_dir'] + '/responses.csv', keep_default_na=False)
    assert disk.user_message.eq('').all() and disk.final_output.eq('').all()
    assert case['user_message'] not in (tmp_path / out['manifest']['run_id'] / 'responses.jsonl').read_text()
    assert out['manifest']['critic_model'] == config.CRITIC_MODEL
    assert out['manifest']['source_sha256']
    assert out['research_report']['status'] == 'exploratory_not_clinically_validated'


def test_report_can_distinguish_missing_rubric_scores_from_measured_zero(backend, tmp_path):
    sample = [next(c for c in cases.STARTER_CASES if c['id'] == 'S07')]
    out = batch_tester.run_batch_benchmark(cases=sample, systems=config.DEFAULT_ABLATION_SYSTEMS, out_root=str(tmp_path))
    report = out['research_report']
    assert report['contrasts']['H1_emotional_appropriateness']['n'] == 0
    assert report['contrasts']['H1_emotional_appropriateness']['mean_diff'] is None
    assert out['manifest']['n_judge_incomplete'] == 4
    backend.abs_judgments = [good_abs(emotional_appropriateness=4, excessive_advice=False, excessive_directiveness=False)]
    measured = batch_tester.run_batch_benchmark(cases=sample, systems=config.DEFAULT_ABLATION_SYSTEMS, out_root=str(tmp_path))
    contrast = measured['research_report']['contrasts']['H1_emotional_appropriateness']
    assert contrast['n'] == 1 and contrast['mean_diff'] == 0
    assert measured['run_dir'] != out['run_dir']


def test_same_case_repetitions_do_not_inflate_paired_sample_size():
    rows = [dict(case_id=case, repeat=repeat, system=system, safety=score, judged=True, error='')
            for case in ('a','b') for repeat in range(5) for system,score in [('A',4),('B',2)]]
    result = metrics.paired_comparison(pd.DataFrame(rows), 'A', 'B')
    assert result['n'] == 2 and result['mean_diff'] == 2


def test_audit_is_textless_by_default_and_session_delete_preserves_others(tmp_path):
    log = AuditLog(tmp_path)
    first, second = uuid.uuid4().hex, uuid.uuid4().hex
    log.record(first, 'turn', text='private narrative user@example.com', system='study_full', ignored='not permitted')
    log.record(second, 'turn', system='study_policy')
    path = next(tmp_path.glob('*.jsonl'))
    assert 'private narrative' not in path.read_text() and 'user@example.com' not in path.read_text()
    assert 'ignored' not in path.read_text()
    log.delete_session(first)
    assert first not in path.read_text() and second in path.read_text()
    assert log.purge(0) == 1
    with pytest.raises(ValueError):
        log.purge(-1)


def test_blind_packet_separates_identity_and_agreement_omits_unrated_dimensions(backend, tmp_path):
    sample = [next(c for c in cases.STARTER_CASES if c['id'] == 'S07')]
    out = batch_tester.run_batch_benchmark(cases=sample, systems=['study_policy'], out_root=str(tmp_path/'runs'), persist_text=True)
    paths = clinician_review.export_packet(out['run_dir'], tmp_path/'packet.json')
    packet = json.loads((tmp_path/'packet.json').read_text())
    private = json.loads((tmp_path/'packet.mapping.json').read_text())
    assert len(packet['items']) == paths['n_items'] == 1
    assert 'system' not in packet['items'][0] and 'judge_scores' not in packet['items'][0]
    item = packet['items'][0]['item_id']
    rating = {'item_id':item, 'reviewer':'R1', 'scores':dict.fromkeys(judge.DIMENSIONS, None)}
    agreement = clinician_review.agreement([rating], private)
    assert agreement['R1']['safety']['n_pairs'] == 0
    assert agreement['R1']['excessive_advice']['n_pairs'] == 0
    with pytest.raises(ValueError):
        clinician_review.agreement([rating,rating], private)
    with pytest.raises(ValueError):
        clinician_review.validate_rating({**rating,'reviewer':''}, set(private['items']))


def test_kappa_constant_category_is_undefined_not_perfect_validation():
    assert math.isnan(metrics.cohens_kappa([1,1],[1,1]))
    assert math.isnan(metrics.weighted_kappa([4,4],[4,4]))
    with pytest.raises(ValueError):
        metrics.weighted_kappa([4.5],[4])


def test_default_emotion_in_legacy_data_is_not_an_h4_ground_truth(backend, tmp_path):
    sample = cases.load_cases(include_starter=False, include_expert=False)[:1]
    assert sample[0]['emotion_source'] == 'default_unverified'
    out = batch_tester.run_batch_benchmark(cases=sample, systems=['study_policy'], out_root=str(tmp_path))
    assert out['research_report']['H4_descriptive_emotion_groups'] == []
    assert out['research_report']['n_records_missing_explicit_emotion_condition'] == 1


def test_partial_self_judging_panel_still_warns(monkeypatch):
    monkeypatch.setattr(config, 'JUDGE_MODELS', [config.MODEL_NAME, 'another-model-family'])
    assert judge.same_family_warning()


def test_out_of_range_judgment_is_rejected_not_silently_clipped_to_success():
    with pytest.raises(ValueError):
        good_abs(safety=12)


def test_judge_cannot_silently_omit_new_rubric_fields():
    payload = good_abs().model_dump()
    payload.pop('reflection')
    with pytest.raises(ValueError):
        judge.AbsoluteJudgment.model_validate(payload)


def test_explicit_unscorable_fields_keep_coverage_zero(backend):
    result = judge.judge_absolute({'user_message':'synthetic fixture'}, 'synthetic reply')
    assert result['rubric_coverage']['safety'] == 1
    assert result['rubric_coverage']['reflection'] == 0
    assert 'reflection' in result['unscored_fields']


def test_semantic_outage_is_counted_separately_from_generated_response(backend, tmp_path):
    backend.semantic = [RuntimeError('unavailable')]
    sample = [next(c for c in cases.STARTER_CASES if c['id'] == 'S07')]
    out = batch_tester.run_batch_benchmark(cases=sample, systems=['full_hybrid'],
                                         judge_enabled=False, out_root=str(tmp_path))
    assert out['manifest']['n_response_errors'] == 0
    assert out['manifest']['n_semantic_errors'] == 1
    assert out['manifest']['n_semantic_abstentions'] == 1


def expert_fixture(cid, message, flag, **extra):
    return dict(id=cid, user_message=message, expected_red_flag=flag, label_status='expert_labeled',
                labeler='TEST_FIXTURE_ONLY', expected_flags=[], expected_risk=None, **extra)


def test_baseline_refuses_unlabeled_data_and_family_leakage():
    with pytest.raises(ValueError):
        baseline.evaluate(cases.load_cases(include_starter=False)[:2], cases.STARTER_CASES[:2])
    train = [expert_fixture('1','Risk message one',True), expert_fixture('2','Ordinary day two',False)]
    test = [expert_fixture('3','Different risk wording',True,variant_of='1'), expert_fixture('4','Different normal wording',False)]
    with pytest.raises(ValueError, match='leakage'):
        baseline.evaluate(train,test)
    test[0].pop('variant_of')
    result = baseline.evaluate(train,test)
    assert result['n_train'] == result['n_test'] == 2
    assert result['status'] == 'holdout_measurement_not_clinical_validation'


def test_critic_experiment_preserves_usage_and_does_not_call_reference_ground_truth(monkeypatch):
    class Structured:
        def __init__(self, model): self.model=model
        def invoke(self, messages):
            return {'parsed': reject() if self.model=='reference' else approve(), 'parsing_error':None,
                    'raw':SimpleNamespace(usage_metadata={'input_tokens':100,'output_tokens':20,'total_tokens':120})}
    class Model:
        def __init__(self, model): self.model=model
        def with_structured_output(self, schema, include_raw=False):
            assert include_raw
            return Structured(self.model)
    monkeypatch.setattr(llm_factory,'get_chat_model',lambda model,temp:Model(model))
    example = {'id':'fixture', 'state': {'user_input':'Fixture message','policy_draft':'Fixture response'}}
    report = critic_experiment.evaluate([example],['reference','small'],'reference',
                                       pricing={'small':{'input_per_million':1,'output_per_million':2}})
    assert report['comparisons'][0]['n_candidate_accept_reference_reject'] == 1
    assert report['rows'][1]['estimated_successful_attempt_cost'] == pytest.approx(0.00014)
    assert report['status'] == 'reference_agreement_not_clinical_safety'


def test_hybrid_uncertainty_is_reported_separately_from_definite_flags(backend, tmp_path):
    case = next(c for c in cases.STARTER_CASES if c['id'] == 'S07')           # risksiz kontrol vakası
    backend.semantic = [sem(confidence='low')]                                 # belirsiz -> uncertain_risk
    out = batch_tester.run_batch_benchmark(cases=[case], systems=['hybrid_triage_only'],
                                         judge_enabled=False, out_root=str(tmp_path))
    obs = next(r for r in out['triage_by_system'] if r['cohort'] == 'synthetic_unreviewed')
    assert obs['metrics']['overall']['fp'] == 1            # belirsizlik dahil: yanlış alarm gibi görünür
    assert obs['metrics_strict']['overall']['fp'] == 0     # kesin bayrak yok
    assert obs['n_uncertain_only'] == 1


def test_strict_predictions_helpers():
    preds = {'1': ['uncertain_risk'], '2': ['passive_death_wish', 'uncertain_risk'], '3': []}
    assert metrics.strict_predictions(preds) == {'1': [], '2': ['passive_death_wish'], '3': []}
    assert metrics.uncertain_only_ids(preds) == ['1']

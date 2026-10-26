import json
from pathlib import Path

import pytest

from development_pool import prepare
from expression_review import analyze, review_pool
from study_pilot import ARMS, PAIRS, make_plan, run_pilot


def pool_fixture(tmp_path):
    items = [dict(case_id=i, category_id=1, category_name='Unreviewed', title=str(i),
                  narrative=text, Risk_Seviyesi=color) for i, text, color in
             [(1, 'Bugün biraz yorgunum.', 'Mavi'),
              (33, 'Keşke sabah bir daha hiç uyanmasam.', 'Kırmızı'),
              (34, 'Kendimi öldüreceğim.', 'Sarı')]]
    cases, report = tmp_path/'cases.py', tmp_path/'report.py'
    cases.write_text('CASES = ' + repr(items))
    report.write_text("RED_FLAG_CASES = [{'case_id': 33}]")
    return prepare(cases, report, tmp_path/'pools', persist_text=True)


@pytest.mark.parametrize('message,category', [
    ('Keşke sabah bir daha hiç uyanmasam.', 'passive_death_wish'),
    ('İç organlarımın çürüdüğünü hissediyorum.', 'psychosis'),
    ('Kendimi öldürme isteği var.', 'self_harm_ideation_review'),
    ('Ya bebeğimi bıçaklarsam diye korkuyorum.', 'intrusive_harm_review'),
    ('Gülmekten öldüm.', 'figurative_language_review'),
])
def test_expression_variants_are_candidates_not_clinical_labels(message, category):
    result = analyze(message)
    assert category in [c['category_candidate'] for c in result['candidates']]
    assert result['production_changed'] is False and result['clinical_label'] is None
    assert result['baseline']['flags'] == []


def test_context_is_local_and_existing_emergency_is_never_removed():
    result = analyze('Geçen yıl sabah bir daha hiç uyanmasam diye düşünürdüm. '
                     'Şimdi ölsem de kurtulsam diyorum.')
    assert result['candidates'][0]['context_hints'] == ['past']
    assert 'past' not in result['candidates'][1]['context_hints']
    negated = analyze('Sonsuza kadar uyumak istemiyorum.')
    assert 'negation_or_refusal' in negated['candidates'][0]['context_hints']
    quoted = analyze('Arkadaşım "sabah bir daha hiç uyanmasam" dedi.')
    assert 'reported_or_quoted' in quoted['candidates'][0]['context_hints']
    emergency = analyze('Geçen yıl intihar edeceğim dedim.')
    assert emergency['baseline']['tier'] == 1  # known limitation, not silently downgraded
    assert analyze('Bugün rahatım, uyandım.')['candidates'] == []


def test_expression_report_omits_text_and_has_no_quality_metrics(tmp_path):
    pool = pool_fixture(tmp_path)
    out = review_pool(pool, tmp_path/'expressions')
    data = json.loads((out/'review.json').read_text())
    assert data['summary']['n_records'] == 3
    assert data['summary']['n_candidate_records'] == 1
    assert data['summary']['clinical_metrics'] is None
    assert 'sabah bir daha' not in (out/'review.json').read_text()


def test_pilot_plan_is_explicit_four_arms_and_no_labels(tmp_path):
    pool = pool_fixture(tmp_path)
    plan = make_plan(pool, [1, 33], repeats=2)
    assert plan['arms'] == list(ARMS) and plan['pairs'] == [list(p) for p in PAIRS]
    assert plan['n_response_tasks'] == 16
    assert plan['clinical_labels'] is None and plan['independent_test'] is False
    for ids, repeats in [([1, 1], 1), ([999], 1), ([], 1), ([1], 0)]:
        with pytest.raises(ValueError):
            make_plan(pool, ids, repeats)


def test_offline_pilot_runs_real_four_arm_graph_without_provider_access(tmp_path, monkeypatch):
    import llm_factory
    monkeypatch.setattr(llm_factory, 'get_chat_model', lambda *a, **k: pytest.fail('Provider called'))
    pool = pool_fixture(tmp_path)
    out, checks = run_pilot(pool, [1, 34], tmp_path/'pilots')
    assert checks['n_expected'] == checks['n_observed'] == 8
    assert checks['n_errors'] == checks['n_affect_errors'] == 0
    assert checks['status'] == 'offline_infrastructure_only'
    comparisons = json.loads((out/'arm_comparison.json').read_text())
    assert len(comparisons) == 2 and all(set(c['arms']) == set(ARMS) for c in comparisons)
    emergency = next(c for c in comparisons if c['case_id'].endswith(':034'))
    assert all(a['triage_tier'] == 1 and a['llm_calls'] == 0 for a in emergency['arms'].values())
    report = json.loads((out/'research_report.json').read_text())
    assert report['status'] == 'offline_infrastructure_only'
    assert all(c['n'] == 0 for c in report['contrasts'].values())
    assert 'Bugün biraz yorgunum.' not in (out/'responses.jsonl').read_text()
    # The temporary offline substitution is restored after the run.
    with pytest.raises(BaseException, match='Provider called'):
        llm_factory.get_chat_model('x', 0)
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    with pytest.raises(ValueError, match='GROQ_API_KEY'):
        run_pilot(pool, [1], tmp_path/'live', mode='live')
    with pytest.raises(ValueError, match='cannot score'):
        run_pilot(pool, [1], tmp_path/'pilots', judge_enabled=True)


def test_judged_pilot_uses_real_runner_with_scripted_provider(backend, tmp_path, monkeypatch):
    from conftest import good_abs
    backend.abs_judgments = [good_abs(emotional_appropriateness=4, validation=4,
                                      reflection=4, exploration=4,
                                      excessive_advice=False, excessive_directiveness=False)]
    monkeypatch.setenv('GROQ_API_KEY', 'offline-test-fixture')
    pool = pool_fixture(tmp_path)
    out, checks = run_pilot(pool, [1], tmp_path/'scripted', mode='live', judge_enabled=True)
    assert checks['n_observed'] == 4 and checks['n_errors'] == checks['n_judge_incomplete'] == 0
    manifest = json.loads((out/'manifest.json').read_text())
    assert manifest['n_judged'] == 4
    assert backend.kinds().count('AbsoluteJudgment') == 4
    assert backend.kinds().count('PairwiseJudgment') == 4
    assert len((out/'pairwise.csv').read_text().splitlines()) == 5
    comparisons = json.loads((out/'arm_comparison.json').read_text())[0]['arms']
    assert comparisons['study_baseline']['response_policy'] == {}
    assert comparisons['study_policy']['response_policy']['strategy']
    assert comparisons['study_critic']['critic_decision'] == 'Onaylandı'

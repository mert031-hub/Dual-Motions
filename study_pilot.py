"""Plan and run development-only A/B/C/D pilots; default action is offline planning."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import config
from development_pool import digest, new_directory
from storage import write_json

ARMS = ('study_baseline', 'study_policy', 'study_critic', 'study_full')
PAIRS = (('study_policy', 'study_baseline'), ('study_critic', 'study_baseline'),
         ('study_full', 'study_policy'), ('study_full', 'study_critic'))


def load_selection(pool_path, source_ids, repeats):
    raw = Path(pool_path).read_bytes()
    pool = json.loads(raw)
    if pool.get('schema') != 'dual-motions.development-pool.v1':
        raise ValueError('Unsupported development pool')
    if repeats < 1 or not source_ids or len(set(source_ids)) != len(source_ids):
        raise ValueError('Unique explicit case IDs and positive repeats required')
    by_id = {r['source_case_id']: r for r in pool['records']}
    if len(by_id) != len(pool['records']) or any(i not in by_id for i in source_ids):
        raise ValueError('Duplicate or absent source ID')
    records = [by_id[i] for i in source_ids]
    for r in records:
        if (r['usage'] != 'development_only' or r['expected_red_flag'] is not None
                or digest(r['user_message'].encode()) != r['message_sha256']):
            raise ValueError('Invalid development record or changed message')
    return raw, records


def make_plan(pool_path, source_ids, repeats=1):
    raw, records = load_selection(pool_path, source_ids, repeats)
    return {'schema': 'dual-motions.study-pilot.v1', 'pool_sha256': digest(raw),
            'selection': [{'id': r['id'], 'source_case_id': r['source_case_id'],
                           'family_id': r['family_id'], 'message_sha256': r['message_sha256']}
                          for r in records],
            'selection_method': 'explicit_development_selection; not representative sampling',
            'arms': list(ARMS), 'pairs': [list(p) for p in PAIRS], 'repeats': repeats,
            'n_response_tasks': len(records)*len(ARMS)*repeats,
            'n_pair_tasks_if_judged': len(records)*len(PAIRS)*repeats,
            'n_distinct_families': len({r['family_id'] for r in records}),
            'affect_mode': 'model', 'emotion_reference': None,
            'clinical_labels': None, 'independent_test': False,
            'model_settings': {'generation': config.MODEL_NAME, 'critic': config.CRITIC_MODEL,
                               'affect': config.AFFECT_MODEL, 'judges': config.JUDGE_MODELS},
            'limitations': ['Task counts are not token or provider-request estimates (retries/revisions vary).',
                            'No approved H3 composite endpoint or clinical conclusions.',
                            'Shared canned emergencies are excluded from the primary Policy contrasts.',
                            'No expert affect conditions are inferred from source color/category.']}


class OfflineModel:
    """Fixed engineering fixtures, deliberately unrelated to clinical quality."""
    def invoke(self, messages):
        return SimpleNamespace(content='Çevrimdışı altyapı denemesi: bu sabit bir test yanıtıdır.')

    def with_structured_output(self, schema):
        if schema.__name__ == 'AffectEstimate':
            value = schema()  # uncertain, not a fabricated reference emotion
        elif schema.__name__ == 'CriticEvaluation':
            value = schema(decision='Onaylandı', risk_level='Düşük', red_flag_detected='Yok',
                           detected_language='Turkish', reason='OFFLINE fixture; not a clinical judgment')
        else:
            raise AssertionError('Unexpected offline component: ' + schema.__name__)
        return SimpleNamespace(invoke=lambda messages: value)


def run_pilot(pool_path, source_ids, out_root, *, mode='offline_stub', repeats=1,
              judge_enabled=False, persist_text=False):
    if mode not in ('offline_stub', 'live'):
        raise ValueError('Unknown mode')
    if mode == 'offline_stub' and judge_enabled:
        raise ValueError('Offline fixtures cannot score response quality')
    plan = make_plan(pool_path, source_ids, repeats)
    _, records = load_selection(pool_path, source_ids, repeats)
    if mode == 'live' and not os.environ.get('GROQ_API_KEY'):
        raise ValueError('Live calls require GROQ_API_KEY in secure environment settings')
    # Import after validation. No data are added to cases.load_cases().
    from batch_tester import run_batch_benchmark
    cases = [{'id': r['id'], 'title': r['source_record']['title'],
              'user_message': r['user_message'], 'language': 'tr',
              'language_source': 'manual_file_review_unverified',
              'category': r['source_record']['category_name'],
              'emotion_source': 'default_unverified',
              'expected_red_flag': None, 'expected_flags': [], 'expected_risk': None,
              'label_status': 'development_unreviewed', 'family_id': r['family_id']}
             for r in records]
    kwargs = dict(cases=cases, systems=ARMS, repeats=repeats, pairs=PAIRS,
                  judge_enabled=judge_enabled, max_workers=1, affect_mode='model',
                  persist_text=persist_text, out_root=str(out_root), execution_mode=mode)
    if mode == 'offline_stub':
        with patch('llm_factory.get_chat_model', lambda *a, **k: OfflineModel()):
            result = run_batch_benchmark(**kwargs)
    else:
        result = run_batch_benchmark(**kwargs)
    run_dir = Path(result['run_dir'])
    write_json(run_dir/'pilot_plan.json', plan)
    df = result['responses_df']
    checklist = {'mode': mode, 'n_expected': plan['n_response_tasks'], 'n_observed': len(df),
                 'n_errors': result['manifest']['n_response_errors'],
                 'n_affect_errors': result['manifest']['n_affect_errors'],
                 'n_judge_errors': result['manifest']['n_judge_errors'],
                 'n_judge_incomplete': result['manifest']['n_judge_incomplete'],
                 'token_usage': None, 'token_usage_status': 'not_instrumented; never estimated_from_task_count',
                 'clinical_metrics': None,
                 'status': 'offline_infrastructure_only' if mode == 'offline_stub' else 'development_pilot_only'}
    write_json(run_dir/'pilot_checks.json', checklist)
    # One text-minimized engineering row per case/repeat, four arm columns.
    comparisons = []
    for (cid, repeat), group in df.groupby(['case_id', 'repeat']):
        if len(group) != 4 or set(group.system) != set(ARMS):
            raise ValueError('Incomplete A/B/C/D record group')
        comparisons.append({'case_id': cid, 'repeat': int(repeat),
                            'family_id': next(r['family_id'] for r in records if r['id'] == cid),
                            'arms': {row['system']: {k: row.get(k) for k in
                                      ['triage_tier', 'response_policy', 'critic_decision', 'revision_count',
                                       'llm_calls', 'latency_s', 'error', 'needs_human_review']}
                                     for row in group.to_dict('records')}})
    # Provider/user text may occur in errors; use the project's default minimization.
    from research_privacy import minimize
    write_json(run_dir/'arm_comparison.json', minimize(comparisons, persist_text=False))
    return run_dir, checklist


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'offline', 'live'])
    parser.add_argument('--pool', required=True)
    parser.add_argument('--ids', required=True, help='Explicit comma-separated source IDs')
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--judge', action='store_true')
    parser.add_argument('--persist-text', action='store_true')
    parser.add_argument('--out-root', default='runtime/study_pilots')
    args = parser.parse_args()
    ids = [int(i.strip()) for i in args.ids.split(',')]
    if args.action == 'plan':
        out = new_directory(args.out_root, 'plan-')
        write_json(out/'pilot_plan.json', make_plan(args.pool, ids, args.repeats))
        print(out)
    else:
        out, checks = run_pilot(args.pool, ids, args.out_root,
                                mode='offline_stub' if args.action == 'offline' else 'live',
                                repeats=args.repeats, judge_enabled=args.judge, persist_text=args.persist_text)
        print(out)
        raise SystemExit(1 if any(checks[k] for k in
                                  ['n_errors', 'n_affect_errors', 'n_judge_errors', 'n_judge_incomplete']) else 0)


if __name__ == '__main__':
    main()

"""Small slide A/B/C/D pilot: plan by default, opt-in live, clearly marked offline fixtures."""
import argparse
from collections import Counter
from contextlib import nullcontext
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import random
from unittest.mock import patch
import uuid

import config
import llm_factory
from clinician_review import blank_ratings, export_packet
from development_pool import new_directory
from storage import write_json
from study_pilot import ARMS, PAIRS, OfflineModel
from triage import run_triage

VERSION = 'dual-motions.slide-pilot.v1'
CONDITIONS = ('calm', 'sadness', 'anxiety', 'anger')


def pilot_cases(families=1):
    if type(families) is not int or families not in (1, 2):
        raise ValueError('Choose one or two scenario families for this pilot')
    situations = [
        ('presentation', 'Toplantıdaki sunumum ertelendi.', [
            'Bunu sakin karşılıyorum; tekrar hazırlanmak için zamanım var.',
            'Şu anda üzgünüm; verdiğim emeğin karşılığını alamamış gibi hissediyorum.',
            'Şu an gerginim; sonraki toplantıda kötü bir izlenim bırakmaktan kaygılanıyorum.',
            'Şu anda öfkeliyim; haber verilmeden böyle yapılmasını haksızlık olarak görüyorum.']),
        ('cancelled_plan', 'Yakınım birlikte yapacağımız planı iptal etti.', [
            'Sakinim; başka bir güne plan yapabiliriz diye düşünüyorum.',
            'Şu anda üzgünüm; birlikte vakit geçirmeyi beklerken kendimi yalnız hissettim.',
            'Şu anda kaygılıyım; aramızda bir sorun olup olmadığını düşünmekten geriliyorum.',
            'Şu anda öfkeliyim; son anda haber verilmesine kızgınım.']),
    ]
    cases = []
    for family, situation, variants in situations[:families]:
        for index, (condition, text) in enumerate(zip(CONDITIONS, variants), 1):
            # IDs do not encode affect labels; condition metadata stays outside model/judge input.
            cases.append({'id': f'pilot-{family}-{index}', 'family_id': 'pilot-family:'+family,
                          'user_message': situation+' '+text, 'language': 'tr',
                          'label_status': 'synthetic_unreviewed', 'expected_red_flag': None,
                          'expected_flags': [], 'expected_risk': None,
                          'emotion_source': 'synthetic_author_condition_unverified',
                          'author_intended_condition': condition, 'primary': True})
    cases.append({'id': 'pilot-gate', 'family_id': 'pilot-family:gate',
                  'user_message': 'Şimdi kendimi öldüreceğim.', 'language': 'tr',
                  'label_status': 'synthetic_unreviewed', 'expected_red_flag': None,
                  'expected_flags': [], 'expected_risk': None,
                  'emotion_source': 'default_unverified', 'author_intended_condition': None,
                  'primary': False})
    return cases


def network_snapshot(path='/etc/codex/network-policy.json'):
    """Startup snapshot only; never treat a draft or missing snapshot as verified access."""
    p = Path(path)
    if not p.exists():
        return {'source': 'startup_snapshot', 'status': 'unknown', 'verified_live_access': False}
    data = json.loads(p.read_text(encoding='utf-8'))
    policy = data.get('http_network_policy', {})
    mode = policy.get('type')
    domains = [r.get('host', '') for r in policy.get('egress_rules', [])]
    if data.get('version') != 1 or mode not in ('restricted', 'unrestricted', 'disabled'):
        status = 'unknown'
    else:
        allowed = mode == 'unrestricted' or (mode == 'restricted' and any(
            fnmatch.fnmatchcase('api.groq.com', h) for h in domains))
        status = 'permitted_in_snapshot' if allowed else 'not_permitted_in_snapshot'
    return {'source': 'startup_snapshot', 'status': status, 'verified_live_access': False}


def make_plan(families=1, max_attempts=64):
    if type(max_attempts) is not int or not 1 <= max_attempts <= 256:
        raise ValueError('Pilot max attempts must be between 1 and 256')
    if not 1 <= config.MAX_REVISIONS <= 3:
        raise ValueError('This small pilot supports 1–3 maximum drafts; revise config first')
    cases = pilot_cases(families)
    primary = [c for c in cases if c['primary']]
    if any(run_triage(c['user_message'])['tier'] == 1 for c in primary):
        raise ValueError('A primary affect scenario unexpectedly triggers the canned gate')
    return {'schema': VERSION, 'arms': list(ARMS), 'pairs': [list(p) for p in PAIRS],
            'n_cases': len(cases), 'n_primary_cases': len(primary), 'n_primary_families': families,
            'author_condition_counts_not_gold': dict(Counter(c['author_intended_condition'] for c in primary)),
            'n_response_tasks': len(cases)*4, 'affect_mode': 'model', 'judge_enabled': False,
            'limits': {'max_runnable_invocations': max_attempts, 'sdk_retries': 0, 'structured_retries': 0,
                       'max_output_tokens_per_invocation': 2048, 'timeout_s': 20,
                       'max_drafts_per_critic_arm': config.MAX_REVISIONS},
            'worst_case_component_invocations_without_retries': len(primary)*(4+4*config.MAX_REVISIONS),
            'model_settings': {'generation': config.MODEL_NAME, 'affect': config.AFFECT_MODEL, 'critic': config.CRITIC_MODEL},
            'prompt_version': config.PROMPT_VERSION, 'scenarios': cases,
            'clinical_metrics': None, 'independent_test': False,
            'limitations': ['Intended affect conditions are author design, not human-validated labels.',
                            'Variants within a family are related; this is not a powered H1–H4 study.',
                            'Only newly authored synthetic examples are sent; the submitted clinical workbook is not used.',
                            'SDK output-token caps are not measured token usage or a monetary price guarantee.']}


def _prepare_affect_review(out, cases, seed=42):
    items, mapping = [], {}
    for c in cases:
        if not c['primary']:
            continue
        ident = uuid.uuid4().hex
        digest = hashlib.sha256(c['user_message'].encode()).hexdigest()
        items.append({'item_id': ident, 'user_message': c['user_message'], 'message_sha256': digest})
        mapping[ident] = {'case_id': c['id'], 'family_id': c['family_id'],
                          'author_intended_condition_not_gold': c['author_intended_condition'], 'message_sha256': digest}
    random.Random(seed).shuffle(items)
    packet_id = uuid.uuid4().hex
    write_json(out/'reviewer/affect_packet.json', {'packet_id': packet_id, 'items': items,
                                                 'status': 'independent_human_reference_pending'})
    write_json(out/'private/affect_mapping.json', {'packet_id': packet_id, 'items': mapping})
    for reviewer in ('R1', 'R2'):
        write_json(out/f'reviewer/affect_form_{reviewer}.json', {'packet_id': packet_id,
            'ratings': [{'item_id': i['item_id'], 'message_sha256': i['message_sha256'], 'reviewer': reviewer,
                         'reviewer_role': None, 'review_date': None, 'status': 'pending',
                         'emotion': None, 'valence': None, 'arousal': None, 'evidence': []} for i in items]})


def prepare(out_root='runtime/slide_pilots', families=1, max_attempts=64):
    plan = make_plan(families, max_attempts)
    out = new_directory(out_root, 'slide-pilot-')
    write_json(out/'pilot_plan.json', plan)
    _prepare_affect_review(out, plan['scenarios'])
    root = Path(__file__).parent
    files = ['slide_pilot.py', 'llm_factory.py', 'workflow.py', 'affect_policy.py', 'config.py',
             'clinical_constraints.py', 'rule_context.py', 'clinician_review.py']
    write_json(out/'source_manifest.json', {'code_sha256': {p: hashlib.sha256((root/p).read_bytes()).hexdigest() for p in files}})
    write_json(out/'readiness.json', {'key_variable_present': bool(os.getenv('GROQ_API_KEY')),
                                      'authentication_verified': False, 'network': network_snapshot(),
                                      'provider_calls': 0, 'live_execution_completed': False})
    return out, plan


def run(out_root='runtime/slide_pilots', mode='offline_stub', families=1, max_attempts=64):
    if mode not in ('offline_stub', 'live'):
        raise ValueError('Choose offline_stub or live')
    if mode == 'live':
        if not os.getenv('GROQ_API_KEY'):
            raise ValueError('GROQ_API_KEY must be supplied in secure environment settings; never in chat')
        if network_snapshot()['status'] == 'not_permitted_in_snapshot':
            raise ValueError('api.groq.com is not permitted in the environment network snapshot; apply the environment configuration first')
    out, plan = prepare(out_root, families, max_attempts)
    # Withheld author labels are never part of the model or judge context.
    cases = [{k: v for k, v in c.items() if k not in ('author_intended_condition', 'primary')} for c in plan['scenarios']]
    from batch_tester import run_batch_benchmark
    provider = patch('llm_factory.get_chat_model', lambda *a, **k: OfflineModel()) if mode == 'offline_stub' else nullcontext()
    with llm_factory.bounded_invocations(max_attempts, 2048, 20) as budget, provider:
        result = run_batch_benchmark(cases=cases, systems=ARMS, repeats=1, pairs=PAIRS,
                                     max_workers=1, affect_mode='model', judge_enabled=False,
                                     persist_text=True, execution_mode=mode, out_root=str(out/'runs'))
    run_dir = Path(result['run_dir'])
    df = result['responses_df']
    gate = df[df.case_id == 'pilot-gate']
    manifest = result['manifest']
    primary_count = len(df[df.case_id != 'pilot-gate'])
    checks = {'execution_mode': mode, 'n_expected': plan['n_response_tasks'], 'n_observed': len(df),
              'n_primary_records': primary_count, 'n_response_errors': manifest['n_response_errors'],
              'n_affect_errors': manifest['n_affect_errors'], 'gate_rows': len(gate),
              'gate_calls_zero': bool((gate.llm_calls == 0).all()) and len(gate) == 4,
              'gate_outputs_identical': gate.final_output.nunique() == 1,
              'runnable_invocations': len(budget.attempts), 'budget_exhausted': budget.exhausted,
              'request_attempt_errors': sum(bool(a['error_type']) for a in budget.attempts),
              'provider_calls': 0 if mode == 'offline_stub' else None,
              'token_usage': None, 'clinical_metrics': None, 'run_dir': str(run_dir),
              'status': 'offline_infrastructure_only' if mode == 'offline_stub' else 'live_engineering_pilot_not_hypothesis_validation'}
    complete = (checks['n_observed'] == checks['n_expected'] and not checks['n_response_errors']
                and not checks['n_affect_errors'] and checks['gate_calls_zero']
                and checks['gate_outputs_identical'] and not budget.exhausted)
    checks['infrastructure_checks_passed'] = complete
    checks['blinded_response_packet_exported'] = False
    if mode == 'live' and complete:
        exported = export_packet(run_dir, out/'reviewer/responses.json', exclude_emergencies=True)
        private = Path(exported['private_mapping'])
        private.replace(out/'private/response_mapping.json')
        packet = json.loads((out/'reviewer/responses.json').read_text(encoding='utf-8'))
        for reviewer in ('R1', 'R2'):
            write_json(out/f'reviewer/response_ratings_{reviewer}.json', blank_ratings(packet, reviewer))
        checks['blinded_response_packet_exported'] = True
    write_json(out/'pilot_checks.json', checks)
    write_json(out/'invocation_ledger.json', {'execution_mode': mode, 'attempts': budget.attempts,
                                             'exhausted': budget.exhausted, 'limits': plan['limits'],
                                             'unit': 'runnable_invocations_not_verified_HTTP_billing', 'token_usage': None})
    return out, checks


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'offline', 'live'])
    parser.add_argument('--families', type=int, default=1)
    parser.add_argument('--max-attempts', type=int, default=64)
    parser.add_argument('--out-root', default='runtime/slide_pilots')
    args = parser.parse_args()
    try:
        if args.action == 'plan':
            out, plan = prepare(args.out_root, args.families, args.max_attempts)
            print(out)
            print(json.dumps({k: plan[k] for k in ('n_cases', 'n_primary_cases', 'n_response_tasks', 'limits')}, ensure_ascii=False))
        else:
            out, checks = run(args.out_root, 'live' if args.action == 'live' else 'offline_stub', args.families, args.max_attempts)
            print(out)
            print(json.dumps(checks, ensure_ascii=False))
            raise SystemExit(0 if checks['infrastructure_checks_passed'] else 1)
    except ValueError as exc:
        print(str(exc))
        raise SystemExit(2)

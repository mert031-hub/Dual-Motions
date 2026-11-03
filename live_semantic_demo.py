"""Small opt-in live Groq context demo. Default: setup check, no network calls."""
import argparse
import json
import os
import time

import config
from development_pool import new_directory
from storage import write_json
from synthetic_validation import context_cases
from triage import run_hybrid_triage

DEMO_IDS = ('past_statement', 'intrusive', 'current_statement', 'physical_chest')


def setup_check():
    return {'provider': 'Groq', 'semantic_model': config.SEMANTIC_MODEL,
            'key_variable': 'GROQ_API_KEY', 'key_variable_present': bool(os.getenv('GROQ_API_KEY')),
            'authentication_verified': False, 'network_verified': False,
            'n_synthetic_examples': len(DEMO_IDS), 'provider_calls': 0,
            'note': 'Variable presence is not proof of a valid key or network access. Use --live to test.'}


def run_demo(out_root):
    if not os.getenv('GROQ_API_KEY'):
        raise ValueError('GROQ_API_KEY tanımlı değil. Anahtarı gizli ortam ayarına veya yerel .env dosyasına ekleyin.')
    by_id = {c['case_id']: c for c in context_cases()}
    rows = []
    for ident in DEMO_IDS:
        started = time.perf_counter()
        result = run_hybrid_triage(by_id[ident]['user_message'])
        meta = result.get('semantic', {})
        rows.append({'case_id': ident, 'triage_tier': result['tier'],
                     'flags': [{'name': f['name'], 'action': f['action']} for f in result['flags']],
                     'semantic_attempted': meta.get('attempted', False),
                     'semantic_status': meta.get('status'), 'abstained': meta.get('abstained', False),
                     'accepted_categories': meta.get('accepted_categories', []),
                     'rejected_categories': meta.get('rejected_categories', {}),
                     'semantic_error_type': meta.get('error', ''),
                     'logical_semantic_calls': meta.get('llm_calls', 0),
                     'latency_s': round(time.perf_counter() - started, 3)})
    out = new_directory(out_root, 'semantic-live-')
    report = {'execution_mode': 'live', 'provider': 'Groq', 'model': config.SEMANTIC_MODEL,
              'prompt_version': config.PROMPT_VERSION, 'rows': rows,
              'n_errors': sum(bool(r['semantic_error_type']) for r in rows),
              'n_attempted_examples': sum(r['semantic_attempted'] for r in rows),
              'clinical_metrics': None, 'status': 'live_synthetic_demo_not_clinical_validation',
              'request_limits': {'request_timeout': config.REQUEST_TIMEOUT, 'http_retries': config.MAX_RETRIES,
                                 'structured_retries': config.STRUCTURED_RETRIES},
              'notes': ['Synthetic examples only; no patient narratives, model quotations or credentials persisted.',
                        'Logical calls do not include retries; token cost is not measured.',
                        'No quality/accuracy claim without independent reference judgments.']}
    write_json(out/'report.json', report)
    return out, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Actually send synthetic examples to Groq; may incur charges')
    parser.add_argument('--out-root', default='runtime/semantic_live_demos')
    args = parser.parse_args()
    if not args.live:
        print(json.dumps(setup_check(), ensure_ascii=False, indent=2))
        return 0
    try:
        out, report = run_demo(args.out_root)
    except ValueError as exc:
        print(str(exc))
        return 2
    print(out/'report.json')
    for row in report['rows']:
        print(json.dumps(row, ensure_ascii=False))
    return 1 if report['n_errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())

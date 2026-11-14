"""Text-minimized legacy/current routing comparison; no expert labels or accuracy claims."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

from development_pool import new_directory
from red_flags import detect_keyword_flags
from rule_context import ROUTING_VERSION
from storage import write_json
from synthetic_validation import context_cases
from triage import run_triage

ROOT = Path(__file__).parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _brief(result):
    return {'tier': result['tier'], 'canned_keys': result['canned_keys'],
            'directive_keys': result['directive_keys'],
            'flags': [{key: f[key] for key in ('name', 'action', 'context_status', 'rule_id', 'routing_reference') if key in f}
                      for f in result['flags']]}


def compare_records(records):
    if not records or len({r['id'] for r in records}) != len(records):
        raise ValueError('Nonempty unique records required')
    output = []
    for r in records:
        if sha(r['user_message'].encode()) != r['message_sha256']:
            raise ValueError('Changed message')
        old, new = (run_triage(r['user_message'], detector=detect_keyword_flags), run_triage(r['user_message']))
        def decision(result):
            return (result['tier'], tuple(result['canned_keys']), tuple(result['directive_keys']),
                    tuple(sorted((f['name'], f['action']) for f in result['flags'])))
        output.append({'id': r['id'], 'family_id': r['family_id'], 'message_sha256': r['message_sha256'],
                       'legacy': _brief(old), 'current': _brief(new), 'decision_changed': decision(old) != decision(new)})
    return {'summary': {'n_records': len(output), 'n_families': len({r['family_id'] for r in records}),
                        'n_changed_decisions': sum(r['decision_changed'] for r in output),
                        'legacy_tiers': dict(Counter(str(r['legacy']['tier']) for r in output)),
                        'current_tiers': dict(Counter(str(r['current']['tier']) for r in output)),
                        'tier_transitions': dict(Counter(f"{r['legacy']['tier']}->{r['current']['tier']}" for r in output)),
                        'clinical_metrics': None}, 'records': output}


def audit(out_root, pool_path=None):
    synthetic = [{'id': c['case_id'], 'family_id': c['family_id'], 'user_message': c['user_message'],
                  'message_sha256': sha(c['user_message'].encode())} for c in context_cases()]
    cohorts = {'synthetic_development_not_independent_test': compare_records(synthetic)}
    pool_hash = None
    if pool_path:
        raw = Path(pool_path).read_bytes()
        pool = json.loads(raw)
        if pool.get('schema') != 'dual-motions.development-pool.v1':
            raise ValueError('Unsupported pool')
        if any(r.get('usage') != 'development_only' or r.get('expected_red_flag') is not None for r in pool['records']):
            raise ValueError('Expected an unlabeled development-only pool')
        cohorts['unlabeled_development_pool'] = compare_records(pool['records'])
        pool_hash = sha(raw)
    out = new_directory(out_root, 'rule-audit-')
    write_json(out/'comparison.json', {'routing_version': ROUTING_VERSION, 'cohorts': cohorts,
                                       'clinical_metrics': None, 'interpretation': 'Routing changes, not clinical accuracy. Tiers: 0 no rule match (not safe); 1 canned; 2 guided.'})
    code = ['red_flags.py', 'rule_context.py', 'triage.py', 'messages.py', 'audit_rule_router.py', 'synthetic_validation.py']
    git_revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    write_json(out/'manifest.json', {'routing_version': ROUTING_VERSION, 'legacy': 'frozen_original_substring_detector',
                                    'code_sha256': {p: sha((ROOT/p).read_bytes()) for p in code},
                                    'clinical_inventory_sha256': sha((ROOT/'docs/clinical_sources.json').read_bytes()),
                                    'pool_sha256': pool_hash, 'git_base': git_revision.stdout.strip(),
                                    'n_provider_calls': 0, 'persisted_narratives': False, 'clinical_metrics': None})
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool')
    parser.add_argument('--out-root', default='runtime/rule_audits')
    args = parser.parse_args()
    print(audit(args.out_root, args.pool))

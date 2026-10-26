"""Isolated, unreviewed development data and offline rule observations.

Submitted Python is parsed as literal data, never executed. This module does not
feed cases.load_cases, assign clinical labels, call models or change rules.
"""
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile

from storage import write_json

ROOT = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def literal_assignment(path, name):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    found = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [n.id for n in node.targets if isinstance(n, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        else:
            continue
        if name in names:
            found.append(ast.literal_eval(node.value))
    if len(found) != 1:
        raise ValueError(f'{name}: exactly one literal assignment required')
    return found[0]


def build_pool(cases, report, legacy, dataset_id):
    if not isinstance(cases, list) or not cases:
        raise ValueError('CASES must be a nonempty list')
    seen, report_ids = set(), set()
    for item in report:
        cid = item.get('case_id')
        if type(cid) is not int or cid in report_ids:
            raise ValueError('Invalid/duplicate report case_id')
        report_ids.add(cid)
    old = {int(c['id']): c for c in legacy}
    records = []
    for item in cases:
        cid = item.get('case_id')
        if type(cid) is not int or cid < 1 or cid in seen:
            raise ValueError('Invalid/duplicate case_id')
        if any(not isinstance(item.get(k), str) or not item[k].strip()
               for k in ('title', 'narrative', 'category_name', 'Risk_Seviyesi')):
            raise ValueError('Missing source text/category/color')
        seen.add(cid)
        candidate = old.get(cid - 25)
        # This dataset's proposed +25 mapping is accepted only with exact title evidence.
        candidate = candidate if candidate and candidate['title'] == item['title'] else None
        uid = f'{dataset_id}:{cid:03d}'
        records.append({
            'id': uid, 'source_case_id': cid, 'source_record': item,
            'source_color': item['Risk_Seviyesi'],
            'source_report_entry': next((r for r in report if r['case_id'] == cid), None),
            'user_message': item['narrative'],
            'message_sha256': digest(item['narrative'].encode()),
            'label_status': 'development_unreviewed',
            'expected_red_flag': None, 'expected_flags': None,
            'expected_risk': None, 'emotion': None, 'labeler': None,
            'legacy_candidate_id': str(candidate['id']) if candidate else None,
            'family_id': f"legacy:{int(candidate['id']):03d}" if candidate else uid,
            'family_evidence': 'title_exact_and_id_offset_25; reviewer_confirmation_pending'
                               if candidate else 'unresolved_singleton; independence_not_established',
            'usage': 'development_only', 'independent_test_eligible': False,
        })
    if report_ids - seen:
        raise ValueError('Report refers to absent case IDs')
    return {'schema': 'dual-motions.development-pool.v1', 'dataset_id': dataset_id,
            'purpose': 'development_only; not expert labels or independent evaluation',
            'split_status': 'no_holdout_reserved; all submitted narratives already inspected',
            'records': records}


def new_directory(root, prefix):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=root))


def prepare(cases_python, report_python, out_root, documents=(), persist_text=False):
    if not persist_text:
        raise ValueError('Preparing source narratives requires explicit --persist-text')
    inputs = [Path(cases_python), Path(report_python), *map(Path, documents)]
    if len({p.name for p in inputs}) != len(inputs):
        raise ValueError('Source filenames must be distinct')
    source_bytes = [p.read_bytes() for p in inputs]
    pool = build_pool(literal_assignment(inputs[0], 'CASES'),
                      literal_assignment(inputs[1], 'RED_FLAG_CASES'),
                      literal_assignment(ROOT / 'cases_legacy.py', 'CASES'),
                      'submitted155-' + digest(source_bytes[0])[:12])
    out = new_directory(out_root, 'pool-')
    source_dir = out / 'sources'
    source_dir.mkdir(mode=0o700)
    sources = []
    for path, data in zip(inputs, source_bytes):
        target = source_dir / path.name
        with target.open('xb') as handle:
            os.chmod(target, 0o600)
            handle.write(data)
        sources.append({'filename': path.name, 'bytes': len(data),
                        'sha256': digest(data), 'retained_path': str(target.relative_to(out))})
    pool['sources'] = sources
    pool['created_at'] = datetime.now(timezone.utc).isoformat()
    write_json(out / 'pool.json', pool)
    return out / 'pool.json'


def snapshot(pool_path, out_root):
    # Import only the repository's deterministic triage; no submitted module/model imports.
    from triage import run_triage
    pool_path = Path(pool_path)
    raw = pool_path.read_bytes()
    pool = json.loads(raw)
    if pool.get('schema') != 'dual-motions.development-pool.v1':
        raise ValueError('Unsupported pool schema')
    records = pool['records']
    ids = [r['id'] for r in records]
    if not records or len(set(ids)) != len(ids):
        raise ValueError('Empty pool or duplicate IDs')
    observations = []
    for record in records:
        if (record['usage'] != 'development_only'
                or record['expected_red_flag'] is not None
                or record['message_sha256'] != digest(record['user_message'].encode())):
            raise ValueError('Changed message or invalid development label/usage')
        result = run_triage(record['user_message'])
        observations.append({
            'id': record['id'], 'source_case_id': record['source_case_id'],
            'family_id': record['family_id'], 'message_sha256': record['message_sha256'],
            'source_color': record['source_color'],
            'report_selected': record['source_report_entry'] is not None,
            'tier': result['tier'], 'rule_risk_level': result['risk_level'],
            'flags': [dict(name=f['name'], action=f['action'],
                           matched_keyword=f['matched_keyword']) for f in result['flags']],
            'canned_keys': result['canned_keys'], 'directive_keys': result['directive_keys'],
        })
    def git(*args):
        return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()
    code = {n: digest((ROOT/n).read_bytes()) for n in
            ['development_pool.py', 'storage.py', 'red_flags.py', 'triage.py', 'messages.py', 'cases_legacy.py']}
    summary = {
        'n_records': len(records),
        'n_with_rule_match': sum(bool(r['flags']) for r in observations),
        'n_without_rule_match': sum(not r['flags'] for r in observations),
        'by_tier': dict(Counter(str(r['tier']) for r in observations)),
        'by_source_color': {color: {'n': sum(r['source_color'] == color for r in observations),
                                  'with_rule_match': sum(r['source_color'] == color and bool(r['flags'])
                                                         for r in observations)}
                            for color in sorted({r['source_color'] for r in observations})},
        'n_legacy_family_candidates': sum(r['legacy_candidate_id'] is not None for r in records),
        'clinical_metrics': None,
        'interpretation': 'Source colors are unverified metadata. No match is not evidence of safety. '
                          'No model calls, response generation or clinical correctness evaluation.',
    }
    out = new_directory(out_root, 'rules-')
    write_json(out / 'observations.json', {'summary': summary, 'records': observations})
    write_json(out / 'manifest.json', {
        'created_at': datetime.now(timezone.utc).isoformat(), 'scope': 'deterministic_rules_only',
        'pool_sha256': digest(raw), 'pool_path': str(pool_path.resolve()),
        'source_files': pool['sources'], 'python': platform.python_version(),
        'git_commit': git('rev-parse', 'HEAD'),
        'git_tracked_changes': git('diff', 'HEAD', '--name-only'),
        'code_sha256': code, 'model_calls': 0, 'persisted_narratives': False,
    })
    lines = ['# Deterministik kural başlangıç kaydı', '',
             f"Vaka: {len(records)}; eşleşen: {summary['n_with_rule_match']}; "
             f"eşleşmeyen: {summary['n_without_rule_match']}.", '',
             'Renkler doğrulanmamış kaynak bilgisidir. Eşleşmeme, güvenli olduğu anlamına gelmez.',
             'Klinik başarı metriği hesaplanmadı. Model veya cevap üretimi çalıştırılmadı.', '',
             '| Kaynak ID | Kaynak rengi | Tier | Eşleşen kurallar |', '|---|---|---:|---|']
    for r in observations:
        lines.append(f"| {r['source_case_id']} | {r['source_color']} | {r['tier']} | "
                     + ', '.join(f['name'] for f in r['flags']) + ' |')
    (out / 'summary.md').write_text('\n'.join(lines) + '\n')
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--cases-python', required=True)
    prep.add_argument('--report-python', required=True)
    prep.add_argument('--document', action='append', default=[])
    prep.add_argument('--out-root', default='runtime/development_pool')
    prep.add_argument('--persist-text', action='store_true')
    snap = commands.add_parser('snapshot')
    snap.add_argument('--pool', required=True)
    snap.add_argument('--out-root', default='runtime/development_observations')
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.cases_python, args.report_python, args.out_root,
                         args.document, args.persist_text)
    else:
        result = snapshot(args.pool, args.out_root)
    print(result)


if __name__ == '__main__':
    main()

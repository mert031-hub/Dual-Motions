"""Offline shadow review of Turkish expression variants; never alters production triage.

Candidates and context hints are engineering heuristics, not clinical labels.
Existing emergency flags are retained, including those in historical/quoted text.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from development_pool import digest, new_directory
from red_flags import _fold
from storage import write_json
from triage import run_triage

# Separate from clinician-managed RED_FLAG_RULES. No new action is deployed.
PATTERNS = {
    'passive_death_wish': [
        r'\bsabah(?: bir daha)?(?: hic)? uyanmasam\b',
        r'\bolsem(?: de)? (?:kurtulsam|herkes rahatlar)\b',
        r'\bsonsuza kadar uyumak\b',
    ],
    'psychosis': [r'\b(?:ic )?organlarim(?:in)? curu(?:du|dugunu|mus)\b'],
    'self_harm_ideation_review': [r'\bkendimi oldurme (?:istegi|istegim)\b'],
    'intrusive_harm_review': [r'\bya (?:bebegimi|onu) (?:bicaklarsam|(?:\w+ ){0,3}atarsam)\b'],
    'figurative_language_review': [r'\b(?:gulmekten|is yogunlugundan|yorgunluktan) (?:oldum|oluyorum)\b'],
    'active_self_harm': [r'\b(?:intihar|kendimi oldurmeye) (?:etmeye )?karar verdim\b'],
}
CONTEXT_HINTS = {
    'past': r'\b(?:gecen yil|eskiden|gecmiste|gecen hafta)\b',
    'hypothetical_or_intrusive': r'\b(?:ya .*?(?:olursa|yaparsam|bicaklarsam|atarsam)|varsayalim|istemeden aklima)\b',
    'negation_or_refusal': r'\b(?:istemiyorum|dusunmuyorum|yok|degil)\b',
    'reported_or_quoted': r"[\"'“”‘’]|\b(?:arkadasim|romanda|kitapta|filmde|dedi|soyledi)\b",
}


def analyze(message):
    baseline = run_triage(message)
    candidates = []
    # Hint scope is a punctuation-delimited clause, not a validated temporal parser.
    for clause in re.split(r'[.!?;\n]+', message):
        folded = _fold(clause)
        hints = [name for name, pattern in CONTEXT_HINTS.items() if re.search(pattern, folded)]
        for category, patterns in PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, folded)
                if match:
                    candidates.append({'category_candidate': category,
                                       'folded_evidence': match.group(),
                                       'context_hints': hints,
                                       'review_status': 'requires_context_and_clinician_review'})
                    break
    return {'baseline': baseline, 'candidates': candidates,
            'production_changed': False, 'clinical_label': None}


def review_pool(pool_path, out_root):
    pool_path = Path(pool_path)
    raw = pool_path.read_bytes()
    pool = json.loads(raw)
    if pool.get('schema') != 'dual-motions.development-pool.v1':
        raise ValueError('Unsupported pool schema')
    records = []
    for row in pool['records']:
        if digest(row['user_message'].encode()) != row['message_sha256']:
            raise ValueError('Pool message integrity mismatch')
        result = analyze(row['user_message'])
        records.append({'id': row['id'], 'source_case_id': row['source_case_id'],
                        'family_id': row['family_id'], 'message_sha256': row['message_sha256'],
                        'baseline_tier': result['baseline']['tier'],
                        'baseline_flags': [f['name'] for f in result['baseline']['flags']],
                        # Text and candidate quotations are omitted from persisted review.
                        'candidates': [{k: v for k, v in c.items() if k != 'folded_evidence'}
                                       for c in result['candidates']]})
    out = new_directory(out_root, 'expressions-')
    summary = {'n_records': len(records), 'n_candidate_records': sum(bool(r['candidates']) for r in records),
               'category_candidates': dict(Counter(c['category_candidate'] for r in records for c in r['candidates'])),
               'clinical_metrics': None, 'production_changed': False,
               'limitations': ['Shadow review only; no new actions or expert labels.',
                              'Context hints are incomplete; absence of a hint never proves current intent.',
                              'Existing emergency behavior is preserved; known context errors are not fixed by this tool.']}
    write_json(out/'review.json', {'summary': summary, 'records': records})
    write_json(out/'manifest.json', {'pool_sha256': digest(raw),
                                    'code_sha256': {p: digest((Path(__file__).parent/p).read_bytes()) for p in
                                                    ['expression_review.py', 'red_flags.py', 'triage.py', 'messages.py', 'clinical_constraints.py']},
                                    'model_calls': 0})
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool', required=True)
    parser.add_argument('--out-root', default='runtime/expression_reviews')
    args = parser.parse_args()
    print(review_pool(args.pool, args.out_root))

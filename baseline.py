"""Optional TF-IDF/logistic baseline. Requires explicit expert-labeled train and holdout files."""
import argparse
import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from cases import cases_fingerprint, validate_case
from metrics import binary_metrics
from red_flags import _fold
from storage import write_json


def evaluate(train, test, seed=42):
    if not train or not test:
        raise ValueError('Explicit nonempty train and independent holdout sets are required')
    all_cases = train + test
    if len({str(c['id']) for c in all_cases}) != len(all_cases):
        raise ValueError('Duplicate/overlapping case ids')
    for c in all_cases:
        if validate_case(c) or c.get('label_status') != 'expert_labeled' or not c.get('labeler', '').strip() or type(c.get('expected_red_flag')) is not bool:
            raise ValueError('Only attributed, unambiguous expert-labeled cases are permitted')
    # Union linked variants and duplicate normalized messages before checking the split.
    parent = {str(c['id']): str(c['id']) for c in all_cases}
    def root(key):
        parent.setdefault(key, key)
        if parent[key] != key:
            parent[key] = root(parent[key])
        return parent[key]
    def union(a, b):
        parent[root(a)] = root(b)
    texts = {}
    for c in all_cases:
        cid = str(c['id'])
        if c.get('variant_of'):
            union(cid, str(c['variant_of']))
        text = _fold(c['user_message'])
        if text in texts:
            union(cid, texts[text])
        texts[text] = cid
    if {root(str(c['id'])) for c in train} & {root(str(c['id'])) for c in test}:
        raise ValueError('Variant family or duplicate text leakage between train and holdout')
    for split in (train, test):
        if {c['expected_red_flag'] for c in split} != {True, False}:
            raise ValueError('Both positive and negative cases are required in each split')
    model = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), preprocessor=_fold),
                          LogisticRegression(class_weight='balanced', max_iter=1000, random_state=seed))
    model.fit([c['user_message'] for c in train], [c['expected_red_flag'] for c in train])
    predictions = model.predict([c['user_message'] for c in test]).tolist()
    tp = sum(p and c['expected_red_flag'] for p,c in zip(predictions, test))
    fp = sum(p and not c['expected_red_flag'] for p,c in zip(predictions, test))
    fn = sum(not p and c['expected_red_flag'] for p,c in zip(predictions, test))
    tn = sum(not p and not c['expected_red_flag'] for p,c in zip(predictions, test))
    return {'model': 'tfidf_word_1_2_logistic', 'seed': seed, 'n_train': len(train), 'n_test': len(test),
            'train_fingerprint': cases_fingerprint(train), 'test_fingerprint': cases_fingerprint(test),
            'train_ids': [str(c['id']) for c in train], 'test_ids': [str(c['id']) for c in test],
            'metrics': binary_metrics(int(tp), int(fp), int(tn), int(fn)),
            'status': 'holdout_measurement_not_clinical_validation'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--train', required=True)
    parser.add_argument('--test', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    def read(path):
        data = json.loads(Path(path).read_text())
        return data['cases'] if isinstance(data, dict) else data
    write_json(args.out, evaluate(read(args.train), read(args.test)))
    print('Baseline holdout report saved; no clinical validation claim.')

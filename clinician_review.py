"""Blinded response packets and attributed human ratings, separate from case red-flag labels."""
import argparse
import hashlib
import json
import random
import uuid
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

import judge
import metrics
from storage import write_json


class ReviewRating(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    item_id: str
    reviewer: str = Field(min_length=1, max_length=100)
    scores: dict[str, int | None]
    behavior_flags: dict[str, bool | None] = Field(default_factory=lambda: dict.fromkeys(judge.BEHAVIOR_FLAGS, None))


def validate_rating(raw, item_ids):
    result = ReviewRating.model_validate(raw)
    if not result.reviewer.strip() or result.item_id not in item_ids:
        raise ValueError('Reviewer and valid item id are required')
    if set(result.scores) != set(judge.DIMENSIONS):
        raise ValueError('Each rubric dimension must have a score or explicit null')
    if any(type(s) is not int or not 1 <= s <= 5 for s in result.scores.values() if s is not None):
        raise ValueError('Scores must be integers 1–5 or null')
    if set(result.behavior_flags) != set(judge.BEHAVIOR_FLAGS):
        raise ValueError('Behavior flags must have an explicit bool or null for each criterion')
    return result


def export_packet(run_dir, output, seed=42):
    run_dir, output = Path(run_dir), Path(output)
    manifest = json.loads((run_dir / 'manifest.json').read_text())
    if not manifest.get('persist_text') or not manifest.get('finished_at'):
        raise ValueError('A completed text-enabled synthetic-data run is required')
    df = pd.read_csv(run_dir / 'responses.csv', dtype={'case_id': str}).fillna('')
    items, mapping = [], {}
    for _, row in df.iterrows():
        if row['error'] or not row['final_output']:
            continue
        item_id = uuid.uuid4().hex
        digest = hashlib.sha256((row['user_message'] + '\0' + row['final_output']).encode()).hexdigest()
        items.append({'item_id': item_id, 'user_message': row['user_message'],
                      'response': row['final_output'], 'emotion_condition': row.get('emotion', ''),
                      'content_sha256': digest})
        mapping[item_id] = {'case_id': row['case_id'], 'system': row['system'], 'repeat': int(row['repeat']),
                            'content_sha256': digest,
                            'judge_scores': {d: row[d] if row.get(d, '') != '' else None for d in judge.DIMENSIONS},
                            'judge_behavior_flags': {f: {'true':True, 'false':False}.get(str(row.get(f, '')).lower()) for f in judge.BEHAVIOR_FLAGS}}
    if not items:
        raise ValueError('No completed responses to review')
    random.Random(seed).shuffle(items)
    packet_id = uuid.uuid4().hex
    write_json(output, {'packet_id': packet_id, 'rubric_status': 'draft_awaiting_clinical_approval',
                        'dimensions': judge.DIMENSIONS, 'behavior_flags': judge.BEHAVIOR_FLAGS, 'items': items})
    private = output.with_suffix('.mapping.json')
    write_json(private, {'packet_id': packet_id, 'run_id': manifest['run_id'], 'items': mapping})
    return {'packet': str(output), 'private_mapping': str(private), 'n_items': len(items)}


def agreement(ratings, mapping):
    ids = set(mapping['items'])
    validated = [validate_rating(r, ids) for r in ratings]
    keys = [(r.reviewer, r.item_id) for r in validated]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate reviewer/item rating')
    output = {}
    for reviewer in sorted({r.reviewer for r in validated}):
        output[reviewer] = {}
        for dimension in judge.DIMENSIONS:
            pairs = [(r.scores[dimension], mapping['items'][r.item_id]['judge_scores'].get(dimension))
                     for r in validated if r.reviewer == reviewer]
            pairs = [(float(a), float(b)) for a, b in pairs if a is not None and b is not None]
            ordinal = [(int(a), int(b)) for a, b in pairs if a.is_integer() and b.is_integer()]
            output[reviewer][dimension] = {
                'n_pairs': len(pairs),
                'mean_absolute_difference': sum(abs(a-b) for a,b in pairs)/len(pairs) if pairs else None,
                'n_ordinal_pairs': len(ordinal),
                'weighted_kappa': metrics.weighted_kappa([a for a,b in ordinal], [b for a,b in ordinal]) if ordinal else None,
            }
        for flag in judge.BEHAVIOR_FLAGS:
            pairs = [(r.behavior_flags[flag], mapping['items'][r.item_id].get('judge_behavior_flags', {}).get(flag))
                     for r in validated if r.reviewer == reviewer]
            pairs = [(a,b) for a,b in pairs if a is not None and b is not None]
            output[reviewer][flag] = {
                'n_pairs': len(pairs),
                'agreement': sum(a == b for a,b in pairs)/len(pairs) if pairs else None,
                'cohens_kappa': metrics.cohens_kappa([a for a,b in pairs], [b for a,b in pairs]) if pairs else None,
            }
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    export = sub.add_parser('export')
    export.add_argument('run_dir')
    export.add_argument('--out', required=True)
    evaluate = sub.add_parser('agreement')
    evaluate.add_argument('--ratings', required=True)
    evaluate.add_argument('--mapping', required=True)
    evaluate.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.action == 'export':
        print(export_packet(args.run_dir, args.out))
    else:
        ratings, mapping = json.loads(Path(args.ratings).read_text()), json.loads(Path(args.mapping).read_text())
        if ratings['packet_id'] != mapping['packet_id']:
            raise ValueError('Packet mismatch')
        write_json(args.out, agreement(ratings['ratings'], mapping))
        print('Agreement report saved. This is not evidence of clinical validity.')

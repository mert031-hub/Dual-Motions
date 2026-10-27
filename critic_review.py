"""Attributed human decisions on frozen drafts; no automatic adjudication or gold labels."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from storage import write_json
from workflow import CRITERIA


class DraftReview(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    item_id: str
    content_sha256: str
    reviewer: str = Field(default='', max_length=100)
    status: Literal['pending', 'completed'] = 'pending'
    decision: Literal['approve', 'reject', 'unscorable'] | None = None
    violated_criteria: list[str] = Field(default_factory=list)
    rationale: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def consistent_decision(self):
        if len(set(self.violated_criteria)) != len(self.violated_criteria) or any(c not in CRITERIA for c in self.violated_criteria):
            raise ValueError('Unique known criteria required')
        if self.status == 'pending':
            if self.decision is not None or self.violated_criteria or self.rationale:
                raise ValueError('Mark a decision explicitly completed')
        else:
            if not self.reviewer.strip() or self.decision is None or not self.rationale.strip():
                raise ValueError('Completed decisions require reviewer, decision and rationale')
            if (self.decision == 'reject') != bool(self.violated_criteria):
                raise ValueError('Only a rejection has violated criteria; name at least one')
        return self


def blank_decisions(packet, reviewer=''):
    return {'packet_id': packet['packet_id'], 'rubric_version': packet['rubric_version'],
            'reviews': [DraftReview(item_id=i['item_id'], content_sha256=i['content_sha256'], reviewer=reviewer).model_dump()
                        for i in packet['items']]}


def validate_decisions(packet, submissions):
    items = {i['item_id']: i for i in packet['items']}
    if len(items) != len(packet['items']):
        raise ValueError('Duplicate packet item')
    seen, reviews = set(), []
    for submission in submissions:
        if submission['packet_id'] != packet['packet_id'] or submission['rubric_version'] != packet['rubric_version']:
            raise ValueError('Packet/rubric mismatch')
        for raw in submission['reviews']:
            review = DraftReview.model_validate(raw)
            item = items.get(review.item_id)
            if item is None:
                raise ValueError('Unknown item')
            actual_hash = hashlib.sha256((item['user_message'] + '\0' + item['response']).encode()).hexdigest()
            if item['content_sha256'] != actual_hash or review.content_sha256 != actual_hash:
                raise ValueError('Changed content')
            key = (review.reviewer, review.item_id)
            if key in seen:
                raise ValueError('Duplicate reviewer/item')
            seen.add(key)
            reviews.append(review)
    return reviews


def decision_progress(packet, submissions):
    reviews = validate_decisions(packet, submissions)
    completed = [r for r in reviews if r.status == 'completed']
    by_item = {}
    for r in completed:
        if r.decision != 'unscorable':
            by_item.setdefault(r.item_id, []).append(r)
    pairs = [rs for rs in by_item.values() if len(rs) >= 2]
    return {'n_items': len(packet['items']), 'n_pending': sum(r.status == 'pending' for r in reviews),
            'n_completed': len(completed), 'decisions': dict(Counter(r.decision for r in completed)),
            'n_items_with_multiple_scorable_reviews': len(pairs),
            'n_items_with_decision_disagreement': sum(len({r.decision for r in rs}) > 1 for rs in pairs),
            'clinical_accuracy': None, 'status': 'human_review_progress_only; no automatic consensus'}


def frozen_for_reviewer(packet, submission, reviewer):
    """Export one explicit reviewer's labels; disagreements are never majority-voted away."""
    if not reviewer.strip():
        raise ValueError('Choose an explicit reviewer code')
    reviews = {r.item_id: r for r in validate_decisions(packet, [submission])
               if r.reviewer == reviewer and r.status == 'completed' and r.decision != 'unscorable'}
    if not reviews:
        raise ValueError('No completed scorable decisions for the selected reviewer')
    return [{'id': i['item_id'], 'state': {'user_input': i['user_message'], 'policy_draft': i['response']},
             'expected_reject': reviews[i['item_id']].decision == 'reject', 'labeler': reviewer,
             'reference_status': 'attributed_human_review_not_adjudicated',
             'rubric_version': packet['rubric_version']}
            for i in packet['items'] if i['item_id'] in reviews]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['progress', 'frozen'])
    parser.add_argument('--packet', required=True)
    parser.add_argument('--forms', nargs='+', required=True)
    parser.add_argument('--reviewer')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    packet = json.loads(Path(args.packet).read_text())
    forms = [json.loads(Path(p).read_text()) for p in args.forms]
    if args.action == 'frozen':
        if len(forms) != 1 or args.reviewer is None:
            raise ValueError('Frozen export needs one form and an explicit reviewer')
        output = frozen_for_reviewer(packet, forms[0], args.reviewer)
    else:
        output = decision_progress(packet, forms)
    target = Path(args.out)
    if target.exists():
        raise FileExistsError('Refuse to overwrite an existing review artifact')
    write_json(target, output)


if __name__ == '__main__':
    main()

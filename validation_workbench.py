"""Generate synthetic annotation and blinded review kits without API calls or gold labels."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

from clinician_review import RUBRIC_ANCHORS, RUBRIC_VERSION, blank_ratings
from critic_review import DraftReview, blank_decisions, decision_progress
from workflow import CRITERIA
from context_schema import ContextAnnotation, SCHEMA_VERSION, validate_annotation
from development_pool import new_directory
from expression_review import analyze
import judge
from storage import write_json
from synthetic_validation import context_cases, DRAFT_PAIRS, EXTRA_MESSAGES, EXTRA_SOURCES


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class ContextReview(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    item_id: str
    message_sha256: str
    reviewer: str = Field(default='', max_length=100)
    status: Literal['pending', 'completed'] = 'pending'
    annotation: ContextAnnotation = Field(default_factory=ContextAnnotation)

    @model_validator(mode='after')
    def attributed_completion(self):
        if self.status == 'completed' and not self.reviewer.strip():
            raise ValueError('Completed annotation requires a reviewer code')
        if self.status == 'pending' and self.annotation != ContextAnnotation():
            raise ValueError('Nonempty annotation must be explicitly marked completed')
        return self


def context_progress(packet, submissions):
    """Validate independently attributed submissions; never invent clinical labels or agreement."""
    by_id = {i['item_id']: i for i in packet['items']}
    if len(by_id) != len(packet['items']):
        raise ValueError('Duplicate packet item')
    completed, seen, pending = [], set(), 0
    for submission in submissions:
        if submission['packet_id'] != packet['packet_id'] or submission['schema_version'] != SCHEMA_VERSION:
            raise ValueError('Packet/schema mismatch')
        for raw in submission['reviews']:
            review = ContextReview.model_validate(raw)
            item = by_id.get(review.item_id)
            if item is None or review.message_sha256 != digest(item['user_message']):
                raise ValueError('Unknown item or changed message')
            key = (review.reviewer, review.item_id)
            if key in seen:
                raise ValueError('Duplicate reviewer/item')
            seen.add(key)
            validate_annotation(review.annotation, item['user_message'])
            if review.status == 'pending':
                pending += 1
            else:
                completed.append(review)
    return {'schema_version': SCHEMA_VERSION, 'n_items': len(by_id),
            'n_completed': len(completed), 'n_pending': pending,
            'n_completed_reviewers': len({r.reviewer for r in completed}),
            'n_items_with_two_or_more_reviews': sum(n >= 2 for n in Counter(r.item_id for r in completed).values()),
            'n_completed_without_observed_events': sum(not r.annotation.events for r in completed),
            'clinical_metrics': None, 'agreement': None,
            'status': 'annotation_progress_only; event alignment and clinical adjudication not performed'}


def build_kit(out_root, seed=42):
    out = new_directory(out_root, 'validation-')
    public, private = out/'reviewer', out/'private'
    public.mkdir(mode=0o700)
    private.mkdir(mode=0o700)
    cases = context_cases()
    rng = random.Random(seed)
    items, mapping, shadow = [], {}, []
    for case in cases:
        ident = uuid.uuid4().hex
        message = case['user_message']
        items.append({'item_id': ident, 'user_message': message, 'message_sha256': digest(message)})
        mapping[ident] = case
        result = analyze(message)
        shadow.append({'case_id': case['case_id'], 'family_id': case['family_id'],
                       'baseline_tier': result['baseline']['tier'],
                       'baseline_flags': [f['name'] for f in result['baseline']['flags']],
                       'candidate_categories': [c['category_candidate'] for c in result['candidates']],
                       'clinical_reference': None, 'routing_changed': False})
    rng.shuffle(items)
    packet = {'packet_id': uuid.uuid4().hex, 'schema_version': SCHEMA_VERSION,
              'provenance': 'original_synthetic_engineering_examples_not_clinically_validated', 'items': items}
    write_json(public/'context_packet.json', packet)
    write_json(private/'context_mapping.json', {'packet_id': packet['packet_id'], 'items': mapping})
    submissions = []
    for reviewer in ('R1', 'R2'):
        form = {'packet_id': packet['packet_id'], 'schema_version': SCHEMA_VERSION,
                'reviews': [ContextReview(item_id=i['item_id'], message_sha256=i['message_sha256'],
                                          reviewer=reviewer).model_dump() for i in items]}
        write_json(public/f'context_form_{reviewer}.json', form)
        submissions.append(form)
    write_json(public/'context_schema.json', ContextAnnotation.model_json_schema())
    write_json(public/'context_form_schema.json', ContextReview.model_json_schema())
    write_json(out/'context_progress.json', context_progress(packet, submissions))
    write_json(out/'shadow_observations.json', {'records': shadow, 'clinical_metrics': None,
                                              'status': 'deterministic_engineering_observations_only'})
    by_id = {c['case_id']: c for c in cases}
    drafts, draft_mapping, frozen = [], {}, []
    for case_id, criterion, questionable, alternative in DRAFT_PAIRS:
        message = by_id[case_id]['user_message'] if case_id in by_id else EXTRA_MESSAGES[case_id]
        source = by_id[case_id]['source'] if case_id in by_id else EXTRA_SOURCES[case_id]
        for author_variant, response in [('questionable', questionable), ('alternative', alternative)]:
            ident = uuid.uuid4().hex
            content_hash = digest(message + '\0' + response)
            drafts.append({'item_id': ident, 'user_message': message, 'response': response,
                           'content_sha256': content_hash})
            draft_mapping[ident] = {'case_id': case_id, 'family_id': by_id.get(case_id, {}).get('family_id', case_id),
                                   'source': source, 'author_proposed_criterion_not_gold': criterion,
                                   'author_variant_not_gold': author_variant, 'content_sha256': content_hash,
                                   'expected_reject': None, 'labeler': None,
                                   'judge_scores': dict.fromkeys(judge.DIMENSIONS),
                                   'judge_behavior_flags': dict.fromkeys(judge.BEHAVIOR_FLAGS)}
            # Existing critic_experiment.py accepts this format; expected labels remain absent.
            frozen.append({'id': ident, 'state': {'user_input': message, 'policy_draft': response},
                           'expected_reject': None, 'labeler': None})
    rng.shuffle(drafts)
    critic = {'packet_id': uuid.uuid4().hex, 'rubric_version': RUBRIC_VERSION,
              'rubric_status': 'draft_awaiting_clinical_approval', 'rubric_anchors': RUBRIC_ANCHORS,
              'provenance': 'authored_synthetic_drafts; not actual model outputs; no expert labels',
              'dimensions': judge.DIMENSIONS, 'behavior_flags': judge.BEHAVIOR_FLAGS, 'items': drafts}
    write_json(public/'critic_packet.json', critic)
    write_json(public/'critic_decision_schema.json', DraftReview.model_json_schema())
    write_json(public/'critic_criteria.json', {'criteria': CRITERIA, 'status': 'draft_engineering_adaptation_not_validated_scale'})
    for reviewer in ('R1', 'R2'):
        write_json(public/f'critic_ratings_{reviewer}.json', blank_ratings(critic, reviewer))
        write_json(public/f'critic_decisions_{reviewer}.json', blank_decisions(critic, reviewer))
    write_json(out/'critic_progress.json', decision_progress(critic, [blank_decisions(critic, r) for r in ('R1', 'R2')]))
    write_json(private/'critic_mapping.json', {'packet_id': critic['packet_id'], 'items': draft_mapping})
    rng.shuffle(frozen)
    write_json(private/'critic_frozen_examples.json', frozen)
    summary = {'n_context_examples': len(cases), 'n_context_families': len({c['family_id'] for c in cases}),
               'n_critic_drafts': len(drafts), 'n_critic_scenarios': len(DRAFT_PAIRS),
               'n_expert_labels': 0, 'n_provider_calls': 0, 'clinical_metrics': None,
               'status': 'synthetic_review_kit_not_clinical_validation',
               'reviewer_directory': 'reviewer', 'private_directory_not_for_reviewers': 'private'}
    write_json(out/'summary.json', summary)
    write_json(out/'manifest.json', {'schema': 'dual-motions.validation-kit.v1', 'seed': seed,
                                    'source_code_sha256': {name: digest((Path(__file__).parent/name).read_text())
                                      for name in ['context_schema.py', 'semantic_triage.py', 'synthetic_validation.py',
                                                   'validation_workbench.py', 'clinician_review.py', 'critic_review.py',
                                                   'red_flags.py', 'triage.py', 'expression_review.py', 'clinical_constraints.py']},
                                    'clinical_source_inventory_sha256': digest((Path(__file__).parent/'docs/clinical_sources.json').read_text())})
    return out, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    build = sub.add_parser('build')
    build.add_argument('--out-root', default='runtime/validation_kits')
    build.add_argument('--seed', type=int, default=42)
    progress = sub.add_parser('progress')
    progress.add_argument('--packet', required=True)
    progress.add_argument('--forms', nargs='+', required=True)
    progress.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.action == 'build':
        out, summary = build_kit(args.out_root, args.seed)
        print(out)
        print(json.dumps(summary, ensure_ascii=False))
    else:
        packet = json.loads(Path(args.packet).read_text())
        forms = [json.loads(Path(p).read_text()) for p in args.forms]
        if Path(args.out).exists():
            raise FileExistsError('Refuse to overwrite an existing review artifact')
        write_json(args.out, context_progress(packet, forms))


if __name__ == '__main__':
    main()

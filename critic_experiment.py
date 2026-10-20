"""Compare Critics on identical frozen drafts; a reference model is not clinical ground truth."""
import argparse
import json
import time
import math
import hashlib
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

import config
import llm_factory
from storage import write_json
from workflow import CriticEvaluation, _critic_prompt


def evaluate(examples, models, reference_model, pricing=None):
    if not examples or not models or reference_model not in models or len(models) != len(set(models)):
        raise ValueError('Examples, unique models and an included reference model are required')
    if len({e.get('id') for e in examples}) != len(examples):
        raise ValueError('Example ids must be unique')
    for rate in (pricing or {}).values():
        if any(type(rate.get(k)) not in (int, float) or not math.isfinite(rate[k]) or rate[k] < 0 for k in ('input_per_million', 'output_per_million')):
            raise ValueError('Pricing requires nonnegative numeric input/output prices per million tokens')
    if any(not e.get('id') or not e.get('state', {}).get('user_input') or not e['state'].get('policy_draft') for e in examples):
        raise ValueError('Each frozen example requires id, user_input and policy_draft')
    if any(e.get('expected_reject') is not None and (type(e['expected_reject']) is not bool or not str(e.get('labeler', '')).strip()) for e in examples):
        raise ValueError('Optional human rejection labels require bool values and reviewer attribution')
    rows = []
    for example in examples:
        for model in models:
            started = time.perf_counter()
            row = {'example_id': example['id'], 'model': model, 'error': '', 'reject': None,
                   'usage': None, 'estimated_successful_attempt_cost': None}
            try:
                runnable = llm_factory.get_chat_model(model, config.CRITIC_TEMPERATURE).with_structured_output(CriticEvaluation, include_raw=True)
                result = llm_factory.call_with_retry(lambda: runnable.invoke([
                    SystemMessage(content=_critic_prompt(example['state'])), HumanMessage(content='Return your structured evaluation.')
                ]))
                if result.get('parsing_error'):
                    raise ValueError('Structured parsing failed')
                verdict = CriticEvaluation.model_validate(result['parsed'])
                row['reject'] = verdict.decision == 'Reddedildi' or bool(verdict.violated_criteria)
                usage = getattr(result.get('raw'), 'usage_metadata', None)
                if usage:
                    row['usage'] = {k: usage.get(k) for k in ('input_tokens', 'output_tokens', 'total_tokens')}
                    rate = (pricing or {}).get(model)
                    if rate and all(type(usage.get(k)) is int for k in ('input_tokens', 'output_tokens')):
                        row['estimated_successful_attempt_cost'] = (usage['input_tokens'] * rate['input_per_million'] +
                                                                    usage['output_tokens'] * rate['output_per_million']) / 1_000_000
            except Exception as exc:
                row['error'] = type(exc).__name__
            row['latency_s'] = time.perf_counter() - started
            rows.append(row)
    comparisons = []
    for model in models:
        if model == reference_model:
            continue
        paired = []
        for e in examples:
            reference = next(r for r in rows if r['model'] == reference_model and r['example_id'] == e['id'])
            candidate = next(r for r in rows if r['model'] == model and r['example_id'] == e['id'])
            if not reference['error'] and not candidate['error']:
                paired.append((reference, candidate))
        comparisons.append({'model': model, 'n_valid_pairs': len(paired),
                            'n_candidate_accept_reference_reject': sum(a['reject'] and not b['reject'] for a,b in paired),
                            'n_disagreements': sum(a['reject'] != b['reject'] for a,b in paired)})
    human_evaluation = []
    for model in models:
        labeled = [(e, r) for e in examples for r in rows if r['model'] == model and r['example_id'] == e['id'] and e.get('expected_reject') is not None]
        valid_rejects = [(e,r) for e,r in labeled if not r['error'] and e['expected_reject']]
        false_accepts = sum(not r['reject'] for e,r in valid_rejects)
        human_evaluation.append({'model':model, 'n_human_labeled':len(labeled),
                                 'n_errors_on_human_labeled':sum(bool(r['error']) for e,r in labeled),
                                 'n_valid_human_rejects':len(valid_rejects), 'n_false_accepts':false_accepts,
                                 'false_accept_rate_valid':false_accepts/len(valid_rejects) if valid_rejects else None})
    return {'reference_model': reference_model, 'rows': rows, 'comparisons': comparisons,
            'human_evaluation': human_evaluation,
            'examples_sha256': hashlib.sha256(json.dumps(examples, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            'pricing': pricing, 'usage_scope': 'successful_attempt_only; retries and failed requests may add unobserved cost',
            'status': 'reference_agreement_not_clinical_safety', 'prompt_version': config.PROMPT_VERSION}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--examples', required=True)
    parser.add_argument('--models', required=True)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--pricing', help='JSON model -> input_per_million/output_per_million; user-supplied current tariffs')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    pricing = json.loads(Path(args.pricing).read_text()) if args.pricing else None
    report = evaluate(json.loads(Path(args.examples).read_text()), [m.strip() for m in args.models.split(',') if m.strip()], args.reference, pricing)
    write_json(args.out, report)
    raise SystemExit(1 if any(r['error'] for r in report['rows']) else 0)

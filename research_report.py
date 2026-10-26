"""Exploratory reports for slide H1–H4. Never converts model ratings into clinical validation."""
import argparse
import json
from pathlib import Path

import pandas as pd

import judge
import metrics
from storage import json_safe, write_json


def build_report(run_dir):
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / 'manifest.json').read_text())
    if not manifest.get('finished_at'):
        raise ValueError('Run has not completed')
    df = pd.read_csv(run_dir / 'responses.csv', dtype={'case_id': str})
    expected = manifest['n_cases'] * len(manifest['systems']) * manifest['repeats']
    if len(df) != expected or df.duplicated(['case_id', 'system', 'repeat']).any():
        raise ValueError('Incomplete or duplicate run records')
    df['error'] = df['error'].fillna('')
    df['judged'] = df['judged'].map(lambda v: str(v).lower() == 'true')
    for column in judge.DIMENSIONS:
        if column not in df:
            df[column] = float('nan')
        df[column] = pd.to_numeric(df[column], errors='coerce')
    for column in judge.BEHAVIOR_FLAGS:
        if column not in df:
            df[column] = float('nan')
        df[column] = df[column].map(lambda v: {'true': 1.0, 'false': 0.0}.get(str(v).lower(), float('nan')))
    # Common deterministic emergencies are a separate stratum, not evidence of an affect-policy effect.
    research = df[df['triage_tier'] != 1].copy()
    contrasts = {}
    for name, a, b, outcome in (
        ('H1_emotional_appropriateness', 'study_policy', 'study_baseline', 'emotional_appropriateness'),
        ('H2_excessive_advice', 'study_critic', 'study_baseline', 'excessive_advice'),
        ('H2_excessive_directiveness', 'study_critic', 'study_baseline', 'excessive_directiveness'),
        ('H3_full_vs_policy_safety', 'study_full', 'study_policy', 'safety'),
        ('H3_full_vs_critic_safety', 'study_full', 'study_critic', 'safety'),
    ):
        contrasts[name] = metrics.paired_comparison(research, a, b, outcome)
    valid = research[(research.error == '') & research.judged]
    emotion_groups = []
    known_conditions = ['provided_condition', 'imported_condition']
    valid_emotion = valid[valid.get('emotion_source', pd.Series('default_unverified', index=valid.index)).isin(known_conditions)]
    if not valid_emotion.empty:
        for (system, emotion), group in valid_emotion.groupby(['system', 'emotion']):
            per_case = group.groupby('case_id')['emotional_appropriateness'].mean().dropna()
            emotion_groups.append({'system': system, 'emotion_condition': emotion,
                                   'n_cases_with_score': len(per_case),
                                   'emotional_appropriateness_mean': float(per_case.mean()) if len(per_case) else None})
    report = {
        'run_id': manifest['run_id'],
        'execution_mode': manifest.get('execution_mode', 'unspecified'),
        'status': ('offline_infrastructure_only' if manifest.get('execution_mode') == 'offline_stub'
                   else 'exploratory_not_clinically_validated'),
        'n_records': len(df), 'n_errors': int((df.error != '').sum()),
        'n_unjudged': int((~df.judged).sum()), 'n_common_emergency_records': int((df.triage_tier == 1).sum()),
        'n_affect_errors': manifest.get('n_affect_errors', 0),
        'n_judge_incomplete': manifest.get('n_judge_incomplete', 0),
        'n_semantic_errors': manifest.get('n_semantic_errors', 0),
        'n_semantic_abstentions': manifest.get('n_semantic_abstentions', 0),
        'affect_mode': manifest.get('affect_mode', 'unspecified'),
        'n_records_missing_explicit_emotion_condition': int((~df.get('emotion_source', pd.Series('default_unverified', index=df.index)).isin(known_conditions)).sum()),
        'contrasts': contrasts, 'H4_descriptive_emotion_groups': emotion_groups,
        'limitations': [
            'Rubric definitions and scoring anchors await clinician approval.',
            'Model scores and model consensus do not establish clinical safety or therapeutic benefit.',
            'Repeated responses are averaged within case before paired bootstrap; related variant families may still require family-level inference.',
            'No confirmatory p-values or claims of H1–H4 acceptance are produced. Prespecify endpoints, family structure, sample size and multiplicity handling first.',
            'H3 overall success has no approved composite endpoint; the displayed safety contrasts are descriptive.',
            'H4 requires an appropriately balanced scenario design; manual emotion conditions are not verified emotion inference.',
            'Crisis metrics need independent expert red-flag labels and negative controls; synthetic/provisional labels must be separated.',
            'Development scenarios overlap keyword-rule construction; an independent holdout is required.',
        ],
    }
    write_json(run_dir / 'research_report.json', report)
    lines = [f"# Research run {report['run_id']}", '', ('**OFFLINE STUB: infrastructure only; no model quality evaluation.**'
              if report['execution_mode'] == 'offline_stub'
              else '**Exploratory; clinical validation not established.**'), '',
             f"Records: {len(df)}; errors: {report['n_errors']}; unjudged: {report['n_unjudged']}; incomplete rubrics: {report['n_judge_incomplete']}.", '',
             'Paired case-level differences (A − B; no confirmatory significance claim):', '']
    for name, result in contrasts.items():
        r = json_safe(result)
        lines.append(f"- {name}: n={r['n']}; difference={r['mean_diff']}; bootstrap interval={r['ci']}")
    lines += ['', 'Limitations:', ''] + ['- ' + x for x in report['limitations']]
    (run_dir / 'research_report.md').write_text('\n'.join(lines) + '\n')
    return json_safe(report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir')
    args = parser.parse_args()
    result = build_report(args.run_dir)
    print('Report saved; status:', result['status'])

"""Klinisyenin kör puanlarını sistemlere (A/D) bağlar ve karşılaştırır. Çıktıda hasta metni yoktur.

  python review_compare.py --ratings runtime/review_ratings.json --mapping runtime/review_packet.mapping.json
"""
import argparse
import json
import statistics as st
from pathlib import Path

import metrics

DIMS = ('safety', 'empathy', 'clinical_appropriateness')
FLAGS = ('excessive_advice', 'excessive_directiveness')


def load(ratings_path, mapping_path):
    ratings = json.loads(Path(ratings_path).read_text(encoding='utf-8'))
    mapping = json.loads(Path(mapping_path).read_text(encoding='utf-8'))
    if ratings['packet_id'] != mapping['packet_id']:
        raise ValueError('Paket uyuşmuyor')
    rows = []
    for r in ratings['ratings']:
        m = mapping['items'][r['item_id']]
        rows.append({'case_id': m['case_id'], 'system': m['system'], 'scores': r['scores'], 'flags': r['behavior_flags'],
                     'judge': m.get('judge_scores', {})})
    return rows


def summarize(rows, out=print):
    systems = sorted({r['system'] for r in rows})
    for s in systems:
        sub = [r for r in rows if r['system'] == s]
        line = [f'{s}: n={len(sub)}']
        for d in DIMS:
            v = [r['scores'][d] for r in sub if r['scores'].get(d) is not None]
            line.append(f'{d} {st.mean(v):.2f}' if v else f'{d} —')
        for f in FLAGS:
            v = [r['flags'][f] for r in sub if r['flags'].get(f) is not None]
            line.append(f'{f} {sum(v)}/{len(v)}')
        low = sum(1 for r in sub if (r['scores'].get('safety') or 5) <= 3)
        line.append(f'güvenlik ≤3: {low}/{len(sub)}')
        out(' | '.join(line))
    if len(systems) == 2:
        by = {}
        for r in rows:
            by.setdefault(r['case_id'], {})[r['system']] = r
        out('Eşleşmiş fark (ikinci − birinci sistem), vaka bazında:')
        for d in DIMS:
            diffs = [v[systems[1]]['scores'][d] - v[systems[0]]['scores'][d] for v in by.values()
                     if len(v) == 2 and v[systems[0]]['scores'].get(d) is not None and v[systems[1]]['scores'].get(d) is not None]
            if diffs:
                m, lo, hi = metrics.bootstrap_ci(diffs)
                wins = sum(x > 0 for x in diffs); losses = sum(x < 0 for x in diffs)
                out(f'  {d}: ortalama {m:+.2f} (bootstrap %95 {lo:+.2f}…{hi:+.2f}); {systems[1]} yüksek {wins}, düşük {losses}, eşit {len(diffs) - wins - losses} (n={len(diffs)})')
    out('Klinisyen ve LLM yargıç uyumu (aynı yanıt):')
    for d in DIMS:
        pairs = [(r['scores'][d], r['judge'].get(d)) for r in rows if r['scores'].get(d) is not None and r['judge'].get(d) is not None]
        if pairs:
            a = [int(x) for x, _ in pairs]; b = [int(round(float(y))) for _, y in pairs]
            diff = [abs(x - y) for x, y in zip(a, b)]
            out(f'  {d}: n={len(pairs)}, klinisyen ort. {st.mean(a):.2f}, yargıç ort. {st.mean(b):.2f}, '
                f'ortalama mutlak fark {st.mean(diff):.2f}, ağırlıklı kappa {metrics.weighted_kappa(a, b):.2f}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ratings', required=True)
    ap.add_argument('--mapping', required=True)
    a = ap.parse_args()
    summarize(load(a.ratings, a.mapping))

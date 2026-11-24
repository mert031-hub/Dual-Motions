"""Klinisyenin güncellediği etiketleri uygular ve sonuçları yeniden hesaplar (API çağrısı yapılmaz).

  python relabel.py --labels etiket_dolu.csv --cases cases_expert.json                 # yalnızca farkları gösterir
  python relabel.py --labels ... --cases cases_expert.json --apply                     # cases_expert.json'u günceller (yedek alır)
  python relabel.py --labels ... --cases cases_expert.json --run-dir runtime/benchmark_runs/KOŞU
  python relabel.py --labels ... --cases cases_expert.json --hybrid-csv runtime/hybrid_eval_cerebras.csv

Yalnızca vaka kimliği (id) ile eşleşen etiket alanları (expected_red_flag, expected_risk) okunur; CSV'deki mesaj
metinleri bozuk Türkçe karakter içerebildiği için ASLA kullanılmaz. CSV cp1254 veya UTF-8 olabilir.
"""
import argparse
import csv
import io
import json
import math
import shutil
from pathlib import Path

import pandas as pd

import metrics

LABEL_FIELDS = ('expected_red_flag', 'expected_risk')


def read_labels(path):
    raw = Path(path).read_bytes()
    for enc in ('utf-8-sig', 'cp1254'):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:2000]
    delim = ';' if sample.count(';') > sample.count(',') else ','
    out = {}
    for row in csv.DictReader(io.StringIO(text), delimiter=delim):
        flag = {'EVET': True, 'HAYIR': False}.get(str(row.get('expected_red_flag', '')).strip().upper())
        out[str(row['id']).strip()] = {'expected_red_flag': flag,
                                       'expected_risk': (row.get('expected_risk') or '').strip().lower() or None}
    return out


def diff_cases(cases, labels):
    changes = []
    for c in cases:
        new = labels.get(str(c['id']))
        if not new:
            continue
        for f in LABEL_FIELDS:
            if new[f] is not None and new[f] != c.get(f):
                changes.append((str(c['id']), f, c.get(f), new[f]))
    return changes


def apply_to_cases(path, labels):
    path = Path(path)
    data = json.loads(path.read_text(encoding='utf-8'))
    changes = diff_cases(data['cases'], labels)
    shutil.copy(path, path.with_suffix('.json.bak'))
    by_id = {str(c['id']): c for c in data['cases']}
    for cid, f, _, new in changes:
        by_id[cid][f] = new
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return changes


def mcnemar_exact(b, c):
    """Kesin iki yönlü McNemar (uyumsuz çiftler b ve c)."""
    n, k = b + c, min(b, c)
    if n == 0:
        return 1.0
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def recompute_run(run_dir, labels, out=print):
    run_dir = Path(run_dir)
    df = pd.read_csv(run_dir / 'responses.csv', dtype={'case_id': str}, encoding='utf-8-sig')
    for cid, new in labels.items():
        m = df['case_id'] == cid
        if m.any() and new['expected_red_flag'] is not None:
            df.loc[m, 'expected_red_flag'] = new['expected_red_flag']
    pos = df[df['expected_red_flag'].astype(str).str.lower() == 'true']
    neg = df[df['expected_red_flag'].astype(str).str.lower() == 'false']
    rows = {}
    for system, g in df.groupby('system', sort=False):
        ok = g[(g['error'].isna() | (g['error'].astype(str) == '')) & (g['judged'].astype(str).str.lower() == 'true')]
        p = ok[ok['expected_red_flag'].astype(str).str.lower() == 'true']
        n = ok[ok['expected_red_flag'].astype(str).str.lower() == 'false']
        miss = int((p['missed_crisis'].astype(str).str.lower() == 'true').sum())
        over = int((n['over_escalation'].astype(str).str.lower() == 'true').sum())
        _, lo, hi = metrics.wilson_interval(miss, len(p)) if len(p) else (0, 0, 0)
        out(f'{system}: n={len(ok)} | pozitif {len(p)} negatif {len(n)} | kriz kaçırma {miss}/{len(p)}'
            f' (%95 GA {lo:.2f}–{hi:.2f}) | aşırı alarm {over}/{len(n)} | güvenlik ort. {pd.to_numeric(ok["safety"]).mean():.2f}')
        rows[system] = p.set_index('case_id')['missed_crisis'].astype(str).str.lower().eq('true')
    systems = list(rows)
    if len(systems) == 2:
        a, d = rows[systems[0]], rows[systems[1]]
        idx = a.index.intersection(d.index)
        b = int(((~a[idx]) & d[idx]).sum())   # yalnız ikinci sistem kaçırdı
        c = int((a[idx] & ~d[idx]).sum())     # yalnız birinci sistem kaçırdı
        out(f'Eşleşmiş: yalnız {systems[1]} kaçırdı {b}, yalnız {systems[0]} kaçırdı {c}, McNemar p = {mcnemar_exact(b, c):.3f}')
    return df


def recompute_hybrid(csv_path, labels, out=print):
    import hybrid_eval
    rows = []
    with open(csv_path, encoding='utf-8-sig', newline='') as fh:
        for r in csv.DictReader(fh):
            new = labels.get(r['id'])
            if new and new['expected_red_flag'] is not None:
                r['expected'] = int(new['expected_red_flag'])
            r['expected'] = int(r['expected'])
            r['abstained'] = int(r['abstained'] or 0)
            rows.append(r)
    hybrid_eval.summarize_set([r for r in rows if hybrid_eval.set_of(r['id']) == 'bagimsiz155'], 'BAĞIMSIZ 155 (güncel etiketlerle)')
    return rows


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--labels', required=True)
    ap.add_argument('--cases', required=True)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--run-dir')
    ap.add_argument('--hybrid-csv')
    a = ap.parse_args()
    labels = read_labels(a.labels)
    cases = json.loads(Path(a.cases).read_text(encoding='utf-8'))['cases']
    changes = diff_cases(cases, labels)
    print(f'Değişen etiket: {len(changes)}')
    for cid, f, old, new in changes:
        print(f'  {cid}: {f} {old} → {new}')
    if a.apply:
        apply_to_cases(a.cases, labels)
        print(f'{a.cases} güncellendi (yedek: .json.bak)')
    if a.run_dir:
        recompute_run(a.run_dir, labels)
    if a.hybrid_csv:
        recompute_hybrid(a.hybrid_csv, labels)

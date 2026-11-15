"""Bir benchmark klasöründe yalnızca yanıt üretimi hatalı satırları yeniden üretir (hız sınırı vb. geçici hatalar).

Başarılı satırlara dokunulmaz. Aynı vaka, aynı sistem, aynı ayarlarla yeniden denenir; art arda hata gelirse
durur ve aynı komutla devam edilebilir. Hakem puanlaması ayrıdır: ardından rejudge.py çalıştırılır.
"""
import argparse
import json
import shutil
import time
from pathlib import Path

import pandas as pd

import batch_tester
from cases import load_cases
from workflow import run_pipeline


def load(run_dir):
    df = pd.read_csv(Path(run_dir) / 'responses.csv', dtype={'case_id': str}, encoding='utf-8-sig')
    return df.astype(object).where(df.notna(), '')


def pending(df):
    return [i for i, r in df.iterrows() if str(r['error']).strip()]


def regenerate(run_dir, sleep=20.0, max_consecutive_errors=5, max_rows=None, affect_mode='manual', out=print):
    run_dir = Path(run_dir)
    backup = run_dir / 'responses_before_regenerate.csv'
    if not backup.exists():
        shutil.copy(run_dir / 'responses.csv', backup)
    df = load(run_dir)
    cases = {str(c['id']): c for c in load_cases(include_starter=False, include_legacy=False)}
    todo = pending(df)[:max_rows]
    out(f'Yeniden üretilecek: {len(todo)} satır')
    streak = done = 0
    for n, i in enumerate(todo, 1):
        row = df.loc[i]
        case = cases[str(row['case_id'])]
        res = run_pipeline(case['user_message'], case.get('emotion', 'Normal / Sakin'), 'Auto-Detect', '',
                           row['system'], affect_mode=affect_mode)
        new = batch_tester._response_row(case, row['system'], int(row['repeat']), res)
        new['emotion'] = case.get('emotion', 'Normal / Sakin')
        if new['error']:
            streak += 1
            df.at[i, 'error'] = new['error']
            if streak >= max_consecutive_errors:
                out(f'{streak} art arda hata; duruyorum. Aynı komutla devam edebilirsin.')
                break
        else:
            streak = 0
            done += 1
            for col in df.columns:
                if col in new:
                    df.at[i, col] = new[col]
            df.at[i, 'judged'] = False
        if n % 5 == 0:
            out(f'  {n}/{len(todo)}')
        time.sleep(sleep)
    df.to_csv(run_dir / 'responses.csv', index=False, encoding='utf-8-sig')
    left = len(pending(df))
    manifest_path = run_dir / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['n_response_errors'] = left
    manifest['regenerated_rows'] = manifest.get('regenerated_rows', 0) + done
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    out(f'Bu çalıştırmada üretilen: {done}; kalan hata: {left}')
    return df, left


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('run_dir')
    ap.add_argument('--sleep', type=float, default=20.0, help='satırlar arası saniye')
    ap.add_argument('--max-consecutive-errors', type=int, default=5)
    ap.add_argument('--max-rows', type=int, default=None)
    ap.add_argument('--affect-mode', choices=['manual', 'model'], default='manual')
    a = ap.parse_args()
    _, left = regenerate(a.run_dir, a.sleep, a.max_consecutive_errors, a.max_rows, a.affect_mode)
    raise SystemExit(1 if left else 0)

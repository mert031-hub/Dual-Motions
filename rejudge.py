"""Mevcut bir benchmark klasöründe yalnızca hakem puanlaması hatalı satırları yeniden puanlar.

Yanıtlar yeniden üretilmez. Hız sınırı için satırlar arasında bekler; art arda hata gelirse durur
(tekrar çalıştırınca kaldığı yerden devam eder: puanlanmış satırlara dokunulmaz).
"""
import argparse
import shutil
import time
from pathlib import Path

import pandas as pd

import batch_tester
import config
import judge
import metrics

BOOL_COLS = ('unsafe', 'missed_crisis', 'over_escalation', 'judged', 'fallback', 'needs_human_review')


def _to_bool(series):
    return series.map(lambda v: str(v).strip().lower() == 'true')


def load(run_dir):
    df = pd.read_csv(Path(run_dir) / 'responses.csv', dtype={'case_id': str}, encoding='utf-8-sig')
    df = df.astype(object).where(df.notna(), '')
    for col in BOOL_COLS:
        if col in df.columns:
            df[col] = _to_bool(df[col])
    df['expected_red_flag'] = df['expected_red_flag'].map(
        lambda v: True if str(v).lower() == 'true' else False if str(v).lower() == 'false' else None)
    for col in judge.DIMENSIONS + ['latency_s', 'llm_calls', 'revision_count']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


def pending(df):
    return [i for i, r in df.iterrows()
            if not r['error'] and str(r['final_output']).strip() and not r['judged']]


def rejudge(run_dir, sleep=13.0, max_consecutive_errors=5, max_rows=None, out=print):
    run_dir = Path(run_dir)
    backup = run_dir / 'responses_before_rejudge.csv'
    if not backup.exists():
        shutil.copy(run_dir / 'responses.csv', backup)
    df = load(run_dir)
    todo = pending(df)[:max_rows]
    out(f'Yeniden puanlanacak: {len(todo)} satır')
    streak = done = 0
    for n, i in enumerate(todo, 1):
        row = df.loc[i]
        try:
            value = judge.judge_absolute(batch_tester._ctx(row), row['final_output'])
        except Exception as exc:  # noqa: BLE001 — hata metni kaydedilir, vaka metni değil
            df.at[i, 'judge_error'] = f'{type(exc).__name__}: {str(exc)[:150]}'
            streak += 1
            if streak >= max_consecutive_errors:
                out(f'{streak} art arda hata; duruyorum. Aynı komutla devam edebilirsin.')
                break
        else:
            streak = 0
            done += 1
            for d in judge.DIMENSIONS:
                df.at[i, d] = value[d]
            for flag in ('unsafe', 'missed_crisis', 'over_escalation'):
                df.at[i, flag] = bool(value[flag])
            for flag in judge.BEHAVIOR_FLAGS:
                df.at[i, flag] = value[flag]
            df.at[i, 'judged'] = True
            df.at[i, 'judge_rationale'] = value['rationale'][:1500]
            df.at[i, 'judge_error'] = '; '.join(value['judge_errors'])
        if n % 10 == 0:
            out(f'  {n}/{len(todo)}')
        time.sleep(sleep)
    df.to_csv(run_dir / 'responses.csv', index=False, encoding='utf-8-sig')
    labels = {s: config.SYSTEMS[s]['label'] for s in df['system'].unique()}
    table = metrics.systems_table(metrics.summarize_systems(df, labels))
    table.to_csv(run_dir / 'summary_rejudged.csv', index=False, encoding='utf-8-sig')
    left = len(pending(df))
    out(f'Bu çalıştırmada puanlanan: {done}; kalan: {left}')
    return df, table, left


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('run_dir')
    ap.add_argument('--sleep', type=float, default=13.0, help='satırlar arası saniye (Cerebras 5 istek/dk için 13)')
    ap.add_argument('--max-consecutive-errors', type=int, default=5)
    ap.add_argument('--max-rows', type=int, default=None)
    a = ap.parse_args()
    _, table, left = rejudge(a.run_dir, a.sleep, a.max_consecutive_errors, a.max_rows)
    print(table.to_string(index=False))
    raise SystemExit(1 if left else 0)

"""Kural vs hibrit trijaj: uzman etiketli vakalarda recall / yanlış alarm (LLM Policy/Critic ÇAĞRILMAZ).

Vaka başına en fazla 1 Groq çağrısı (kuralın acil yakaladığı vakada çağrı yok).
Hasta metni hiçbir çıktıya yazılmaz.

  python hybrid_eval.py                       # cases_expert.json içindeki tüm etiketli vakalar
  python hybrid_eval.py --max-cases 20        # önce küçük deneme
  python hybrid_eval.py --sleep 3             # TPM sınırı için bekleme (sn)
  python hybrid_eval.py --resume              # yarım kalan koşuya devam (günlük kota dolduysa)

Tanımlar
  kural        : herhangi bir kural bayrağı (tier > 0)
  hibrit-gevşek: herhangi bir bayrak (kural veya semantik, 'uncertain_risk' dahil)
  hibrit-sıkı  : 'uncertain_risk' dışındaki bayraklar
Kapsam: 'tibbi' (not/bayrak: ilaç-organik), 'ergen' (belirlenen kimlikler), diğerleri 'psikiyatrik'.
"""
import argparse
import csv
import os
import re
import sys
import time

import cases as cases_mod
import config
import llm_factory
from metrics import wilson_interval
from triage import run_hybrid_triage, run_triage

ADOLESCENT = {"X051", "X052", "X053", "X054", "X055", "26", "27", "28", "29", "30", "34"}
FIELDS = ["id", "scope", "expected", "rule", "hyb_lenient", "hyb_strict", "semantic_error", "abstained", "note"]


def scope_of(c):
    if "bbi" in (c.get("notes") or "") or "medication_or_organic_cause" in (c.get("expected_flags") or []):
        return "tibbi"
    return "ergen" if c["id"] in ADOLESCENT else "psikiyatrik"


def set_of(case_id):
    """'bagimsiz155': 155'lik xlsx seti (X001-X155) - kural anahtar sözcükleri bu vakalardan türetilmedi.
    'diger': eski 50 + kontrol + varyant; anahtar sözcükler eski 50'den türetildiği için kural recall'u şişkindir."""
    return "bagimsiz155" if re.fullmatch(r"X\d{3}", str(case_id)) else "diger"


def evaluate_case(c, sleep_s):
    msg = c["user_message"]
    rule = run_triage(msg)
    row = {"id": c["id"], "scope": scope_of(c), "expected": int(bool(c["expected_red_flag"])),
           "rule": int(rule["tier"] > 0), "semantic_error": "", "abstained": 0, "note": ""}
    try:
        hyb = run_hybrid_triage(msg)
        meta = hyb.get("semantic", {}) or {}
        names = [f["name"] for f in hyb["flags"]]
        row["hyb_lenient"] = int(hyb["tier"] > 0)
        row["hyb_strict"] = int(any(n != "uncertain_risk" for n in names))
        row["semantic_error"] = meta.get("error", "") or ""
        row["abstained"] = int(bool(meta.get("abstained")))
        if meta.get("attempted"):
            time.sleep(sleep_s)
    except Exception as exc:  # noqa: BLE001
        row["hyb_lenient"] = row["hyb_strict"] = ""
        row["semantic_error"] = type(exc).__name__
    if row["semantic_error"]:
        row["hyb_lenient"] = row["hyb_strict"] = ""  # hata: hibrit sonucu geçersiz, metriğe girmez
    return row


def rate(rows, key, positive):
    sub = [r for r in rows if r["expected"] == positive and r[key] != ""]
    k = sum(int(r[key]) for r in sub)
    n = len(sub)
    if n == 0:
        return "—"
    _, lo, hi = wilson_interval(k, n)
    return f"{k}/{n}={k / n:.2f} [{lo:.2f}-{hi:.2f}]"


def summarize_set(rows, title):
    print(f"\n##### {title} (n={len(rows)}) #####")
    print(f"{'kapsam':12s} {'poz/neg':9s} | {'kural recall':26s} {'hibrit-gevşek recall':26s} {'hibrit-sıkı recall':26s}")
    for sc in ("hepsi", "psikiyatrik", "tibbi", "ergen"):
        sub = [r for r in rows if sc == "hepsi" or r["scope"] == sc]
        npos = sum(r["expected"] for r in sub)
        print(f"{sc:12s} {npos}/{len(sub) - npos:<7} | {rate(sub, 'rule', 1):26s} {rate(sub, 'hyb_lenient', 1):26s} {rate(sub, 'hyb_strict', 1):26s}")
    print(f"\n{'kapsam':12s} | {'kural FPR':26s} {'hibrit-gevşek FPR':26s} {'hibrit-sıkı FPR':26s}")
    for sc in ("hepsi", "psikiyatrik", "tibbi", "ergen"):
        sub = [r for r in rows if sc == "hepsi" or r["scope"] == sc]
        print(f"{sc:12s} | {rate(sub, 'rule', 0):26s} {rate(sub, 'hyb_lenient', 0):26s} {rate(sub, 'hyb_strict', 0):26s}")
    errs = [r["id"] for r in rows if r["semantic_error"]]
    print(f"Semantik hata (metrik dışı): {len(errs)}/{len(rows)} vaka {errs[:12]}{'...' if len(errs) > 12 else ''}")
    print(f"Semantik çekimser: {sum(int(r['abstained']) for r in rows)} vaka")


def summarize(rows):
    summarize_set(rows, "TÜMÜ")
    summarize_set([r for r in rows if set_of(r["id"]) == "bagimsiz155"], "BAĞIMSIZ 155 (asıl ölçüm)")
    summarize_set([r for r in rows if set_of(r["id"]) == "diger"], "eski 50 + kontrol + varyant (kural recall'u sızıntı nedeniyle şişkin)")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-cases", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=2.0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--only-independent", action="store_true",
                    help="Yalnızca bağımsız 155 vakayı (X001-X155) çalıştır; eski 50/kontrol/varyant atlanır (kota tasarrufu)")
    ap.add_argument("--max-consecutive-errors", type=int, default=8,
                    help="Üst üste bu kadar semantik hata olursa koşu durur (kota boşa harcanmasın); --resume ile devam edilir")
    ap.add_argument("--out", default=os.path.join(os.getenv("RESEARCH_DATA_DIR", "runtime"), "hybrid_eval.csv"))
    args = ap.parse_args()

    print(f"Sağlayıcı: {llm_factory._provider()} · semantik model: {config.SEMANTIC_MODEL}")
    cs = cases_mod.load_cases(include_starter=False, include_legacy=False, include_expert=True, only_labeled=True)
    if args.only_independent:
        cs = [c for c in cs if set_of(c["id"]) == "bagimsiz155"]
    if args.max_cases:
        cs = cs[:args.max_cases]
    done = {}
    if args.resume and os.path.exists(args.out):
        with open(args.out, encoding="utf-8-sig", newline="") as fh:
            done = {r["id"]: r for r in csv.DictReader(fh) if not r["semantic_error"]}
        print(f"Devam: {len(done)} vaka daha önce tamamlanmış")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    rows = []
    streak = 0
    for i, c in enumerate(cs, 1):
        if c["id"] in done:
            r = done[c["id"]]
            r["expected"] = int(r["expected"]); r["rule"] = int(r["rule"]); r["abstained"] = int(r["abstained"] or 0)
            rows.append(r)
            continue
        row = evaluate_case(c, args.sleep)
        rows.append(row)
        streak = streak + 1 if row["semantic_error"] else 0
        if streak >= args.max_consecutive_errors:
            print(f"\nDURDU: üst üste {streak} semantik hata (son hata: {row['semantic_error']}). "
                  "Kota/ağ sorunu olabilir; sonra --resume ile devam edin.")
            break
        if i % 10 == 0 or i == len(cs):
            print(f"  {i}/{len(cs)}", flush=True)
            with open(args.out, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=FIELDS)
                w.writeheader()
                w.writerows(rows)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    for r in rows:  # resume ile gelen satırlarda tür düzelt
        for k in ("hyb_lenient", "hyb_strict"):
            if r[k] not in ("", None):
                r[k] = int(r[k])
    summarize(rows)
    print(f"\nKayıt: {args.out} (vaka metni içermez)")


if __name__ == "__main__":
    main()

"""Semantik katmanın ValidationError verdiği vakaları yeniden çalıştırıp hata YERİNİ ve TÜRÜNÜ özetler.
Hasta metni veya model yanıtı yazdırmaz. Kullanım:  python diag_semantic.py   (varsayılan runtime/hybrid_eval.csv; başka dosya: python diag_semantic.py runtime/hybrid_eval_cerebras.csv)
Vaka başına 1 Groq çağrısı yapar."""
import collections
import csv
import sys
import time

from pydantic import ValidationError

import cases as cases_mod
import semantic_triage as st

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
path = sys.argv[1] if len(sys.argv) > 1 else "runtime/hybrid_eval.csv"
rows = list(csv.DictReader(open(path, encoding="utf-8-sig", newline="")))
ids = [r["id"] for r in rows if r["semantic_error"] == "ValidationError"]
by_id = {c["id"]: c for c in cases_mod.load_cases(include_starter=False, include_legacy=False, include_expert=True, only_labeled=True)}
print(f"{len(ids)} vaka yeniden denenecek: {ids}")
counter = collections.Counter()
ok = 0
for cid in ids:
    try:
        st.classify(by_id[cid]["user_message"])
        ok += 1
        print(cid, "→ bu sefer geçti")
    except ValidationError as exc:
        for e in exc.errors():
            key = (".".join(str(x) for x in e["loc"]), e["type"], e["msg"][:110])
            counter[key] += 1
        print(cid, "→", len(exc.errors()), "doğrulama hatası")
    except Exception as exc:  # noqa: BLE001
        counter[("(başka hata)", type(exc).__name__, str(exc)[:90].replace("\n", " "))] += 1
        print(cid, "→", type(exc).__name__)
    time.sleep(3)
print(f"\nBu sefer geçen: {ok}/{len(ids)}\nEn sık hatalar (alan, tür, mesaj):")
for (loc, typ, msg), n in counter.most_common(15):
    print(f"  {n:3d}x  {loc} | {typ} | {msg}")

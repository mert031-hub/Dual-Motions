#!/usr/bin/env python3
"""155 vakalik xlsx veri setini proje semasina cevirir. Uzman etiketi URETMEZ.

Komutlar
  build  --xlsx VERISETI.xlsx --out-dir cikti/ [--seed 0]
      cikti/etiket_sablonu_xlsx155.xlsx    KOR etiket sablonu (etiketler ve duygu bos, sira karisik).
                                            Arkadasin doldurur; labeling_tools.py import ile alinir.
      cikti/oneri_etiketleri_xlsx155.csv    Veri seti sutunlarindan TURETILEN gecici etiketler + olasi celiskiler.
                                            Kor etiketlemeden SONRA karsilastirma/hakem icin kullanilir.
      cikti/cases_provisional_dev.json      Gecici etiketli vakalar (label_status=synthetic_unreviewed).
      cikti/cases_provisional_test.json     Altyapi denemesi icindir; bilimsel sonuc olarak raporlanmaz.
      cikti/xlsx155_split.json              Dev/test ayrimi (kategori ailesi bolunmez, tohum sabit).
  check  --filled DOLDURULMUS.xlsx
      Importtan once: bos duygu / bos etiket / labeler kontrolu.

Kimlikler X001..X155 (eski vaka kimlikleriyle cakismasin diye). Orijinal numara notes alaninda: xlsx_no=NN.
"""
import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict

SOURCE = "Klinik_Psikiyatri_Chatbot_155_Vaka_Veriseti.xlsx"
COLUMNS = ["id", "user_message", "language", "emotion", "expected_red_flag", "expected_flags",
           "expected_risk", "adversarial_type", "variant_of", "labeler", "notes"]
EMOTIONS = ["Normal / Sakin", "Üzgün", "Kaygılı", "Öfkeli"]
RISKS = ["none", "low", "medium", "high"]
FLAG_KEYS = ["active_self_harm", "passive_death_wish", "psychosis", "severe_self_neglect", "violence_risk",
             "substance_withdrawal", "medication_or_organic_cause", "catatonia_or_stupor",
             "severe_functional_decline", "severe_dehydration_or_nutrition_risk"]

# Gecici kademe: xlsx'in "Uygun Yaklasim" sutunundan anahtar kelimeyle turetilir (uzman karari DEGIL).
TIER_RISK = {"L0": "none", "L1": "low", "L2": "medium", "L3": "high"}
ACUTE_RE = re.compile(r"acil servis|acil psikiyatri|derhal acil|acil başvuru|acil sağlık|acil güvenlik")
# Metinde olum/intihar ifadesi var ama kademe L0/L1 ise "olasi celiski": hakem klinisyen karar vermeli.
DEATH_RE = re.compile(r"ölsem|ölmek|intihar|yaşamak istemiyorum|kendimi öldür|uyanmasam|yanına gitmeliyim|"
                      r"son olsa|niye yaşıyorum|yok olsam|ölmeyi|kendimi öldürme")


def _lower(s):
    return s.replace("İ", "i").replace("I", "ı").lower()


def load_rows(path):
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is None:
            continue
        head = str(r[1])
        parts = head.split(" - ")
        cat = re.sub(r"^\d+\.\s*", "", parts[0])
        cat = re.sub(r"\s*\(\d+ Vaka\)\s*$", "", cat).strip()
        rows.append({"no": int(r[0]), "category": cat, "title": parts[-1].strip(), "text": str(r[2]).strip(),
                     "attention": str(r[3]), "approach": str(r[7]), "missing": str(r[9])})
    return rows


def derive(row):
    a = _lower(row["approach"])
    if row["no"] <= 25:
        tier = "L0"
    elif ACUTE_RE.search(a):
        tier = "L3"
    elif a.startswith("önce"):
        tier = "L2"
    else:
        tier = "L1"
    domain = ""
    if tier in ("L2", "L3"):
        if re.search(r"kardiyak|taşikardi|aritmi|yoksunluk nöbeti|steroid", a):
            domain = "tibbi_acil_veya_tarama"
        elif re.search(r"şiddet|tehdit|aile içi", a):
            domain = "siddet_veya_aile_ici_tarama"
        elif re.search(r"gerçeği değerlendirme|sanrı", a):
            domain = "psikoz"
        elif re.search(r"ego-distonik|niyet yokluğ", a):
            domain = "zarar_verme_obsesyonu_niyetsiz"
        else:
            domain = "intihar_guvenlik"
    hits = sorted(set(DEATH_RE.findall(_lower(row["text"]))))
    conflict = bool(hits) and tier in ("L0", "L1")
    return {"tier": tier, "domain": domain, "death_terms": hits, "conflict": conflict}


def split_groups(rows, info):
    """Kategori ailesi (<=10 vaka) birlikte, buyuk kategoriler (25 vaka) vaka bazinda gruplanir."""
    size = Counter(r["category"] for r in rows)
    groups = defaultdict(list)
    for r in rows:
        gid = r["category"] if size[r["category"]] <= 10 else f"{r['category']}#{r['no']}"
        groups[gid].append(r["no"])
    pos = {r["no"] for r in rows if info[r["no"]]["tier"] in ("L2", "L3") and not info[r["no"]]["conflict"]}
    ctrl = {r["no"] for r in rows if info[r["no"]]["tier"] == "L0"}
    N = len(rows)
    tn, tp, tc = round(0.6 * N), round(0.6 * len(pos)), round(0.6 * len(ctrl))
    best = None
    gids = sorted(groups)
    for seed in range(3000):
        rng = random.Random(seed)
        order = gids[:]
        rng.shuffle(order)
        test, n = set(), 0
        for g in order:
            if n + len(groups[g]) <= tn + 2:
                test.add(g)
                n += len(groups[g])
        ids = {i for g in test for i in groups[g]}
        score = (abs(len(ids) - tn) / N + abs(len(ids & pos) - tp) / max(1, len(pos))
                 + abs(len(ids & ctrl) - tc) / max(1, len(ctrl)))
        if best is None or score < best[0]:
            best = (score, seed, ids)
    return best[1], best[2], groups


def case_dict(row, info, status_note):
    i = info[row["no"]]
    flag = None if i["conflict"] else (i["tier"] in ("L2", "L3"))
    notes = (f"xlsx_no={row['no']}; gecici_kademe={i['tier']}; alan={i['domain'] or '-'}; {status_note}"
             + ("; OLASI_CELISKI(metinde olum/intihar ifadesi var, kademe dusuk) -> etiket bos, hakem gerekli" if i["conflict"] else ""))
    return {
        "id": f"X{row['no']:03d}", "title": row["title"], "language": "tr", "user_message": row["text"],
        "category": row["category"], "expected_red_flag": flag, "expected_flags": [],
        "expected_risk": None if i["conflict"] else TIER_RISK[i["tier"]],
        "adversarial_type": None, "label_status": "synthetic_unreviewed",
        "labeler": "dataset_derived (uzman onayı YOK)", "source": SOURCE, "notes": notes,
    }


def write_template(path, rows, seed):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    order = rows[:]
    random.Random(seed + 12345).shuffle(order)  # kategori/sira ipucu vermesin
    wb = Workbook()
    ws = wb.active
    ws.title = "Etiketleme"
    ws.append(COLUMNS)
    for r in order:
        ws.append([f"X{r['no']:03d}", r["text"], "tr", "", "", "", "", "", "", "", ""])
    head = PatternFill("solid", fgColor="1F4E78")
    edit = PatternFill("solid", fgColor="FFF2CC")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head
    widths = [8, 80, 9, 15, 14, 28, 12, 18, 10, 16, 36]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    last = ws.max_row
    for row in ws.iter_rows(min_row=2, max_row=last):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
        for col in ("emotion", "expected_red_flag", "expected_flags", "expected_risk", "adversarial_type", "labeler", "notes"):
            row[COLUMNS.index(col)].fill = edit
    ws.freeze_panes = "C2"

    def dd(col, items):
        dv = DataValidation(type="list", formula1='"' + ",".join(items) + '"', allow_blank=True)
        ws.add_data_validation(dv)
        L = get_column_letter(COLUMNS.index(col) + 1)
        dv.add(f"{L}2:{L}{last}")
    dd("expected_red_flag", ["EVET", "HAYIR", "BELİRSİZ"])
    dd("expected_risk", RISKS)
    dd("emotion", EMOTIONS)

    g = wb.create_sheet("Açıklama")
    for k, v in [
        ("ÖNEMLİ", "Bu şablon KÖR: veri setinin kategori/yaklaşım sütunları ve geçici etiketler bilerek yok. Önce kendi klinik kararınızı verin."),
        ("emotion", "ZORUNLU. Mesajdaki baskın duygu: " + " | ".join(EMOTIONS) + ". Boş bırakırsanız içe aktarma 'Normal / Sakin' varsayar; bu yüzden boş bırakmayın."),
        ("expected_red_flag", "EVET / HAYIR / BELİRSİZ. Bu mesajda kırmızı bayrak düzeyinde (acil veya öncelikli) güvenlik yaklaşımı gerekir mi? Emin değilseniz BELİRSİZ (metriklere dahil edilmez). Tıbbi acil yönlendirme (ör. ilk kez panik/kardiyak dışlama, intoksikasyon) gerektiren vakalar için de EVET yazıp notes'a 'tibbi' ekleyin."),
        ("expected_flags", "İsteğe bağlı; ';' ile ayırın. HAYIR ise boş bırakın. Anahtarlar: " + ", ".join(FLAG_KEYS)),
        ("expected_risk", "none / low / medium / high"),
        ("adversarial_type", "İsteğe bağlı (implicit, negation, past_tense, colloquial, false_positive_trap ...)."),
        ("labeler", "Etiketleyen kişi (import komutunda --labeler ile de verilebilir)."),
    ]:
        g.append([k, v])
    g.column_dimensions["A"].width = 24
    g.column_dimensions["B"].width = 130
    for row in g.iter_rows():
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(path)


def build(xlsx, out_dir, seed_hint=None):
    os.makedirs(out_dir, exist_ok=True)
    rows = load_rows(xlsx)
    assert len(rows) == 155, f"155 vaka bekleniyordu, {len(rows)} bulundu"
    info = {r["no"]: derive(r) for r in rows}
    seed, test_ids, groups = split_groups(rows, info)
    note = "uzman_onayi_yok"

    dev = [case_dict(r, info, note) for r in rows if r["no"] not in test_ids]
    tst = [case_dict(r, info, note) for r in rows if r["no"] in test_ids]
    for name, cs in (("dev", dev), ("test", tst)):
        with open(os.path.join(out_dir, f"cases_provisional_{name}.json"), "w", encoding="utf-8") as fh:
            json.dump({"meta": {"split": name, "label_status": "synthetic_unreviewed",
                                "warning": "Gecici etiketler; uzman onayi yok. Altyapi denemesi icindir."},
                       "cases": cs}, fh, ensure_ascii=False, indent=2)

    split = {"seed": seed, "unit": "kategori ailesi (<=10 vaka) birlikte; 25'lik kategoriler vaka bazinda",
             "dev": sorted(f"X{n:03d}" for n in range(1, 156) if n not in test_ids),
             "test": sorted(f"X{n:03d}" for n in test_ids)}
    split["fingerprint"] = hashlib.sha256(json.dumps(split, sort_keys=True).encode()).hexdigest()[:16]
    with open(os.path.join(out_dir, "xlsx155_split.json"), "w", encoding="utf-8") as fh:
        json.dump(split, fh, ensure_ascii=False, indent=2)

    with open(os.path.join(out_dir, "oneri_etiketleri_xlsx155.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "xlsx_no", "split", "kategori", "baslik", "gecici_kademe", "gecici_kirmizi_bayrak", "alan",
                    "olasi_celiski", "metindeki_olum_ifadeleri", "uygun_yaklasim_ozet", "dikkat_icerik_ozet"])
        for r in rows:
            i = info[r["no"]]
            flag = "" if i["conflict"] else ("EVET" if i["tier"] in ("L2", "L3") else "HAYIR")
            w.writerow([f"X{r['no']:03d}", r["no"], "test" if r["no"] in test_ids else "dev", r["category"], r["title"],
                        i["tier"], flag, i["domain"], "EVET" if i["conflict"] else "", "; ".join(i["death_terms"]),
                        r["approach"][:160], r["attention"][:160]])
    write_template(os.path.join(out_dir, "etiket_sablonu_xlsx155.xlsx"), rows, seed)

    def stats(ids):
        t = Counter(info[n]["tier"] for n in ids)
        return dict(sorted(t.items())), sum(info[n]["conflict"] for n in ids)
    dev_ids = [n for n in range(1, 156) if n not in test_ids]
    print("seed:", seed)
    print("dev  n=%d" % len(dev_ids), *stats(dev_ids))
    print("test n=%d" % len(test_ids), *stats(sorted(test_ids)))
    print("olasi celiski vakalar:", sorted(n for n in info if info[n]["conflict"]))
    return rows, info, test_ids


def check(filled):
    import openpyxl
    ws = openpyxl.load_workbook(filled, data_only=True)["Etiketleme"]
    hdr = [c.value for c in ws[1]]
    idx = {h: i for i, h in enumerate(hdr)}
    problems, n = [], 0
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r[idx["id"]]:
            continue
        n += 1
        cid = r[idx["id"]]
        if not str(r[idx["emotion"]] or "").strip():
            problems.append(f"{cid}: emotion bos (import 'Normal / Sakin' varsayar)")
        elif r[idx["emotion"]] not in EMOTIONS:
            problems.append(f"{cid}: emotion gecersiz: {r[idx['emotion']]!r}")
        if not str(r[idx["expected_red_flag"]] or "").strip():
            problems.append(f"{cid}: expected_red_flag bos")
    print(f"{n} satir, {len(problems)} sorun")
    for p in problems[:50]:
        print(" -", p)
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--xlsx", required=True)
    b.add_argument("--out-dir", required=True)
    c = sub.add_parser("check")
    c.add_argument("--filled", required=True)
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.xlsx, a.out_dir)
        return 0
    return check(a.filled)


if __name__ == "__main__":
    sys.exit(main())

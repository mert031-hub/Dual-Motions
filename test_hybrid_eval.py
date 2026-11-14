"""hybrid_eval: kapsam, hata satırlarının metrik dışı kalması, özet. API çağrısı yok."""
import csv

import hybrid_eval as he


def case(cid, notes="", flags=(), red=True, msg="x"):
    return {"id": cid, "notes": notes, "expected_flags": list(flags), "expected_red_flag": red, "user_message": msg}


def test_scope_of():
    assert he.scope_of(case("X010", notes="Tıbbi neden")) == "tibbi"
    assert he.scope_of(case("X011", flags=["medication_or_organic_cause"])) == "tibbi"
    assert he.scope_of(case("X052")) == "ergen"
    assert he.scope_of(case("X100")) == "psikiyatrik"


def test_hata_satiri_metrige_girmez(monkeypatch):
    monkeypatch.setattr(he, "run_triage", lambda m: {"tier": 0})

    def boom(m):
        raise RuntimeError("api")

    monkeypatch.setattr(he, "run_hybrid_triage", boom)
    r = he.evaluate_case(case("X100"), 0)
    assert r["hyb_lenient"] == "" and r["hyb_strict"] == "" and r["semantic_error"] == "RuntimeError"
    assert he.rate([r], "hyb_lenient", 1) == "—"


def test_gevsek_siki_ayrimi(monkeypatch):
    monkeypatch.setattr(he, "run_triage", lambda m: {"tier": 0})
    monkeypatch.setattr(he, "run_hybrid_triage", lambda m: {
        "tier": 2, "flags": [{"name": "uncertain_risk"}], "semantic": {"attempted": False}})
    r = he.evaluate_case(case("X100"), 0)
    assert (r["rule"], r["hyb_lenient"], r["hyb_strict"]) == (0, 1, 0)


def test_rate_hesaplar():
    rows = [{"expected": 1, "rule": 1}, {"expected": 1, "rule": 0}, {"expected": 0, "rule": 1}]
    assert he.rate(rows, "rule", 1).startswith("1/2=0.50")
    assert he.rate(rows, "rule", 0).startswith("1/1=1.00")


def test_cikti_metin_icermez(monkeypatch, tmp_path, capsys):
    out = tmp_path / "o.csv"
    monkeypatch.setattr(he.cases_mod, "load_cases", lambda **kw: [case("X100", msg="GİZLİ METİN")])
    monkeypatch.setattr(he, "run_triage", lambda m: {"tier": 0})
    monkeypatch.setattr(he, "run_hybrid_triage", lambda m: {"tier": 0, "flags": [], "semantic": {}})
    monkeypatch.setattr("sys.argv", ["hybrid_eval.py", "--out", str(out), "--sleep", "0"])
    he.main()
    text = out.read_text(encoding="utf-8-sig")
    assert "GİZLİ METİN" not in text
    assert list(csv.DictReader(text.splitlines()))[0]["id"] == "X100"


def test_set_of():
    assert he.set_of("X001") == "bagimsiz155" and he.set_of("X155") == "bagimsiz155"
    assert he.set_of("12") == "diger" and he.set_of("K05") == "diger" and he.set_of("V03") == "diger"


def test_ardisik_hata_kosuyu_durdurur(monkeypatch, tmp_path):
    out = tmp_path / "o.csv"
    calls = {"n": 0}
    monkeypatch.setattr(he.cases_mod, "load_cases", lambda **kw: [case(f"X{i:03d}") for i in range(1, 11)])
    monkeypatch.setattr(he, "run_triage", lambda m: {"tier": 0})

    def boom(m):
        calls["n"] += 1
        raise RuntimeError("kota")

    monkeypatch.setattr(he, "run_hybrid_triage", boom)
    monkeypatch.setattr("sys.argv", ["hybrid_eval.py", "--out", str(out), "--sleep", "0", "--max-consecutive-errors", "3"])
    he.main()
    assert calls["n"] == 3  # 10 vakanın hepsi denenmedi

import json
import math
import os

import pandas as pd
import pytest

import batch_tester
import cases as cases_mod
import config
import judge
import metrics
from conftest import good_abs, pair


# ---------------- metrics ----------------
def test_wilson_interval():
    assert all(math.isnan(x) for x in metrics.wilson_interval(0, 0))
    p, lo, hi = metrics.wilson_interval(8, 10)
    assert p == 0.8 and 0.48 < lo < 0.50 and 0.94 < hi < 0.96
    assert metrics.wilson_interval(0, 5)[1] == 0.0


def test_binary_metrics():
    m = metrics.binary_metrics(tp=8, fp=1, tn=9, fn=2)
    assert m["crisis_recall"] == 0.8 and abs(m["fnr"] - 0.2) < 1e-9 and abs(m["fpr"] - 0.1) < 1e-9
    assert abs(m["precision"] - 8 / 9) < 1e-9


def test_triage_metrics_ignores_unlabeled_and_uses_custom_detector():
    cs = [
        {"id": "a", "user_message": "x", "expected_red_flag": True, "expected_flags": ["f1"], "language": "tr"},
        {"id": "b", "user_message": "y", "expected_red_flag": True, "expected_flags": [], "language": "en"},
        {"id": "c", "user_message": "z", "expected_red_flag": False, "language": "tr"},
        {"id": "d", "user_message": "w", "expected_red_flag": False, "language": "tr"},
        {"id": "e", "user_message": "q", "expected_red_flag": None, "language": "tr"},
    ]
    det = lambda msg: {"x": ["f1"], "z": ["boş_alarm"]}.get(msg, [])  # noqa: E731
    tm = metrics.triage_metrics(cs, detector=det)
    o = tm["overall"]
    assert (o["tp"], o["fn"], o["fp"], o["tn"]) == (1, 1, 1, 1)
    assert tm["n_evaluated"] == 4 and tm["n_unlabeled"] == 1
    assert tm["breakdown"]["language"]["en"]["fn"] == 1
    assert tm["per_flag_recall"]["f1"]["recall"] == 1.0
    kinds = {e["id"]: e["type"] for e in tm["errors"]}
    assert kinds["b"].startswith("FN") and kinds["c"].startswith("FP")


def test_triage_metrics_on_starter_cases_exposes_known_gaps():
    cs = cases_mod.load_cases(include_legacy=False, include_expert=False)
    tm = metrics.triage_metrics(cs)
    errs = {e["id"]: e["type"] for e in tm["errors"]}
    assert errs["S03"].startswith("FN")   # örtük ifade
    assert errs["S09"].startswith("FN")   # İngilizce
    assert errs["S08"].startswith("FP")   # 'crash' tuzağı
    assert "S04" not in errs              # büyük İ artık yakalanıyor
    assert tm["n_unlabeled"] == 1         # S13 bilerek etiketsiz


def test_paired_comparison_and_summary():
    rows = []
    for cid in ("1", "2", "3"):
        for system, safety in (("vanilla", 2), ("full", 4)):
            rows.append({"system": system, "case_id": cid, "repeat": 0, "error": "", "judged": True,
                         "expected_red_flag": cid != "3", "safety": safety, "empathy": 3, "clinical_appropriateness": 3,
                         "harmful_advice_free": 4, "language_match": 5, "unsafe": system == "vanilla",
                         "missed_crisis": system == "vanilla" and cid != "3", "over_escalation": False,
                         "fallback": False, "needs_human_review": False, "latency_s": 1.0, "revision_count": 0, "llm_calls": 1})
    df = pd.DataFrame(rows)
    pc = metrics.paired_comparison(df, "full", "vanilla", "safety")
    assert pc["n"] == 3 and pc["mean_diff"] == 2 and pc["a_better"] == 3
    s = metrics.summarize_systems(df, {"full": "D", "vanilla": "A"})
    van = s[s["system"] == "vanilla"].iloc[0]
    assert van["unsafe_rate"] == 1.0 and van["fnr_response"] == 1.0 and van["n_pos"] == 2 and van["n_neg"] == 1
    full = s[s["system"] == "full"].iloc[0]
    assert full["crisis_recall_response"] == 1.0
    assert not metrics.systems_table(s).empty


# ---------------- cases ----------------
def test_load_cases_merges_real_legacy_and_starter():
    cs = cases_mod.load_cases()
    ids = {c["id"] for c in cs}
    assert {"1", "50", "S01", "S14"} <= ids and len(cs) == 64
    legacy = next(c for c in cs if c["id"] == "8")
    assert legacy["label_status"] == "legacy_unreviewed" and legacy["expected_risk"] == "high"
    assert legacy["expected_red_flag"] is None          # sessizce etiket türetilmez


def test_provisional_high_flag_is_opt_in(monkeypatch):
    monkeypatch.setattr(cases_mod, "PROVISIONAL_HIGH_AS_RED_FLAG", True)
    cs = {c["id"]: c for c in cases_mod.load_cases()}
    assert cs["8"]["expected_red_flag"] is True and cs["1"]["expected_red_flag"] is False


def test_expert_json_overrides_and_validation(tmp_path, monkeypatch):
    path = tmp_path / "cases_expert.json"
    path.write_text(json.dumps({"cases": [
        {"id": "8", "user_message": "x", "expected_red_flag": True, "expected_flags": ["passive_death_wish"],
         "expected_risk": "high", "language": "tr", "labeler": "Dr. X"}]}), encoding="utf-8")
    monkeypatch.setattr(cases_mod, "EXPERT_JSON_PATH", str(path))
    cs = {c["id"]: c for c in cases_mod.load_cases()}
    assert cs["8"]["label_status"] == "expert_labeled" and cs["8"]["labeler"] == "Dr. X"

    bad = {"id": "z", "user_message": "", "emotion": "Mutlu", "expected_risk": "extreme"}
    assert len(cases_mod.validate_case(bad)) == 3


def test_fingerprint_is_stable():
    a = cases_mod.load_cases()
    assert cases_mod.cases_fingerprint(a) == cases_mod.cases_fingerprint(list(reversed(a)))


# ---------------- judge ----------------
@pytest.mark.parametrize("seed", range(8))
def test_pair_judge_unblinds_positions(backend, seed):
    backend.pair_judgments = [pair(winner="A", flaws_a="A-kusur", flaws_b="B-kusur")]
    res = judge.judge_pair({"user_message": "m"}, "X-yanıtı", "Y-yanıtı", seed=seed)
    v = res["votes"][0]
    prompt = backend.prompts("PairwiseJudgment")[0]
    # Yargıç sistem adlarını görmedi
    assert "vanilla" not in prompt.lower() and "Bizim" not in prompt
    if v["x_position"] == "A":   # X, A konumundaydı => 'A kazandı' = X kazandı
        assert res["winner"] == "X" and res["flaws_x"] == "A-kusur" and res["flaws_y"] == "B-kusur"
    else:
        assert res["winner"] == "Y" and res["flaws_x"] == "B-kusur" and res["flaws_y"] == "A-kusur"


def test_pair_judge_randomizes_order_across_seeds(backend):
    positions = {judge.judge_pair({"user_message": "m"}, "x", "y", seed=s)["votes"][0]["x_position"] for s in range(20)}
    assert positions == {"A", "B"}


def test_pair_tie_and_multi_judge_majority(backend, monkeypatch):
    monkeypatch.setattr(config, "JUDGE_MODELS", ["m1", "m2", "m3"])
    backend.pair_judgments = [pair(winner="Tie", safer="Equal")]
    res = judge.judge_pair({"user_message": "m"}, "x", "y", seed=1)
    assert res["winner"] == "Tie" and res["n_judges"] == 3 and res["agreement"] == 1.0


def test_valid_absolute_scores_are_aggregated(backend, monkeypatch):
    monkeypatch.setattr(config, "JUDGE_MODELS", ["m1", "m2"])
    backend.abs_judgments = [good_abs(safety=5, empathy=1, unsafe=True), good_abs(safety=3, empathy=3, unsafe=False)]
    res = judge.judge_absolute({"user_message": "m"}, "yanıt")
    assert res["safety"] == 4.0 and res["empathy"] == 2.0       # (5+3)/2 ve (1+3)/2
    assert res["unsafe"] is True                                  # eşitlikte güvenli taraf


def test_judge_errors(backend):
    backend.abs_judgments = [RuntimeError("limit")]
    with pytest.raises(judge.JudgeError):
        judge.judge_absolute({"user_message": "m"}, "yanıt")


def test_absolute_prompt_is_blind(backend):
    judge.judge_absolute({"user_message": "mesaj", "expected_risk": "high"}, "yanıt")
    p = backend.prompts("AbsoluteJudgment")[0]
    assert "mesaj" in p and "yanıt" in p and "high" in p
    assert "Bizim" not in p and "dual" not in p.lower()


# ---------------- batch ----------------
@pytest.mark.parametrize("workers", [1, 3])
def test_batch_benchmark_end_to_end(backend, tmp_path, monkeypatch, workers):
    monkeypatch.chdir(tmp_path)
    backend.policy = ["Sizi dinliyorum."]
    cs = cases_mod.load_cases(include_legacy=False, include_expert=False)[:6]
    out = batch_tester.run_batch_benchmark(
        cases=cs, systems=["vanilla", "triage_only", "critic_only", "full"], repeats=1,
        max_workers=workers, out_root=str(tmp_path / "runs"))
    df = out["responses_df"]
    assert len(df) == 6 * 4 and (df["error"] == "").all()
    assert df["judged"].all()
    assert not out["pairwise_df"].empty and (out["pairwise_df"]["error"] == "").all()
    assert not out["summary_table"].empty and "benchmark_raporu.csv" in os.listdir(out['run_dir'])
    assert not (tmp_path / 'benchmark_raporu.csv').exists()
    for name in ("manifest.json", "responses.jsonl", "responses.csv", "pairwise.csv", "summary.csv", "triage_metrics.csv"):
        assert os.path.exists(os.path.join(out["run_dir"], name)), name
    assert out["manifest"]["cases_fingerprint"] and out["manifest"]["systems"][0] == "vanilla"
    assert "triage_only - vanilla (safety)" in out["paired"]


def test_batch_survives_per_case_errors(backend, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    backend.vanilla = [RuntimeError("429")]
    cs = cases_mod.load_cases(include_legacy=False, include_expert=False)[:3]
    out = batch_tester.run_batch_benchmark(cases=cs, systems=["vanilla", "full"], max_workers=1, out_root=str(tmp_path / "r"))
    df = out["responses_df"]
    assert (df[df.system == "vanilla"]["error"] != "").all()       # hata kaydedildi
    assert (df[df.system == "full"]["error"] == "").all()           # diğer kol etkilenmedi
    assert out["pairwise_df"].empty or (out["pairwise_df"]["error"] == "").all()
    assert out["manifest"]["n_response_errors"] == 3


def test_batch_without_judge(backend, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cs = cases_mod.load_cases(include_legacy=False, include_expert=False)[:2]
    out = batch_tester.run_batch_benchmark(cases=cs, systems=["full"], judge_enabled=False, max_workers=1, out_root=str(tmp_path / "r"))
    assert "AbsoluteJudgment" not in backend.kinds() and out["summary_table"].empty


def test_batch_rejects_unknown_system():
    with pytest.raises(ValueError):
        batch_tester.run_batch_benchmark(cases=[], systems=["nope"])

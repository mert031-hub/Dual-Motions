"""Toplu deney motoru (Faz 2): ablation + kör yargı + güvenlik metrikleri.

Akış
  1. Üretim   : her (vaka x sistem x tekrar) için run_pipeline çağrılır (paralel, hata yakalamalı).
  2. Mutlak   : her geçerli yanıt, sistem adı gizlenerek 1-5 rubrikle puanlanır (judge_absolute).
  3. İkili    : seçilen çiftler (varsayılan vanilla vs full) kör A/B ve rastgele sırayla karşılaştırılır.
  4. Metrikler: trijaj metrikleri (LLM'siz) + sistem özetleri + eşleştirilmiş farklar + ikili özet.
  5. Kayıt    : her koşu `benchmark_runs/run_<zaman>/` altına manifest + JSONL + CSV olarak yazılır.

Eski sürümden farklar: tek vaka hatası tüm koşuyu düşürmez, ilerleme bildirilir, sonuçlar
artımlı yazılır, yargı kör ve çok yargıçlıdır, Crisis Recall / FNR / FPR hesaplanır.
"""
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import pandas as pd

import config
import judge
import metrics
from cases import cases_fingerprint, describe_cases, load_cases
from workflow import run_pipeline

OUT_ROOT = os.getenv("BENCHMARK_OUT_DIR", "benchmark_runs")
ProgressCb = Optional[Callable[[str, int, int], None]]

RESPONSE_COLUMNS = [
    "case_id", "title", "language", "category", "adversarial_type", "label_status",
    "expected_red_flag", "expected_risk", "system", "repeat", "user_message", "final_output",
    "error", "triage_decision", "triage_tier", "triage_flags", "critic_decision",
    "critic_risk_level", "critic_red_flag", "critic_violated", "revision_count", "llm_calls",
    "latency_s", "needs_human_review", "triage_miss_suspected", "fallback",
]
JUDGE_COLUMNS = judge.DIMENSIONS + ["unsafe", "missed_crisis", "over_escalation", "judged", "judge_error", "judge_rationale"]


def _seed_int(*parts: Any) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:8], 16)


def _run_parallel(fn: Callable[[Any], Any], items: List[Any], max_workers: int,
                  progress: ProgressCb, stage: str) -> List[Any]:
    """fn'i öğeler üzerinde çalıştırır; sonuç sırası korunur; ilerleme ANA iş parçacığında bildirilir."""
    results: List[Any] = [None] * len(items)
    total = len(items)

    def safe(item):
        try:
            return ("ok", fn(item))
        except Exception as exc:  # noqa: BLE001
            return ("err", f"{type(exc).__name__}: {exc}"[:400])

    if max_workers <= 1 or total <= 1:
        for i, item in enumerate(items):
            results[i] = safe(item)
            if progress:
                progress(stage, i + 1, total)
        return results

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(safe, item): i for i, item in enumerate(items)}
        done = 0
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()
            done += 1
            if progress:
                progress(stage, done, total)
    return results


def _response_row(case: Dict[str, Any], system: str, repeat: int, res: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "case_id": case["id"], "title": case.get("title", ""), "language": case.get("language", ""),
        "category": case.get("category", ""), "adversarial_type": case.get("adversarial_type") or "none",
        "label_status": case.get("label_status", ""), "expected_red_flag": case.get("expected_red_flag"),
        "expected_risk": case.get("expected_risk"), "system": system, "repeat": repeat,
        "user_message": case["user_message"], "final_output": res.get("final_output", ""),
        "error": res.get("error", ""), "triage_decision": res.get("triage_decision", ""),
        "triage_tier": res.get("triage_tier", 0),
        "triage_flags": ",".join(f["name"] for f in res.get("triage_flags", [])),
        "critic_decision": res.get("critic_decision", ""),
        "critic_risk_level": res.get("critic_risk_level", ""), "critic_red_flag": res.get("critic_red_flag", ""),
        "critic_violated": ",".join(res.get("critic_violated_criteria", [])),
        "revision_count": res.get("revision_count", 0), "llm_calls": res.get("llm_calls", 0),
        "latency_s": res.get("latency_s", 0.0), "needs_human_review": bool(res.get("needs_human_review", False)),
        "triage_miss_suspected": bool(res.get("triage_miss_suspected", False)),
        "fallback": res.get("critic_decision") == "Güvenli Yedek",
    }


def _ctx(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "user_message": row["user_message"], "emotion": row.get("emotion", "Normal / Sakin"),
        "language": row.get("language", ""), "expected_risk": row.get("expected_risk"),
    }


def run_batch_benchmark(
    cases: Optional[List[Dict[str, Any]]] = None,
    systems: Sequence[str] = tuple(config.DEFAULT_ABLATION_SYSTEMS),
    repeats: int = 1,
    pairs: Optional[Sequence[Tuple[str, str]]] = None,
    judge_enabled: bool = True,
    max_workers: int = 2,
    seed: int = 42,
    max_cases: Optional[int] = None,
    out_root: Optional[str] = None,
    progress: ProgressCb = None,
) -> Dict[str, Any]:
    """Ablation deneyini çalıştırır ve sonuçları döndürür/kaydeder.

    pairs: kör A/B için (sistem_x, sistem_y) çiftleri. Varsayılan: [("vanilla", "full")] (ikisi de seçiliyse).
    judge_enabled=False => yalnızca üretim + trijaj metrikleri (ucuz ön deneme).
    """
    for s in systems:
        if s not in config.SYSTEMS:
            raise ValueError(f"Bilinmeyen sistem: {s!r}")
    cases = list(cases if cases is not None else load_cases())
    if max_cases:
        cases = cases[:max_cases]
    if pairs is None:
        pairs = [("vanilla", "full")] if {"vanilla", "full"} <= set(systems) else []
    pairs = [(x, y) for x, y in pairs if x in systems and y in systems]

    run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir = os.path.join(out_root or OUT_ROOT, run_id)
    os.makedirs(run_dir, exist_ok=True)

    manifest = {
        "run_id": run_id, "started_at": datetime.now().isoformat(timespec="seconds"),
        "systems": list(systems), "repeats": repeats, "pairs": [list(p) for p in pairs],
        "n_cases": len(cases), "cases_fingerprint": cases_fingerprint(cases), "cases_summary": describe_cases(cases),
        "generation_model": config.MODEL_NAME, "judge_models": config.JUDGE_MODELS, "judge_enabled": judge_enabled,
        "temperatures": {"policy": config.POLICY_TEMPERATURE, "vanilla": config.VANILLA_TEMPERATURE,
                         "critic": config.CRITIC_TEMPERATURE, "judge": config.JUDGE_TEMPERATURE},
        "max_revisions": config.MAX_REVISIONS, "prompt_version": config.PROMPT_VERSION,
        "code_version": config.CODE_VERSION, "seed": seed, "max_workers": max_workers,
        "same_family_warning": judge.same_family_warning(),
    }
    with open(os.path.join(run_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    # ---------- 1) Üretim ----------
    tasks = [(c, s, r) for c in cases for s in systems for r in range(repeats)]

    def generate(task):
        case, system, repeat = task
        return run_pipeline(case["user_message"], case.get("emotion", "Normal / Sakin"), "Auto-Detect", "", system)

    gen = _run_parallel(generate, tasks, max_workers, progress, "Üretim")
    rows: List[Dict[str, Any]] = []
    with open(os.path.join(run_dir, "responses.jsonl"), "w", encoding="utf-8") as fh:
        for (case, system, repeat), (status, value) in zip(tasks, gen):
            if status == "ok":
                row = _response_row(case, system, repeat, value)
            else:  # run_pipeline normalde atmaz; yine de koru
                row = _response_row(case, system, repeat, {"error": f"batch: {value}"})
            row["emotion"] = case.get("emotion", "Normal / Sakin")
            rows.append(row)
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    df = pd.DataFrame(rows)
    for col in RESPONSE_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # ---------- 2) Mutlak kör puanlama ----------
    for col in judge.DIMENSIONS:
        df[col] = float("nan")
    for col in ("unsafe", "missed_crisis", "over_escalation", "judged"):
        df[col] = False
    df["judge_error"] = ""
    df["judge_rationale"] = ""

    if judge_enabled:
        idx = [i for i, r in df.iterrows() if not r["error"] and str(r["final_output"]).strip()]

        def judge_one(i):
            row = df.loc[i]
            return judge.judge_absolute(_ctx(row), row["final_output"])

        verdicts = _run_parallel(judge_one, idx, max_workers, progress, "Mutlak puanlama")
        with open(os.path.join(run_dir, "judgments_absolute.jsonl"), "w", encoding="utf-8") as fh:
            for i, (status, value) in zip(idx, verdicts):
                if status == "ok":
                    for d in judge.DIMENSIONS:
                        df.at[i, d] = value[d]
                    for flag in ("unsafe", "missed_crisis", "over_escalation"):
                        df.at[i, flag] = bool(value[flag])
                    df.at[i, "judged"] = True
                    df.at[i, "judge_rationale"] = value["rationale"][:1500]
                    df.at[i, "judge_error"] = "; ".join(value["judge_errors"])
                    fh.write(json.dumps({"case_id": df.at[i, "case_id"], "system": df.at[i, "system"],
                                         "repeat": int(df.at[i, "repeat"]), **value}, ensure_ascii=False, default=str) + "\n")
                else:
                    df.at[i, "judge_error"] = value

    # ---------- 3) Kör ikili karşılaştırma ----------
    pair_rows: List[Dict[str, Any]] = []
    if judge_enabled and pairs:
        valid = df[(df["error"] == "") & (df["final_output"].astype(str).str.strip() != "")]
        pair_tasks = []
        for sx, sy in pairs:
            vx = valid[valid["system"] == sx].set_index(["case_id", "repeat"])
            vy = valid[valid["system"] == sy].set_index(["case_id", "repeat"])
            for key in vx.index.intersection(vy.index):
                rx, ry = vx.loc[key], vy.loc[key]
                pair_tasks.append({"case_id": key[0], "repeat": int(key[1]), "sx": sx, "sy": sy,
                                   "ctx": _ctx(rx), "x": rx["final_output"], "y": ry["final_output"]})

        def judge_pair_one(t):
            return judge.judge_pair(t["ctx"], t["x"], t["y"], seed=_seed_int(seed, t["case_id"], t["repeat"], t["sx"], t["sy"]))

        pair_results = _run_parallel(judge_pair_one, pair_tasks, max_workers, progress, "Kör A/B")
        for t, (status, v) in zip(pair_tasks, pair_results):
            base = {"case_id": t["case_id"], "repeat": t["repeat"], "system_x": t["sx"], "system_y": t["sy"]}
            if status == "ok":
                name = {"X": t["sx"], "Y": t["sy"], "Tie": "Tie"}
                pair_rows.append({**base, "winner_system": name[v["winner"]], "safer_system": name[v["safer"]],
                                  "agreement": v["agreement"], "n_judges": v["n_judges"], "rationale": v["rationale"][:1500],
                                  "flaws_x": v["flaws_x"][:800], "flaws_y": v["flaws_y"][:800], "error": ""})
            else:
                pair_rows.append({**base, "winner_system": None, "safer_system": None, "agreement": float("nan"),
                                  "n_judges": 0, "rationale": "", "flaws_x": "", "flaws_y": "", "error": v})
    pair_df = pd.DataFrame(pair_rows, columns=["case_id", "repeat", "system_x", "system_y", "winner_system", "safer_system",
                                               "agreement", "n_judges", "rationale", "flaws_x", "flaws_y", "error"])
    pair_ok = pair_df[pair_df["error"] == ""] if not pair_df.empty else pair_df

    # ---------- 4) Metrikler ----------
    labels = {s: config.SYSTEMS[s]["label"] for s in systems}
    summary = metrics.summarize_systems(df, labels) if judge_enabled else pd.DataFrame()
    summary_table = metrics.systems_table(summary) if not summary.empty else pd.DataFrame()
    paired = {}
    if judge_enabled and "vanilla" in systems:
        for s in systems:
            if s != "vanilla":
                paired[f"{s} - vanilla (safety)"] = metrics.paired_comparison(df, s, "vanilla", "safety", seed=seed)
    tmetrics = metrics.triage_metrics(cases)
    ttable = metrics.triage_metrics_table(tmetrics)
    pair_summary = metrics.pairwise_summary(pair_ok)

    # ---------- 5) Kayıt ----------
    df.to_csv(os.path.join(run_dir, "responses.csv"), index=False, encoding="utf-8-sig")
    df.to_csv("benchmark_raporu.csv", index=False, encoding="utf-8-sig")  # eski dosya adıyla uyumluluk
    pair_df.to_csv(os.path.join(run_dir, "pairwise.csv"), index=False, encoding="utf-8-sig")
    if not summary_table.empty:
        summary_table.to_csv(os.path.join(run_dir, "summary.csv"), index=False, encoding="utf-8-sig")
    ttable.to_csv(os.path.join(run_dir, "triage_metrics.csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(run_dir, "triage_errors.json"), "w", encoding="utf-8") as fh:
        json.dump(tmetrics["errors"], fh, ensure_ascii=False, indent=2)
    manifest["finished_at"] = datetime.now().isoformat(timespec="seconds")
    manifest["n_response_errors"] = int((df["error"] != "").sum())
    with open(os.path.join(run_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    return {
        "run_dir": run_dir, "manifest": manifest, "responses_df": df, "pairwise_df": pair_df,
        "summary_df": summary, "summary_table": summary_table, "paired": paired,
        "pairwise_summary": pair_summary, "triage_metrics": tmetrics, "triage_table": ttable,
    }


if __name__ == "__main__":  # python batch_tester.py  -> komut satırından çalıştır
    import argparse

    ap = argparse.ArgumentParser(description="Ablation benchmark")
    ap.add_argument("--systems", default=",".join(config.DEFAULT_ABLATION_SYSTEMS))
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--max-cases", type=int, default=None)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--no-judge", action="store_true")
    args = ap.parse_args()
    out = run_batch_benchmark(
        systems=[s.strip() for s in args.systems.split(",") if s.strip()], repeats=args.repeats,
        max_cases=args.max_cases, max_workers=args.workers, judge_enabled=not args.no_judge,
        progress=lambda stage, d, t: print(f"[{stage}] {d}/{t}", end="\r"),
    )
    print("\nKayıt klasörü:", out["run_dir"])
    print(out["triage_table"].to_string(index=False))
    if not out["summary_table"].empty:
        print(out["summary_table"].to_string(index=False))

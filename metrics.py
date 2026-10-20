"""Güvenlik ve deney metrikleri (Faz 2): Crisis Recall, FNR, FPR, precision/F1, Wilson aralıkları,
eşleştirilmiş bootstrap ve ablation özetleri.

Terimler
  Pozitif sınıf : uzman etiketine göre kırmızı bayrak düzeyinde müdahale gerektiren vaka
                  (cases.expected_red_flag == True)
  Crisis Recall : pozitif vakaların ne kadarı yakalandı  (= 1 - FNR)
  FNR           : kaçırılan pozitif oranı
  FPR           : negatif (kontrol) vakalarda gereksiz alarm oranı

İki ayrı ölçüm vardır:
  1) triage_metrics     : SADECE kural/hibrit trijaj katmanı (LLM yok, deterministik, ucuz).
  2) summarize_systems  : LLM kollarının yanıt düzeyi sonuçları (yargıç puanları + bayraklar).

Önemli: etiketsiz (expected_red_flag=None) vakalar oranlara dahil edilmez; sentetik/etiketsiz
vakalardan üretilen sayılar bilimsel sonuç olarak raporlanmamalıdır.
"""
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from triage import run_triage

NAN = float("nan")


# ------------------------------------------------------------------
# İstatistik yardımcıları
# ------------------------------------------------------------------
def wilson_interval(k: int, n: int, z: float = 1.96) -> Tuple[float, float, float]:
    """(oran, alt, üst) – Wilson skor aralığı. n=0 ise NaN."""
    if n <= 0:
        return NAN, NAN, NAN
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def bootstrap_ci(values: Sequence[float], n_boot: int = 2000, seed: int = 0, alpha: float = 0.05) -> Tuple[float, float, float]:
    """(ortalama, alt, üst) – yüzdelik bootstrap güven aralığı."""
    arr = np.asarray([v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))], dtype=float)
    if arr.size == 0:
        return NAN, NAN, NAN
    if arr.size == 1:
        return float(arr[0]), float(arr[0]), float(arr[0])
    rng = np.random.default_rng(seed)
    means = rng.choice(arr, size=(n_boot, arr.size), replace=True).mean(axis=1)
    return float(arr.mean()), float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def binary_metrics(tp: int, fp: int, tn: int, fn: int) -> Dict[str, Any]:
    pos, neg = tp + fn, fp + tn
    recall, r_lo, r_hi = wilson_interval(tp, pos)
    fpr, f_lo, f_hi = wilson_interval(fp, neg)
    precision = tp / (tp + fp) if (tp + fp) else NAN
    f1 = (2 * precision * recall / (precision + recall)) if (precision == precision and recall == recall and (precision + recall) > 0) else NAN
    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn, "positives": pos, "negatives": neg,
        "crisis_recall": recall, "crisis_recall_ci": (r_lo, r_hi),
        "fnr": (1 - recall) if recall == recall else NAN, "fnr_ci": ((1 - r_hi) if r_hi == r_hi else NAN, (1 - r_lo) if r_lo == r_lo else NAN),
        "fpr": fpr, "fpr_ci": (f_lo, f_hi),
        "specificity": (1 - fpr) if fpr == fpr else NAN,
        "precision": precision, "f1": f1,
    }


# ------------------------------------------------------------------
# 1) Trijaj katmanı metrikleri
# ------------------------------------------------------------------
def default_detector(message: str) -> List[str]:
    """Varsayılan: kural tabanlı trijajın yakaladığı bayrak adları."""
    return [f["name"] for f in run_triage(message)["flags"]]


def triage_metrics(
    cases: List[Dict[str, Any]],
    detector: Optional[Callable[[str], List[str]]] = None,
    breakdown_by: Sequence[str] = ("language", "adversarial_type", "category"),
) -> Dict[str, Any]:
    """Trijaj katmanını etiketli vakalar üzerinde ölçer. `detector(message) -> bayrak adları listesi`.

    Hibrit trijaj (Faz 3) aynı imzayla takılıp kural tabanlıyla karşılaştırılabilir (H2).
    """
    detector = detector or default_detector
    labeled = [c for c in cases if c.get("expected_red_flag") is not None]
    rows = []
    for c in labeled:
        names = detector(c["user_message"])
        pred = len(names) > 0
        truth = bool(c["expected_red_flag"])
        rows.append({
            "id": c["id"], "title": c.get("title", ""), "language": c.get("language", ""),
            "adversarial_type": c.get("adversarial_type") or "none", "category": c.get("category", ""),
            "truth": truth, "pred": pred, "detected": names, "expected_flags": c.get("expected_flags", []),
            "label_status": c.get("label_status", ""),
        })
    df = pd.DataFrame(rows)

    def counts(frame: pd.DataFrame) -> Dict[str, Any]:
        tp = int(((frame.truth) & (frame.pred)).sum())
        fn = int(((frame.truth) & (~frame.pred)).sum())
        fp = int(((~frame.truth) & (frame.pred)).sum())
        tn = int(((~frame.truth) & (~frame.pred)).sum())
        return binary_metrics(tp, fp, tn, fn)

    result: Dict[str, Any] = {
        "n_total": len(cases), "n_evaluated": len(labeled), "n_unlabeled": len(cases) - len(labeled),
        "overall": counts(df) if len(df) else binary_metrics(0, 0, 0, 0),
        "breakdown": {}, "per_flag_recall": {}, "errors": [],
    }
    if df.empty:
        return result

    for col in breakdown_by:
        if col in df.columns:
            result["breakdown"][col] = {str(k): counts(g) for k, g in df.groupby(col)}

    flag_hits: Dict[str, List[int]] = {}
    for r in rows:
        for flag in r["expected_flags"]:
            flag_hits.setdefault(flag, []).append(int(flag in r["detected"]))
    for flag, hits in flag_hits.items():
        rate, lo, hi = wilson_interval(sum(hits), len(hits))
        result["per_flag_recall"][flag] = {"n": len(hits), "recall": rate, "ci": (lo, hi)}

    for r in rows:  # hata analizi
        if r["truth"] and not r["pred"]:
            result["errors"].append({"id": r["id"], "title": r["title"], "type": "FN (kaçırılan kriz)", "language": r["language"], "adversarial_type": r["adversarial_type"]})
        elif (not r["truth"]) and r["pred"]:
            result["errors"].append({"id": r["id"], "title": r["title"], "type": "FP (yanlış alarm)", "language": r["language"], "adversarial_type": r["adversarial_type"], "detected": r["detected"]})
    return result


def triage_metrics_table(tm: Dict[str, Any]) -> pd.DataFrame:
    """Arayüz/rapor için tek tablo: Genel + kırılımlar."""
    def row(name: str, m: Dict[str, Any]) -> Dict[str, Any]:
        def ci(t):
            return f"[{t[0]:.2f}, {t[1]:.2f}]" if t[0] == t[0] else "-"
        fmt = lambda x: f"{x:.2f}" if x == x else "-"  # noqa: E731
        return {
            "Küme": name, "Pozitif": m["positives"], "Negatif": m["negatives"],
            "Crisis Recall": fmt(m["crisis_recall"]), "Recall %95 GA": ci(m["crisis_recall_ci"]),
            "FNR": fmt(m["fnr"]), "FPR": fmt(m["fpr"]), "FPR %95 GA": ci(m["fpr_ci"]),
            "Precision": fmt(m["precision"]), "F1": fmt(m["f1"]),
            "TP/FP/TN/FN": f"{m['tp']}/{m['fp']}/{m['tn']}/{m['fn']}",
        }
    rows = [row("GENEL", tm["overall"])]
    for dim, groups in tm["breakdown"].items():
        for key, m in groups.items():
            rows.append(row(f"{dim}={key}", m))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# 2) LLM kolları: yanıt düzeyi özetler
# ------------------------------------------------------------------
JUDGE_DIMS = ["safety", "empathy", "clinical_appropriateness", "harmful_advice_free", "language_match"]


def summarize_systems(df: pd.DataFrame, system_labels: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """Sistem başına özet. `df` sütunları: system, case_id, repeat, error, judged, expected_red_flag,
    <JUDGE_DIMS>, unsafe, missed_crisis, over_escalation, fallback, needs_human_review, latency_s,
    revision_count, llm_calls."""
    system_labels = system_labels or {}
    rows = []
    for system, g in df.groupby("system", sort=False):
        valid = g[(g["error"].fillna("") == "") & (g["judged"] == True)]  # noqa: E712
        row: Dict[str, Any] = {
            "system": system, "Sistem": system_labels.get(system, system),
            "n_yanıt": len(g), "n_hata": int((g["error"].fillna("") != "").sum()), "n_puanlanan": len(valid),
        }
        for d in JUDGE_DIMS:
            mean, lo, hi = bootstrap_ci(valid[d].tolist()) if len(valid) else (NAN, NAN, NAN)
            row[d] = mean
            row[f"{d}_ci"] = (lo, hi)

        n = len(valid)
        u_rate, u_lo, u_hi = wilson_interval(int(valid["unsafe"].sum()), n) if n else (NAN, NAN, NAN)
        row["unsafe_rate"], row["unsafe_rate_ci"] = u_rate, (u_lo, u_hi)

        pos = valid[valid["expected_red_flag"] == True]   # noqa: E712
        neg = valid[valid["expected_red_flag"] == False]  # noqa: E712
        missed, m_lo, m_hi = wilson_interval(int(pos["missed_crisis"].sum()), len(pos)) if len(pos) else (NAN, NAN, NAN)
        row["n_pos"], row["n_neg"] = len(pos), len(neg)
        row["fnr_response"], row["fnr_response_ci"] = missed, (m_lo, m_hi)
        row["crisis_recall_response"] = (1 - missed) if missed == missed else NAN
        over, o_lo, o_hi = wilson_interval(int(neg["over_escalation"].sum()), len(neg)) if len(neg) else (NAN, NAN, NAN)
        row["fpr_response"], row["fpr_response_ci"] = over, (o_lo, o_hi)

        row["fallback_rate"] = float(g["fallback"].mean()) if len(g) else NAN
        row["human_review_rate"] = float(g["needs_human_review"].mean()) if len(g) else NAN
        row["latency_s_mean"] = float(g["latency_s"].mean()) if len(g) else NAN
        row["revisions_mean"] = float(g["revision_count"].mean()) if len(g) else NAN
        row["llm_calls_mean"] = float(g["llm_calls"].mean()) if len(g) else NAN
        rows.append(row)
    return pd.DataFrame(rows)


def systems_table(summary: pd.DataFrame) -> pd.DataFrame:
    """Okunabilir tablo (oran ve güven aralıkları biçimlendirilmiş)."""
    def pct(x):
        return f"{x:.0%}" if x == x else "-"

    def ci(t, scale100=False):
        return f"[{t[0]:.2f}, {t[1]:.2f}]" if t[0] == t[0] else "-"

    out = []
    for _, r in summary.iterrows():
        out.append({
            "Sistem": r["Sistem"], "n (puanlanan/hata)": f"{r['n_puanlanan']}/{r['n_hata']}",
            "Güvenlik (1-5)": f"{r['safety']:.2f} {ci(r['safety_ci'])}" if r["safety"] == r["safety"] else "-",
            "Empati": f"{r['empathy']:.2f}" if r["empathy"] == r["empathy"] else "-",
            "Klinik Uygunluk": f"{r['clinical_appropriateness']:.2f}" if r["clinical_appropriateness"] == r["clinical_appropriateness"] else "-",
            "Güvensiz Yanıt %": f"{pct(r['unsafe_rate'])} {ci(r['unsafe_rate_ci'])}",
            "Crisis Recall (yanıt)": f"{pct(r['crisis_recall_response'])} (n={r['n_pos']})",
            "FNR (yanıt)": f"{pct(r['fnr_response'])} {ci(r['fnr_response_ci'])}",
            "FPR (aşırı alarm)": f"{pct(r['fpr_response'])} {ci(r['fpr_response_ci'])} (n={r['n_neg']})",
            "Güvenli Yedek %": pct(r["fallback_rate"]),
            "Gecikme (sn)": f"{r['latency_s_mean']:.1f}", "LLM çağrısı/mesaj": f"{r['llm_calls_mean']:.1f}",
        })
    return pd.DataFrame(out)


def paired_comparison(df: pd.DataFrame, system_a: str, system_b: str, metric: str = "safety",
                      n_boot: int = 2000, seed: int = 0) -> Dict[str, Any]:
    """Aynı (vaka, tekrar) için A - B farkı; ortalama fark + bootstrap GA + üstünlük sayıları."""
    valid = df[(df["error"].fillna("") == "") & (df["judged"] == True)]  # noqa: E712
    a = valid[valid["system"] == system_a].set_index(["case_id", "repeat"])[metric]
    b = valid[valid["system"] == system_b].set_index(["case_id", "repeat"])[metric]
    joined = pd.concat([a.rename("a"), b.rename("b")], axis=1, join="inner").dropna()
    if joined.empty:
        return {"n": 0, "mean_diff": NAN, "ci": (NAN, NAN), "a_better": 0, "b_better": 0, "ties": 0}
    diff = (joined["a"] - joined["b"]).astype(float)
    mean, lo, hi = bootstrap_ci(diff.tolist(), n_boot=n_boot, seed=seed)
    return {
        "n": int(len(diff)), "mean_diff": mean, "ci": (lo, hi),
        "a_better": int((diff > 0).sum()), "b_better": int((diff < 0).sum()), "ties": int((diff == 0).sum()),
    }


def pairwise_summary(pair_df: pd.DataFrame) -> pd.DataFrame:
    """Kör A/B sonuçlarının özeti. `pair_df`: system_x, system_y, winner_system ('Tie' veya sistem adı)."""
    rows = []
    if pair_df.empty:
        return pd.DataFrame(rows)
    for (sx, sy), g in pair_df.groupby(["system_x", "system_y"], sort=False):
        n = len(g)
        x_w = int((g["winner_system"] == sx).sum())
        y_w = int((g["winner_system"] == sy).sum())
        ties = int((g["winner_system"] == "Tie").sum())
        decisive = x_w + y_w
        rate, lo, hi = wilson_interval(x_w, decisive) if decisive else (NAN, NAN, NAN)
        safer_x = int((g["safer_system"] == sx).sum())
        safer_y = int((g["safer_system"] == sy).sum())
        rows.append({
            "Karşılaştırma": f"{sx} vs {sy}", "n": n,
            f"{sx} kazandı": x_w, f"{sy} kazandı": y_w, "Eşdeğer": ties,
            f"{sx} kazanma oranı (beraberlik hariç)": f"{rate:.0%} [{lo:.2f}, {hi:.2f}]" if rate == rate else "-",
            f"Daha güvenli: {sx}": safer_x, f"Daha güvenli: {sy}": safer_y,
            "Yargıç uyumu (ort.)": f"{g['agreement'].mean():.2f}",
        })
    return pd.DataFrame(rows)

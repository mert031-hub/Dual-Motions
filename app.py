import html
import uuid

import pandas as pd
import streamlit as st

import config
import judge
import metrics
from batch_tester import run_batch_benchmark
from cases import describe_cases, load_cases
from workflow import format_history, run_pipeline
from memory import ClinicalMemory
from research_privacy import AuditLog
from app_auth import require_access

# --- SAYFA YAPILANDIRMASI ---
st.set_page_config(
    page_title="Affective & Clinical LLM Prototipi",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_access()

st.markdown("""
    <style>
    .status-box { padding: 15px; border-radius: 8px; margin-bottom: 12px; font-size: 0.95rem; }
    .approved { background-color: #d4edda; color: #155724; border-left: 5px solid #28a745; }
    .rejected { background-color: #f8d7da; color: #721c24; border-left: 5px solid #dc3545; }
    .fallback { background-color: #fff3cd; color: #856404; border-left: 5px solid #ffc107; }
    .neutral  { background-color: #e2e3e5; color: #383d41; border-left: 5px solid #6c757d; }
    .verdict-banner { padding: 15px; border-radius: 8px; background-color: #1b3a2b; color: #a3cfbb; border-left: 6px solid #20c997; margin-bottom: 15px; }
    </style>
""", unsafe_allow_html=True)


def esc(value) -> str:
    """LLM çıktısını HTML'e koymadan önce kaçışla (unsafe_allow_html ile enjeksiyonu önler)."""
    return html.escape(str(value or ""))


# --- SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "turn" not in st.session_state:
    st.session_state.turn = None          # son turun {result, vanilla, comparison, comparison_error, system_key}
if "benchmark" not in st.session_state:
    st.session_state.benchmark = None
if 'clinical_memory' not in st.session_state:
    st.session_state.clinical_memory = ClinicalMemory()
if 'audit_session' not in st.session_state:
    st.session_state.audit_session = uuid.uuid4().hex

SYSTEM_KEYS = list(config.SYSTEMS.keys())
LABEL = {k: v["label"] for k, v in config.SYSTEMS.items()}

# --- ARAŞTIRMA PROTOTİPİ UYARISI ---
st.warning(
    "**Araştırma prototipi — tıbbi cihaz değildir, tanı/tedavi sunmaz.** Gerçek hasta verisi veya kimlik bilgisi girmeyin. "
    "Acil bir durumdaysanız yerel acil numarayı arayın (Türkiye: 112)."
)

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Klinik Simülasyon Ayarları")
    emotion_input = st.selectbox("Modül 1 (Duygu) Simülasyonu:", ("Normal / Sakin", "Üzgün", "Kaygılı", "Öfkeli"))
    language_choice = st.selectbox(
        "Hedef / Çıktı Dili:", ("Auto-Detect", "Turkish", "Russian", "German", "English", "French", "Spanish")
    )
    chat_system = st.selectbox(
        "Sohbet sistemi (ablation kolu):", SYSTEM_KEYS, index=SYSTEM_KEYS.index("study_full"), format_func=lambda k: LABEL[k]
    )
    affect_mode = st.selectbox('Duygu kaynağı', ['manual', 'model'],
                               format_func=lambda v: 'Elle verilen deney koşulu' if v == 'manual' else 'Metinden tahmin (deneysel)')
    live_compare = st.checkbox("Canlı kör karşılaştırma (Yalın model ile)", value=True,
                               help="Her mesajda Yalın model + yargıç çağrılır; maliyeti ve gecikmeyi artırır.")
    warn = judge.same_family_warning()
    use_memory = st.checkbox('Yapılandırılmış bellek (deneysel, ek model çağrısı)', value=False)
    if use_memory:
        st.caption('Hasta beyanları oturum içinde tutulur; risk olayları kendiliğinden silinmez. Klinik olarak doğrulanmamıştır.')
    if warn:
        st.caption(f"⚠️ {warn}")
    if st.button("Tüm Sohbeti ve Analizi Temizle"):
        AuditLog().delete_session(st.session_state.audit_session)
        st.session_state.messages = []
        st.session_state.turn = None
        st.session_state.benchmark = None
        st.session_state.clinical_memory = ClinicalMemory()
        st.session_state.audit_session = uuid.uuid4().hex
        st.rerun()


def run_turn(user_text: str, history_text: str):
    """Seçili sistemi çalıştırır; istenirse kör yargıçla Yalın modelle karşılaştırır."""
    memory = st.session_state.clinical_memory.render() if use_memory else ''
    result = run_pipeline(user_text, emotion_input, language_choice, history_text, chat_system,
                          clinical_memory=memory, affect_mode=affect_mode)
    if use_memory:
        previous = next((m['content'] for m in reversed(st.session_state.messages[:-1]) if m['role'] == 'assistant'), '')
        st.session_state.clinical_memory.update_from_message(
            user_text, result['triage_flags'], len(st.session_state.messages), previous,
            extract=result['triage_tier'] != 1)
        if st.session_state.clinical_memory.last_error:
            result['needs_human_review'] = True
            st.warning('Bellek çıkarımı tamamlanamadı; mevcut risk kayıtları korundu. İnsan incelemesi gerekiyor.')
    AuditLog().record(st.session_state.audit_session, 'turn', system=chat_system,
                      model=config.MODEL_NAME, triage_tier=result['triage_tier'],
                      needs_human_review=result['needs_human_review'], llm_calls=result['llm_calls'],
                      latency_s=result['latency_s'], error_type=result['error'].split(':')[0] if result['error'] else '')
    turn = {"result": result, "system_key": chat_system, "vanilla": None, "comparison": None, "comparison_error": ""}
    baseline_key = 'study_baseline' if config.SYSTEMS[chat_system].get('study_arm') else 'vanilla'
    if live_compare and chat_system != baseline_key and result['triage_tier'] != 1 and result["final_output"] and not result["error"]:
        vanilla = run_pipeline(user_text, emotion_input, language_choice, history_text, baseline_key,
                               clinical_memory=memory, affect_mode=affect_mode)
        turn["vanilla"] = vanilla
        if vanilla["final_output"] and not vanilla["error"]:
            ctx = {"user_message": user_text, "emotion": emotion_input, "language": language_choice, "expected_risk": None}
            try:
                # X = Yalın model, Y = seçili sistem; yargıç etiketleri görmez, sıra rastgeledir.
                turn["comparison"] = judge.judge_pair(ctx, vanilla["final_output"], result["final_output"])
            except Exception as exc:  # noqa: BLE001
                turn["comparison_error"] = f"{type(exc).__name__}: {exc}"
        else:
            turn["comparison_error"] = f"Yalın model yanıtı alınamadı: {vanilla['error']}"
    return turn


# --- SEKMELER ---
tab_chat, tab_benchmark = st.tabs(["💬 Canlı Klinik Sohbet & Karar Röntgeni", "🔬 Toplu Vaka Test Laboratuvarı (Benchmark)"])

with tab_chat:
    col_hasta, col_dashboard = st.columns([1.15, 1], gap="large")

    with col_hasta:
        st.subheader(f"📱 Hasta İletişim Arayüzü ({LABEL[chat_system]})")
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if user_input := st.chat_input("Hasta mesajını veya vaka senaryosunu buraya yazın..."):
            history_text = format_history(st.session_state.messages)  # o anki mesaj HARİÇ
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)

            with st.chat_message("assistant"):
                with st.spinner("Sistem çalışıyor (trijaj → Policy → Critic) ..."):
                    turn = run_turn(user_input, history_text)
                st.session_state.turn = turn
                out = turn["result"]["final_output"]
                if out:
                    st.markdown(out)
                if turn["result"]["error"]:
                    st.error(f"Hata: {turn['result']['error']}")
            if out:
                st.session_state.messages.append({"role": "assistant", "content": out})

    with col_dashboard:
        st.subheader("🧠 Karar Röntgeni")
        turn = st.session_state.turn
        if not turn:
            st.caption("Bir hasta mesajı gönderin; trijaj, Critic ve revizyon ayrıntıları burada görünür.")
        else:
            r = turn["result"]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Duygu", r["emotion"] or "-")
            m2.metric("Trijaj", r["triage_decision"])
            m3.metric("Critic Riski", r["critic_risk_level"])
            m4.metric("Revizyon", r["revision_count"])

            if r["needs_human_review"]:
                st.error("👤 Bu vaka **insan incelemesi** gerektiriyor (acil trijaj, güvenli yedek veya hata).")
            if r["triage_miss_suspected"]:
                st.warning("🔎 Kural trijajı bayrak vermedi ama Critic yüksek risk saptadı: **olası trijaj kaçağı** (hata analizine ekleyin).")
            if r["error"]:
                st.error(f"Teknik hata: {r['error']}")

            st.markdown("**Trijaj bayrakları**")
            if r["triage_flags"]:
                st.dataframe(pd.DataFrame([{
                    "Bayrak": f["name"], "Eşleşen ifade": f["matched_keyword"], "Eylem": f["action"],
                    "Mod": f["mode"], "Öncelik": f["priority"],
                    "Kaynak": f.get('source', 'rule'),
                } for f in r["triage_flags"]]), hide_index=True)
                if r["triage_directives"]:
                    with st.expander("Policy'ye verilen zorunlu yönergeler"):
                        for d in r["triage_directives"]:
                            st.write("•", d)
            else:
                st.caption("Eşleşen kural yok" if r["triage_decision"] != "Atlandı" else "Bu sistem kolunda trijaj kapalı")

            if r.get('semantic_meta', {}).get('abstained'):
                st.warning('Semantik değerlendirme belirsiz veya kullanılamıyor; bu durum risksiz sonuç anlamına gelmez.')
            if r.get('affect_meta'):
                st.caption(f"Duygu kaynağı: {r['affect_meta'].get('source', '-')} · Strateji: {r.get('response_policy', {}).get('strategy', '-')}")
                if r['affect_meta'].get('error'):
                    st.warning('Duygu tahmini kullanılamıyor; belirsizlik stratejisi seçildi.')
            if use_memory:
                with st.expander('Oturum belleği — doğrulanmamış hasta beyanları'):
                    st.json(st.session_state.clinical_memory.model_dump())
            st.markdown("**Güvenlik Kapısı: Critic**")
            decision = r["critic_decision"] or "-"
            if decision == "Onaylandı":
                css = "approved"
            elif decision == "Reddedildi":
                css = "rejected"
            elif decision == "Güvenli Yedek":
                css = "fallback"
            else:
                css = "neutral"
            violated = ", ".join(r["critic_violated_criteria"]) or "-"
            st.markdown(
                f'<div class="status-box {css}"><b>Karar:</b> {esc(decision)}<br>'
                f'<b>Kırmızı bayrak (Critic):</b> {esc(r["critic_red_flag"])}<br>'
                f'<b>Gerekçe:</b> {esc(r["critic_reason"])}<br>'
                f'<b>İhlal edilen kriterler:</b> {esc(violated)}</div>',
                unsafe_allow_html=True,
            )

            if r["revision_log"]:
                with st.expander(f"Taslak / revizyon geçmişi ({len(r['revision_log'])} denetim)"):
                    for item in r["revision_log"]:
                        st.markdown(f"**Deneme {item['attempt']} — {item['decision']}**")
                        st.code(item["draft"], language="markdown")
                        if item["violated"]:
                            st.write("İhlaller:", ", ".join(item["violated"]))
                        if item["risky_spans"]:
                            st.write("Riskli alıntılar:", " | ".join(item["risky_spans"]))
                        if item["notes"]:
                            st.write("Revizyon talimatı:", item["notes"])
            st.caption(f"LLM çağrısı: {r['llm_calls']} · Gecikme: {r['latency_s']} sn")

    # --- ALT EKRAN: KÖR KARŞILAŞTIRMA ---
    st.divider()
    st.subheader("⚖️ Yalın Model vs. Seçili Sistem: Kör Yargıç Karşılaştırması")
    turn = st.session_state.turn
    if turn and turn["comparison"]:
        comp, van, ours = turn["comparison"], turn["vanilla"], turn["result"]
        c_van, c_our = st.columns(2, gap="large")
        with c_van:
            st.markdown("#### Yalın Model (Standart LLM)")
            st.info(van["final_output"])
        with c_our:
            st.markdown(f"#### {LABEL[turn['system_key']]}")
            st.info(ours["final_output"])

        names = {"X": "Yalın Model", "Y": LABEL[turn["system_key"]], "Tie": "Eşdeğer"}
        st.markdown(
            f'<div class="verdict-banner"><h4>Kör yargıç kararı: {esc(names[comp["winner"]])}</h4>'
            f'<p><b>Daha güvenli bulunan:</b> {esc(names[comp["safer"]])} · '
            f'<b>Yargıç sayısı:</b> {comp["n_judges"]} · <b>Uyum:</b> {comp["agreement"]}</p>'
            f'<p><b>Gerekçe:</b> {esc(comp["rationale"])}</p></div>',
            unsafe_allow_html=True,
        )
        st.caption("Yargıç yanıtları anonim ve rastgele sırayla gördü; sistem adlarını bilmiyordu. "
                   "LLM yargıç kararı klinik doğruluk kanıtı değildir; klinisyen puanlamasıyla doğrulanmalıdır.")
        a1, a2 = st.columns(2)
        a1.markdown("##### Yalın Modelin kusurları")
        a1.write(comp["flaws_x"])
        a2.markdown(f"##### {LABEL[turn['system_key']]} kusurları")
        a2.write(comp["flaws_y"])
    elif turn and turn["comparison_error"]:
        st.error(f"Karşılaştırma yapılamadı: {turn['comparison_error']}")
    else:
        st.caption("Karşılaştırma için kenar çubuğunda 'Canlı kör karşılaştırma'yı açın ve 'Yalın' dışında bir sistem seçin.")


# ============================================================
# BENCHMARK SEKMESİ
# ============================================================
with tab_benchmark:
    st.subheader("🔬 Ablation Deneyi ve Güvenlik Metrikleri")

    all_cases = load_cases()
    desc = describe_cases(all_cases)
    c1, c2, c3 = st.columns(3)
    c1.metric("Toplam vaka", desc["total"])
    c2.metric("Etiketli vaka (sentetik/geçici dahil)", desc["labeled"])
    c3.metric("Etiket durumları", ", ".join(f"{k}: {v}" for k, v in desc["by_status"].items()) or "-")

    if desc['expert_labeled'] == 0:
        st.warning(
            "Henüz **uzman etiketli** vaka yok. Crisis Recall / FNR / FPR için vakalara `expected_red_flag` etiketi "
            "gerekir (`cases_expert.json`). Mevcut sayılar yalnızca altyapı denemesidir; bilimsel sonuç olarak raporlamayın."
        )
    with st.expander("Vaka kaynakları ve etiket şeması"):
        st.markdown(
            "- `cases_legacy.py`: klinisyenin hazırladığı 50 vaka (yalnızca `risk_level` içerir, **kırmızı bayrak etiketi yok**).\n"
            "- `cases_expert.json`: bağımsız uzman etiketli vakalar (`expected_red_flag`, `expected_flags`, `expected_risk`, `language`, `adversarial_type`).\n"
            "- `cases.py` içindeki `S01–S14`: **sentetik** başlangıç/kontrol vakaları (kontrol, İngilizce, örtük, yanlış alarm tuzağı).\n"
            "- Geçici deneme için `LEGACY_HIGH_AS_RED_FLAG=1` ortam değişkeni `risk_level=high` olanları pozitif sayar (uzman etiketi değildir)."
        )

    st.markdown("#### 1) Yalnızca trijaj katmanı (LLM yok, ücretsiz)")
    if st.button("Trijaj metriklerini hesapla"):
        tm = metrics.triage_metrics(all_cases)
        st.caption(f"Değerlendirilen: {tm['n_evaluated']} etiketli vaka · etiketsiz (dışarıda): {tm['n_unlabeled']}")
        if tm["n_evaluated"]:
            st.dataframe(metrics.triage_metrics_table(tm), hide_index=True)
            if tm["errors"]:
                st.markdown("**Hata analizi (FN = kaçırılan kriz, FP = yanlış alarm)**")
                st.dataframe(pd.DataFrame(tm["errors"]), hide_index=True)
        else:
            st.info("Etiketli vaka yok; önce `expected_red_flag` etiketleyin.")

    st.markdown("#### 2) Tam ablation deneyi (LLM çağrıları yapar)")
    s1, s2 = st.columns(2)
    with s1:
        systems_sel = st.multiselect("Sistem kolları", SYSTEM_KEYS, default=config.DEFAULT_ABLATION_SYSTEMS, format_func=lambda k: LABEL[k])
        repeats = st.number_input("Tekrar sayısı (varyans için)", min_value=1, max_value=5, value=1)
        max_cases = st.number_input("En fazla vaka (0 = hepsi)", min_value=0, max_value=max(1, len(all_cases)), value=0)
    with s2:
        workers = st.slider("Paralel iş parçacığı (rate limit için düşük tutun)", 1, 6, 2)
        judge_on = st.checkbox("Kör yargıçla puanla", value=True)
        pair_on = st.checkbox("Kör A/B: Baseline vs birleşik sistem", value=True)
        persist_text = st.checkbox('Sentetik vaka metinlerini deney dosyalarına kaydet', value=False,
                                   help='Varsayılan kayıt metinsizdir. Yalnızca onaylı sentetik araştırma verisi için açın.')

    n_cases = len(all_cases) if max_cases == 0 else min(int(max_cases), len(all_cases))
    n_runs = n_cases * len(systems_sel) * int(repeats)
    n_judges = len(config.JUDGE_MODELS)
    est_judge = (n_runs + (n_cases * int(repeats) if pair_on else 0)) * n_judges if judge_on else 0
    st.caption(f"Tahmini yük: {n_runs} üretim çalıştırması (her biri 1–8 LLM çağrısı) + yaklaşık {est_judge} yargıç çağrısı.")

    if st.button("🚀 Ablation deneyini başlat", type="primary", disabled=not systems_sel):
        bar = st.progress(0.0)
        status = st.empty()

        def on_progress(stage: str, done: int, total: int):
            bar.progress(min(1.0, done / max(total, 1)))
            status.text(f"{stage}: {done}/{total}")

        try:
            pairs = (None if pair_on else [])
            st.session_state.benchmark = run_batch_benchmark(
                cases=all_cases, systems=systems_sel, repeats=int(repeats), pairs=pairs,
                judge_enabled=judge_on, max_workers=workers, max_cases=int(max_cases) or None, progress=on_progress,
                persist_text=persist_text,
                affect_mode=affect_mode,
            )
            status.text("Tamamlandı.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Deney başarısız: {type(exc).__name__}: {exc}")

    bm = st.session_state.benchmark
    if bm:
        st.success(f"Koşu kaydedildi: `{bm['run_dir']}` (manifest, JSONL ve CSV dosyaları dahil)")
        if bm["manifest"].get("same_family_warning"):
            st.warning(bm["manifest"]["same_family_warning"])
        n_err = bm["manifest"].get("n_response_errors", 0)
        if n_err:
            st.error(f"{n_err} yanıt hata ile sonuçlandı; bu yanıtlar puanlanmadı ve özetlerde 'n_hata' olarak sayıldı.")
        n_incomplete = bm['manifest'].get('n_judge_incomplete', 0)
        if n_incomplete:
            st.warning(f'{n_incomplete} yanıtta yargıç rubriği eksik: puanlanamayan alanlar doldurulmadı; deney eksiksiz başarılı sayılamaz.')

        st.markdown("##### Trijaj katmanı metrikleri")
        st.dataframe(bm["triage_table"], hide_index=True)

        if not bm["summary_table"].empty:
            st.markdown("##### Sistem kolları (ablation özeti)")
            st.dataframe(bm["summary_table"], hide_index=True)
            if bm["paired"]:
                st.markdown("##### Eşleştirilmiş güvenlik puanı farkı (kol − Yalın; bootstrap %95 GA)")
                st.dataframe(pd.DataFrame([
                    {"Karşılaştırma": k, "n": v["n"],
                     "Ort. fark": f"{v['mean_diff']:.2f}" if v["mean_diff"] == v["mean_diff"] else "-",
                     "%95 GA": f"[{v['ci'][0]:.2f}, {v['ci'][1]:.2f}]" if v["ci"][0] == v["ci"][0] else "-",
                     "Kol daha iyi": v["a_better"], "Yalın daha iyi": v["b_better"], "Eşit": v["ties"]}
                    for k, v in bm["paired"].items()
                ]), hide_index=True)
        if not bm["pairwise_summary"].empty:
            st.markdown("##### Kör A/B sonuçları")
            st.dataframe(bm["pairwise_summary"], hide_index=True)

        with st.expander("Yanıt düzeyi ham sonuçlar"):
            cols = ["case_id", "system", "repeat", "triage_decision", "triage_flags", "critic_decision", "revision_count",
                    "safety", "empathy", "unsafe", "missed_crisis", "over_escalation", "error", "final_output"]
            st.dataframe(bm["responses_df"][[c for c in cols if c in bm["responses_df"].columns]], hide_index=True)

        d1, d2, d3 = st.columns(3)
        d1.download_button("responses.csv", bm["responses_df"].to_csv(index=False).encode("utf-8-sig"), "responses.csv", "text/csv")
        d2.download_button("pairwise.csv", bm["pairwise_df"].to_csv(index=False).encode("utf-8-sig"), "pairwise.csv", "text/csv")
        if not bm["summary_table"].empty:
            d3.download_button("summary.csv", bm["summary_table"].to_csv(index=False).encode("utf-8-sig"), "summary.csv", "text/csv")
        with st.expander("Deney manifestosu (yeniden üretilebilirlik)"):
            st.json(bm["manifest"])

import streamlit as st
from workflow import app as graph_app, run_vanilla_llm, compare_models_deeply
from batch_tester import run_batch_benchmark, TEST_CASES

# --- SAYFA YAPILANDIRMASI ---
st.set_page_config(
    page_title="Affective & Clinical LLM Prototipi",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .status-box { padding: 15px; border-radius: 8px; margin-bottom: 12px; font-size: 0.95rem; }
    .approved { background-color: #d4edda; color: #155724; border-left: 5px solid #28a745; }
    .rejected { background-color: #f8d7da; color: #721c24; border-left: 5px solid #dc3545; }
    .verdict-banner { padding: 15px; border-radius: 8px; background-color: #1b3a2b; color: #a3cfbb; border-left: 6px solid #20c997; margin-bottom: 15px; }
    </style>
""", unsafe_allow_html=True)

# --- SESSION STATE BAŞLATMA ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "system_logs" not in st.session_state:
    st.session_state.system_logs = {
        "emotion": "Bekleniyor...",
        "policy_draft": "Bekleniyor...",
        "critic_decision": "Bekleniyor...",
        "critic_risk_level": "Bilinmiyor",
        "critic_red_flag": "Yok",
        "critic_reason": "Bekleniyor...",
        "critic_revision_notes": "",
        "revision_count": 0,
        "vanilla_response": "",
        "our_response": "",
        "comparison": None
    }

def run_full_evaluation_pipeline(user_text, simulated_emotion, target_lang):
    initial_state = {
        "user_input": user_text,
        "emotion": simulated_emotion,
        "target_language": target_lang,
        "revision_count": 0,
        "chat_history": "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages[-4:]])
    }
    result = graph_app.invoke(initial_state)
    our_final = result.get("final_output", "")
    red_flag = result.get("critic_red_flag", "Yok")

    vanilla_out = run_vanilla_llm(user_text, target_lang)
    comparison_report = compare_models_deeply(user_text, simulated_emotion, vanilla_out, our_final, red_flag)

    st.session_state.system_logs = {
        "emotion": result.get("emotion", ""),
        "policy_draft": result.get("policy_draft", ""),
        "critic_decision": result.get("critic_decision", ""),
        "critic_risk_level": result.get("critic_risk_level", "Düşük"),
        "critic_red_flag": red_flag,
        "critic_reason": result.get("critic_reason", ""),
        "critic_revision_notes": result.get("critic_revision_notes", ""),
        "revision_count": result.get("revision_count", 0),
        "vanilla_response": vanilla_out,
        "our_response": our_final,
        "comparison": comparison_report
    }
    return our_final

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Klinik Simülasyon Ayarları")
    emotion_input = st.selectbox(
        "Modül 1 (Duygu) Simülasyonu:",
        ("Normal / Sakin", "Üzgün", "Kaygılı", "Öfkeli")
    )
    language_choice = st.selectbox(
        "Hedef / Çıktı Dili:",
        ("Auto-Detect", "Turkish", "Russian", "German", "English", "French", "Spanish")
    )
    if st.button("Tüm Sohbeti ve Analizi Temizle"):
        st.session_state.messages = []
        st.session_state.system_logs["comparison"] = None
        st.rerun()

# --- ANA SEKMELİ YAPI (TABS) ---
tab_chat, tab_benchmark = st.tabs(["💬 Canlı Klinik Sohbet & Karar Röntgeni", "🔬 Toplu Vaka Test Laboratuvarı (Benchmark)"])

with tab_chat:
    col_hasta, col_dashboard = st.columns([1.15, 1], gap="large")

    with col_hasta:
        st.subheader("📱 Hasta İletişim Arayüzü (Bizim Modelimiz)")
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if user_input := st.chat_input("Hasta mesajını veya vaka senaryosunu buraya yazın..."):
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)

            with st.chat_message("assistant"):
                with st.spinner("Çift katmanlı klinik denetim ve Yalın Model karşılaştırması yapılıyor..."):
                    response = run_full_evaluation_pipeline(user_input, emotion_input, language_choice)
                    st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

    with col_dashboard:
        st.subheader("🧠 Çift Katmanlı LLM Karar Röntgeni")
        logs = st.session_state.system_logs

        m1, m2, m3 = st.columns(3)
        m1.metric("Saptanan Durum", logs["emotion"])
        m2.metric("Klinik Risk", logs["critic_risk_level"])
        m3.metric("Revizyon Döngüsü", logs["revision_count"])

        st.info(f"🚩 **Saptanan Kırmızı Bayrak Kategori:** {logs['critic_red_flag']}")

        st.markdown("**Modül 2: Policy (Onaylanan Son Taslak)**")
        st.code(logs["policy_draft"], language="markdown")

        st.markdown("**Güvenlik Kapısı: Critic Denetim Gerekçesi**")
        decision = logs["critic_decision"]
        if decision == "Onaylandı":
            st.markdown(f'<div class="status-box approved"><b>Karar:</b> {decision}<br><b>Klinik Gerekçe:</b> {logs["critic_reason"]}</div>', unsafe_allow_html=True)
        elif decision == "Reddedildi":
            st.markdown(f'<div class="status-box rejected"><b>Karar:</b> {decision}<br><b>Klinik Gerekçe:</b> {logs["critic_reason"]}<br><b>Revizyon Talimatı:</b> {logs["critic_revision_notes"]}</div>', unsafe_allow_html=True)

    # --- ALT EKRAN: YALIN MODEL VS BİZİM MODELİMİZ DERİN ANALİZ ---
    st.divider()
    st.subheader("⚔️ Yalın Model (Standart LLM) vs. Bizim Modelimiz: Klinik Fark ve Üstünlük Analizi")

    comp = st.session_state.system_logs.get("comparison")
    if comp:
        c_van, c_our = st.columns(2, gap="large")
        with c_van:
            st.markdown("#### ❌ Yalın Modelin (Filtresiz Standart LLM) Yanıtı")
            st.warning(st.session_state.system_logs["vanilla_response"])
        with c_our:
            st.markdown("#### ✅ Bizim Çift Katmanlı Klinik Modelimizin Yanıtı")
            st.success(st.session_state.system_logs["our_response"])

        st.markdown(f"""
        <div class="verdict-banner">
            <h4>🏆 Klinik Hakem Kararı: {comp.superior_model}</h4>
            <p><b>Üstünlük Gerekçesi:</b> {comp.detailed_verdict_rationale}</p>
        </div>
        """, unsafe_allow_html=True)

        a_col1, a_col2, a_col3 = st.columns(3)
        with a_col1:
            st.markdown("##### 🔍 Mesajlar Neden Farklı?")
            st.write(comp.why_messages_differ)
        with a_col2:
            st.markdown("##### ⚠️ Yalın Modelin Klinik Hataları & Riskleri")
            st.write(comp.vanilla_clinical_flaws)
        with a_col3:
            st.markdown("##### 🛡️ Bizim Modelimizin Klinik Müdahalesi")
            st.write(comp.our_model_clinical_strengths)
    else:
        st.caption("Klinik karşılaştırma ve nedensellik analizini görmek için yukarıdan bir hasta mesajı gönderin.")

with tab_benchmark:
    st.subheader("🔬 Otomatik Vaka Test ve Performans Laboratuvarı")
    st.markdown("Tıpçı arkadaşınızın hazırladığı vaka seti üzerinden sistemimizin başarı oranını toplu olarak test edin.")
    
    st.info(f"Sistemde şu an yüklü olan aktif test senaryosu sayısı: **{len(TEST_CASES)} Vaka** (Arkadaşınız `clinical_cases.py` eklediğinde bu sayı otomatik olarak 50'ye çıkacaktır.)")
    
    if st.button("🚀 Tüm Vakalar İçin Toplu Testi Başlat (Benchmark Runner)"):
        with st.spinner("Vakalar Yalın Model ve Çift Katmanlı Sistemimizden geçiriliyor, klinik hakem raporları hazırlanıyor..."):
            df_report = run_batch_benchmark()
            st.success("Toplu test başarıyla tamamlandı ve `benchmark_raporu.csv` olarak kaydedildi!")
            st.dataframe(df_report, use_container_width=True)
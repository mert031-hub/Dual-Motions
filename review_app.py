"""A separate blinded rating interface; it never loads the private system mapping."""
import json

import streamlit as st

from app_auth import require_access
from clinician_review import validate_rating, RUBRIC_ANCHORS
import judge

st.set_page_config(page_title='Kör klinisyen değerlendirmesi')
require_access()
st.title('Kör yanıt değerlendirmesi')
st.caption('Yalnızca onaylı sentetik araştırma verisi. Rubrik taslaktır; puanlama öncesi klinisyenlerle kalibre edilmelidir.')
uploaded = st.file_uploader('Değerlendirme paketi (.json)', type=['json'])
if uploaded:
    try:
        packet = json.load(uploaded)
        if 'mapping' in packet or not packet.get('items') or not packet.get('packet_id'):
            raise ValueError('Geçerli kör paket gerekli; eşleme dosyasını yüklemeyin.')
        ids = [item['item_id'] for item in packet['items']]
        if len(ids) != len(set(ids)):
            raise ValueError('Tekrarlı item_id')
        reviewer = st.text_input('Değerlendirici kodu (ad/kişisel bilgi girmeyin)')
        with st.expander('Puanlama çıpaları — taslak, klinik olarak doğrulanmış ölçek değildir'):
            st.json(packet.get('rubric_anchors', RUBRIC_ANCHORS))
        if st.session_state.get('packet_id') != packet['packet_id']:
            st.session_state.packet_id = packet['packet_id']
            st.session_state.ratings = {}
        item_id = st.selectbox('Yanıt', ids)
        item = next(i for i in packet['items'] if i['item_id'] == item_id)
        st.write('Senaryo:', item['user_message'])
        st.write('Yanıt:', item['response'])
        with st.form('rate_' + item_id):
            scores = {}
            for dimension in judge.DIMENSIONS:
                value = st.selectbox(dimension, ['Puanlanmadı', 1, 2, 3, 4, 5], key=item_id + dimension)
                scores[dimension] = None if value == 'Puanlanmadı' else value
            behavior_flags = {}
            for flag in judge.BEHAVIOR_FLAGS:
                value = st.selectbox(flag, ['Puanlanmadı', 'Yok', 'Var'], key=item_id + flag)
                behavior_flags[flag] = {'Yok':False, 'Var':True}.get(value)
            if st.form_submit_button('Puanı kaydet'):
                rating = validate_rating(dict(item_id=item_id, reviewer=reviewer, scores=scores,
                                              behavior_flags=behavior_flags), set(ids))
                st.session_state.ratings[item_id] = rating.model_dump()
                st.success('Bu oturumda kaydedildi.')
        st.caption(f"Puanlanan: {len(st.session_state.ratings)} / {len(ids)}")
        st.download_button('Puanları indir', json.dumps({'packet_id': packet['packet_id'],
                           'ratings': list(st.session_state.ratings.values())}, ensure_ascii=False),
                           file_name='review_ratings.json', mime='application/json')
    except (ValueError, KeyError, TypeError) as exc:
        st.error(f'Paket veya puan geçersiz: {type(exc).__name__}')

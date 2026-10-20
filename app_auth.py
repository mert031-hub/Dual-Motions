"""Optional research password gate; deployment still needs TLS and upstream rate limiting."""
import hashlib
import hmac
import os


def verify_password(password, expected_hash):
    parts = expected_hash.split('$')
    if len(parts) != 4 or parts[0] != 'pbkdf2_sha256':
        return False
    try:
        iterations = int(parts[1])
        if not 600_000 <= iterations <= 2_000_000:
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(parts[2]), iterations).hex()
        return hmac.compare_digest(digest, parts[3])
    except (ValueError, TypeError):
        return False


def hash_password(password):
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600_000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'


def require_access():
    import streamlit as st
    required = os.getenv('APP_REQUIRE_AUTH', '0') == '1'
    expected = os.getenv('APP_PASSWORD_HASH', '')
    if not required and not expected:
        return
    if not expected:
        st.error('Erişim kapalı: APP_PASSWORD_HASH ortam ayarlarında tanımlanmalı.')
        st.stop()
    if st.session_state.get('authenticated_hash') == expected:
        if st.sidebar.button('Çıkış yap'):
            st.session_state.clear()
            st.rerun()
        return
    import time
    now = time.monotonic()
    if now < st.session_state.get('login_retry_at', 0):
        st.warning('Tekrar denemeden önce kısa bir süre bekleyin.')
        st.stop()
    with st.form('access_gate'):
        password = st.text_input('Araştırma erişim parolası', type='password')
        submitted = st.form_submit_button('Giriş')
    if submitted:
        if verify_password(password, expected):
            st.session_state.authenticated_hash = expected
            st.rerun()
        st.session_state.login_retry_at = now + 3
        st.error('Giriş bilgisi doğrulanamadı.')
    st.stop()


if __name__ == '__main__':
    import getpass
    print(hash_password(getpass.getpass('New research password: ')))

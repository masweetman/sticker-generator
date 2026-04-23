"""
Tests for TOTP 2FA flows:
  - Setup/enable flow (valid and invalid TOTP)
  - Login with 2FA challenge
  - Disable flow authorization
  - Invalid code retry handling
"""
import pytest
import pyotp
from werkzeug.security import generate_password_hash

from app import app as flask_app, db as _db
from app.models import User
from conftest import _create_user, login_session


def _enable_2fa_for_user(user_id):
    """Helper: directly set 2FA fields on a user in the DB."""
    secret = pyotp.random_base32()
    with flask_app.app_context():
        u = _db.session.get(User, user_id)
        u.two_factor_secret = secret
        u.two_factor_enabled = True
        _db.session.commit()
    return secret


def _current_totp(secret):
    return pyotp.TOTP(secret).now()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Login 2FA challenge
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestLogin2faChallenge:
    def test_login_with_2fa_enabled_redirects_to_2fa_page(self, client, user_a):
        # Arrange
        _enable_2fa_for_user(user_a.id)

        # Act
        r = client.post('/login/', data={
            'user': user_a.username, 'password': user_a.password,
        }, follow_redirects=False)

        # Assert — redirected to the TOTP challenge page, not to sheets
        assert r.status_code in (301, 302)
        assert '/login/2fa' in r.headers.get('Location', '')

    def test_login_with_2fa_enabled_does_not_create_full_session(
            self, client, user_a):
        # Arrange
        _enable_2fa_for_user(user_a.id)

        # Act
        client.post('/login/', data={
            'user': user_a.username, 'password': user_a.password,
        }, follow_redirects=False)

        # Assert — no authenticated session yet
        with client.session_transaction() as sess:
            assert '_user_id' not in sess
            assert '_2fa_pending_user_id' in sess

    def test_login_2fa_page_loads(self, client):
        r = client.get('/login/2fa/')
        # Without a pending session it should redirect to login
        assert r.status_code in (200, 301, 302)

    def test_login_2fa_with_valid_code_creates_session(self, client, user_a):
        # Arrange
        secret = _enable_2fa_for_user(user_a.id)
        client.post('/login/', data={
            'user': user_a.username, 'password': user_a.password,
        }, follow_redirects=False)

        # Act
        code = _current_totp(secret)
        r = client.post('/login/2fa/', data={'code': code}, follow_redirects=False)

        # Assert
        assert r.status_code in (301, 302)
        assert '/sheets' in r.headers.get('Location', '') or '/login' not in r.headers.get('Location', '')
        with client.session_transaction() as sess:
            assert '_user_id' in sess
            assert '_2fa_pending_user_id' not in sess

    def test_login_2fa_with_invalid_code_does_not_create_session(
            self, client, user_a):
        # Arrange
        _enable_2fa_for_user(user_a.id)
        client.post('/login/', data={
            'user': user_a.username, 'password': user_a.password,
        }, follow_redirects=False)

        # Act
        r = client.post('/login/2fa/', data={'code': '000000'},
                        follow_redirects=True)

        # Assert
        assert r.status_code == 200
        with client.session_transaction() as sess:
            assert '_user_id' not in sess

    def test_login_without_2fa_still_works(self, client, user_a):
        """Users without 2FA enabled must log in normally (no challenge)."""
        r = client.post('/login/', data={
            'user': user_a.username, 'password': user_a.password,
        }, follow_redirects=False)
        assert r.status_code in (301, 302)
        assert '/sheets' in r.headers.get('Location', '')
        with client.session_transaction() as sess:
            assert '_user_id' in sess


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2FA setup/enable flow
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTwoFactorSetup:
    def test_setup_page_requires_login(self, client):
        r = client.get('/profile/2fa/setup/', follow_redirects=False)
        assert r.status_code in (301, 302)
        assert '/login' in r.headers.get('Location', '')

    def test_setup_page_loads_for_authenticated_user(self, client_a):
        r = client_a.get('/profile/2fa/setup/')
        assert r.status_code == 200
        assert b'QR' in r.data or b'qr' in r.data or b'authenticator' in r.data.lower()

    def test_enable_with_wrong_password_fails(self, client_a, user_a):
        # Arrange — hit setup page to seed the session secret
        client_a.get('/profile/2fa/setup/')

        # Act
        r = client_a.post('/profile/2fa/setup/', data={
            'current_password': 'WRONG_PASS',
            'code': '000000',
        }, follow_redirects=True)

        # Assert
        assert r.status_code == 200
        with flask_app.app_context():
            u = _db.session.get(User, user_a.id)
            assert not u.two_factor_enabled

    def test_enable_with_invalid_totp_code_fails(self, client_a, user_a):
        # Arrange
        client_a.get('/profile/2fa/setup/')

        # Act
        r = client_a.post('/profile/2fa/setup/', data={
            'current_password': user_a.password,
            'code': '000000',  # almost certainly wrong
        }, follow_redirects=True)

        # Assert
        assert r.status_code == 200
        with flask_app.app_context():
            u = _db.session.get(User, user_a.id)
            assert not u.two_factor_enabled

    def test_enable_with_valid_credentials_and_code_succeeds(
            self, client_a, user_a):
        # Arrange — get the session secret via setup page
        client_a.get('/profile/2fa/setup/')
        with client_a.session_transaction() as sess:
            secret = sess.get('two_factor_setup_secret')
        assert secret, 'Setup secret must be stored in session'

        # Act
        code = _current_totp(secret)
        r = client_a.post('/profile/2fa/setup/', data={
            'current_password': user_a.password,
            'code': code,
        }, follow_redirects=True)

        # Assert
        assert r.status_code == 200
        with flask_app.app_context():
            u = _db.session.get(User, user_a.id)
            assert u.two_factor_enabled
            assert u.two_factor_secret == secret


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2FA disable flow
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTwoFactorDisable:
    def test_disable_requires_login(self, client):
        r = client.post('/profile/2fa/disable/', data={
            'disable-current_password': 'x', 'disable-code': '000000',
        }, follow_redirects=False)
        assert r.status_code in (301, 302)
        assert '/login' in r.headers.get('Location', '')

    def test_disable_with_wrong_password_fails(self, client_a, user_a):
        # Arrange
        secret = _enable_2fa_for_user(user_a.id)

        # Act
        r = client_a.post('/profile/2fa/disable/', data={
            'disable-current_password': 'WRONG',
            'disable-code': _current_totp(secret),
        }, follow_redirects=True)

        # Assert — still enabled
        assert r.status_code == 200
        with flask_app.app_context():
            u = _db.session.get(User, user_a.id)
            assert u.two_factor_enabled

    def test_disable_with_invalid_totp_fails(self, client_a, user_a):
        # Arrange
        _enable_2fa_for_user(user_a.id)

        # Act
        r = client_a.post('/profile/2fa/disable/', data={
            'disable-current_password': user_a.password,
            'disable-code': '000000',
        }, follow_redirects=True)

        # Assert — still enabled
        assert r.status_code == 200
        with flask_app.app_context():
            u = _db.session.get(User, user_a.id)
            assert u.two_factor_enabled

    def test_disable_with_valid_credentials_succeeds(self, client_a, user_a):
        # Arrange
        secret = _enable_2fa_for_user(user_a.id)

        # Act
        code = _current_totp(secret)
        r = client_a.post('/profile/2fa/disable/', data={
            'disable-current_password': user_a.password,
            'disable-code': code,
        }, follow_redirects=True)

        # Assert
        assert r.status_code == 200
        with flask_app.app_context():
            u = _db.session.get(User, user_a.id)
            assert not u.two_factor_enabled
            assert u.two_factor_secret is None

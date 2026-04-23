"""
Adversarial and security tests.
Covers OWASP Top-10 areas relevant to this app:
  - Broken Access Control (cross-user resource access)
  - Injection (SQL injection via form fields)
  - Security Misconfiguration (CSRF, security headers)
  - XSS (stored XSS via sheet name)
  - Path Traversal
  - Rate limiting
"""
import json
import pytest
from unittest.mock import patch, MagicMock

from app import app as flask_app, db as _db
from app.models import User, StickerSheet, Sticker
from conftest import _create_sheet, _create_sticker, VALID_PNG_DATA_URL


def _json(client, method, url, **kwargs):
    fn = getattr(client, method)
    kwargs.setdefault('content_type', 'application/json')
    return fn(url, **kwargs)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Broken Access Control — cross-user isolation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCrossUserIsolation:
    """User B must never be able to modify or read User A's resources."""

    def test_user_b_cannot_view_user_a_sheet(self, client_b, sheet_a):
        r = client_b.get(f'/sheets/{sheet_a}/')
        assert r.status_code == 404

    def test_user_b_cannot_delete_user_a_sheet(self, client_b, sheet_a):
        r = client_b.post(f'/sheets/{sheet_a}/delete/')
        assert r.status_code == 404
        with flask_app.app_context():
            assert StickerSheet.query.get(sheet_a) is not None

    def test_user_b_cannot_resize_user_a_sheet(self, client_b, sheet_a):
        r = client_b.post(f'/sheets/{sheet_a}/resize/',
                          data={'rows': '1', 'cols': '1'})
        assert r.status_code == 404
        with flask_app.app_context():
            sheet = StickerSheet.query.get(sheet_a)
            assert sheet.rows == 4  # unchanged

    def test_user_b_cannot_generate_sticker_on_user_a_sheet(
            self, client_b, sheet_a):
        r = _json(client_b, 'post', '/api/generate/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0,
                                   'prompt': 'cat'}))
        assert r.status_code in (400, 404)

    def test_user_b_cannot_upload_sticker_to_user_a_sheet(
            self, client_b, sheet_a, image_dir):
        r = _json(client_b, 'post', '/api/upload-sticker/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0,
                                   'prompt': 'x', 'image_data': VALID_PNG_DATA_URL}))
        assert r.status_code in (400, 404)

    def test_user_b_cannot_delete_sticker_from_user_a_sheet(
            self, client_b, sheet_a, sticker_a):
        r = client_b.delete(f'/api/sticker/{sheet_a}/0/0/')
        assert r.status_code == 404
        with flask_app.app_context():
            assert Sticker.query.filter_by(
                sheet_id=sheet_a, row=0, col=0).first() is not None

    def test_user_b_cannot_rename_user_a_sheet(self, client_b, sheet_a):
        r = _json(client_b, 'post', '/api/rename-sheet/',
                  data=json.dumps({'sheet_id': sheet_a, 'name': 'Hacked!'}))
        assert r.status_code == 404
        with flask_app.app_context():
            assert StickerSheet.query.get(sheet_a).name == 'Sheet A'

    def test_user_b_cannot_copy_all_on_user_a_sheet(self, client_b, sheet_a,
                                                     sticker_a):
        r = _json(client_b, 'post', '/api/copy-all/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0}))
        assert r.status_code == 404


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Admin access control
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAdminAccessControl:
    def test_non_admin_cannot_access_admin_panel(self, client_a):
        r = client_a.get('/admin/', follow_redirects=False)
        # Must NOT return 200
        assert r.status_code != 200

    def test_unauthenticated_cannot_access_admin_panel(self, client):
        r = client.get('/admin/', follow_redirects=False)
        assert r.status_code != 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CSRF protection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCsrfProtection:
    def test_post_without_csrf_token_rejected_when_csrf_enabled(
            self, clean_db, user_a):
        """
        With WTF_CSRF_ENABLED=True, a form POST without a CSRF token must
        be rejected with HTTP 400.
        """
        flask_app.config['WTF_CSRF_ENABLED'] = True
        try:
            with flask_app.test_client() as c:
                r = c.post('/login/', data={
                    'user': user_a.username,
                    'password': user_a.password,
                }, follow_redirects=False)
                assert r.status_code == 400, (
                    f'Expected 400 without CSRF token, got {r.status_code}'
                )
        finally:
            flask_app.config['WTF_CSRF_ENABLED'] = False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SQL injection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSqlInjection:
    def test_sql_injection_in_username_does_not_crash(self, client):
        """SQL metacharacters in the username field must be treated as literal text."""
        payload = "' OR '1'='1'; DROP TABLE user; --"
        r = client.post('/login/', data={'user': payload, 'password': 'x'},
                        follow_redirects=True)
        # App must respond normally (not 500)
        assert r.status_code in (200, 400)

    def test_sql_injection_username_does_not_authenticate(self, client):
        """The injection attempt must not log the attacker in."""
        payload = "' OR '1'='1"
        client.post('/login/', data={'user': payload, 'password': 'x'})
        with client.session_transaction() as sess:
            assert '_user_id' not in sess

    def test_sql_injection_in_registration(self, client):
        """Registration with SQL-special username must store it safely, not crash."""
        evil_name = "evil'); DROP TABLE user;--"
        r = client.post('/register/', data={
            'user': evil_name, 'name': '', 'email': '', 'password': 'safepass',
        }, follow_redirects=True)
        assert r.status_code in (200, 400)
        # If it succeeded, the username should have been stored literally
        with flask_app.app_context():
            u = User.query.filter_by(user=evil_name).first()
            if u:
                assert u.user == evil_name  # stored exactly, not interpreted


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# XSS — stored XSS via sheet name
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestXss:
    def test_xss_payload_in_sheet_name_is_escaped_in_list(
            self, client_a, user_a):
        """A <script> tag in a sheet name must be HTML-escaped, not executed."""
        xss = '<script>alert("xss")</script>'
        _create_sheet(user_a.id, xss)
        r = client_a.get('/sheets/')
        body = r.data.decode('utf-8')
        assert '<script>' not in body, \
            'Raw <script> tag must not appear in the HTML output'

    def test_xss_payload_via_rename_api_is_escaped_in_editor(
            self, client_a, sheet_a):
        xss = '<script>alert(1)</script>'
        _json(client_a, 'post', '/api/rename-sheet/',
              data=json.dumps({'sheet_id': sheet_a, 'name': xss}))
        r = client_a.get(f'/sheets/{sheet_a}/')
        body = r.data.decode('utf-8')
        # The raw payload must not appear unescaped in the HTML body.
        # Jinja2 auto-escaping converts < to &lt; and > to &gt;,
        # so alert(1) should appear but only within an HTML-escaped context.
        assert 'alert(1)</script>' not in body, \
            'XSS payload must not appear unescaped in the rendered HTML'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Path traversal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPathTraversal:
    def test_non_integer_sheet_id_returns_404(self, client_a):
        """Flask route uses <int:sheet_id>; a non-integer must return 404."""
        r = client_a.get('/sheets/../../etc/passwd/')
        assert r.status_code == 404

    def test_invalid_sticker_delete_path(self, client_a):
        r = client_a.delete('/api/sticker/abc/0/0/')
        assert r.status_code == 404


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Invalid / malformed inputs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestMalformedInputs:
    def test_upload_malformed_data_url_returns_400(self, client_a, sheet_a,
                                                   image_dir):
        """A string that doesn't match the data:[mime];base64,[data] format
        must be rejected with 400.
        """
        r = _json(client_a, 'post', '/api/upload-sticker/',
                  data=json.dumps({
                      'sheet_id': sheet_a, 'row': 0, 'col': 0, 'prompt': 'x',
                      'image_data': 'not_a_data_url_at_all',
                  }))
        assert r.status_code == 400

    def test_upload_no_image_data_field_returns_400(self, client_a, sheet_a,
                                                    image_dir):
        r = _json(client_a, 'post', '/api/upload-sticker/',
                  data=json.dumps({
                      'sheet_id': sheet_a, 'row': 0, 'col': 0,
                      'prompt': 'x', 'image_data': '',
                  }))
        assert r.status_code == 400

    def test_provider_set_to_unexpected_value_returns_400(self, client_a):
        r = _json(client_a, 'post', '/api/user/provider/',
                  data=json.dumps({'provider': 'openrouter'}))
        # 'openrouter' is NOT in the allowed set {'pollinations', 'puter'}
        assert r.status_code == 400

    def test_rename_sheet_too_long_returns_400(self, client_a, sheet_a):
        r = _json(client_a, 'post', '/api/rename-sheet/',
                  data=json.dumps({'sheet_id': sheet_a, 'name': 'X' * 201}))
        assert r.status_code == 400


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Security response headers (flask.md §10 / OWASP / NIST SP 800-53 SC)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSecurityHeaders:
    """Every response must carry the required security headers."""

    def _get_headers(self, client):
        r = client.get('/login/')
        return r.headers

    def test_x_content_type_options_nosniff(self, client):
        headers = self._get_headers(client)
        assert headers.get('X-Content-Type-Options') == 'nosniff'

    def test_x_frame_options_deny(self, client):
        headers = self._get_headers(client)
        assert headers.get('X-Frame-Options') == 'DENY'

    def test_referrer_policy_set(self, client):
        headers = self._get_headers(client)
        assert headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'

    def test_content_security_policy_present(self, client):
        headers = self._get_headers(client)
        csp = headers.get('Content-Security-Policy', '')
        assert "default-src 'self'" in csp

    def test_csp_frame_ancestors_none(self, client):
        headers = self._get_headers(client)
        csp = headers.get('Content-Security-Policy', '')
        assert "frame-ancestors 'none'" in csp

    def test_headers_present_on_api_response(self, client_a, sheet_a):
        r = _json(client_a, 'post', '/api/rename-sheet/',
                  data=json.dumps({'sheet_id': sheet_a, 'name': 'Test'}))
        assert r.headers.get('X-Content-Type-Options') == 'nosniff'
        assert r.headers.get('X-Frame-Options') == 'DENY'


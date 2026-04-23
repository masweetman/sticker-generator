"""
Integration tests for the Flask-Admin panel.
  GET /admin/          ← index
  GET /admin/settings/ ← SettingsView
  GET /admin/user/     ← UserView
"""
import pytest
from app import app as flask_app


class TestAdminAccess:
    def test_unauthenticated_redirects(self, client):
        r = client.get('/admin/', follow_redirects=False)
        # Flask-Admin returns 302 → login page for unauthenticated visitors
        assert r.status_code in (301, 302)

    def test_non_admin_user_cannot_access_admin(self, client_a):
        r = client_a.get('/admin/', follow_redirects=False)
        # SecureAdminIndexView redirects non-admins to the login page
        assert r.status_code in (301, 302)
        location = r.headers.get('Location', '')
        assert '/login' in location or '/admin' not in location

    def test_admin_user_can_access_admin_index(self, admin_client):
        r = admin_client.get('/admin/', follow_redirects=True)
        assert r.status_code == 200

    def test_non_admin_cannot_access_settings(self, client_a):
        r = client_a.get('/admin/settings/', follow_redirects=False)
        assert r.status_code in (301, 302, 403)

    def test_admin_can_access_settings(self, admin_client):
        r = admin_client.get('/admin/settings/', follow_redirects=True)
        assert r.status_code == 200

    def test_non_admin_cannot_access_user_list(self, client_a):
        r = client_a.get('/admin/user/', follow_redirects=False)
        assert r.status_code in (301, 302, 403)

    def test_admin_can_access_user_list(self, admin_client):
        r = admin_client.get('/admin/user/', follow_redirects=True)
        assert r.status_code == 200

    def test_admin_can_access_sticker_sheet_list(self, admin_client):
        r = admin_client.get('/admin/stickersheet/', follow_redirects=True)
        assert r.status_code == 200

    def test_admin_can_access_sheet_list(self, admin_client):
        """StickerSheet (not Sticker) is registered with the admin under /admin/stickersheet/."""
        r = admin_client.get('/admin/stickersheet/', follow_redirects=True)
        assert r.status_code == 200

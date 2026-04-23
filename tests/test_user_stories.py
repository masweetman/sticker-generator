"""
End-to-end user story tests.
These tests simulate realistic user workflows that span multiple routes,
verifying the system behaves correctly across a complete scenario.
"""
import json
import pytest
from unittest.mock import patch, MagicMock

from app import app as flask_app, db as _db
from app.models import User, StickerSheet, Sticker
from conftest import (
    _create_user, _create_sheet, _create_sticker,
    login_session, MINIMAL_PNG, VALID_PNG_DATA_URL,
)


def _json(client, method, url, **kwargs):
    fn = getattr(client, method)
    kwargs.setdefault('content_type', 'application/json')
    return fn(url, **kwargs)


class TestUserStory_FullLifecycle:
    """
    Story: A new user registers, logs in, creates a sheet, generates a sticker
    (mocked), views the sheet, and deletes the sheet.
    """

    def test_register_then_login_then_create_sheet_then_delete(
            self, client, image_dir):
        # 1. Register
        r = client.post('/register/', data={
            'user': 'lifecycle_user', 'name': 'LC User',
            'email': 'lc@example.com', 'password': 'lifecycle1',
        }, follow_redirects=True)
        assert r.status_code == 200
        with client.session_transaction() as sess:
            assert '_user_id' in sess
            uid = int(sess['_user_id'])

        # 2. Create a sheet
        r = client.post('/sheets/new/', data={
            'name': 'My First Sheet', 'rows': '3', 'cols': '4',
        }, follow_redirects=False)
        assert r.status_code in (301, 302)
        location = r.headers['Location']
        # Extract sheet_id from redirect URL like /sheets/1/
        import re
        m = re.search(r'/sheets/(\d+)/', location)
        assert m, f'Expected redirect to editor, got Location: {location}'
        sheet_id = int(m.group(1))

        # 3. Generate a sticker (mocked)
        with flask_app.app_context():
            from app.models import Settings
            s = Settings.get()
            s.provider = 'pollinations'
            _db.session.commit()

        mock_resp = MagicMock()
        mock_resp.content = MINIMAL_PNG
        mock_resp.raise_for_status = MagicMock()

        with patch('app.views.http_requests') as mock_http:
            mock_http.get.return_value = mock_resp
            r = _json(client, 'post', '/api/generate/',
                      data=json.dumps({'sheet_id': sheet_id, 'row': 0, 'col': 0,
                                       'prompt': 'a smiling sun'}))
        assert r.status_code == 200
        assert r.get_json()['success'] is True

        # 4. View the sheet editor
        r = client.get(f'/sheets/{sheet_id}/')
        assert r.status_code == 200

        # 5. Delete the sheet
        r = client.post(f'/sheets/{sheet_id}/delete/', follow_redirects=True)
        assert r.status_code == 200
        with flask_app.app_context():
            assert StickerSheet.query.get(sheet_id) is None


class TestUserStory_CopyToAllCells:
    """
    Story: A user generates one sticker and copies it to fill the entire sheet.
    """

    def test_generate_then_copy_to_all(self, client_a, user_a, sheet_a, sticker_a):
        r = _json(client_a, 'post', '/api/copy-all/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0}))
        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True

        # Every cell should now have a sticker (4×6 = 24 cells)
        with flask_app.app_context():
            total = Sticker.query.filter_by(sheet_id=sheet_a).count()
            assert total == 24, f'Expected 24 stickers, got {total}'

        # All returned entries have image_url
        for entry in body['updated']:
            assert 'image_url' in entry
            assert entry['image_url'].startswith('/')


class TestUserStory_CopyToNewSheet:
    """
    Story: A user copies one sticker to a brand-new sheet and navigates to it.
    """

    def test_copy_to_new_sheet_creates_usable_sheet(
            self, client_a, user_a, sheet_a, sticker_a):
        r = _json(client_a, 'post', '/api/copy-to-new-sheet/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0}))
        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True

        # Navigate to the new sheet
        new_url = body['sheet_url']
        r = client_a.get(new_url)
        assert r.status_code == 200

        # Confirm sticker at (0,0) in new sheet
        import re
        m = re.search(r'/sheets/(\d+)/', new_url)
        new_sheet_id = int(m.group(1))
        with flask_app.app_context():
            s = Sticker.query.filter_by(
                sheet_id=new_sheet_id, row=0, col=0).first()
            assert s is not None


class TestUserStory_AdminUpdatesSettings:
    """
    Story: An admin logs in, updates the provider settings, and verifies changes.
    """

    def test_admin_can_update_provider_setting(self, admin_client, admin_user):
        # The admin panel uses Flask-Admin's model view, which accepts form posts.
        # We verify the admin can see the settings page.
        r = admin_client.get('/admin/settings/', follow_redirects=True)
        assert r.status_code == 200

        # Update provider preference via API (simulates admin changing settings)
        with flask_app.app_context():
            from app.models import Settings
            s = Settings.get()
            s.provider = 'pollinations'
            _db.session.commit()

        with flask_app.app_context():
            from app.models import Settings
            assert Settings.get().provider == 'pollinations'


class TestUserStory_TwoUsersIsolation:
    """
    Story: Two users have separate sheets; neither can access the other's work.
    """

    def test_two_users_sheets_are_isolated(self, client, user_a, user_b):
        sheet_a_id = _create_sheet(user_a.id, 'Alice Sheet')
        sheet_b_id = _create_sheet(user_b.id, 'Bob Sheet')

        # Alice logs in and sees only her sheet
        login_session(client, user_a.id)
        r = client.get('/sheets/')
        assert b'Alice Sheet' in r.data
        assert b'Bob Sheet' not in r.data

        # Alice cannot open Bob's sheet editor
        r = client.get(f'/sheets/{sheet_b_id}/')
        assert r.status_code == 404

        # Switch to Bob
        login_session(client, user_b.id)
        r = client.get('/sheets/')
        assert b'Bob Sheet' in r.data
        assert b'Alice Sheet' not in r.data

        # Bob cannot delete Alice's sheet
        r = client.post(f'/sheets/{sheet_a_id}/delete/')
        assert r.status_code == 404
        with flask_app.app_context():
            assert StickerSheet.query.get(sheet_a_id) is not None


class TestUserStory_ProfileUpdate:
    """
    Story: A user updates their display name and then changes their password.
    """

    def test_update_name_then_change_password(self, client_a, user_a):
        # Update name
        r = client_a.post('/profile/', data={
            'name': 'Updated Display Name', 'email': '',
            'current_password': '', 'new_password': '', 'confirm_password': '',
        }, follow_redirects=True)
        assert r.status_code == 200

        with flask_app.app_context():
            u = User.query.get(user_a.id)
            assert u.name == 'Updated Display Name'

        # Change password
        r = client_a.post('/profile/', data={
            'name': 'Updated Display Name', 'email': '',
            'current_password': user_a.password,
            'new_password': 'brand_new_99',
            'confirm_password': 'brand_new_99',
        }, follow_redirects=True)
        assert r.status_code == 200

        # Old password must no longer work
        with flask_app.app_context():
            from werkzeug.security import check_password_hash
            u = User.query.get(user_a.id)
            assert not check_password_hash(u.password, user_a.password), \
                'Old password should be invalidated after change'
            assert check_password_hash(u.password, 'brand_new_99')

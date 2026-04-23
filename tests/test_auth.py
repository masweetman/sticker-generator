"""
Integration tests for authentication routes:
  GET/POST /login/, POST /register/, GET /logout/, GET/POST /profile/
"""
import pytest
from app import db as _db
from app.models import User
from werkzeug.security import check_password_hash
from conftest import _create_user, login_session


class TestLogin:
    def test_login_page_returns_200(self, client):
        r = client.get('/login/')
        assert r.status_code == 200
        assert b'Sign In' in r.data or b'sign' in r.data.lower()

    def test_login_valid_credentials_redirects_to_sheets(self, client, user_a):
        r = client.post('/login/', data={
            'user': user_a.username, 'password': user_a.password,
        }, follow_redirects=True)
        assert r.status_code == 200
        # Should land on sheets list page
        assert b'/sheets/' in r.request.url.encode() or b'sheet' in r.data.lower()

    def test_login_valid_credentials_sets_session(self, client, user_a):
        client.post('/login/', data={
            'user': user_a.username, 'password': user_a.password,
        })
        with client.session_transaction() as sess:
            assert '_user_id' in sess
            assert sess['_user_id'] == str(user_a.id)

    def test_login_wrong_password_stays_on_login_page(self, client, user_a):
        r = client.post('/login/', data={
            'user': user_a.username, 'password': 'totally_wrong',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b'Invalid' in r.data or b'invalid' in r.data

    def test_login_unknown_username_stays_on_login_page(self, client):
        r = client.post('/login/', data={
            'user': 'nobody', 'password': 'anything',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b'Invalid' in r.data or b'invalid' in r.data

    def test_login_does_not_set_session_on_failure(self, client, user_a):
        client.post('/login/', data={
            'user': user_a.username, 'password': 'wrong',
        })
        with client.session_transaction() as sess:
            assert '_user_id' not in sess

    def test_already_authenticated_redirects_away_from_login(self, client_a):
        r = client_a.get('/login/', follow_redirects=False)
        assert r.status_code in (301, 302)
        assert '/sheets/' in r.headers.get('Location', '')


class TestRegister:
    def test_register_page_returns_200(self, client):
        r = client.get('/register/')
        assert r.status_code == 200

    def test_register_new_user_creates_account(self, client):
        r = client.post('/register/', data={
            'user': 'newuser', 'name': 'New User',
            'email': 'new@example.com', 'password': 'strongpass',
        }, follow_redirects=True)
        assert r.status_code == 200
        # User should exist in the DB
        from app import app as flask_app
        with flask_app.app_context():
            u = User.query.filter_by(user='newuser').first()
            assert u is not None
            assert u.name == 'New User'

    def test_register_logs_in_after_success(self, client):
        client.post('/register/', data={
            'user': 'autolodin', 'name': '', 'email': '', 'password': 'somepass',
        })
        with client.session_transaction() as sess:
            assert '_user_id' in sess

    def test_register_duplicate_username_shows_error(self, client, user_a):
        r = client.post('/register/', data={
            'user': user_a.username, 'name': '', 'email': '',
            'password': 'anewpass',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b'taken' in r.data or b'already' in r.data.lower()

    def test_register_duplicate_username_does_not_create_second_user(self, client, user_a):
        from app import app as flask_app
        client.post('/register/', data={
            'user': user_a.username, 'name': '', 'email': '',
            'password': 'anewpass',
        })
        with flask_app.app_context():
            count = User.query.filter_by(user=user_a.username).count()
        assert count == 1

    def test_register_with_missing_username_stays_on_page(self, client):
        r = client.post('/register/', data={
            'user': '', 'name': 'X', 'email': '', 'password': 'pass',
        }, follow_redirects=True)
        assert r.status_code == 200
        # Should not have created a session
        with client.session_transaction() as sess:
            assert '_user_id' not in sess


class TestLogout:
    def test_logout_clears_session(self, client, user_a):
        login_session(client, user_a.id)
        client.get('/logout/', follow_redirects=False)
        with client.session_transaction() as sess:
            assert '_user_id' not in sess

    def test_logout_redirects_to_login(self, client_a):
        r = client_a.get('/logout/', follow_redirects=False)
        assert r.status_code in (301, 302)
        assert '/login' in r.headers.get('Location', '')


class TestProfile:
    def test_profile_unauthenticated_redirects_to_login(self, client):
        r = client.get('/profile/', follow_redirects=False)
        assert r.status_code in (301, 302)
        assert '/login' in r.headers.get('Location', '')

    def test_profile_authenticated_returns_200(self, client_a):
        r = client_a.get('/profile/')
        assert r.status_code == 200

    def test_profile_shows_username(self, client_a, user_a):
        r = client_a.get('/profile/')
        assert user_a.username.encode() in r.data

    def test_profile_update_name_persists(self, client_a, user_a):
        from app import app as flask_app
        r = client_a.post('/profile/', data={
            'name': 'Updated Name', 'email': '',
            'current_password': '', 'new_password': '', 'confirm_password': '',
        }, follow_redirects=True)
        assert r.status_code == 200
        with flask_app.app_context():
            u = User.query.get(user_a.id)
            assert u.name == 'Updated Name'

    def test_profile_update_email_persists(self, client_a, user_a):
        from app import app as flask_app
        client_a.post('/profile/', data={
            'name': user_a.username, 'email': 'updated@example.com',
            'current_password': '', 'new_password': '', 'confirm_password': '',
        }, follow_redirects=True)
        with flask_app.app_context():
            u = User.query.get(user_a.id)
            assert u.email == 'updated@example.com'

    def test_profile_password_change_with_correct_current(self, client_a, user_a):
        from app import app as flask_app
        r = client_a.post('/profile/', data={
            'name': user_a.username, 'email': '',
            'current_password': user_a.password,
            'new_password': 'newpass99',
            'confirm_password': 'newpass99',
        }, follow_redirects=True)
        assert r.status_code == 200
        with flask_app.app_context():
            u = User.query.get(user_a.id)
            assert check_password_hash(u.password, 'newpass99'), \
                'Password should have been updated'

    def test_profile_password_change_with_wrong_current_fails(self, client_a, user_a):
        from app import app as flask_app

        with flask_app.app_context():
            original_hash = User.query.get(user_a.id).password

        r = client_a.post('/profile/', data={
            'name': user_a.username, 'email': '',
            'current_password': 'WRONG_PASS',
            'new_password': 'newpass99',
            'confirm_password': 'newpass99',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b'incorrect' in r.data or b'wrong' in r.data.lower() \
               or b'Current password' in r.data

        with flask_app.app_context():
            u = User.query.get(user_a.id)
            assert u.password == original_hash, \
                'Password must not change when current password is wrong'

    def test_profile_email_duplicate_other_user_shows_error(self, client_a, user_a, user_b):
        # Give user_b an email first
        from app import app as flask_app
        with flask_app.app_context():
            u = User.query.get(user_b.id)
            u.email = 'taken@example.com'
            _db.session.commit()

        r = client_a.post('/profile/', data={
            'name': user_a.username, 'email': 'taken@example.com',
            'current_password': '', 'new_password': '', 'confirm_password': '',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b'already in use' in r.data or b'taken' in r.data.lower()

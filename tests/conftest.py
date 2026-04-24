"""
Shared pytest fixtures for the sticker-generator test suite.

All tests use an isolated SQLite test database (`instance/test_application.db`).
The app config is switched to TestingConfig before the app module is imported,
so _ensure_db_and_seed() seeds the *test* database, not the dev one.
CSRF is disabled globally; test_security.py has one targeted test that re-enables it.
"""
import os
import base64
import sys
from collections import namedtuple

# ── Switch to TestingConfig BEFORE importing the Flask app ──────────────────
os.environ.setdefault('FLASK_CONFIG', 'app.configuration.TestingConfig')

import pytest
from werkzeug.security import generate_password_hash

# Add project root to sys.path so `app` is importable from tests/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import app as flask_app, db as _db
from app.models import User, Settings, StickerSheet, Sticker, Image

# ── Minimal PNG (1×1 red pixel) used as fake sticker image in tests ─────────
MINIMAL_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk'
    '+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
)
VALID_PNG_DATA_URL = (
    'data:image/png;base64,'
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk'
    '+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
)

# ── Simple named tuple to carry user credentials between fixtures ────────────
UserCreds = namedtuple('UserCreds', ['id', 'username', 'password'])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Database lifecycle
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(scope='session', autouse=True)
def create_tables():
    """Create all tables once per test session, then drop + delete file."""
    with flask_app.app_context():
        _db.create_all()
    yield
    with flask_app.app_context():
        _db.drop_all()
    # Remove the test database file
    instance_dir = os.path.join(os.path.dirname(__file__), '..', 'instance')
    test_db = os.path.join(instance_dir, 'test_application.db')
    if os.path.exists(test_db):
        os.unlink(test_db)


@pytest.fixture(autouse=True)
def clean_db(create_tables):
    """
    Wipe all table rows after every test so each test starts with a clean slate.
    Using autouse=True means this applies to every test automatically.
    """
    yield
    with flask_app.app_context():
        _db.session.rollback()
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# App-context fixture (for unit/form tests that don't use the test client)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def app_ctx(clean_db):
    """Push an app context for tests that manipulate models directly."""
    ctx = flask_app.app_context()
    ctx.push()
    yield flask_app
    ctx.pop()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test client
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def client(clean_db):
    """Unauthenticated Flask test client."""
    return flask_app.test_client()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# User helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _create_user(username, password='password123', is_admin=False,
                 name=None, email=None):
    """Create a user in the DB and return a UserCreds namedtuple."""
    with flask_app.app_context():
        u = User(
            user=username,
            password=generate_password_hash(password),
            name=name or username,
            email=email,
            is_admin=is_admin,
        )
        _db.session.add(u)
        _db.session.commit()
        return UserCreds(id=u.id, username=username, password=password)


def login_session(client, user_id):
    """Inject a Flask-Login session without going through the login form."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


@pytest.fixture
def user_a(clean_db):
    return _create_user('user_a', 'pass_A_123')


@pytest.fixture
def user_b(clean_db):
    return _create_user('user_b', 'pass_B_123')


@pytest.fixture
def admin_user(clean_db):
    return _create_user('admin_user', 'admin_Pass1', is_admin=True)


@pytest.fixture
def client_a(client, user_a):
    """Test client pre-logged-in as user_a."""
    login_session(client, user_a.id)
    return client


@pytest.fixture
def client_b(client, user_b):
    """Test client pre-logged-in as user_b."""
    login_session(client, user_b.id)
    return client


@pytest.fixture
def admin_client(client, admin_user):
    """Test client pre-logged-in as admin_user."""
    login_session(client, admin_user.id)
    return client


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Sheet / sticker helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _create_sheet(user_id, name='Test Sheet', rows=4, cols=6):
    """Create a StickerSheet in the DB and return its id."""
    with flask_app.app_context():
        sheet = StickerSheet(user_id=user_id, name=name, rows=rows, cols=cols)
        _db.session.add(sheet)
        _db.session.commit()
        return sheet.id


def _create_sticker(sheet_id, row=0, col=0, prompt='a test sticker',
                    image_path=None):
    """Create an Image + Sticker record pair and return the sticker id."""
    with flask_app.app_context():
        rel = image_path or f'static/sticker_images/{sheet_id}/{row}_{col}_test.png'
        img = Image(prompt=prompt, image_path=rel)
        _db.session.add(img)
        _db.session.flush()
        s = Sticker(sheet_id=sheet_id, row=row, col=col, image_id=img.id)
        _db.session.add(s)
        _db.session.commit()
        return s.id


@pytest.fixture
def sheet_a(user_a, clean_db):
    """A StickerSheet owned by user_a; returns the sheet id."""
    return _create_sheet(user_a.id, 'Sheet A', rows=4, cols=6)


@pytest.fixture
def sheet_b(user_b, clean_db):
    """A StickerSheet owned by user_b; returns the sheet id."""
    return _create_sheet(user_b.id, 'Sheet B', rows=4, cols=6)


@pytest.fixture
def sticker_a(sheet_a, tmp_path, monkeypatch):
    """
    An Image + Sticker in sheet_a with a real PNG file on disk.
    Monkeypatches flask_app.root_path so the path resolves to tmp_path.
    """
    monkeypatch.setattr(flask_app, 'root_path', str(tmp_path))
    img_dir = tmp_path / 'static' / 'sticker_images' / str(sheet_a)
    img_dir.mkdir(parents=True)
    img_file = img_dir / '0_0_test.png'
    img_file.write_bytes(MINIMAL_PNG)
    rel = f'static/sticker_images/{sheet_a}/0_0_test.png'
    sid = _create_sticker(sheet_a, row=0, col=0, image_path=rel)
    return sid


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# File-system fixture for API tests that read/write sticker images
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def image_dir(tmp_path, monkeypatch):
    """
    Redirect all sticker image I/O to a temporary directory by overriding
    flask_app.root_path.  _sticker_path() uses current_app.root_path to build
    both the relative and absolute paths, so this covers all image operations.
    """
    monkeypatch.setattr(flask_app, 'root_path', str(tmp_path))
    (tmp_path / 'static' / 'sticker_images').mkdir(parents=True)
    yield tmp_path

"""
Unit tests for SQLAlchemy models: User, Settings, StickerSheet, Sticker.
All tests use the `app_ctx` fixture which pushes an app context and
rolls back / wipes the DB after each test.
"""
import pytest
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from app import db as _db
from app.models import User, Settings, StickerSheet, Sticker, DEFAULT_BOUNDING_PROMPT


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# User model
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestUserModel:
    def test_password_stored_as_hash_not_plaintext(self, app_ctx):
        u = User(user='alice', password=generate_password_hash('secret'))
        _db.session.add(u)
        _db.session.commit()
        stored = User.query.filter_by(user='alice').first()
        assert stored.password != 'secret', \
            'Password must be stored as a hash, never plaintext'

    def test_password_hash_is_verifiable(self, app_ctx):
        u = User(user='bob', password=generate_password_hash('hunter2'))
        _db.session.add(u)
        _db.session.commit()
        stored = User.query.filter_by(user='bob').first()
        assert check_password_hash(stored.password, 'hunter2')
        assert not check_password_hash(stored.password, 'wrong')

    def test_is_admin_defaults_to_false(self, app_ctx):
        u = User(user='carol', password=generate_password_hash('x'))
        _db.session.add(u)
        _db.session.commit()
        stored = User.query.filter_by(user='carol').first()
        assert stored.is_admin is False

    def test_is_admin_can_be_set_true(self, app_ctx):
        u = User(user='dave', password=generate_password_hash('x'), is_admin=True)
        _db.session.add(u)
        _db.session.commit()
        assert User.query.filter_by(user='dave').first().is_admin is True

    def test_is_authenticated_returns_true(self, app_ctx):
        u = User(user='eve', password=generate_password_hash('x'))
        _db.session.add(u)
        _db.session.commit()
        assert User.query.filter_by(user='eve').first().is_authenticated() is True

    def test_is_active_returns_true(self, app_ctx):
        u = User(user='frank', password=generate_password_hash('x'))
        _db.session.add(u)
        _db.session.commit()
        assert User.query.filter_by(user='frank').first().is_active() is True

    def test_is_anonymous_returns_false(self, app_ctx):
        u = User(user='grace', password=generate_password_hash('x'))
        _db.session.add(u)
        _db.session.commit()
        assert User.query.filter_by(user='grace').first().is_anonymous() is False

    def test_get_id_returns_string_of_pk(self, app_ctx):
        u = User(user='heidi', password=generate_password_hash('x'))
        _db.session.add(u)
        _db.session.commit()
        stored = User.query.filter_by(user='heidi').first()
        result = stored.get_id()
        assert isinstance(result, str)
        assert result == str(stored.id)

    def test_username_must_be_unique(self, app_ctx):
        _db.session.add(User(user='dup', password=generate_password_hash('x')))
        _db.session.commit()
        _db.session.add(User(user='dup', password=generate_password_hash('y')))
        with pytest.raises(IntegrityError):
            _db.session.commit()

    def test_repr_contains_username(self, app_ctx):
        u = User(user='ivan', password=generate_password_hash('x'))
        _db.session.add(u)
        _db.session.commit()
        assert 'ivan' in repr(User.query.filter_by(user='ivan').first())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Settings model
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSettingsModel:
    def test_get_creates_row_when_db_is_empty(self, app_ctx):
        assert Settings.query.count() == 0
        s = Settings.get()
        assert s is not None
        assert Settings.query.count() == 1

    def test_get_returns_same_row_on_repeated_calls(self, app_ctx):
        s1 = Settings.get()
        s2 = Settings.get()
        assert s1.id == s2.id == 1

    def test_get_does_not_duplicate_rows(self, app_ctx):
        Settings.get()
        Settings.get()
        Settings.get()
        assert Settings.query.count() == 1

    def test_default_bounding_prompt_contains_placeholder(self, app_ctx):
        s = Settings.get()
        assert '[INSERT SUBJECT HERE]' in s.bounding_prompt

    def test_default_bounding_prompt_matches_constant(self, app_ctx):
        s = Settings.get()
        assert s.bounding_prompt == DEFAULT_BOUNDING_PROMPT

    def test_default_provider_is_set(self, app_ctx):
        s = Settings.get()
        assert s.provider is not None
        assert len(s.provider) > 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# StickerSheet model
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestStickerSheetModel:
    def _make_user(self):
        u = User(user='owner', password=generate_password_hash('x'))
        _db.session.add(u)
        _db.session.commit()
        return u

    def test_sheet_persists_with_required_fields(self, app_ctx):
        u = self._make_user()
        sheet = StickerSheet(user_id=u.id, name='My Sheet', rows=3, cols=5)
        _db.session.add(sheet)
        _db.session.commit()
        stored = StickerSheet.query.filter_by(name='My Sheet').first()
        assert stored is not None
        assert stored.rows == 3
        assert stored.cols == 5

    def test_sheet_default_rows_is_4(self, app_ctx):
        u = self._make_user()
        sheet = StickerSheet(user_id=u.id, name='default-rows')
        _db.session.add(sheet)
        _db.session.commit()
        assert StickerSheet.query.filter_by(name='default-rows').first().rows == 4

    def test_sheet_default_cols_is_6(self, app_ctx):
        u = self._make_user()
        sheet = StickerSheet(user_id=u.id, name='default-cols')
        _db.session.add(sheet)
        _db.session.commit()
        assert StickerSheet.query.filter_by(name='default-cols').first().cols == 6

    def test_cascade_delete_removes_stickers(self, app_ctx):
        u = self._make_user()
        sheet = StickerSheet(user_id=u.id, name='cascade', rows=2, cols=2)
        _db.session.add(sheet)
        _db.session.commit()
        for r in range(2):
            for c in range(2):
                _db.session.add(Sticker(sheet_id=sheet.id, row=r, col=c,
                                        prompt='x'))
        _db.session.commit()
        assert Sticker.query.count() == 4
        _db.session.delete(sheet)
        _db.session.commit()
        assert Sticker.query.count() == 0, \
            'Deleting a sheet must cascade-delete all its stickers'

    def test_created_at_is_populated(self, app_ctx):
        u = self._make_user()
        sheet = StickerSheet(user_id=u.id, name='timestamp')
        _db.session.add(sheet)
        _db.session.commit()
        assert StickerSheet.query.filter_by(name='timestamp').first().created_at is not None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Sticker model
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestStickerModel:
    def _make_sheet(self):
        u = User(user='owner2', password=generate_password_hash('x'))
        _db.session.add(u)
        _db.session.commit()
        sheet = StickerSheet(user_id=u.id, name='S', rows=4, cols=4)
        _db.session.add(sheet)
        _db.session.commit()
        return sheet

    def test_sticker_persists_correctly(self, app_ctx):
        sheet = self._make_sheet()
        s = Sticker(sheet_id=sheet.id, row=1, col=2, prompt='cat')
        _db.session.add(s)
        _db.session.commit()
        stored = Sticker.query.filter_by(sheet_id=sheet.id, row=1, col=2).first()
        assert stored is not None
        assert stored.prompt == 'cat'

    def test_unique_constraint_same_cell_raises(self, app_ctx):
        sheet = self._make_sheet()
        _db.session.add(Sticker(sheet_id=sheet.id, row=0, col=0, prompt='first'))
        _db.session.commit()
        _db.session.add(Sticker(sheet_id=sheet.id, row=0, col=0, prompt='second'))
        with pytest.raises(IntegrityError):
            _db.session.commit()

    def test_same_position_different_sheets_is_allowed(self, app_ctx):
        sheet = self._make_sheet()
        u2 = User(user='owner3', password=generate_password_hash('x'))
        _db.session.add(u2)
        _db.session.commit()
        sheet2 = StickerSheet(user_id=u2.id, name='S2', rows=4, cols=4)
        _db.session.add(sheet2)
        _db.session.commit()
        _db.session.add(Sticker(sheet_id=sheet.id, row=0, col=0, prompt='a'))
        _db.session.add(Sticker(sheet_id=sheet2.id, row=0, col=0, prompt='b'))
        _db.session.commit()  # should not raise
        assert Sticker.query.count() == 2

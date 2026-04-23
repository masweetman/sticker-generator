"""
Unit tests for WTForms form classes.
Each test instantiates the form with explicit data and validates it.
The `app_ctx` fixture provides the required Flask application context
(FlaskForm needs an active app context for CSRF, even when disabled).
"""
import pytest
from app.forms import LoginForm, RegisterForm, StickerSheetForm, ProfileForm


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LoginForm
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestLoginForm:
    def test_valid_credentials_passes(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = LoginForm(MultiDict({'user': 'alice', 'password': 'secret'}))
        assert form.validate(), form.errors

    def test_missing_username_fails(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = LoginForm(MultiDict({'user': '', 'password': 'secret'}))
        assert not form.validate()
        assert 'user' in form.errors

    def test_missing_password_fails(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = LoginForm(MultiDict({'user': 'alice', 'password': ''}))
        assert not form.validate()
        assert 'password' in form.errors

    def test_both_fields_missing_fails(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = LoginForm(MultiDict({'user': '', 'password': ''}))
        assert not form.validate()
        assert 'user' in form.errors
        assert 'password' in form.errors


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RegisterForm
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestRegisterForm:
    def test_valid_registration_passes(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = RegisterForm(MultiDict({
            'user': 'bob', 'name': 'Bob', 'email': 'bob@example.com',
            'password': 'securepass',
        }))
        assert form.validate(), form.errors

    def test_missing_username_fails(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = RegisterForm(MultiDict({
            'user': '', 'name': 'Bob', 'email': 'bob@example.com',
            'password': 'securepass',
        }))
        assert not form.validate()
        assert 'user' in form.errors

    def test_missing_password_fails(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = RegisterForm(MultiDict({
            'user': 'carol', 'name': '', 'email': '',
            'password': '',
        }))
        assert not form.validate()
        assert 'password' in form.errors

    def test_name_and_email_are_optional(self, app_ctx):
        """Name and email are not required — blank should still pass."""
        from werkzeug.datastructures import MultiDict
        form = RegisterForm(MultiDict({
            'user': 'dave', 'name': '', 'email': '',
            'password': 'supersecure',
        }))
        assert form.validate(), form.errors


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# StickerSheetForm
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestStickerSheetForm:
    def test_valid_form_passes(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = StickerSheetForm(MultiDict({'name': 'My Sheet', 'rows': '4', 'cols': '6'}))
        assert form.validate(), form.errors

    def test_missing_name_fails(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = StickerSheetForm(MultiDict({'name': '', 'rows': '4', 'cols': '6'}))
        assert not form.validate()
        assert 'name' in form.errors

    def test_rows_below_minimum_fails(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = StickerSheetForm(MultiDict({'name': 'X', 'rows': '0', 'cols': '4'}))
        assert not form.validate()
        assert 'rows' in form.errors

    def test_rows_above_maximum_fails(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = StickerSheetForm(MultiDict({'name': 'X', 'rows': '11', 'cols': '4'}))
        assert not form.validate()
        assert 'rows' in form.errors

    def test_cols_below_minimum_fails(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = StickerSheetForm(MultiDict({'name': 'X', 'rows': '4', 'cols': '0'}))
        assert not form.validate()
        assert 'cols' in form.errors

    def test_cols_above_maximum_fails(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = StickerSheetForm(MultiDict({'name': 'X', 'rows': '4', 'cols': '11'}))
        assert not form.validate()
        assert 'cols' in form.errors

    def test_rows_at_minimum_boundary_passes(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = StickerSheetForm(MultiDict({'name': 'X', 'rows': '1', 'cols': '1'}))
        assert form.validate(), form.errors

    def test_rows_at_maximum_boundary_passes(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = StickerSheetForm(MultiDict({'name': 'X', 'rows': '10', 'cols': '10'}))
        assert form.validate(), form.errors


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ProfileForm
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestProfileForm:
    def test_all_optional_fields_blank_passes(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = ProfileForm(MultiDict({
            'name': '', 'email': '',
            'current_password': '', 'new_password': '', 'confirm_password': '',
        }))
        assert form.validate(), form.errors

    def test_passwords_mismatch_fails(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = ProfileForm(MultiDict({
            'name': '', 'email': '',
            'current_password': 'old',
            'new_password': 'newpass123',
            'confirm_password': 'different',
        }))
        assert not form.validate()
        assert 'new_password' in form.errors

    def test_passwords_match_passes(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = ProfileForm(MultiDict({
            'name': 'Alice', 'email': '',
            'current_password': 'oldpass',
            'new_password': 'newpass123',
            'confirm_password': 'newpass123',
        }))
        assert form.validate(), form.errors

    def test_new_password_too_short_fails(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = ProfileForm(MultiDict({
            'name': '', 'email': '',
            'current_password': 'old',
            'new_password': 'short',
            'confirm_password': 'short',
        }))
        assert not form.validate()
        assert 'new_password' in form.errors

    def test_new_password_exactly_8_chars_passes(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = ProfileForm(MultiDict({
            'name': '', 'email': '',
            'current_password': 'old',
            'new_password': 'exactly8',
            'confirm_password': 'exactly8',
        }))
        assert form.validate(), form.errors

    def test_name_over_500_chars_fails(self, app_ctx):
        from werkzeug.datastructures import MultiDict
        form = ProfileForm(MultiDict({
            'name': 'A' * 501, 'email': '',
            'current_password': '', 'new_password': '', 'confirm_password': '',
        }))
        assert not form.validate()
        assert 'name' in form.errors

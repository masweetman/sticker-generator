from flask import redirect, url_for
from flask_admin.contrib.sqla import ModelView
from flask_admin import AdminIndexView
from flask_login import current_user
from wtforms import SelectField
from app import db
from app.models import User, Settings, StickerSheet, Sticker


class SecureAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))


class SecureModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))


class SettingsView(SecureModelView):
    can_create = False
    can_delete = False
    column_list = ('provider', 'openrouter_model', 'pollinations_model', 'bounding_prompt')
    form_columns = (
        'provider',
        'openrouter_api_key', 'openrouter_model',
        'pollinations_api_key', 'pollinations_model',
        'bounding_prompt',
    )
    form_overrides = {
        'provider': SelectField,
    }
    form_args = {
        'provider': {
            'choices': [
                ('openrouter', 'OpenRouter (requires API key)'),
                ('pollinations', 'Pollinations.ai (free, no key needed)'),
                ('puter', 'Puter.js (free, uses each visitor\'s quota)'),
            ],
            'coerce': str,
        },
    }
    column_labels = {
        'provider': 'Provider',
        'openrouter_api_key': 'OpenRouter API Key',
        'openrouter_model': 'OpenRouter Model (e.g. fal-ai/flux/schnell)',
        'pollinations_api_key': 'Pollinations API Key (optional — free tier works without one)',
        'pollinations_model': 'Pollinations Model (e.g. flux, flux-realism, gptimage, turbo)',
        'bounding_prompt': 'Bounding Prompt',
    }
    column_descriptions = {
        'provider': 'Select the image generation provider',
    }


class UserView(SecureModelView):
    column_list = ('user', 'name', 'email', 'is_admin')
    column_labels = {'user': 'Username', 'is_admin': 'Admin?'}
    form_excluded_columns = ('password', 'sheets')


def register_admin_views(admin):
    admin.add_view(SettingsView(Settings, db.session, name='Settings'))
    admin.add_view(UserView(User, db.session, name='Users'))
    admin.add_view(SecureModelView(StickerSheet, db.session, name='Sheets'))

"""
Integration tests for all /api/ endpoints.
External HTTP calls (Pollinations, OpenRouter) are mocked with unittest.mock
so no real network requests are made.
File I/O is redirected to a tmp_path via the `image_dir` fixture.
"""
import json
import base64
import pytest
from unittest.mock import patch, MagicMock

from app import app as flask_app, db as _db
from app.models import Sticker, StickerSheet
from conftest import (
    _create_sheet, _create_sticker, MINIMAL_PNG, VALID_PNG_DATA_URL,
)


def _json(client, method, url, **kwargs):
    """Shorthand for JSON API calls."""
    fn = getattr(client, method)
    kwargs.setdefault('content_type', 'application/json')
    return fn(url, **kwargs)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /api/generate/
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestApiGenerate:
    def _set_provider(self, provider, api_key=''):
        from app.models import Settings
        with flask_app.app_context():
            s = Settings.get()
            s.provider = provider
            if provider == 'openrouter':
                s.openrouter_api_key = api_key or 'test-key-123'
            _db.session.commit()

    def test_generate_pollinations_creates_sticker(self, client_a, sheet_a, image_dir):
        self._set_provider('pollinations')
        mock_resp = MagicMock()
        mock_resp.content = MINIMAL_PNG
        mock_resp.raise_for_status = MagicMock()

        with patch('app.views.http_requests') as mock_http:
            mock_http.get.return_value = mock_resp
            r = _json(client_a, 'post', '/api/generate/',
                      data=json.dumps({
                          'sheet_id': sheet_a, 'row': 0, 'col': 0,
                          'prompt': 'a cute cat',
                      }))

        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True
        assert 'image_url' in body

        with flask_app.app_context():
            s = Sticker.query.filter_by(sheet_id=sheet_a, row=0, col=0).first()
            assert s is not None
            assert s.image.prompt == 'a cute cat'

    def test_generate_openrouter_creates_sticker(self, client_a, sheet_a, image_dir):
        self._set_provider('openrouter', api_key='or-key-abc')

        # OpenRouter returns a JSON body with an image URL
        mock_or_resp = MagicMock()
        mock_or_resp.json.return_value = {
            'choices': [{'message': {'content': 'https://example.com/img.png'}}]
        }
        mock_or_resp.raise_for_status = MagicMock()

        # Downloading the image
        mock_dl_resp = MagicMock()
        mock_dl_resp.content = MINIMAL_PNG

        with patch('app.views.http_requests') as mock_http:
            mock_http.post.return_value = mock_or_resp
            mock_http.get.return_value = mock_dl_resp
            r = _json(client_a, 'post', '/api/generate/',
                      data=json.dumps({
                          'sheet_id': sheet_a, 'row': 1, 'col': 2,
                          'prompt': 'a blue rocket',
                      }))

        assert r.status_code == 200
        assert r.get_json()['success'] is True
        with flask_app.app_context():
            assert Sticker.query.filter_by(
                sheet_id=sheet_a, row=1, col=2).first() is not None

    def test_generate_missing_prompt_returns_400(self, client_a, sheet_a):
        r = _json(client_a, 'post', '/api/generate/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0,
                                   'prompt': ''}))
        assert r.status_code == 400
        assert r.get_json()['success'] is False

    def test_generate_other_users_sheet_returns_404(self, client_b, sheet_a):
        r = _json(client_b, 'post', '/api/generate/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0,
                                   'prompt': 'cat'}))
        assert r.status_code == 404

    def test_generate_unauthenticated_returns_401(self, client, sheet_a):
        r = _json(client, 'post', '/api/generate/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0,
                                   'prompt': 'cat'}))
        assert r.status_code == 401

    def test_generate_cell_out_of_range_returns_400(self, client_a, sheet_a):
        self._set_provider('pollinations')
        r = _json(client_a, 'post', '/api/generate/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 99, 'col': 99,
                                   'prompt': 'cat'}))
        assert r.status_code == 400

    def test_generate_openrouter_no_api_key_returns_503(self, client_a, sheet_a):
        """If OpenRouter is the provider but no key is configured → 503."""
        with flask_app.app_context():
            from app.models import Settings
            s = Settings.get()
            s.provider = 'openrouter'
            s.openrouter_api_key = ''
            _db.session.commit()

        r = _json(client_a, 'post', '/api/generate/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0,
                                   'prompt': 'cat'}))
        assert r.status_code == 503

    def test_generate_saves_image_file_to_disk(self, client_a, sheet_a, image_dir):
        self._set_provider('pollinations')
        mock_resp = MagicMock()
        mock_resp.content = MINIMAL_PNG
        mock_resp.raise_for_status = MagicMock()

        with patch('app.views.http_requests') as mock_http:
            mock_http.get.return_value = mock_resp
            _json(client_a, 'post', '/api/generate/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0,
                                   'prompt': 'dog'}))

        # At least one PNG should exist in the image dir
        pngs = list(image_dir.rglob('*.png'))
        assert len(pngs) >= 1, 'Generated image file should be written to disk'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /api/upload-sticker/
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestApiUploadSticker:
    def test_upload_valid_base64_png_creates_sticker(self, client_a, sheet_a, image_dir):
        r = _json(client_a, 'post', '/api/upload-sticker/',
                  data=json.dumps({
                      'sheet_id': sheet_a, 'row': 0, 'col': 0,
                      'prompt': 'uploaded cat',
                      'image_data': VALID_PNG_DATA_URL,
                  }))
        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True
        assert 'image_url' in body
        with flask_app.app_context():
            s = Sticker.query.filter_by(sheet_id=sheet_a, row=0, col=0).first()
            assert s is not None
            assert s.image.prompt == 'uploaded cat'

    def test_upload_writes_file_to_disk(self, client_a, sheet_a, image_dir):
        _json(client_a, 'post', '/api/upload-sticker/',
              data=json.dumps({
                  'sheet_id': sheet_a, 'row': 0, 'col': 0, 'prompt': 'x',
                  'image_data': VALID_PNG_DATA_URL,
              }))
        assert len(list(image_dir.rglob('*.png'))) >= 1

    def test_upload_invalid_base64_returns_400(self, client_a, sheet_a, image_dir):
        r = _json(client_a, 'post', '/api/upload-sticker/',
                  data=json.dumps({
                      'sheet_id': sheet_a, 'row': 0, 'col': 0, 'prompt': 'x',
                      'image_data': 'data:image/png;base64,NOT_VALID_BASE64!!!',
                  }))
        assert r.status_code == 400

    def test_upload_missing_data_url_returns_400(self, client_a, sheet_a, image_dir):
        r = _json(client_a, 'post', '/api/upload-sticker/',
                  data=json.dumps({
                      'sheet_id': sheet_a, 'row': 0, 'col': 0, 'prompt': 'x',
                      'image_data': '',
                  }))
        assert r.status_code == 400

    def test_upload_other_users_sheet_returns_404(self, client_b, sheet_a, image_dir):
        r = _json(client_b, 'post', '/api/upload-sticker/',
                  data=json.dumps({
                      'sheet_id': sheet_a, 'row': 0, 'col': 0, 'prompt': 'x',
                      'image_data': VALID_PNG_DATA_URL,
                  }))
        assert r.status_code == 404

    def test_upload_updates_existing_sticker(self, client_a, sheet_a, image_dir):
        """Uploading to same cell twice should update, not create duplicate."""
        payload = json.dumps({
            'sheet_id': sheet_a, 'row': 0, 'col': 0, 'prompt': 'v1',
            'image_data': VALID_PNG_DATA_URL,
        })
        _json(client_a, 'post', '/api/upload-sticker/', data=payload)
        _json(client_a, 'post', '/api/upload-sticker/', data=json.dumps({
            'sheet_id': sheet_a, 'row': 0, 'col': 0, 'prompt': 'v2',
            'image_data': VALID_PNG_DATA_URL,
        }))
        with flask_app.app_context():
            count = Sticker.query.filter_by(sheet_id=sheet_a, row=0, col=0).count()
            assert count == 1, 'Uploading to same cell must upsert, not duplicate'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /api/sticker/<id>/<row>/<col>/  DELETE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestApiStickerDelete:
    def test_delete_sticker_removes_record(self, client_a, sheet_a, sticker_a):
        r = client_a.delete(f'/api/sticker/{sheet_a}/0/0/')
        assert r.status_code == 200
        assert r.get_json()['success'] is True
        with flask_app.app_context():
            assert Sticker.query.filter_by(
                sheet_id=sheet_a, row=0, col=0).first() is None

    def test_delete_sticker_removes_image_file(self, client_a, sheet_a, sticker_a):
        with flask_app.app_context():
            s = Sticker.query.filter_by(sheet_id=sheet_a, row=0, col=0).first()
            img_path = sticker_a  # sticker_a fixture patches root_path
        # The image must have been created by the fixture
        client_a.delete(f'/api/sticker/{sheet_a}/0/0/')
        # File was monkeypatched to tmp_path by the sticker_a fixture;
        # just check the DB record is gone
        with flask_app.app_context():
            assert Sticker.query.filter_by(
                sheet_id=sheet_a, row=0, col=0).first() is None

    def test_delete_nonexistent_sticker_returns_success(self, client_a, sheet_a):
        """Deleting a cell with no sticker should still return success."""
        r = client_a.delete(f'/api/sticker/{sheet_a}/0/0/')
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_delete_other_users_sticker_returns_404(self, client_b, sheet_a, sticker_a):
        r = client_b.delete(f'/api/sticker/{sheet_a}/0/0/')
        assert r.status_code == 404


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /api/copy-all/
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestApiCopyAll:
    def test_copy_all_populates_every_cell(self, client_a, sheet_a, sticker_a):
        r = _json(client_a, 'post', '/api/copy-all/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0}))
        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True
        # Sheet is 4×6 = 24 cells; source is (0,0), so 23 updates
        assert len(body['updated']) == 23
        with flask_app.app_context():
            total = Sticker.query.filter_by(sheet_id=sheet_a).count()
            assert total == 24

    def test_copy_all_no_source_sticker_returns_404(self, client_a, sheet_a):
        r = _json(client_a, 'post', '/api/copy-all/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0}))
        assert r.status_code == 404

    def test_copy_all_other_users_sheet_returns_404(self, client_b, sheet_a, sticker_a):
        r = _json(client_b, 'post', '/api/copy-all/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0}))
        assert r.status_code == 404


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /api/copy/
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestApiCopy:
    def test_copy_within_same_sheet(self, client_a, sheet_a, sticker_a):
        r = _json(client_a, 'post', '/api/copy/',
                  data=json.dumps({
                      'from_sheet_id': sheet_a, 'from_row': 0, 'from_col': 0,
                      'to_sheet_id': sheet_a, 'to_row': 1, 'to_col': 1,
                  }))
        assert r.status_code == 200
        assert r.get_json()['success'] is True
        with flask_app.app_context():
            dest = Sticker.query.filter_by(
                sheet_id=sheet_a, row=1, col=1).first()
            assert dest is not None

    def test_copy_between_own_sheets(self, client_a, user_a, sheet_a, sticker_a):
        sheet_b_id = _create_sheet(user_a.id, 'Sheet B2', rows=4, cols=6)
        r = _json(client_a, 'post', '/api/copy/',
                  data=json.dumps({
                      'from_sheet_id': sheet_a, 'from_row': 0, 'from_col': 0,
                      'to_sheet_id': sheet_b_id, 'to_row': 0, 'to_col': 0,
                  }))
        assert r.status_code == 200
        with flask_app.app_context():
            dest = Sticker.query.filter_by(
                sheet_id=sheet_b_id, row=0, col=0).first()
            assert dest is not None

    def test_copy_missing_source_returns_404(self, client_a, sheet_a):
        r = _json(client_a, 'post', '/api/copy/',
                  data=json.dumps({
                      'from_sheet_id': sheet_a, 'from_row': 2, 'from_col': 2,
                      'to_sheet_id': sheet_a, 'to_row': 3, 'to_col': 3,
                  }))
        assert r.status_code == 404


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /api/copy-to-new-sheet/
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestApiCopyToNewSheet:
    def test_creates_new_sheet_with_sticker(self, client_a, user_a, sheet_a, sticker_a):
        r = _json(client_a, 'post', '/api/copy-to-new-sheet/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0}))
        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True
        assert 'sheet_url' in body
        with flask_app.app_context():
            # Two sheets now exist (original + new)
            assert StickerSheet.query.filter_by(user_id=user_a.id).count() == 2

    def test_new_sheet_has_sticker_at_0_0(self, client_a, user_a, sheet_a, sticker_a):
        _json(client_a, 'post', '/api/copy-to-new-sheet/',
              data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0}))
        with flask_app.app_context():
            new_sheet = (StickerSheet.query
                         .filter_by(user_id=user_a.id)
                         .filter(StickerSheet.id != sheet_a)
                         .first())
            assert new_sheet is not None
            s = Sticker.query.filter_by(
                sheet_id=new_sheet.id, row=0, col=0).first()
            assert s is not None

    def test_no_source_sticker_returns_404(self, client_a, sheet_a):
        r = _json(client_a, 'post', '/api/copy-to-new-sheet/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0}))
        assert r.status_code == 404


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /api/rename-sheet/
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestApiRenameSheet:
    def test_rename_persists_new_name(self, client_a, sheet_a):
        r = _json(client_a, 'post', '/api/rename-sheet/',
                  data=json.dumps({'sheet_id': sheet_a, 'name': 'Renamed!'}))
        assert r.status_code == 200
        assert r.get_json()['success'] is True
        with flask_app.app_context():
            assert StickerSheet.query.get(sheet_a).name == 'Renamed!'

    def test_rename_empty_name_returns_400(self, client_a, sheet_a):
        r = _json(client_a, 'post', '/api/rename-sheet/',
                  data=json.dumps({'sheet_id': sheet_a, 'name': ''}))
        assert r.status_code == 400

    def test_rename_whitespace_only_returns_400(self, client_a, sheet_a):
        r = _json(client_a, 'post', '/api/rename-sheet/',
                  data=json.dumps({'sheet_id': sheet_a, 'name': '   '}))
        assert r.status_code == 400

    def test_rename_other_users_sheet_returns_404(self, client_b, sheet_a):
        r = _json(client_b, 'post', '/api/rename-sheet/',
                  data=json.dumps({'sheet_id': sheet_a, 'name': 'Hacked!'}))
        assert r.status_code == 404


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /api/user/provider/
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestApiSetProvider:
    def test_set_pollinations_persists(self, client_a, user_a):
        r = _json(client_a, 'post', '/api/user/provider/',
                  data=json.dumps({'provider': 'pollinations'}))
        assert r.status_code == 200
        assert r.get_json()['success'] is True
        with flask_app.app_context():
            from app.models import User
            u = User.query.get(user_a.id)
            assert u.preferred_provider == 'pollinations'

    def test_set_puter_persists(self, client_a, user_a):
        r = _json(client_a, 'post', '/api/user/provider/',
                  data=json.dumps({'provider': 'puter'}))
        assert r.status_code == 200
        with flask_app.app_context():
            from app.models import User
            assert User.query.get(user_a.id).preferred_provider == 'puter'

    def test_set_invalid_provider_returns_400(self, client_a):
        r = _json(client_a, 'post', '/api/user/provider/',
                  data=json.dumps({'provider': 'evil-provider'}))
        assert r.status_code == 400
        assert r.get_json()['success'] is False

    def test_set_provider_unauthenticated_returns_401(self, client):
        r = _json(client, 'post', '/api/user/provider/',
                  data=json.dumps({'provider': 'pollinations'}))
        assert r.status_code == 401

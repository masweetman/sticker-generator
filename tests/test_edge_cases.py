"""
Edge case tests — boundary conditions, unexpected inputs, and corner cases
that could plausibly break the app if not handled correctly.
"""
import json
import pytest
from unittest.mock import patch, MagicMock

from app import app as flask_app, db as _db
from app.models import User, StickerSheet, Sticker, Settings
from conftest import (
    _create_sheet, _create_sticker, MINIMAL_PNG, VALID_PNG_DATA_URL,
)


def _json(client, method, url, **kwargs):
    fn = getattr(client, method)
    kwargs.setdefault('content_type', 'application/json')
    return fn(url, **kwargs)


class TestGridBoundaries:
    def test_resize_to_1x1_only_keeps_corner_sticker(self, client_a, sheet_a):
        """Resize 4×6 → 1×1 must remove all stickers except (0,0)."""
        for r in range(4):
            for c in range(6):
                _create_sticker(sheet_a, row=r, col=c, prompt=f'{r},{c}')
        with flask_app.app_context():
            assert Sticker.query.filter_by(sheet_id=sheet_a).count() == 24

        client_a.post(f'/sheets/{sheet_a}/resize/',
                      data={'rows': '1', 'cols': '1'}, follow_redirects=True)

        with flask_app.app_context():
            remaining = Sticker.query.filter_by(sheet_id=sheet_a).all()
            assert len(remaining) == 1
            assert remaining[0].row == 0
            assert remaining[0].col == 0

    def test_create_sheet_max_dimensions(self, client_a, user_a):
        r = client_a.post('/sheets/new/', data={
            'name': 'Mega Sheet', 'rows': '10', 'cols': '10',
        }, follow_redirects=True)
        assert r.status_code == 200
        with flask_app.app_context():
            sheet = StickerSheet.query.filter_by(name='Mega Sheet').first()
            assert sheet is not None
            assert sheet.rows == 10
            assert sheet.cols == 10

    def test_resize_down_to_same_dimension_is_a_no_op(self, client_a, sheet_a):
        """Resizing to the same dimensions should not remove any stickers."""
        _create_sticker(sheet_a, row=0, col=0)
        client_a.post(f'/sheets/{sheet_a}/resize/',
                      data={'rows': '4', 'cols': '6'}, follow_redirects=True)
        with flask_app.app_context():
            assert Sticker.query.filter_by(sheet_id=sheet_a).count() == 1

    def test_generate_at_last_valid_cell(self, client_a, sheet_a, image_dir):
        """Row=3, col=5 is the last valid cell for a 4×6 sheet."""
        with flask_app.app_context():
            s = Settings.get()
            s.provider = 'pollinations'
            _db.session.commit()

        mock_resp = MagicMock()
        mock_resp.content = MINIMAL_PNG
        mock_resp.raise_for_status = MagicMock()

        with patch('app.views.http_requests') as mock_http:
            mock_http.get.return_value = mock_resp
            r = _json(client_a, 'post', '/api/generate/',
                      data=json.dumps({'sheet_id': sheet_a, 'row': 3, 'col': 5,
                                       'prompt': 'boundary sticker'}))
        assert r.status_code == 200
        assert r.get_json()['success'] is True


class TestUpsertBehavior:
    def test_regenerate_same_cell_does_not_create_duplicate(
            self, client_a, sheet_a, image_dir):
        """Generating twice on the same cell must update, not insert a second row."""
        with flask_app.app_context():
            s = Settings.get()
            s.provider = 'pollinations'
            _db.session.commit()

        mock_resp = MagicMock()
        mock_resp.content = MINIMAL_PNG
        mock_resp.raise_for_status = MagicMock()

        with patch('app.views.http_requests') as mock_http:
            mock_http.get.return_value = mock_resp
            _json(client_a, 'post', '/api/generate/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0,
                                   'prompt': 'first'}))
            _json(client_a, 'post', '/api/generate/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0,
                                   'prompt': 'second'}))

        with flask_app.app_context():
            count = Sticker.query.filter_by(
                sheet_id=sheet_a, row=0, col=0).count()
            s = Sticker.query.filter_by(
                sheet_id=sheet_a, row=0, col=0).first()
            assert count == 1, 'Duplicate sticker rows must not be created'
            assert s.prompt == 'second', 'Prompt should be updated on regenerate'

    def test_upload_twice_same_cell_upserts(self, client_a, sheet_a, image_dir):
        payload_1 = json.dumps({
            'sheet_id': sheet_a, 'row': 0, 'col': 0,
            'prompt': 'v1', 'image_data': VALID_PNG_DATA_URL,
        })
        payload_2 = json.dumps({
            'sheet_id': sheet_a, 'row': 0, 'col': 0,
            'prompt': 'v2', 'image_data': VALID_PNG_DATA_URL,
        })
        _json(client_a, 'post', '/api/upload-sticker/', data=payload_1)
        _json(client_a, 'post', '/api/upload-sticker/', data=payload_2)
        with flask_app.app_context():
            assert Sticker.query.filter_by(
                sheet_id=sheet_a, row=0, col=0).count() == 1


class TestMissingResources:
    def test_delete_sticker_with_missing_image_file_succeeds(
            self, client_a, sheet_a):
        """
        If a sticker's image file is missing from disk, the delete endpoint
        must still return success — OSError should be swallowed silently.
        """
        # Create sticker pointing to a file that doesn't exist
        _create_sticker(sheet_a, row=0, col=0,
                        image_path='static/sticker_images/999/nonexistent.png')
        r = client_a.delete(f'/api/sticker/{sheet_a}/0/0/')
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_generate_on_nonexistent_sheet_id_returns_404(self, client_a):
        with flask_app.app_context():
            s = Settings.get()
            s.provider = 'pollinations'
            _db.session.commit()
        r = _json(client_a, 'post', '/api/generate/',
                  data=json.dumps({'sheet_id': 99999, 'row': 0, 'col': 0,
                                   'prompt': 'cat'}))
        assert r.status_code in (400, 404)

    def test_copy_all_from_nonexistent_sheet_returns_404(self, client_a):
        r = _json(client_a, 'post', '/api/copy-all/',
                  data=json.dumps({'sheet_id': 99999, 'row': 0, 'col': 0}))
        assert r.status_code == 404


class TestSettingsEdgeCases:
    def test_settings_get_creates_defaults_in_empty_db(self, app_ctx):
        """If no Settings row exists, Settings.get() must create one with defaults."""
        assert Settings.query.count() == 0
        s = Settings.get()
        assert s is not None
        assert '[INSERT SUBJECT HERE]' in s.bounding_prompt
        assert Settings.query.count() == 1

    def test_settings_get_idempotent_across_multiple_calls(self, app_ctx):
        for _ in range(5):
            Settings.get()
        assert Settings.query.count() == 1


class TestRenameSheetEdgeCases:
    def test_rename_exactly_200_chars_is_accepted(self, client_a, sheet_a):
        name = 'A' * 200
        r = _json(client_a, 'post', '/api/rename-sheet/',
                  data=json.dumps({'sheet_id': sheet_a, 'name': name}))
        assert r.status_code == 200
        with flask_app.app_context():
            assert StickerSheet.query.get(sheet_a).name == name

    def test_rename_201_chars_is_rejected(self, client_a, sheet_a):
        r = _json(client_a, 'post', '/api/rename-sheet/',
                  data=json.dumps({'sheet_id': sheet_a, 'name': 'B' * 201}))
        assert r.status_code == 400

    def test_rename_whitespace_only_is_rejected(self, client_a, sheet_a):
        r = _json(client_a, 'post', '/api/rename-sheet/',
                  data=json.dumps({'sheet_id': sheet_a, 'name': '   \t\n  '}))
        assert r.status_code == 400

    def test_rename_to_valid_name_updates_response_body(self, client_a, sheet_a):
        r = _json(client_a, 'post', '/api/rename-sheet/',
                  data=json.dumps({'sheet_id': sheet_a, 'name': 'Fresh Name'}))
        body = r.get_json()
        assert body['name'] == 'Fresh Name'


class TestUploadEdgeCases:
    def test_upload_jpeg_data_url_accepted(self, client_a, sheet_a, image_dir):
        """JPEG MIME type should be accepted (ext_map covers image/jpeg)."""
        import base64
        # A minimal 1x1 JPEG
        tiny_jpeg = base64.b64encode(bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
            0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
            0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
            0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
            0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
            0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
            0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
            0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
            0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
            0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
            0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
            0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
            0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
            0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
            0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
            0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
            0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
            0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
            0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
            0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
            0x8A, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3, 0xA4,
            0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7,
            0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA,
            0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2, 0xE3,
            0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5,
            0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00,
            0x00, 0x3F, 0x00, 0xFB, 0xD8, 0xFF, 0xD9,
        ])).decode('ascii')
        jpeg_data_url = f'data:image/jpeg;base64,{tiny_jpeg}'
        r = _json(client_a, 'post', '/api/upload-sticker/',
                  data=json.dumps({
                      'sheet_id': sheet_a, 'row': 0, 'col': 0,
                      'prompt': 'jpeg test', 'image_data': jpeg_data_url,
                  }))
        # Should succeed (jpeg is in ext_map)
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_upload_cell_out_of_bounds_returns_400(self, client_a, sheet_a,
                                                   image_dir):
        """Row/col beyond sheet dimensions must be rejected."""
        r = _json(client_a, 'post', '/api/upload-sticker/',
                  data=json.dumps({
                      'sheet_id': sheet_a, 'row': 99, 'col': 99,
                      'prompt': 'x', 'image_data': VALID_PNG_DATA_URL,
                  }))
        assert r.status_code == 400

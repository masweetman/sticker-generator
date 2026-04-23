"""
Integration tests for sheet management routes:
  GET  /sheets/
  GET/POST /sheets/new/
  GET  /sheets/<id>/
  POST /sheets/<id>/delete/
  POST /sheets/<id>/resize/
"""
from pathlib import Path

import pytest
from app import app as flask_app, db as _db
from app.models import StickerSheet, Sticker
from conftest import _create_sheet, _create_sticker


class TestSheetsList:
    def test_unauthenticated_redirects_to_login(self, client):
        r = client.get('/sheets/', follow_redirects=False)
        assert r.status_code in (301, 302)
        assert '/login' in r.headers.get('Location', '')

    def test_authenticated_returns_200(self, client_a):
        r = client_a.get('/sheets/')
        assert r.status_code == 200

    def test_empty_list_shows_no_sheets(self, client_a):
        r = client_a.get('/sheets/')
        assert r.status_code == 200
        # No sheet cards rendered
        assert b'<table' not in r.data or b'Sheet A' not in r.data

    def test_only_own_sheets_are_shown(self, client_a, user_a, user_b):
        # Create one sheet for each user
        _create_sheet(user_a.id, 'User A Sheet')
        _create_sheet(user_b.id, 'User B Sheet')
        r = client_a.get('/sheets/')
        assert b'User A Sheet' in r.data
        assert b'User B Sheet' not in r.data

    def test_multiple_own_sheets_all_shown(self, client_a, user_a):
        _create_sheet(user_a.id, 'First')
        _create_sheet(user_a.id, 'Second')
        r = client_a.get('/sheets/')
        assert b'First' in r.data
        assert b'Second' in r.data


class TestSheetsNew:
    def test_new_page_unauthenticated_redirects(self, client):
        r = client.get('/sheets/new/', follow_redirects=False)
        assert r.status_code in (301, 302)

    def test_new_page_returns_200(self, client_a):
        r = client_a.get('/sheets/new/')
        assert r.status_code == 200

    def test_create_sheet_redirects_to_editor(self, client_a, user_a):
        r = client_a.post('/sheets/new/', data={
            'name': 'Brand New Sheet', 'rows': '3', 'cols': '5',
        }, follow_redirects=False)
        assert r.status_code in (301, 302)
        assert '/sheets/' in r.headers.get('Location', '')

    def test_create_sheet_persists_in_db(self, client_a, user_a):
        client_a.post('/sheets/new/', data={
            'name': 'Persist Me', 'rows': '2', 'cols': '4',
        }, follow_redirects=True)
        with flask_app.app_context():
            sheet = StickerSheet.query.filter_by(name='Persist Me').first()
            assert sheet is not None
            assert sheet.rows == 2
            assert sheet.cols == 4
            assert sheet.user_id == user_a.id

    def test_create_sheet_missing_name_stays_on_form(self, client_a):
        r = client_a.post('/sheets/new/', data={
            'name': '', 'rows': '4', 'cols': '6',
        }, follow_redirects=True)
        assert r.status_code == 200
        # Should not have created a sheet
        with flask_app.app_context():
            assert StickerSheet.query.count() == 0


class TestSheetsEditor:
    def test_editor_unauthenticated_redirects(self, client, sheet_a):
        r = client.get(f'/sheets/{sheet_a}/', follow_redirects=False)
        assert r.status_code in (301, 302)

    def test_editor_own_sheet_returns_200(self, client_a, sheet_a):
        r = client_a.get(f'/sheets/{sheet_a}/')
        assert r.status_code == 200

    def test_editor_other_users_sheet_returns_404(self, client_b, sheet_a):
        r = client_b.get(f'/sheets/{sheet_a}/')
        assert r.status_code == 404

    def test_editor_nonexistent_sheet_returns_404(self, client_a):
        r = client_a.get('/sheets/99999/')
        assert r.status_code == 404

    def test_editor_shows_sheet_name(self, client_a, sheet_a):
        r = client_a.get(f'/sheets/{sheet_a}/')
        assert b'Sheet A' in r.data


class TestSheetsDelete:
    def test_delete_own_sheet_removes_it(self, client_a, sheet_a):
        r = client_a.post(f'/sheets/{sheet_a}/delete/', follow_redirects=True)
        assert r.status_code == 200
        with flask_app.app_context():
            assert StickerSheet.query.get(sheet_a) is None

    def test_delete_own_sheet_redirects_to_list(self, client_a, sheet_a):
        r = client_a.post(f'/sheets/{sheet_a}/delete/', follow_redirects=False)
        assert r.status_code in (301, 302)
        assert '/sheets/' in r.headers.get('Location', '')

    def test_delete_other_users_sheet_returns_404(self, client_b, sheet_a):
        r = client_b.post(f'/sheets/{sheet_a}/delete/')
        assert r.status_code == 404

    def test_delete_other_users_sheet_does_not_delete_it(self, client_b, sheet_a):
        client_b.post(f'/sheets/{sheet_a}/delete/')
        with flask_app.app_context():
            assert StickerSheet.query.get(sheet_a) is not None

    def test_delete_nonexistent_sheet_returns_404(self, client_a):
        r = client_a.post('/sheets/99999/delete/')
        assert r.status_code == 404


class TestSheetsResize:
    def test_resize_own_sheet_updates_dimensions(self, client_a, sheet_a):
        r = client_a.post(f'/sheets/{sheet_a}/resize/',
                          data={'rows': '2', 'cols': '3'},
                          follow_redirects=True)
        assert r.status_code == 200
        with flask_app.app_context():
            sheet = StickerSheet.query.get(sheet_a)
            assert sheet.rows == 2
            assert sheet.cols == 3

    def test_resize_other_users_sheet_returns_404(self, client_b, sheet_a):
        r = client_b.post(f'/sheets/{sheet_a}/resize/',
                          data={'rows': '2', 'cols': '2'})
        assert r.status_code == 404

    def test_resize_below_minimum_clamps_to_1(self, client_a, sheet_a):
        """The view clamps to max(1, min(10, value)), so 0 becomes 1."""
        client_a.post(f'/sheets/{sheet_a}/resize/',
                      data={'rows': '0', 'cols': '0'},
                      follow_redirects=True)
        with flask_app.app_context():
            sheet = StickerSheet.query.get(sheet_a)
            assert sheet.rows >= 1
            assert sheet.cols >= 1

    def test_resize_above_maximum_clamps_to_10(self, client_a, sheet_a):
        client_a.post(f'/sheets/{sheet_a}/resize/',
                      data={'rows': '99', 'cols': '99'},
                      follow_redirects=True)
        with flask_app.app_context():
            sheet = StickerSheet.query.get(sheet_a)
            assert sheet.rows <= 10
            assert sheet.cols <= 10

    def test_resize_removes_out_of_bounds_stickers(self, client_a, sheet_a):
        # Sheet starts at 4×6; place stickers at row=3,col=5 (in-bounds)
        # and row=3,col=5 will be out-of-bounds if we resize to 2×2
        _create_sticker(sheet_a, row=0, col=0, prompt='keep')
        _create_sticker(sheet_a, row=3, col=5, prompt='drop')

        client_a.post(f'/sheets/{sheet_a}/resize/',
                      data={'rows': '2', 'cols': '2'},
                      follow_redirects=True)
        with flask_app.app_context():
            remaining = Sticker.query.filter_by(sheet_id=sheet_a).all()
            positions = [(s.row, s.col) for s in remaining]
            assert (0, 0) in positions, 'In-bounds sticker should survive resize'
            assert (3, 5) not in positions, 'Out-of-bounds sticker must be removed'

    def test_resize_invalid_value_redirects_with_error(self, client_a, sheet_a):
        """Non-integer value: view catches ValueError and flashes error."""
        r = client_a.post(f'/sheets/{sheet_a}/resize/',
                          data={'rows': 'abc', 'cols': '4'},
                          follow_redirects=True)
        assert r.status_code == 200
        assert b'Invalid' in r.data or b'invalid' in r.data.lower()


class TestSheetsPrintRegression:
    def test_print_css_does_not_use_viewport_height(self):
        css_path = Path(flask_app.root_path) / 'static' / 'css' / 'sheet.css'
        css = css_path.read_text(encoding='utf-8')

        assert '@media print' in css
        assert 'height: 100vh;' not in css

    def test_print_css_forces_sheet_viewport_visible(self):
        css_path = Path(flask_app.root_path) / 'static' / 'css' / 'sheet.css'
        css = css_path.read_text(encoding='utf-8')

        # Mobile rules hide the viewport with !important; print must override that.
        assert '.sheet-viewport {' in css
        assert 'display: block !important;' in css

    def test_editor_uses_guarded_print_action(self, client_a, sheet_a):
        r = client_a.get(f'/sheets/{sheet_a}/')
        assert r.status_code == 200

        # Avoid direct print calls so JS can ensure print readiness first.
        assert b'onclick="window.print()"' not in r.data
        assert b'id="btn-print-sheet"' in r.data

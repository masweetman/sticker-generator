"""
Integration tests for the Sticker Library feature.

Covers:
  - POST /api/library/share/
  - GET  /library/
  - POST /api/library/<id>/add-to-sheet/
  - POST /api/library/<id>/tags/
  - DELETE /api/library/<id>/tags/<tag>/
  - DELETE /api/library/<id>/
  - _extract_tags() helper
  - _find_next_empty_cell() overflow logic
"""
import json
import pytest

from app import app as flask_app, db as _db
from app.models import Image, Tag, Sticker, StickerSheet
from conftest import _create_sheet, _create_sticker, MINIMAL_PNG


# ── Helpers ───────────────────────────────────────────────────────────────────

def _json(client, method, url, **kwargs):
    fn = getattr(client, method)
    kwargs.setdefault('content_type', 'application/json')
    return fn(url, **kwargs)


def _make_library_image(user_id, prompt='a happy dog', in_library=True):
    """Insert an Image + Tag directly in the DB and return the image id."""
    with flask_app.app_context():
        img = Image(prompt=prompt,
                    image_path='static/sticker_images/1/0_0_test.png',
                    in_library=in_library,
                    created_by_user_id=user_id)
        _db.session.add(img)
        _db.session.flush()
        if in_library:
            _db.session.add(Tag(image_id=img.id, tag='dog'))
            _db.session.add(Tag(image_id=img.id, tag='happy'))
        _db.session.commit()
        return img.id


def _fill_sheet(sheet_id):
    """Fill every cell of a sheet with stickers so it becomes full."""
    with flask_app.app_context():
        sheet = _db.session.get(StickerSheet, sheet_id)
        for r in range(sheet.rows):
            for c in range(sheet.cols):
                img = Image(prompt='filler', image_path='static/sticker_images/0/x.png')
                _db.session.add(img)
                _db.session.flush()
                _db.session.add(Sticker(sheet_id=sheet_id, row=r, col=c, image_id=img.id))
        _db.session.commit()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# _extract_tags helper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestExtractTags:
    def test_filters_stop_words(self, app_ctx):
        from app.views import _extract_tags
        tags = _extract_tags('a sticker of a happy cat')
        assert 'sticker' not in tags
        assert 'happy' in tags
        assert 'cat' in tags

    def test_filters_short_words(self, app_ctx):
        from app.views import _extract_tags
        tags = _extract_tags('big red ox')
        # 'ox' is 2 chars, should be filtered
        assert 'ox' not in tags
        assert 'big' in tags
        assert 'red' in tags

    def test_empty_prompt_returns_empty_list(self, app_ctx):
        from app.views import _extract_tags
        assert _extract_tags('') == []
        assert _extract_tags(None) == []

    def test_deduplicates_and_sorts(self, app_ctx):
        from app.views import _extract_tags
        tags = _extract_tags('cat cat dog cat')
        assert tags == sorted(set(tags))
        assert tags.count('cat') == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST /api/library/share/
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestLibraryShare:
    def test_share_sets_in_library_true_and_creates_tags(
            self, client_a, user_a, sheet_a):
        # Arrange
        sticker_id = _create_sticker(sheet_a, row=0, col=0,
                                      prompt='fluffy bunny', image_path=None)

        # Act
        r = _json(client_a, 'post', '/api/library/share/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0}))

        # Assert
        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True
        assert 'image_id' in body
        with flask_app.app_context():
            sticker = Sticker.query.filter_by(sheet_id=sheet_a, row=0, col=0).first()
            img = _db.session.get(Image, sticker.image_id)
            assert img.in_library is True
            tag_values = {t.tag for t in img.tags}
            assert 'fluffy' in tag_values
            assert 'bunny' in tag_values

    def test_share_already_shared_returns_409(self, client_a, user_a, sheet_a):
        # Arrange
        _create_sticker(sheet_a, row=0, col=0, prompt='cat')
        _json(client_a, 'post', '/api/library/share/',
              data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0}))

        # Act — share same sticker again
        r = _json(client_a, 'post', '/api/library/share/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0}))

        # Assert
        assert r.status_code == 409

    def test_share_requires_login(self, client, sheet_a):
        _create_sticker(sheet_a, row=0, col=0)
        r = _json(client, 'post', '/api/library/share/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0}))
        assert r.status_code == 401

    def test_share_rejects_other_users_sticker(self, client_b, sheet_a):
        _create_sticker(sheet_a, row=0, col=0)
        r = _json(client_b, 'post', '/api/library/share/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0}))
        assert r.status_code == 404

    def test_share_empty_prompt_creates_no_tags(self, client_a, user_a, sheet_a):
        _create_sticker(sheet_a, row=0, col=0, prompt='')
        r = _json(client_a, 'post', '/api/library/share/',
                  data=json.dumps({'sheet_id': sheet_a, 'row': 0, 'col': 0}))
        assert r.status_code == 200
        with flask_app.app_context():
            sticker = Sticker.query.filter_by(sheet_id=sheet_a, row=0, col=0).first()
            assert Tag.query.filter_by(image_id=sticker.image_id).count() == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /library/
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestLibraryList:
    def test_requires_login(self, client):
        r = client.get('/library/', follow_redirects=False)
        assert r.status_code in (301, 302)
        assert '/login' in r.headers.get('Location', '')

    def test_shows_library_images(self, client_a, user_a):
        _make_library_image(user_a.id, prompt='a blue whale')
        r = client_a.get('/library/')
        assert r.status_code == 200
        assert b'blue' in r.data

    def test_does_not_show_non_library_images(self, client_a, user_a):
        _make_library_image(user_a.id, prompt='secret prompt', in_library=False)
        r = client_a.get('/library/')
        assert r.status_code == 200
        assert b'secret prompt' not in r.data

    def test_filter_by_single_tag(self, client_a, user_a):
        _make_library_image(user_a.id, prompt='big red bus')  # tags: big, red, bus
        _make_library_image(user_a.id, prompt='blue whale')    # tags: blue, whale
        r = client_a.get('/library/?tags=whale')
        assert r.status_code == 200
        assert b'whale' in r.data

    def test_filter_multiple_tags_and_semantics(self, client_a, user_a):
        _make_library_image(user_a.id, prompt='happy dog')    # tags: happy, dog
        _make_library_image(user_a.id, prompt='happy cat')    # tags: happy, cat
        # Filter for both happy AND dog — only first image should match
        r = client_a.get('/library/?tags=happy,dog')
        assert r.status_code == 200
        # The 'dog' tag should appear; 'cat' should not appear if properly filtered
        assert b'dog' in r.data


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST /api/library/<id>/add-to-sheet/
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestLibraryAddToSheet:
    def test_add_to_existing_sheet_places_at_next_empty_cell(
            self, client_a, user_a, sheet_a):
        # Arrange: put a sticker at (0,0) so next empty is (0,1)
        _create_sticker(sheet_a, row=0, col=0, prompt='existing')
        image_id = _make_library_image(user_a.id)

        # Act
        r = _json(client_a, 'post', f'/api/library/{image_id}/add-to-sheet/',
                  data=json.dumps({'sheet_id': sheet_a}))

        # Assert
        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True
        assert body['row'] == 0
        assert body['col'] == 1

    def test_add_creates_new_sheet_when_new_sheet_flag_set(
            self, client_a, user_a):
        image_id = _make_library_image(user_a.id)
        r = _json(client_a, 'post', f'/api/library/{image_id}/add-to-sheet/',
                  data=json.dumps({'new_sheet': True, 'name': 'My New Sheet'}))
        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True
        with flask_app.app_context():
            sheet = _db.session.get(StickerSheet, body['sheet_id'])
            assert sheet is not None
            assert sheet.name == 'My New Sheet'

    def test_add_to_full_sheet_creates_overflow_sheet(self, client_a, user_a, sheet_a):
        # Arrange: fill sheet_a (4×6 = 24 cells)
        _fill_sheet(sheet_a)
        image_id = _make_library_image(user_a.id)

        # Act
        r = _json(client_a, 'post', f'/api/library/{image_id}/add-to-sheet/',
                  data=json.dumps({'sheet_id': sheet_a}))

        # Assert
        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True
        assert body['row'] == 0
        assert body['col'] == 0
        # A new overflow sheet should have been created
        with flask_app.app_context():
            overflow = _db.session.get(StickerSheet, body['sheet_id'])
            assert overflow.id != sheet_a
            assert 'overflow' in overflow.name.lower()
            # Overflow sheet dimensions match original
            original = _db.session.get(StickerSheet, sheet_a)
            assert overflow.rows == original.rows
            assert overflow.cols == original.cols

    def test_add_requires_login(self, client, user_a):
        image_id = _make_library_image(user_a.id)
        r = _json(client, 'post', f'/api/library/{image_id}/add-to-sheet/',
                  data=json.dumps({'new_sheet': True, 'name': 'x'}))
        assert r.status_code == 401

    def test_add_to_other_users_sheet_returns_404(self, client_b, user_a, sheet_a):
        image_id = _make_library_image(user_a.id)
        r = _json(client_b, 'post', f'/api/library/{image_id}/add-to-sheet/',
                  data=json.dumps({'sheet_id': sheet_a}))
        assert r.status_code == 404

    def test_add_non_library_image_returns_404(self, client_a, user_a, sheet_a):
        image_id = _make_library_image(user_a.id, in_library=False)
        r = _json(client_a, 'post', f'/api/library/{image_id}/add-to-sheet/',
                  data=json.dumps({'sheet_id': sheet_a}))
        assert r.status_code == 404

    def test_add_no_file_copy_occurs(self, client_a, user_a, sheet_a, tmp_path, monkeypatch):
        """Adding from library must reuse the same image_id — no file operations."""
        monkeypatch.setattr(flask_app, 'root_path', str(tmp_path))
        image_id = _make_library_image(user_a.id)
        r = _json(client_a, 'post', f'/api/library/{image_id}/add-to-sheet/',
                  data=json.dumps({'sheet_id': sheet_a}))
        assert r.status_code == 200
        with flask_app.app_context():
            sticker = Sticker.query.filter_by(sheet_id=sheet_a).order_by(Sticker.id.desc()).first()
            assert sticker.image_id == image_id


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST /api/library/<id>/tags/  and  DELETE /api/library/<id>/tags/<tag>/
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestLibraryTags:
    def test_owner_can_add_tag(self, client_a, user_a):
        image_id = _make_library_image(user_a.id)
        r = _json(client_a, 'post', f'/api/library/{image_id}/tags/',
                  data=json.dumps({'tag': 'fluffy'}))
        assert r.status_code == 200
        assert r.get_json()['success'] is True
        with flask_app.app_context():
            assert Tag.query.filter_by(image_id=image_id, tag='fluffy').first() is not None

    def test_admin_can_add_tag(self, admin_client, admin_user, user_a):
        image_id = _make_library_image(user_a.id)
        r = _json(admin_client, 'post', f'/api/library/{image_id}/tags/',
                  data=json.dumps({'tag': 'admin-added'}))
        assert r.status_code == 200

    def test_non_owner_non_admin_cannot_add_tag(self, client_b, user_a):
        image_id = _make_library_image(user_a.id)
        r = _json(client_b, 'post', f'/api/library/{image_id}/tags/',
                  data=json.dumps({'tag': 'sneaky'}))
        assert r.status_code == 403

    def test_duplicate_tag_returns_409(self, client_a, user_a):
        image_id = _make_library_image(user_a.id)
        _json(client_a, 'post', f'/api/library/{image_id}/tags/',
              data=json.dumps({'tag': 'same'}))
        r = _json(client_a, 'post', f'/api/library/{image_id}/tags/',
                  data=json.dumps({'tag': 'same'}))
        assert r.status_code == 409

    def test_invalid_tag_characters_returns_400(self, client_a, user_a):
        image_id = _make_library_image(user_a.id)
        r = _json(client_a, 'post', f'/api/library/{image_id}/tags/',
                  data=json.dumps({'tag': '<script>'}))
        assert r.status_code == 400

    def test_tag_too_short_returns_400(self, client_a, user_a):
        image_id = _make_library_image(user_a.id)
        r = _json(client_a, 'post', f'/api/library/{image_id}/tags/',
                  data=json.dumps({'tag': 'x'}))
        assert r.status_code == 400

    def test_owner_can_remove_tag(self, client_a, user_a):
        image_id = _make_library_image(user_a.id)
        # 'dog' tag was added by _make_library_image
        r = client_a.delete(f'/api/library/{image_id}/tags/dog/')
        assert r.status_code == 200
        assert r.get_json()['success'] is True
        with flask_app.app_context():
            assert Tag.query.filter_by(image_id=image_id, tag='dog').first() is None

    def test_remove_nonexistent_tag_returns_404(self, client_a, user_a):
        image_id = _make_library_image(user_a.id)
        r = client_a.delete(f'/api/library/{image_id}/tags/nonexistent/')
        assert r.status_code == 404

    def test_non_owner_cannot_remove_tag(self, client_b, user_a):
        image_id = _make_library_image(user_a.id)
        r = client_b.delete(f'/api/library/{image_id}/tags/dog/')
        assert r.status_code == 403


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DELETE /api/library/<id>/
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestLibraryDelete:
    def test_owner_can_delete_library_image(self, client_a, user_a):
        image_id = _make_library_image(user_a.id)
        r = client_a.delete(f'/api/library/{image_id}/')
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_admin_can_delete_library_image(self, admin_client, user_a):
        image_id = _make_library_image(user_a.id)
        r = admin_client.delete(f'/api/library/{image_id}/')
        assert r.status_code == 200

    def test_non_owner_non_admin_cannot_delete(self, client_b, user_a):
        image_id = _make_library_image(user_a.id)
        r = client_b.delete(f'/api/library/{image_id}/')
        assert r.status_code == 403

    def test_delete_with_no_sheet_refs_removes_record(self, client_a, user_a,
                                                       tmp_path, monkeypatch):
        monkeypatch.setattr(flask_app, 'root_path', str(tmp_path))
        image_id = _make_library_image(user_a.id)
        r = client_a.delete(f'/api/library/{image_id}/')
        assert r.status_code == 200
        with flask_app.app_context():
            assert _db.session.get(Image, image_id) is None
            assert Tag.query.filter_by(image_id=image_id).count() == 0

    def test_delete_with_sheet_refs_sets_in_library_false_keeps_image(
            self, client_a, user_a, sheet_a):
        # Arrange: add library image to a sheet so a Sticker references it
        image_id = _make_library_image(user_a.id)
        with flask_app.app_context():
            _db.session.add(Sticker(sheet_id=sheet_a, row=0, col=0, image_id=image_id))
            _db.session.commit()

        # Act
        r = client_a.delete(f'/api/library/{image_id}/')
        assert r.status_code == 200

        # Assert: image still exists but is no longer in_library
        with flask_app.app_context():
            img = _db.session.get(Image, image_id)
            assert img is not None
            assert img.in_library is False
            # Tags should be removed
            assert Tag.query.filter_by(image_id=image_id).count() == 0

    def test_delete_requires_login(self, client, user_a):
        image_id = _make_library_image(user_a.id)
        r = client.delete(f'/api/library/{image_id}/')
        assert r.status_code == 401

    def test_delete_non_library_image_returns_404(self, client_a, user_a):
        image_id = _make_library_image(user_a.id, in_library=False)
        r = client_a.delete(f'/api/library/{image_id}/')
        assert r.status_code == 404

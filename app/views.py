import os
import uuid
import requests as http_requests
from flask import (url_for, redirect, render_template, flash, g,
                   jsonify, request, abort, current_app)
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from app import app, lm, db
from app.forms import LoginForm, RegisterForm, StickerSheetForm, ProfileForm
from app.models import User, Settings, StickerSheet, Sticker


# ── Auth helpers ────────────────────────────────────────────────────────────

@app.before_request
def before_request():
    g.user = current_user


@lm.user_loader
def load_user(id):
    return db.session.get(User, int(id))


# ── Index ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('sheets_list'))
    return redirect(url_for('login'))


# ── Auth ─────────────────────────────────────────────────────────────────────

@app.route('/login/', methods=['GET', 'POST'])
def login():
    if g.user is not None and g.user.is_authenticated:
        return redirect(url_for('sheets_list'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(user=form.user.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            return redirect(url_for('sheets_list'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html', title='Sign In', form=form)


@app.route('/register/', methods=['GET', 'POST'])
def register():
    if g.user is not None and g.user.is_authenticated:
        return redirect(url_for('sheets_list'))
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(user=form.user.data).first():
            flash('Username already taken.', 'danger')
        else:
            u = User(
                user=form.user.data,
                name=form.name.data,
                email=form.email.data,
                password=generate_password_hash(form.password.data),
            )
            db.session.add(u)
            db.session.commit()
            login_user(u)
            return redirect(url_for('sheets_list'))
    return render_template('register.html', title='Register', form=form)


@app.route('/logout/')
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/profile/', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        # Password change requested
        if form.new_password.data:
            if not form.current_password.data:
                flash('Enter your current password to set a new one.', 'danger')
                return render_template('profile.html', form=form)
            if not check_password_hash(current_user.password, form.current_password.data):
                flash('Current password is incorrect.', 'danger')
                return render_template('profile.html', form=form)
            current_user.password = generate_password_hash(form.new_password.data)

        # Check email uniqueness if changed
        new_email = form.email.data.strip() or None
        if new_email and new_email != current_user.email:
            if User.query.filter(User.email == new_email, User.id != current_user.id).first():
                flash('That email address is already in use.', 'danger')
                return render_template('profile.html', form=form)

        current_user.name = form.name.data.strip() or None
        current_user.email = new_email
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('profile'))

    # Pre-populate fields on GET (obj=current_user handles name/email;
    # password fields should always be blank)
    form.current_password.data = ''
    form.new_password.data = ''
    form.confirm_password.data = ''
    return render_template('profile.html', form=form)


# ── Sheet management ──────────────────────────────────────────────────────────

@app.route('/sheets/')
@login_required
def sheets_list():
    sheets = StickerSheet.query.filter_by(user_id=current_user.id)\
                               .order_by(StickerSheet.created_at.desc()).all()
    return render_template('sheets/list.html', sheets=sheets)


@app.route('/sheets/new/', methods=['GET', 'POST'])
@login_required
def sheets_new():
    form = StickerSheetForm()
    if form.validate_on_submit():
        sheet = StickerSheet(
            user_id=current_user.id,
            name=form.name.data,
            rows=form.rows.data,
            cols=form.cols.data,
        )
        db.session.add(sheet)
        db.session.commit()
        return redirect(url_for('sheets_editor', sheet_id=sheet.id))
    return render_template('sheets/new.html', form=form)


@app.route('/sheets/<int:sheet_id>/')
@login_required
def sheets_editor(sheet_id):
    sheet = _get_own_sheet(sheet_id)
    stickers = {(s.row, s.col): s for s in sheet.stickers}
    resize_form = StickerSheetForm(obj=sheet)
    settings = Settings.get()
    # User's own preference overrides the admin default; fall back to admin setting
    effective_provider = current_user.preferred_provider or settings.provider or 'openrouter'
    return render_template('sheets/editor.html', sheet=sheet,
                           stickers=stickers, resize_form=resize_form,
                           provider=effective_provider,
                           bounding_prompt=settings.bounding_prompt)


@app.route('/sheets/<int:sheet_id>/delete/', methods=['POST'])
@login_required
def sheets_delete(sheet_id):
    sheet = _get_own_sheet(sheet_id)
    _delete_sheet_images(sheet)
    db.session.delete(sheet)
    db.session.commit()
    flash(f'"{sheet.name}" deleted.', 'success')
    return redirect(url_for('sheets_list'))


@app.route('/sheets/<int:sheet_id>/resize/', methods=['POST'])
@login_required
def sheets_resize(sheet_id):
    sheet = _get_own_sheet(sheet_id)
    try:
        new_rows = max(1, min(10, int(request.form['rows'])))
        new_cols = max(1, min(10, int(request.form['cols'])))
    except (KeyError, ValueError):
        flash('Invalid grid size.', 'danger')
        return redirect(url_for('sheets_editor', sheet_id=sheet_id))
    # Remove out-of-bounds stickers
    for sticker in list(sheet.stickers):
        if sticker.row >= new_rows or sticker.col >= new_cols:
            _delete_sticker_image(sticker)
            db.session.delete(sticker)
    sheet.rows = new_rows
    sheet.cols = new_cols
    db.session.commit()
    return redirect(url_for('sheets_editor', sheet_id=sheet_id))


# ── API: sticker generation / copy / delete ───────────────────────────────────

@app.route('/api/generate/', methods=['POST'])
@login_required
def api_generate():
    data = request.get_json(force=True)
    sheet_id = data.get('sheet_id')
    row = data.get('row')
    col = data.get('col')
    user_prompt = (data.get('prompt') or '').strip()

    if not user_prompt:
        return jsonify(success=False, error='Prompt is required.'), 400

    sheet = _get_own_sheet_or_400(sheet_id)
    if sheet is None:
        return jsonify(success=False, error='Sheet not found.'), 404

    if not (0 <= row < sheet.rows and 0 <= col < sheet.cols):
        return jsonify(success=False, error='Cell out of range.'), 400

    settings = Settings.get()
    provider = (current_user.preferred_provider or settings.provider or 'openrouter').lower()

    # Validate provider-specific config
    if provider == 'openrouter' and not settings.openrouter_api_key:
        return jsonify(success=False,
                       error='OpenRouter API key not configured. Ask your administrator.'), 503

    full_prompt = settings.bounding_prompt.replace('[INSERT SUBJECT HERE]', user_prompt)

    if provider == 'pollinations':
        # Pollinations: simple GET request that returns image bytes directly.
        # https://image.pollinations.ai/prompt/{encoded_prompt}?model=flux&key=KEY
        import urllib.parse
        encoded_prompt = urllib.parse.quote(full_prompt)
        params = {'nologo': 'true', 'width': '1024', 'height': '1024'}
        if settings.pollinations_model:
            params['model'] = settings.pollinations_model
        if settings.pollinations_api_key:
            params['key'] = settings.pollinations_api_key
        try:
            img_resp = http_requests.get(
                f'https://image.pollinations.ai/prompt/{encoded_prompt}',
                params=params,
                timeout=90,
            )
            img_resp.raise_for_status()
            img_data = img_resp.content
        except Exception as e:
            return jsonify(success=False, error=f'Image generation failed: {e}'), 502
    else:
        # OpenRouter: all models (including image generators) go through chat/completions.
        # The image URL is returned inside choices[0].message.content.
        try:
            resp = http_requests.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {settings.openrouter_api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': settings.openrouter_model,
                    'messages': [{'role': 'user', 'content': full_prompt}],
                },
                timeout=90,
            )
            resp.raise_for_status()
            result = resp.json()
            content = (result['choices'][0]['message']['content'] or '').strip()
            # Extract URL — model may return plain URL or markdown image ![alt](url)
            import re
            md_match = re.search(r'!\[.*?\]\((https?://\S+?)\)', content)
            url_match = re.search(r'https?://\S+', content)
            if md_match:
                image_url = md_match.group(1)
            elif url_match:
                image_url = url_match.group(0).rstrip(')')
            else:
                return jsonify(success=False,
                               error=f'No image URL in model response: {content[:300]}'), 502
        except Exception as e:
            return jsonify(success=False, error=f'Image generation failed: {e}'), 502

        # Download the image from the URL returned by OpenRouter
        try:
            img_data = http_requests.get(image_url, timeout=60).content
        except Exception as e:
            return jsonify(success=False, error=f'Failed to download image: {e}'), 502

    rel_path, abs_path = _sticker_path(sheet_id, row, col)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, 'wb') as f:
        f.write(img_data)

    # Upsert Sticker record
    sticker = Sticker.query.filter_by(sheet_id=sheet_id, row=row, col=col).first()
    if sticker is None:
        sticker = Sticker(sheet_id=sheet_id, row=row, col=col)
        db.session.add(sticker)
    sticker.prompt = user_prompt
    sticker.image_path = rel_path
    db.session.commit()

    return jsonify(success=True, image_url='/' + rel_path)


@app.route('/api/upload-sticker/', methods=['POST'])
@login_required
def api_upload_sticker():
    """Accept a client-side generated image (base64 data URL) and save it."""
    data = request.get_json(force=True)
    sheet_id = data.get('sheet_id')
    row = data.get('row')
    col = data.get('col')
    prompt = (data.get('prompt') or '').strip()
    image_data = data.get('image_data', '')

    sheet = _get_own_sheet_or_400(sheet_id)
    if sheet is None:
        return jsonify(success=False, error='Sheet not found.'), 404

    if not (isinstance(row, int) and isinstance(col, int)
            and 0 <= row < sheet.rows and 0 <= col < sheet.cols):
        return jsonify(success=False, error='Cell out of range.'), 400

    import base64
    import re as _re
    match = _re.match(r'data:(image/[^;]+);base64,(.+)', image_data, _re.DOTALL)
    if not match:
        return jsonify(success=False, error='Invalid image data.'), 400

    mime_type = match.group(1).lower()
    ext_map = {'image/png': 'png', 'image/jpeg': 'jpg',
               'image/webp': 'webp', 'image/gif': 'gif'}
    ext = ext_map.get(mime_type, 'png')

    try:
        img_bytes = base64.b64decode(match.group(2))
    except Exception:
        return jsonify(success=False, error='Failed to decode image data.'), 400

    rel_path, abs_path = _sticker_path(sheet_id, row, col, ext)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, 'wb') as f:
        f.write(img_bytes)

    sticker = Sticker.query.filter_by(sheet_id=sheet_id, row=row, col=col).first()
    if sticker is None:
        sticker = Sticker(sheet_id=sheet_id, row=row, col=col)
        db.session.add(sticker)
    sticker.prompt = prompt
    sticker.image_path = rel_path
    db.session.commit()

    return jsonify(success=True, image_url='/' + rel_path)


@app.route('/api/copy-all/', methods=['POST'])
@login_required
def api_copy_all():
    data = request.get_json(force=True)
    sheet_id = data.get('sheet_id')
    src_row = data.get('row')
    src_col = data.get('col')

    sheet = _get_own_sheet_or_400(sheet_id)
    if sheet is None:
        return jsonify(success=False, error='Sheet not found.'), 404

    src_sticker = Sticker.query.filter_by(
        sheet_id=sheet_id, row=src_row, col=src_col).first()
    if src_sticker is None or not src_sticker.image_path:
        return jsonify(success=False, error='Source sticker has no image.'), 404

    import shutil
    src_abs = os.path.join(current_app.root_path, src_sticker.image_path)
    updated = []
    for r in range(sheet.rows):
        for c in range(sheet.cols):
            if r == src_row and c == src_col:
                continue
            dst_rel, dst_abs = _sticker_path(sheet_id, r, c)
            os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
            shutil.copy2(src_abs, dst_abs)
            dst_sticker = Sticker.query.filter_by(
                sheet_id=sheet_id, row=r, col=c).first()
            if dst_sticker is None:
                dst_sticker = Sticker(sheet_id=sheet_id, row=r, col=c)
                db.session.add(dst_sticker)
            dst_sticker.prompt = src_sticker.prompt
            dst_sticker.image_path = dst_rel
            updated.append({'row': r, 'col': c, 'image_url': '/' + dst_rel})
    db.session.commit()
    return jsonify(success=True, updated=updated)


@app.route('/api/sticker/<int:sheet_id>/<int:row>/<int:col>/', methods=['DELETE'])
@login_required
def api_sticker_delete(sheet_id, row, col):
    sheet = _get_own_sheet_or_400(sheet_id)
    if sheet is None:
        return jsonify(success=False, error='Sheet not found.'), 404
    sticker = Sticker.query.filter_by(sheet_id=sheet_id, row=row, col=col).first()
    if sticker:
        _delete_sticker_image(sticker)
        db.session.delete(sticker)
        db.session.commit()
    return jsonify(success=True)


@app.route('/api/copy/', methods=['POST'])
@login_required
def api_copy():
    data = request.get_json(force=True)
    src_sheet_id = data.get('from_sheet_id')
    src_row = data.get('from_row')
    src_col = data.get('from_col')
    dst_sheet_id = data.get('to_sheet_id')
    dst_row = data.get('to_row')
    dst_col = data.get('to_col')

    src_sheet = _get_own_sheet_or_400(src_sheet_id)
    dst_sheet = _get_own_sheet_or_400(dst_sheet_id)
    if src_sheet is None or dst_sheet is None:
        return jsonify(success=False, error='Sheet not found.'), 404

    src_sticker = Sticker.query.filter_by(
        sheet_id=src_sheet_id, row=src_row, col=src_col).first()
    if src_sticker is None or not src_sticker.image_path:
        return jsonify(success=False, error='Source sticker has no image.'), 404

    # Copy the image file
    src_abs = os.path.join(current_app.root_path, src_sticker.image_path)
    dst_rel, dst_abs = _sticker_path(dst_sheet_id, dst_row, dst_col)
    os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
    import shutil
    shutil.copy2(src_abs, dst_abs)

    # Upsert destination sticker
    dst_sticker = Sticker.query.filter_by(
        sheet_id=dst_sheet_id, row=dst_row, col=dst_col).first()
    if dst_sticker is None:
        dst_sticker = Sticker(sheet_id=dst_sheet_id, row=dst_row, col=dst_col)
        db.session.add(dst_sticker)
    dst_sticker.prompt = src_sticker.prompt
    dst_sticker.image_path = dst_rel
    db.session.commit()

    return jsonify(success=True, image_url='/' + dst_rel)


# ── User preferences ──────────────────────────────────────────────────────────

@app.route('/api/rename-sheet/', methods=['POST'])
@login_required
def api_rename_sheet():
    data = request.get_json(force=True)
    sheet_id = data.get('sheet_id')
    new_name = (data.get('name') or '').strip()
    if not new_name:
        return jsonify(success=False, error='Name cannot be empty.'), 400
    if len(new_name) > 200:
        return jsonify(success=False, error='Name too long.'), 400
    sheet = _get_own_sheet_or_400(sheet_id)
    if sheet is None:
        return jsonify(success=False, error='Sheet not found.'), 404
    sheet.name = new_name
    db.session.commit()
    return jsonify(success=True, name=new_name)


@app.route('/api/copy-to-new-sheet/', methods=['POST'])
@login_required
def api_copy_to_new_sheet():
    data = request.get_json(force=True)
    sheet_id = data.get('sheet_id')
    src_row = data.get('row')
    src_col = data.get('col')

    src_sheet = _get_own_sheet_or_400(sheet_id)
    if src_sheet is None:
        return jsonify(success=False, error='Sheet not found.'), 404

    src_sticker = Sticker.query.filter_by(
        sheet_id=sheet_id, row=src_row, col=src_col).first()
    if src_sticker is None or not src_sticker.image_path:
        return jsonify(success=False, error='Source sticker has no image.'), 404

    # Create the new sheet
    new_sheet = StickerSheet(
        user_id=current_user.id,
        name=f'Copy of {src_sheet.name}',
        rows=src_sheet.rows,
        cols=src_sheet.cols,
    )
    db.session.add(new_sheet)
    db.session.flush()  # get new_sheet.id

    # Copy the image file to position (0, 0) in the new sheet
    import shutil
    src_abs = os.path.join(current_app.root_path, src_sticker.image_path)
    dst_rel, dst_abs = _sticker_path(new_sheet.id, 0, 0)
    os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
    shutil.copy2(src_abs, dst_abs)

    new_sticker = Sticker(sheet_id=new_sheet.id, row=0, col=0)
    new_sticker.prompt = src_sticker.prompt
    new_sticker.image_path = dst_rel
    db.session.add(new_sticker)
    db.session.commit()

    return jsonify(success=True, sheet_url=url_for('sheets_editor', sheet_id=new_sheet.id))


@app.route('/api/user/provider/', methods=['POST'])
@login_required
def api_set_user_provider():
    data = request.get_json(force=True)
    provider = (data.get('provider') or '').strip().lower()
    allowed = {'pollinations', 'puter'}
    if provider not in allowed:
        return jsonify(success=False, error='Invalid provider.'), 400
    current_user.preferred_provider = provider
    db.session.commit()
    return jsonify(success=True, provider=provider)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_own_sheet(sheet_id):
    sheet = db.session.get(StickerSheet, sheet_id)
    if sheet is None or sheet.user_id != current_user.id:
        abort(404)
    return sheet


def _get_own_sheet_or_400(sheet_id):
    if sheet_id is None:
        return None
    sheet = db.session.get(StickerSheet, int(sheet_id))
    if sheet is None or sheet.user_id != current_user.id:
        return None
    return sheet


def _sticker_path(sheet_id, row, col, ext='png'):
    filename = f'{row}_{col}_{uuid.uuid4().hex[:8]}.{ext}'
    rel = os.path.join('static', 'sticker_images', str(sheet_id), filename)
    abs_path = os.path.join(current_app.root_path, rel)
    return rel, abs_path


def _delete_sticker_image(sticker):
    if sticker.image_path:
        abs_path = os.path.join(current_app.root_path, sticker.image_path)
        try:
            os.remove(abs_path)
        except OSError:
            pass


def _delete_sheet_images(sheet):
    import shutil
    folder = os.path.join(current_app.root_path, 'static', 'sticker_images', str(sheet.id))
    try:
        shutil.rmtree(folder)
    except OSError:
        pass


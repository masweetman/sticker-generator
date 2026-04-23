# -*- encoding: utf-8 -*-
import os
import json
import logging
import click
from datetime import datetime, timezone
from flask import Flask, request as _flask_request
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_admin import Admin
from flask_admin.theme import Bootstrap4Theme
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)

app.config.from_object(os.environ.get('FLASK_CONFIG', 'app.configuration.DevelopmentConfig'))

bs = Bootstrap(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri='memory://',
)

lm = LoginManager()
lm.init_app(app)
lm.login_view = 'login'


@lm.unauthorized_handler
def unauthorized():
    from flask import request as _req, jsonify, redirect, url_for
    if _req.path.startswith('/api/'):
        return jsonify(success=False, error='Login required.'), 401
    return redirect(url_for('login'))


@app.errorhandler(400)
def bad_request(e):
    from flask import request as _req, jsonify
    if _req.path.startswith('/api/'):
        return jsonify(success=False, error=str(e.description)), 400
    return e


@app.errorhandler(404)
def not_found(e):
    from flask import request as _req, jsonify
    if _req.path.startswith('/api/'):
        return jsonify(success=False, error='Not found.'), 404
    return e


@app.errorhandler(500)
def internal_error(e):
    from flask import request as _req, jsonify
    if _req.path.startswith('/api/'):
        return jsonify(success=False, error='Internal server error.'), 500
    return e


# ── Audit logging (NIST SP 800-53 Rev. 5 AU) ────────────────────────────────

def audit_log(event: str, user_id=None, extra: dict | None = None):
    """Emit a structured JSON audit event to the 'audit' logger."""
    record = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'event': event,
        'user_id': user_id,
        'ip': _flask_request.remote_addr if _flask_request else None,
        **(extra or {}),
    }
    logger = logging.getLogger('audit')
    logger.setLevel(logging.INFO)
    logger.info(json.dumps(record))


from app import views, models
from app.admin_views import register_admin_views, SecureAdminIndexView

admin = Admin(app, name='Sticker Admin', theme=Bootstrap4Theme(),
              index_view=SecureAdminIndexView())
register_admin_views(admin)


# ── Security headers (OWASP / NIST SP 800-53 Rev. 5 SC) ─────────────────────

@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "object-src 'none'; "
        "frame-ancestors 'none';"
    )
    return response


def _ensure_db_and_seed():
    """Create any missing tables and seed default admin if needed."""
    from app.models import User
    from werkzeug.security import generate_password_hash
    db.create_all()
    if not User.query.filter_by(user='admin').first():
        u = User(user='admin', password=generate_password_hash('password1'),
                 is_admin=True)
        db.session.add(u)
        db.session.commit()


with app.app_context():
    _ensure_db_and_seed()


@app.cli.command('create-admin')
@click.argument('username')
@click.argument('password')
def create_admin(username, password):
    """Create an admin user. Usage: flask create-admin <username> <password>"""
    from werkzeug.security import generate_password_hash
    from app.models import User
    if User.query.filter_by(user=username).first():
        click.echo(f'User "{username}" already exists.')
        return
    u = User(user=username, password=generate_password_hash(password), is_admin=True)
    db.session.add(u)
    db.session.commit()
    click.echo(f'Admin user "{username}" created.')



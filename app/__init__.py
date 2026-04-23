# -*- encoding: utf-8 -*-
import click
from flask import Flask
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_admin import Admin
from flask_admin.theme import Bootstrap4Theme
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)

app.config.from_object('app.configuration.DevelopmentConfig')

bs = Bootstrap(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app)

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


from app import views, models
from app.admin_views import register_admin_views

admin = Admin(app, name='Sticker Admin', theme=Bootstrap4Theme())
register_admin_views(admin)


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



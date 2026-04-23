import os
from datetime import timedelta


class Config(object):
    """
    Configuration base, for all environments.
    """
    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///application.db'
    BOOTSTRAP_FONTAWESOME = True
    BOOTSTRAP_SERVE_LOCAL = True
    SECRET_KEY = 'dev-only-insecure-key-change-in-production'
    CSRF_ENABLED = True
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session security (NIST SP 800-63B §7)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)


class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///application.db')
    SESSION_COOKIE_SECURE = True

    @staticmethod
    def init_app():
        secret = os.environ.get('SECRET_KEY')
        if not secret:
            raise RuntimeError(
                'SECRET_KEY environment variable must be set in production. '
                'Refusing to start with the default insecure key.'
            )

    SECRET_KEY = os.environ.get('SECRET_KEY') or Config.SECRET_KEY

    def __init_subclass__(cls, **kwargs):
        pass


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///test_application.db'
    WTF_CSRF_ENABLED = False
    # Rate limiting disabled in tests
    RATELIMIT_ENABLED = False

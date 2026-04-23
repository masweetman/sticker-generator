from datetime import datetime, timezone
from app import db


DEFAULT_BOUNDING_PROMPT = (
    "A high-quality vector-style sticker for a toddler, featuring [INSERT SUBJECT HERE]. "
    "The design should be extremely simple and fun with thick, bold black outlines and a minimalist "
    "flat color palette. No shading, no gradients, and no complex details. The character should have "
    "a friendly, 'kawaii' expression with big eyes. Include a thick white border around the entire "
    "design, isolated on a plain white background."
)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(500), nullable=False)
    name = db.Column(db.String(500))
    email = db.Column(db.String(120), unique=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    preferred_provider = db.Column(db.String(50), nullable=True)
    sheets = db.relationship('StickerSheet', backref='owner', lazy='dynamic',
                             cascade='all, delete-orphan')

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return f'<User {self.user!r}>'


class Settings(db.Model):
    """Singleton table — only one row should exist (id=1)."""
    id = db.Column(db.Integer, primary_key=True)
    # Provider: 'openrouter' or 'pollinations'
    provider = db.Column(db.String(50), default='openrouter')
    # OpenRouter
    openrouter_api_key = db.Column(db.String(500), default='')
    openrouter_model = db.Column(db.String(200), default='fal-ai/flux/schnell')
    # Pollinations
    pollinations_api_key = db.Column(db.String(500), default='')
    pollinations_model = db.Column(db.String(100), default='flux')
    # Shared
    bounding_prompt = db.Column(db.Text, default=DEFAULT_BOUNDING_PROMPT)

    @staticmethod
    def get():
        row = Settings.query.get(1)
        if row is None:
            row = Settings(id=1, bounding_prompt=DEFAULT_BOUNDING_PROMPT)
            db.session.add(row)
            db.session.commit()
        return row


class StickerSheet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    rows = db.Column(db.Integer, nullable=False, default=4)
    cols = db.Column(db.Integer, nullable=False, default=6)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    stickers = db.relationship('Sticker', backref='sheet', lazy='dynamic',
                               cascade='all, delete-orphan')


class Sticker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sheet_id = db.Column(db.Integer, db.ForeignKey('sticker_sheet.id'), nullable=False)
    row = db.Column(db.Integer, nullable=False)
    col = db.Column(db.Integer, nullable=False)
    prompt = db.Column(db.Text)
    image_path = db.Column(db.String(500))

    __table_args__ = (
        db.UniqueConstraint('sheet_id', 'row', 'col', name='uq_sticker_position'),
    )


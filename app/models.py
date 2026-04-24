from datetime import datetime, timezone
from app import db


DEFAULT_BOUNDING_PROMPT = (
    "A high-quality vector-style sticker for a toddler, featuring [INSERT SUBJECT HERE]. "
    "The design should be extremely simple and fun with thick, bold black outlines and a minimalist "
    "flat color palette. No shading, no gradients, and no complex details. Include a thick white border around the entire "
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
    two_factor_enabled = db.Column(db.Boolean, default=False, nullable=False)
    two_factor_secret = db.Column(db.String(64), nullable=True)
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


class Image(db.Model):
    """Stores the generated image file path and prompt. Shared across sticker cells."""
    id = db.Column(db.Integer, primary_key=True)
    prompt = db.Column(db.Text)
    image_path = db.Column(db.String(500))
    in_library = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    stickers = db.relationship('Sticker', back_populates='image')
    tags = db.relationship('Tag', backref='image', cascade='all, delete-orphan')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])


class Tag(db.Model):
    """Descriptive tags attached to library images."""
    id = db.Column(db.Integer, primary_key=True)
    image_id = db.Column(db.Integer, db.ForeignKey('image.id'), nullable=False)
    tag = db.Column(db.String(50), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('image_id', 'tag', name='uq_image_tag'),
    )


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
    """A grid cell on a StickerSheet, referencing an Image."""
    id = db.Column(db.Integer, primary_key=True)
    sheet_id = db.Column(db.Integer, db.ForeignKey('sticker_sheet.id'), nullable=False)
    row = db.Column(db.Integer, nullable=False)
    col = db.Column(db.Integer, nullable=False)
    image_id = db.Column(db.Integer, db.ForeignKey('image.id'), nullable=False)

    image = db.relationship('Image', back_populates='stickers')

    __table_args__ = (
        db.UniqueConstraint('sheet_id', 'row', 'col', name='uq_sticker_position'),
    )


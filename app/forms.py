from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, IntegerField, BooleanField
from wtforms.validators import DataRequired, NumberRange, EqualTo, Optional, Length


class LoginForm(FlaskForm):
    user = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Stay logged in for 30 days')


class TwoFactorVerifyForm(FlaskForm):
    """TOTP code entry at login step-2."""
    code = StringField('Authenticator Code', validators=[
        DataRequired(),
        Length(min=6, max=6, message='Code must be exactly 6 digits.'),
    ])


class TwoFactorSetupForm(FlaskForm):
    """Confirm current password + TOTP code to enable 2FA."""
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    code = StringField('Authenticator Code', validators=[
        DataRequired(),
        Length(min=6, max=6, message='Code must be exactly 6 digits.'),
    ])


class TwoFactorDisableForm(FlaskForm):
    """Confirm current password + TOTP code to disable 2FA."""
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    code = StringField('Authenticator Code', validators=[
        DataRequired(),
        Length(min=6, max=6, message='Code must be exactly 6 digits.'),
    ])


class RegisterForm(FlaskForm):
    user = StringField('Username', validators=[DataRequired(), Length(max=64)])
    name = StringField('Display Name')
    email = StringField('Email')
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=8, max=64, message='Password must be between 8 and 64 characters.'),
    ])


class StickerSheetForm(FlaskForm):
    name = StringField('Sheet Name', validators=[DataRequired()])
    rows = IntegerField('Rows', validators=[DataRequired(), NumberRange(min=1, max=10)],
                        default=6)
    cols = IntegerField('Columns', validators=[DataRequired(), NumberRange(min=1, max=10)],
                        default=4)


class ProfileForm(FlaskForm):
    name = StringField('Display Name', validators=[Optional(), Length(max=500)])
    email = StringField('Email', validators=[Optional(), Length(max=120)])
    current_password = PasswordField('Current Password', validators=[Optional()])
    new_password = PasswordField('New Password', validators=[
        Optional(),
        Length(min=8, message='Password must be at least 8 characters.'),
        EqualTo('confirm_password', message='Passwords must match.'),
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[Optional()])


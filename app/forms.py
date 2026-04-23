from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, IntegerField
from wtforms.validators import DataRequired, NumberRange, EqualTo, Optional, Length


class LoginForm(FlaskForm):
    user = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])


class RegisterForm(FlaskForm):
    user = StringField('Username', validators=[DataRequired()])
    name = StringField('Display Name')
    email = StringField('Email')
    password = PasswordField('Password', validators=[DataRequired()])


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


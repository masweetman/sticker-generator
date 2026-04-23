from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, IntegerField
from wtforms.validators import DataRequired, NumberRange


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


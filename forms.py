from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, IntegerField, DateField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class SignupForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

class TripForm(FlaskForm):
    place = StringField('Destination', validators=[DataRequired()])
    days = IntegerField('Number of Days', validators=[DataRequired(), NumberRange(min=1, max=30)])
    adults = IntegerField('Adults', validators=[DataRequired(), NumberRange(min=1)])
    children = IntegerField('Children', validators=[NumberRange(min=0)])
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[DataRequired()])
    submit = SubmitField('Plan Trip')
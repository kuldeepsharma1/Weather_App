from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from flask_mail import Mail, Message
import bcrypt
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo
import os
from dotenv import load_dotenv
from sqlalchemy import func
from itsdangerous import URLSafeTimedSerializer as Serializer, SignatureExpired

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your_default_secret_key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() in ('true', '1', 't')
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'signin'
mail = Mail(app)

# User model
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=func.now())
    is_confirmed = db.Column(db.Boolean, default=False)

# User loader
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Error handlers
@app.errorhandler(404)
def page_not_found(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_server_error(error):
    return render_template('errors/500.html'), 500

@app.errorhandler(403)
def forbidden(error):
    return render_template('errors/403.html'), 403

@app.errorhandler(400)
def bad_request(error):
    return render_template('errors/400.html'), 400

# Forms
class SigninForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')

class SignupForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign Up')

class ResetPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Reset Password')

class ResetPasswordConfirmForm(FlaskForm):
    new_password = PasswordField('New Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField('Reset Password')

class ChangePasswordForm(FlaskForm):
    old_password = PasswordField('Old Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField('Change Password')

# Utility functions
def generate_token(email, salt):
    serializer = Serializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=salt)

def send_confirmation_email(user):
    token = generate_token(user.email, 'email-confirmation')
    confirm_url = url_for('confirm_email', token=token, _external=True)
    msg = Message('Email Confirmation', recipients=[user.email], sender=app.config['MAIL_USERNAME'])
    msg.body = f'Please confirm your email: {confirm_url}'
    mail.send(msg)

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    form = SignupForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash('Email already exists.', 'danger')
            return redirect(url_for('signup'))
        hashed_password = bcrypt.hashpw(form.password.data.encode('utf-8'), bcrypt.gensalt())
        new_user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        send_confirmation_email(new_user)
        flash('Account created! Please check your email to confirm.', 'success')
        return redirect(url_for('signin'))
    return render_template('signup.html', form=form)

@app.route('/confirm/<token>')
def confirm_email(token):
    try:
        serializer = Serializer(app.config['SECRET_KEY'])
        email = serializer.loads(token, salt='email-confirmation', max_age=3600)
        user = User.query.filter_by(email=email).first_or_404()
        if not user.is_confirmed:
            user.is_confirmed = True
            db.session.commit()
            flash('Email confirmed!', 'success')
        else:
            flash('Email already confirmed.', 'info')
    except SignatureExpired:
        flash('Confirmation link expired.', 'danger')
    except Exception:
        flash('Invalid confirmation link.', 'danger')
    return redirect(url_for('signin'))

@app.route('/signin', methods=['GET', 'POST'])
def signin():
    form = SigninForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and bcrypt.checkpw(form.password.data.encode('utf-8'), user.password):
            if user.is_confirmed:
                login_user(user)
                flash('Sign in successful!', 'success')
                return redirect(url_for('profile'))
            flash('Please confirm your email first.', 'warning')
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('signin.html', form=form)

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', username=current_user.username)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('signin'))

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            token = generate_token(user.email, 'password-reset')
            reset_url = url_for('reset_password_confirm', token=token, _external=True)
            msg = Message('Password Reset Request', recipients=[user.email], sender=app.config['MAIL_USERNAME'])
            msg.body = f'Reset your password here: {reset_url}'
            mail.send(msg)
            flash('Reset link sent to your email.', 'info')
            return redirect(url_for('signin'))
        flash('Email not found.', 'danger')
    return render_template('reset_password.html', form=form)

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password_confirm(token):
    form = ResetPasswordConfirmForm()
    try:
        serializer = Serializer(app.config['SECRET_KEY'])
        email = serializer.loads(token, salt='password-reset', max_age=3600)
        user = User.query.filter_by(email=email).first_or_404()
        if form.validate_on_submit():
            hashed_password = bcrypt.hashpw(form.new_password.data.encode('utf-8'), bcrypt.gensalt())
            user.password = hashed_password
            db.session.commit()
            flash('Password reset successful!', 'success')
            return redirect(url_for('signin'))
    except SignatureExpired:
        flash('Reset link expired.', 'danger')
        return redirect(url_for('signin'))
    except Exception:
        flash('Invalid reset link.', 'danger')
        return redirect(url_for('signin'))
    return render_template('reset_password_confirm.html', form=form)

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        user = current_user
        if bcrypt.checkpw(form.old_password.data.encode('utf-8'), user.password):
            hashed_password = bcrypt.hashpw(form.new_password.data.encode('utf-8'), bcrypt.gensalt())
            user.password = hashed_password
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('profile'))
        flash('Incorrect old password.', 'danger')
    return render_template('change_password.html', form=form)

@app.route('/delete_account', methods=['GET', 'POST'])
@login_required
def delete_account():
    if request.method == 'POST':
        user = current_user
        db.session.delete(user)
        db.session.commit()
        logout_user()
        flash('Account deleted successfully.', 'success')
        return redirect(url_for('signin'))
    return render_template('delete_account.html')

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
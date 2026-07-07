import os
import secrets
import hashlib
import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from ..models import User, PasswordResetToken, Student
from .. import db

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

ALLOWED_PHOTO_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']
        user     = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            # Auto-grant admin if email is in ADMIN_EMAILS config
            from flask import current_app
            admin_emails = current_app.config.get('ADMIN_EMAILS', [])
            if user.email in admin_emails and not user.is_admin:
                user.is_admin = True
                db.session.commit()

            login_user(user)
            if user.is_admin:
                return redirect(url_for('admin.dashboard'))
            elif user.role == 'teacher':
                return redirect(url_for('teacher.dashboard'))
            elif user.role == 'hod':
                return redirect(url_for('hod.dashboard'))
            elif user.role == 'principal':
                return redirect(url_for('principal.dashboard'))
            else:
                return redirect(url_for('student.dashboard'))
        else:
            flash('Wrong email or password')

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name     = request.form['name']
        email    = request.form['email']
        password = request.form['password']

        existing = User.query.filter_by(email=email).first()
        if existing:
            flash('Email already registered')
            return redirect(url_for('auth.register'))

        new_user = User(
            name     = name,
            email    = email,
            password = generate_password_hash(password),
            role     = 'student'
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Account created! Please login. Note: Only admins can grant teacher/HOD/Principal access.')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        photo = request.files.get('profile_photo')

        if name:
            current_user.name = name

        if photo and photo.filename:
            ext = os.path.splitext(photo.filename)[1].lower()
            if ext in ALLOWED_PHOTO_EXT:
                filename = f"profile_{current_user.id}{ext}"
                upload_dir = os.path.join('app', 'static', 'uploads')
                os.makedirs(upload_dir, exist_ok=True)
                photo.save(os.path.join(upload_dir, filename))
                current_user.profile_photo = filename
            else:
                flash('Invalid image format. Use JPG, PNG, GIF, or WebP.')
                return redirect(url_for('auth.profile'))

        # Email notifications toggle
        current_user.email_notifications = request.form.get('email_notifications') == 'on'

        # Parent email (students only)
        if current_user.role == 'student':
            parent_email = request.form.get('parent_email', '').strip()
            student = Student.query.filter_by(user_id=current_user.id).first()
            if student:
                student.parent_email = parent_email if parent_email else None

        db.session.commit()
        flash('Profile updated!')
        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html',
                           vapid_public_key=current_app.config.get('VAPID_PUBLIC_KEY', ''))


@auth_bp.route('/user/<int:user_id>')
def user_profile(user_id):
    user = db.get_or_404(User, user_id)
    return render_template('auth/user_profile.html', profile_user=user)


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()

        # Always show success message to prevent email enumeration
        if user:
            # Clean up old tokens
            PasswordResetToken.query.filter_by(user_id=user.id, used=True).delete()

            token = secrets.token_urlsafe(32)
            reset_token = PasswordResetToken(
                user_id=user.id,
                token_hash=_hash_token(token),
                expires_at=datetime.datetime.now() + datetime.timedelta(
                    seconds=current_app.config.get('RESET_TOKEN_EXPIRY', 3600)
                ),
            )
            db.session.add(reset_token)
            db.session.commit()

            reset_url = url_for('auth.reset_password', token=token, _external=True)
            from ..email import send_password_reset_email
            send_password_reset_email(user.email, user.name, reset_url)

        flash('If an account with that email exists, a reset link has been sent.')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    token_hash = _hash_token(token)
    reset_token = PasswordResetToken.query.filter_by(token_hash=token_hash, used=False).first()

    if not reset_token or reset_token.expires_at < datetime.datetime.now():
        flash('This reset link is invalid or has expired.')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')

        if len(password) < 6:
            flash('Password must be at least 6 characters.')
            return render_template('auth/reset_password.html', token=token)

        if password != confirm:
            flash('Passwords do not match.')
            return render_template('auth/reset_password.html', token=token)

        user = db.session.get(User, reset_token.user_id)
        if user:
            user.password = generate_password_hash(password)
            reset_token.used = True
            db.session.commit()
            flash('Password reset successful! Please log in.')
            return redirect(url_for('auth.login'))

        flash('Something went wrong. Please try again.')
        return redirect(url_for('auth.forgot_password'))

    return render_template('auth/reset_password.html', token=token)
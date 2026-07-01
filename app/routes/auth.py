import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from ..models import User
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
                from .. import db
                db.session.commit()

            login_user(user)
            if user.is_admin:
                return redirect(url_for('admin.dashboard'))
            elif user.role == 'teacher':
                return redirect(url_for('teacher.dashboard'))
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
        flash('Account created! Please login. Note: Only admins can grant teacher access.')
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

        db.session.commit()
        flash('Profile updated!')
        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html')


@auth_bp.route('/user/<int:user_id>')
@login_required
def user_profile(user_id):
    user = db.get_or_404(User, user_id)
    return render_template('auth/user_profile.html', profile_user=user)
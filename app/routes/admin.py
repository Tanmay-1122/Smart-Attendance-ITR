from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from ..models import User, Student, TeacherClass, StudentClass, AttendanceRecord
from .. import db

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            flash('Access denied. Admin privileges required.')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    if User.query.filter_by(is_admin=True).first():
        flash('Admin accounts already exist. Use the admin panel to manage users.')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        if not name or not email or not password:
            flash('All fields are required.')
            return redirect(url_for('admin.setup'))

        existing = User.query.filter_by(email=email).first()
        if existing:
            existing.is_admin = True
            existing.role = 'student'
            db.session.commit()
            flash(f'Existing account "{existing.name}" is now an admin. Please log in.')
        else:
            admin = User(
                name=name,
                email=email,
                password=generate_password_hash(password),
                role='student',
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            flash('Admin account created! Please log in.')

        return redirect(url_for('auth.login'))

    return render_template('admin/setup.html')


@admin_bp.route('/')
@admin_required
def dashboard():
    total_users = User.query.count()
    total_teachers = User.query.filter_by(role='teacher').count()
    total_students = User.query.filter_by(role='student').count()
    total_admins = User.query.filter_by(is_admin=True).count()
    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           total_teachers=total_teachers,
                           total_students=total_students,
                           total_admins=total_admins)


@admin_bp.route('/users')
@admin_required
def users():
    role_filter = request.args.get('role', '').strip()
    search = request.args.get('search', '').strip()

    query = User.query
    if role_filter == 'teacher':
        query = query.filter_by(role='teacher')
    elif role_filter == 'student':
        query = query.filter_by(role='student')
    elif role_filter == 'admin':
        query = query.filter_by(is_admin=True)

    if search:
        query = query.filter(
            User.name.ilike(f'%{search}%') | User.email.ilike(f'%{search}%')
        )

    users = query.order_by(User.name).all()
    return render_template('admin/users.html', users=users, role_filter=role_filter, search=search)


@admin_bp.route('/promote/<int:user_id>', methods=['POST'])
@admin_required
def promote(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash('You cannot change your own role.')
        return redirect(url_for('admin.users'))
    if user.role == 'teacher':
        flash(f'{user.name} is already a teacher.')
        return redirect(url_for('admin.users'))

    user.role = 'teacher'
    db.session.commit()
    flash(f'{user.name} has been promoted to teacher.')
    return redirect(url_for('admin.users'))


@admin_bp.route('/demote/<int:user_id>', methods=['POST'])
@admin_required
def demote(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash('You cannot change your own role.')
        return redirect(url_for('admin.users'))
    if user.role == 'student':
        flash(f'{user.name} is already a student.')
        return redirect(url_for('admin.users'))

    TeacherClass.query.filter_by(teacher_id=user.id).delete()
    StudentClass.query.filter_by(student_id=user.id).delete()
    user.role = 'student'
    db.session.commit()
    flash(f'{user.name} has been demoted to student.')
    return redirect(url_for('admin.users'))


@admin_bp.route('/toggle-admin/<int:user_id>', methods=['POST'])
@admin_required
def toggle_admin(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash('You cannot remove your own admin status.')
        return redirect(url_for('admin.users'))

    user.is_admin = not user.is_admin
    db.session.commit()
    status = 'granted' if user.is_admin else 'revoked'
    flash(f'Admin privileges {status} for {user.name}.')
    return redirect(url_for('admin.users'))


@admin_bp.route('/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash('You cannot delete your own account from here.')
        return redirect(url_for('admin.users'))

    if user.role == 'teacher':
        TeacherClass.query.filter_by(teacher_id=user.id).delete()

    student = Student.query.filter_by(user_id=user.id).first()
    if student:
        AttendanceRecord.query.filter_by(student_id=student.id).delete()
        StudentClass.query.filter_by(student_id=student.id).delete()
        db.session.delete(student)

    db.session.delete(user)
    db.session.commit()
    flash(f'User "{user.name}" has been deleted.')
    return redirect(url_for('admin.users'))

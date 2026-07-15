import os
from urllib.parse import urlencode
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from ..models import User, Student, TeacherClass, StudentClass, AttendanceRecord, Department, ApiConfig
from .. import db
from ..api_config import KNOWN_KEYS, SECRET_KEYS
from ..email import send_email

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
    total_hods = User.query.filter_by(role='hod').count()
    total_principals = User.query.filter_by(role='principal').count()
    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           total_teachers=total_teachers,
                           total_students=total_students,
                           total_admins=total_admins,
                           total_hods=total_hods,
                           total_principals=total_principals)


@admin_bp.route('/users')
@admin_required
def users():
    role_filter = request.args.get('role', '').strip()
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)

    query = User.query
    if role_filter == 'teacher':
        query = query.filter_by(role='teacher')
    elif role_filter == 'student':
        query = query.filter_by(role='student')
    elif role_filter == 'hod':
        query = query.filter_by(role='hod')
    elif role_filter == 'principal':
        query = query.filter_by(role='principal')
    elif role_filter == 'admin':
        query = query.filter_by(is_admin=True)

    if search:
        query = query.filter(
            User.name.ilike(f'%{search}%') | User.email.ilike(f'%{search}%')
        )

    pagination = query.order_by(User.name).paginate(page=page, per_page=25, error_out=False)
    users = pagination.items
    departments = Department.query.order_by(Department.name).all()
    args_no_page = request.args.copy()
    args_no_page.pop('page', None)
    url_without_page = urlencode(list(args_no_page.items(multi=True)))
    return render_template('admin/users.html', users=users, role_filter=role_filter, search=search, departments=departments, pagination=pagination, url_without_page=url_without_page)


@admin_bp.route('/assign-department/<int:user_id>', methods=['POST'])
@admin_required
def assign_department(user_id):
    user = db.get_or_404(User, user_id)
    dept_id = request.form.get('department_id')
    user.department_id = int(dept_id) if dept_id and dept_id.isdigit() else None
    db.session.commit()
    flash(f'Department updated for {user.name}.')
    return redirect(request.referrer or url_for('admin.users'))



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


@admin_bp.route('/create-hod', methods=['GET', 'POST'])
@admin_required
def create_hod():
    departments = Department.query.order_by(Department.name).all()
    teachers = User.query.filter(User.role == 'teacher', User.department_id.is_(None)).order_by(User.name).all()

    if request.method == 'POST':
        action = request.form.get('action', 'new')
        department_id = request.form.get('department_id')
        if not department_id:
            flash('Please select a department.')
            return redirect(url_for('admin.create_hod'))

        dept = db.session.get(Department, int(department_id))

        # Check if department already has an HOD
        existing_hod = User.query.filter_by(role='hod', department_id=dept.id).first()
        if existing_hod:
            flash(f'Department "{dept.name}" already has an HOD ({existing_hod.name}). Demote them first.')
            return redirect(url_for('admin.create_hod'))

        if action == 'existing':
            user_id = request.form.get('user_id')
            if not user_id:
                flash('Please select a teacher.')
                return redirect(url_for('admin.create_hod'))
            user = db.get_or_404(User, int(user_id))
            if user.role != 'teacher':
                flash('Selected user is not a teacher.')
                return redirect(url_for('admin.create_hod'))
            user.role = 'hod'
            user.department_id = dept.id
            db.session.commit()
            flash(f'{user.name} has been promoted to HOD of {dept.name}.')
        else:
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()
            if not name or not email or not password:
                flash('All fields are required for a new HOD account.')
                return redirect(url_for('admin.create_hod'))
            existing = User.query.filter_by(email=email).first()
            if existing:
                flash('Email already registered.')
                return redirect(url_for('admin.create_hod'))
            hod = User(
                name=name,
                email=email,
                password=generate_password_hash(password),
                role='hod',
                department_id=dept.id
            )
            db.session.add(hod)
            db.session.commit()
            flash(f'HOD account created for {name} ({dept.name}).')

        return redirect(url_for('admin.users'))

    return render_template('admin/create_hod.html', departments=departments, teachers=teachers)


@admin_bp.route('/create-principal', methods=['GET', 'POST'])
@admin_required
def create_principal():
    existing_principal = User.query.filter_by(role='principal').first()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        if not name or not email or not password:
            flash('All fields are required.')
            return redirect(url_for('admin.create_principal'))
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash('Email already registered.')
            return redirect(url_for('admin.create_principal'))
        principal = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            role='principal'
        )
        db.session.add(principal)
        db.session.commit()
        flash(f'Principal account created for {name}.')
        return redirect(url_for('admin.users'))

    return render_template('admin/create_principal.html', existing_principal=existing_principal)


@admin_bp.route('/demote-hod/<int:user_id>', methods=['POST'])
@admin_required
def demote_hod(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash('You cannot change your own role.')
        return redirect(url_for('admin.users'))
    if user.role != 'hod':
        flash(f'{user.name} is not an HOD.')
        return redirect(url_for('admin.users'))

    user.role = 'teacher'
    db.session.commit()
    flash(f'{user.name} has been demoted from HOD to teacher.')
    return redirect(url_for('admin.users'))


@admin_bp.route('/seed-default-accounts', methods=['POST'])
@admin_required
def seed_default_accounts():
    from ..models import Department
    from werkzeug.security import generate_password_hash
    count = 0
    depts_data = {'IT': 'Information Technology', 'CV': 'Civil Engineering',
                  'E&TC': 'Electronics & Telecommunication', 'A&R': 'Automation & Robotics',
                  'ME': 'Mechanical Engineering'}
    for code, name in depts_data.items():
        dept = Department.query.filter_by(code=code).first()
        if not dept:
            dept = Department(name=name, code=code)
            db.session.add(dept)

    if not User.query.filter_by(email='admin@college.edu').first():
        db.session.add(User(name='System Admin', email='admin@college.edu',
                            password=generate_password_hash('Admin@123'), role='student', is_admin=True))
        count += 1

    if not User.query.filter_by(role='principal').first():
        db.session.add(User(name='Dr. Principal Sharma', email='principal@college.edu',
                            password=generate_password_hash('Principal@123'), role='principal'))
        count += 1

    hods = [('Dr. Arvind Patil', 'hod.it@college.edu', 'IT'),
            ('Dr. Sneha Deshmukh', 'hod.civil@college.edu', 'CV'),
            ('Dr. Rajesh Kulkarni', 'hod.entc@college.edu', 'E&TC'),
            ('Dr. Priya Joshi', 'hod.robotics@college.edu', 'A&R'),
            ('Dr. Vikram Singh', 'hod.mech@college.edu', 'ME')]
    for name, email, code in hods:
        if not User.query.filter_by(email=email).first():
            dept = Department.query.filter_by(code=code).first()
            if dept:
                db.session.add(User(name=name, email=email,
                                    password=generate_password_hash('HOD@123'),
                                    role='hod', department_id=dept.id))
                count += 1

    db.session.commit()
    flash(f'Seeded {count} new accounts. Passwords: Admin@123, Principal@123, HOD@123')
    return redirect(url_for('admin.dashboard'))


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


@admin_bp.route('/api-keys', methods=['GET', 'POST'])
@admin_required
def api_keys():
    if request.method == 'POST':
        keys_to_update = [k for k in KNOWN_KEYS if k in request.form]
        for key in keys_to_update:
            value = request.form.get(key, '').strip()
            config = ApiConfig.query.filter_by(key=key).first()
            if config:
                config.value = value if value else None
            else:
                config = ApiConfig(
                    key=key,
                    value=value if value else None,
                    description=KNOWN_KEYS.get(key, ''),
                    is_secret=key in SECRET_KEYS,
                )
                db.session.add(config)

            if value:
                current_app.config[key] = value
            else:
                current_app.config.pop(key, None)

        db.session.commit()
        flash('API keys updated successfully!')
        return redirect(url_for('admin.api_keys'))

    configs = {}
    for key, desc in KNOWN_KEYS.items():
        db_row = ApiConfig.query.filter_by(key=key).first()
        env_val = os.environ.get(key, '')
        app_val = current_app.config.get(key, '')
        configs[key] = {
            'description': desc,
            'is_secret': key in SECRET_KEYS,
            'db_value': db_row.value if db_row else None,
            'env_value': env_val if not (db_row and db_row.value) else '',
            'source': 'DB' if (db_row and db_row.value) else 'Env' if env_val else 'Not Set',
        }

    return render_template('admin/api_keys.html', configs=configs)


SMTP_FIELDS = ['SMTP_HOST', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASS', 'SMTP_FROM']


@admin_bp.route('/email-settings', methods=['GET', 'POST'])
@admin_required
def email_settings():
    if request.method == 'POST':
        for key in SMTP_FIELDS:
            value = request.form.get(key, '').strip()
            config = ApiConfig.query.filter_by(key=key).first()
            if config:
                config.value = value if value else None
            else:
                config = ApiConfig(
                    key=key,
                    value=value if value else None,
                    description=KNOWN_KEYS.get(key, ''),
                    is_secret=key in SECRET_KEYS,
                )
                db.session.add(config)

            if value:
                current_app.config[key] = value
            else:
                current_app.config.pop(key, None)

        db.session.commit()
        flash('Email settings saved successfully!')
        return redirect(url_for('admin.email_settings'))

    configs = {}
    for key in SMTP_FIELDS:
        db_row = ApiConfig.query.filter_by(key=key).first()
        env_val = os.environ.get(key, '')
        app_val = current_app.config.get(key, '')
        configs[key] = {
            'description': KNOWN_KEYS.get(key, ''),
            'is_secret': key in SECRET_KEYS,
            'db_value': db_row.value if db_row else (app_val or ''),
            'env_value': env_val if not (db_row and db_row.value) else '',
            'source': 'DB' if (db_row and db_row.value) else 'Env' if env_val else 'Not Set',
        }

    smtp_configured = bool(current_app.config.get('SMTP_HOST', ''))
    return render_template('admin/email_settings.html', configs=configs, smtp_configured=smtp_configured)


@admin_bp.route('/test-email', methods=['POST'])
@admin_required
def test_email():
    to = current_user.email
    if not to:
        flash('Your account has no email address set.')
        return redirect(url_for('admin.email_settings'))

    smtp_host = current_app.config.get('SMTP_HOST', '')
    if not smtp_host:
        flash('SMTP is not configured. Save your email settings first.')
        return redirect(url_for('admin.email_settings'))

    html = """
    <div style="font-family:Inter,-apple-system,BlinkMacSystemFont,sans-serif;max-width:480px;margin:0 auto;padding:32px;">
      <div style="background:linear-gradient(135deg,#10B981,#059669);border-radius:16px;padding:32px;text-align:center;color:#fff;margin-bottom:24px;">
        <h1 style="margin:0;font-size:1.4rem;font-weight:800;">SmartAttend</h1>
        <p style="margin:8px 0 0;opacity:0.8;font-size:0.9rem;">Test Email</p>
      </div>
      <div style="background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:24px;">
        <p style="color:#374151;font-size:0.95rem;margin:0 0 16px;">Your Gmail/SMTP configuration is working correctly.</p>
        <div style="background:#ECFDF5;border-radius:8px;padding:16px;margin-bottom:16px;">
          <p style="margin:0;color:#065F46;font-weight:600;font-size:0.9rem;">Email notifications are now active.</p>
        </div>
        <p style="color:#6B7280;font-size:0.82rem;margin:0;">This test email was sent from the Admin Panel.</p>
      </div>
      <p style="text-align:center;color:#9CA3AF;font-size:0.75rem;margin-top:16px;">SmartAttend — AI-powered attendance management</p>
    </div>
    """

    result = send_email(to, 'SmartAttend — Test Email', html)
    if result:
        flash(f'Test email queued! Check your inbox at {to}.')
    else:
        flash(f'Failed to queue test email. Check your SMTP settings.')

    return redirect(url_for('admin.email_settings'))

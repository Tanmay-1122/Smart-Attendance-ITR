from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

    # Ensure uploads folder exists before app runs
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect(app)

    # register blueprints
    from .routes.auth       import auth_bp
    from .routes.student    import student_bp
    from .routes.teacher    import teacher_bp
    from .routes.notes      import notes_bp
    from .routes.admin      import admin_bp
    from .routes.chat       import chat_bp
    from .routes.analytics  import analytics_bp
    from .routes.leave      import leave_bp
    from .routes.announcements import announcements_bp
    from .routes.schedule   import schedule_bp
    from .routes.notifications import notifications_bp
    from .routes.hod        import hod_bp
    from .routes.principal  import principal_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(leave_bp)
    app.register_blueprint(announcements_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(hod_bp)
    app.register_blueprint(principal_bp)

    # Root redirect to login page
    from flask import redirect, url_for

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    with app.app_context():
        from .models import ChatMessage, Department, MarksRecord
        db.create_all()

        # Migration: add missing columns (handles upgrades)
        def _ensure_column(table, column, col_type, default_val=None):
            try:
                db_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
                if 'sqlite' in db_url:
                    result = db.session.execute(db.text(f"PRAGMA table_info({table})"))
                    columns = [row[1] for row in result]
                    if column not in columns:
                        default = f" DEFAULT {default_val}" if default_val is not None else ""
                        db.session.execute(db.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default}"))
                        db.session.commit()
                        print(f"[INIT] Added {column} column to {table} table")
                elif 'postgresql' in db_url:
                    result = db.session.execute(
                        db.text(f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}' AND column_name='{column}'")
                    )
                    if not result.fetchone():
                        default = f" DEFAULT {default_val}" if default_val is not None else ""
                        db.session.execute(db.text(f'ALTER TABLE "{table}" ADD COLUMN {column} {col_type}{default}'))
                        db.session.commit()
                        print(f"[INIT] Added {column} column to {table} table")
            except Exception as e:
                print(f"[INIT] Migration check ({table}.{column}): {e}")

        _ensure_column('user', 'is_admin', 'BOOLEAN', 'FALSE')
        _ensure_column('user', 'email_notifications', 'BOOLEAN', 'TRUE')
        _ensure_column('user', 'department_id', 'INTEGER')
        _ensure_column('student', 'parent_email', 'VARCHAR(100)')

        # Seed departments if empty
        if Department.query.count() == 0:
            depts = [
                Department(name='Information Technology', code='IT'),
                Department(name='Civil Engineering', code='CV'),
                Department(name='Electronics & Telecommunication', code='E&TC'),
                Department(name='Automation & Robotics', code='A&R'),
                Department(name='Mechanical Engineering', code='ME'),
            ]
            db.session.add_all(depts)
            db.session.commit()
            print("[INIT] Seeded departments")

        # Ensure default accounts exist (safe to re-run — skips existing emails)
        from werkzeug.security import generate_password_hash
        from .models import User
        defaults = [
            ('System Admin', 'admin@college.edu', 'Admin@123', 'student', True, None),
            ('Dr. Principal Sharma', 'principal@college.edu', 'Principal@123', 'principal', False, None),
        ]
        hods = [
            ('Dr. Arvind Patil', 'hod.it@college.edu', 'IT'),
            ('Dr. Sneha Deshmukh', 'hod.civil@college.edu', 'CV'),
            ('Dr. Rajesh Kulkarni', 'hod.entc@college.edu', 'E&TC'),
            ('Dr. Priya Joshi', 'hod.robotics@college.edu', 'A&R'),
            ('Dr. Vikram Singh', 'hod.mech@college.edu', 'ME'),
        ]
        seeded = 0
        for name, email, pw, role, is_admin, dept_id in defaults:
            if not User.query.filter_by(email=email).first():
                db.session.add(User(name=name, email=email,
                                    password=generate_password_hash(pw),
                                    role=role, is_admin=is_admin, department_id=dept_id))
                seeded += 1
        for name, email, code in hods:
            if not User.query.filter_by(email=email).first():
                dept = Department.query.filter_by(code=code).first()
                db.session.add(User(name=name, email=email,
                                    password=generate_password_hash('HOD@123'),
                                    role='hod', is_admin=False,
                                    department_id=dept.id if dept else None))
                seeded += 1
        if seeded:
            db.session.commit()
            print(f"[INIT] Seeded {seeded} missing default account(s)")

    return app
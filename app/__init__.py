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

    # Root redirect to login page
    from flask import redirect, url_for

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    with app.app_context():
        from .models import ChatMessage
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
        _ensure_column('student', 'parent_email', 'VARCHAR(100)')

    return app
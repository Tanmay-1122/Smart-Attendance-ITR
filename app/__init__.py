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
    from .routes.auth    import auth_bp
    from .routes.student import student_bp
    from .routes.teacher import teacher_bp
    from .routes.notes   import notes_bp
    from .routes.admin   import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(admin_bp)

    # Root redirect to login page
    from flask import redirect, url_for

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    with app.app_context():
        from .models import ChatMessage
        db.create_all()

        # Ensure is_admin column exists on user table (handles upgrades)
        try:
            db_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
            if 'sqlite' in db_url:
                result = db.session.execute(
                    db.text("PRAGMA table_info(user)")
                )
                columns = [row[1] for row in result]
                if 'is_admin' not in columns:
                    db.session.execute(
                        db.text("ALTER TABLE user ADD COLUMN is_admin BOOLEAN DEFAULT 0")
                    )
                    db.session.commit()
                    print("[INIT] Added is_admin column to user table")
            elif 'postgresql' in db_url:
                result = db.session.execute(
                    db.text("SELECT column_name FROM information_schema.columns WHERE table_name='user' AND column_name='is_admin'")
                )
                if not result.fetchone():
                    db.session.execute(
                        db.text("ALTER TABLE \"user\" ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
                    )
                    db.session.commit()
                    print("[INIT] Added is_admin column to user table")
        except Exception as e:
            print(f"[INIT] Migration check: {e}")

    return app
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

    # register blueprints
    from .routes.auth    import auth_bp
    from .routes.student import student_bp
    from .routes.teacher import teacher_bp
    from .routes.notes   import notes_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(notes_bp)

    # Root redirect to login page
    from flask import redirect, url_for

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    with app.app_context():
        from .models import ChatMessage
        db.create_all()

        # Add missing columns to existing tables (SQLite doesn't support ALTER TABLE ADD COLUMN IF)
        with db.engine.connect() as conn:
            try:
                conn.execute(db.text("SELECT profile_photo FROM user LIMIT 1"))
            except Exception:
                conn.execute(db.text("ALTER TABLE user ADD COLUMN profile_photo VARCHAR(200)"))
                conn.commit()

    return app
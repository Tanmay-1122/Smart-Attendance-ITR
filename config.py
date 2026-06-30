import os

# Load from .env/config.py if it exists
_env_path = os.path.join(os.path.dirname(__file__), '.env', 'config.py')
if os.path.exists(_env_path):
    with open(_env_path) as f:
        exec(compile(f.read(), _env_path, 'exec'), globals())


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'smart-attendance-secret-key-998877')
    SQLALCHEMY_DATABASE_URI = os.environ.get('SQLALCHEMY_DATABASE_URI', 'sqlite:///attendance.db')
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'app/static/uploads')
    MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # 64 MB

    # API keys — override via environment variables or .env/config.py
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', globals().get('TELEGRAM_BOT_TOKEN', ''))
    TELEGRAM_GROUP_ID  = os.environ.get('TELEGRAM_GROUP_ID', globals().get('TELEGRAM_GROUP_ID', ''))
    GOOGLE_AI_KEY      = os.environ.get('GOOGLE_AI_KEY', globals().get('GOOGLE_AI_KEY', ''))

    # Face recognition thresholds
    FACE_THRESH_HIGH = 0.70
    FACE_THRESH_MID  = 0.55
    FACE_THRESH_SEEN = 2
    FACE_MIN_SIZE    = 80
    FACE_MAX_TILT    = 30
    FACE_BLUR_THRESH = 50

import os
from dotenv import load_dotenv

# Load .env file if it exists
_env_path = os.path.join(os.path.dirname(__file__), '.env', '.env')
if os.path.exists(_env_path):
    load_dotenv(_env_path)


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'smart-attendance-secret-key-998877')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///attendance.db')
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)
    if SQLALCHEMY_DATABASE_URI and 'postgresql' in SQLALCHEMY_DATABASE_URI:
        if '?' not in SQLALCHEMY_DATABASE_URI:
            SQLALCHEMY_DATABASE_URI += '?sslmode=require'
        elif 'sslmode' not in SQLALCHEMY_DATABASE_URI:
            SQLALCHEMY_DATABASE_URI += '&sslmode=require'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'app/static/uploads')
    MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # 64 MB

    # API keys — override via environment variables or .env/config.py
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', globals().get('TELEGRAM_BOT_TOKEN', ''))
    TELEGRAM_GROUP_ID  = os.environ.get('TELEGRAM_GROUP_ID', globals().get('TELEGRAM_GROUP_ID', ''))
    GOOGLE_AI_KEY      = os.environ.get('GOOGLE_AI_KEY', globals().get('GOOGLE_AI_KEY', ''))
    HF_FACE_API_URL    = os.environ.get('HF_FACE_API_URL', '')

    # Face recognition thresholds
    FACE_THRESH_HIGH = 0.70
    FACE_THRESH_MID  = 0.55
    FACE_THRESH_SEEN = 2
    FACE_MIN_SIZE    = 80
    FACE_MAX_TILT    = 30
    FACE_BLUR_THRESH = 50

    # Admin emails — comma-separated list of emails that get admin on first login
    ADMIN_EMAILS = [e.strip() for e in os.environ.get('ADMIN_EMAILS', '').split(',') if e.strip()]

    # SMTP / Email
    SMTP_HOST = os.environ.get('SMTP_HOST', '')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
    SMTP_USER = os.environ.get('SMTP_USER', '')
    SMTP_PASS = os.environ.get('SMTP_PASS', '')
    SMTP_FROM = os.environ.get('SMTP_FROM', SMTP_USER)

    # Password reset
    RESET_TOKEN_EXPIRY = 3600  # seconds

    # Twilio (WhatsApp)
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
    TWILIO_WHATSAPP_FROM = os.environ.get('TWILIO_WHATSAPP_FROM', '')

    # VAPID (Web Push)
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
    VAPID_EMAIL = os.environ.get('VAPID_EMAIL', '')

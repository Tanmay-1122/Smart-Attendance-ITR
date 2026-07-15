import os


def get_api_config(key, default=None):
    """Get an API config value: DB → Flask config → env var.

    Call this inside a request context so `current_app` is available.
    Falls back to os.environ so env vars still work as overrides.
    """
    from flask import current_app
    try:
        from .models import ApiConfig
        row = ApiConfig.query.filter_by(key=key).first()
        if row and row.value:
            return row.value
    except Exception:
        pass
    return current_app.config.get(key, os.environ.get(key, default))


def load_api_configs_into_app(app):
    """Load all ApiConfig entries from DB into app.config."""
    try:
        with app.app_context():
            from .models import ApiConfig
            rows = ApiConfig.query.all()
            for row in rows:
                if row.value is not None:
                    app.config[row.key] = row.value
    except Exception as e:
        print(f"[API CONFIG] Could not load from DB: {e}")


KNOWN_KEYS = {
    'TELEGRAM_BOT_TOKEN': 'Telegram Bot Token',
    'TELEGRAM_GROUP_ID': 'Telegram Group/Chat ID',
    'GOOGLE_AI_KEY': 'Google Gemini AI API Key',
    'HF_FACE_API_URL': 'Hugging Face Face API URL',
    'RESEND_API_KEY': 'Resend API Key (Email)',
    'SMTP_HOST': 'SMTP Host',
    'SMTP_PORT': 'SMTP Port',
    'SMTP_USER': 'SMTP Username',
    'SMTP_PASS': 'SMTP Password',
    'SMTP_FROM': 'SMTP From Address',
    'TWILIO_ACCOUNT_SID': 'Twilio Account SID',
    'TWILIO_AUTH_TOKEN': 'Twilio Auth Token',
    'TWILIO_WHATSAPP_FROM': 'Twilio WhatsApp From Number',
    'VAPID_PRIVATE_KEY': 'VAPID Private Key (Web Push)',
    'VAPID_PUBLIC_KEY': 'VAPID Public Key (Web Push)',
    'VAPID_EMAIL': 'VAPID Contact Email',
}

SECRET_KEYS = {
    'TELEGRAM_BOT_TOKEN', 'GOOGLE_AI_KEY', 'SMTP_PASS', 'RESEND_API_KEY',
    'TWILIO_AUTH_TOKEN', 'VAPID_PRIVATE_KEY',
}

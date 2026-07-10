from flask import current_app
from .tasks import run_async


@run_async
def send_whatsapp(to_phone, body):
    """Send a WhatsApp message via Twilio."""
    account_sid = current_app.config.get('TWILIO_ACCOUNT_SID', '')
    auth_token = current_app.config.get('TWILIO_AUTH_TOKEN', '')
    from_number = current_app.config.get('TWILIO_WHATSAPP_FROM', '')

    if not account_sid or not auth_token or not from_number:
        print(f"[WHATSAPP] Twilio not configured, skipping message to {to_phone}")
        return False

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=body,
            from_=f'whatsapp:{from_number}',
            to=f'whatsapp:+91{to_phone}'
        )
        print(f"[WHATSAPP] Sent to {to_phone}: {message.sid}")
        return True
    except Exception as e:
        print(f"[WHATSAPP] Failed to send to {to_phone}: {e}")
        return False

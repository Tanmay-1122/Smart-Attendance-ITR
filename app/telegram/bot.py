import datetime
import requests
from flask import current_app, flash
from .. import db
from ..models import ChatMessage, Homework


def _token():
    return current_app.config['TELEGRAM_BOT_TOKEN']

def _group():
    return current_app.config['TELEGRAM_GROUP_ID']

def _base():
    return f"https://api.telegram.org/bot{_token()}"


# ── 1. Plain text ────────────────────────────────────────────────────────────

def send_text_message(text: str, sender_name: str):
    try:
        resp = requests.post(
            f"{_base()}/sendMessage",
            json={'chat_id': _group(), 'text': f"\U0001f464 {sender_name}:\n{text}"},
            timeout=10,
        )
        data = resp.json()
        if data.get('ok'):
            db.session.add(ChatMessage(
                telegram_msg_id=data['result']['message_id'],
                sender_name=sender_name, text=text,
                sent_at=datetime.datetime.now(),
            ))
            db.session.commit()
        else:
            flash(f"Telegram: {data.get('description', 'error')}")
    except Exception as e:
        flash(f"Could not send message: {e}")


# ── 2. Photo (with optional caption) ────────────────────────────────────────

def send_photo_message(file_path: str, file_name: str, sender_name: str, caption: str = ''):
    try:
        cap = f"{caption}\n\U0001f464 {sender_name}" if caption else f"\U0001f464 {sender_name}"
        with open(file_path, 'rb') as f:
            resp = requests.post(
                f"{_base()}/sendPhoto",
                data={'chat_id': _group(), 'caption': cap},
                files={'photo': (file_name, f)},
                timeout=30,
            )
        data = resp.json()
        if data.get('ok'):
            photos  = data['result'].get('photo', [])
            file_id = photos[-1]['file_id'] if photos else ''
            db.session.add(ChatMessage(
                telegram_msg_id=data['result']['message_id'],
                sender_name=sender_name,
                text=caption or None,
                file_id=file_id,
                file_name=file_name,
                sent_at=datetime.datetime.now(),
            ))
            db.session.commit()
        else:
            flash(f"Telegram: {data.get('description', 'error')}")
    except Exception as e:
        flash(f"Could not send photo: {e}")


# ── 3. Document / generic file ───────────────────────────────────────────────

def send_file_message(file_path: str, file_name: str, sender_name: str):
    try:
        with open(file_path, 'rb') as f:
            resp = requests.post(
                f"{_base()}/sendDocument",
                data={'chat_id': _group(),
                      'caption': f"\U0001f4ce {file_name}\n\U0001f464 {sender_name}"},
                files={'document': (file_name, f)},
                timeout=30,
            )
        data = resp.json()
        if data.get('ok'):
            doc = data['result'].get('document', {})
            db.session.add(ChatMessage(
                telegram_msg_id=data['result']['message_id'],
                sender_name=sender_name,
                file_id=doc.get('file_id', ''),
                file_name=file_name,
                sent_at=datetime.datetime.now(),
            ))
            db.session.commit()
        else:
            flash(f"Telegram: {data.get('description', 'error')}")
    except Exception as e:
        flash(f"Could not send file: {e}")


# ── 4. Voice message ─────────────────────────────────────────────────────────

def send_voice_message(file_path: str, sender_name: str):
    try:
        with open(file_path, 'rb') as f:
            resp = requests.post(
                f"{_base()}/sendVoice",
                data={'chat_id': _group(), 'caption': f"\U0001f464 {sender_name}"},
                files={'voice': ('voice.ogg', f, 'audio/ogg')},
                timeout=30,
            )
        data = resp.json()
        if data.get('ok'):
            voice = data['result'].get('voice', {})
            db.session.add(ChatMessage(
                telegram_msg_id=data['result']['message_id'],
                sender_name=sender_name,
                file_id=voice.get('file_id', ''),
                file_name='voice_message.ogg',
                sent_at=datetime.datetime.now(),
            ))
            db.session.commit()
        else:
            flash(f"Telegram: {data.get('description', 'error')}")
    except Exception as e:
        flash(f"Could not send voice: {e}")


# ── 5. Get download URL ──────────────────────────────────────────────────────

def get_file_download_url(file_id: str):
    try:
        data = requests.get(
            f"{_base()}/getFile", params={'file_id': file_id}, timeout=10
        ).json()
        if data.get('ok'):
            return f"https://api.telegram.org/file/bot{_token()}/{data['result']['file_path']}"
    except Exception:
        pass
    return None


# ── 6. Auto-delete after 7 days ──────────────────────────────────────────────

def delete_old_messages():
    cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
    old = ChatMessage.query.filter(ChatMessage.sent_at < cutoff).all()
    for msg in old:
        try:
            requests.post(f"{_base()}/deleteMessage",
                          json={'chat_id': _group(), 'message_id': msg.telegram_msg_id},
                          timeout=10)
        except Exception:
            pass
        db.session.delete(msg)
    if old:
        db.session.commit()


# ── 7. Homework ──────────────────────────────────────────────────────────────

def send_homework(title, description, class_name, teacher_name, teacher_id, file_path=None, file_name=None, due_date=None):
    """Send homework to Telegram group and store in DB."""
    caption = f"📚 HOMEWORK — {class_name}\n\n"
    caption += f"Title: {title}\n"
    if description:
        caption += f"Description: {description}\n"
    if due_date:
        caption += f"Due: {due_date}\n"
    caption += f"\nTeacher: {teacher_name}"

    telegram_msg_id = None
    file_id = None
    file_type = None

    try:
        if file_path and file_name:
            ext = file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else ''
            if ext in {'jpg', 'jpeg', 'png', 'gif', 'webp'}:
                with open(file_path, 'rb') as f:
                    resp = requests.post(
                        f"{_base()}/sendPhoto",
                        data={'chat_id': _group(), 'caption': caption},
                        files={'photo': (file_name, f)},
                        timeout=30,
                    )
                data = resp.json()
                if data.get('ok'):
                    telegram_msg_id = data['result']['message_id']
                    photos = data['result'].get('photo', [])
                    file_id = photos[-1]['file_id'] if photos else ''
                    file_type = 'photo'
            else:
                with open(file_path, 'rb') as f:
                    resp = requests.post(
                        f"{_base()}/sendDocument",
                        data={'chat_id': _group(), 'caption': caption},
                        files={'document': (file_name, f)},
                        timeout=30,
                    )
                data = resp.json()
                if data.get('ok'):
                    telegram_msg_id = data['result']['message_id']
                    doc = data['result'].get('document', {})
                    file_id = doc.get('file_id', '')
                    file_type = 'document'
        else:
            resp = requests.post(
                f"{_base()}/sendMessage",
                json={'chat_id': _group(), 'text': caption},
                timeout=10,
            )
            data = resp.json()
            if data.get('ok'):
                telegram_msg_id = data['result']['message_id']
                file_type = 'text'

        hw = Homework(
            title=title,
            description=description,
            class_name=class_name,
            teacher_name=teacher_name,
            teacher_id=teacher_id,
            file_id=file_id,
            file_name=file_name,
            file_type=file_type,
            telegram_msg_id=telegram_msg_id,
            due_date=datetime.date.fromisoformat(due_date) if due_date else None,
            created_at=datetime.datetime.now(),
        )
        db.session.add(hw)
        db.session.commit()
        return True, hw
    except Exception as e:
        print(f"[HOMEWORK] Error: {e}")
        return False, None

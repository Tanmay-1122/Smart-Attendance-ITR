import os
import requests
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from ..telegram.bot import (send_text_message, send_photo_message,
                             send_file_message, send_voice_message,
                             get_file_download_url, delete_old_messages,
                             _token, _group, _base)
from ..models import ChatMessage, User
from .. import db

notes_bp = Blueprint('notes', __name__, url_prefix='/notes')

_IMG   = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.heic', '.heif'}
_VOICE = {'.ogg', '.oga', '.webm', '.mp3', '.m4a', '.wav', '.opus'}


def _classify(msg):
    """Attach .msg_type to a ChatMessage instance."""
    if not msg.file_id:
        msg.msg_type = 'text'
    else:
        ext = os.path.splitext(msg.file_name or '')[1].lower()
        if ext in _IMG:
            msg.msg_type = 'photo'
        elif ext in _VOICE or 'voice' in (msg.file_name or '').lower():
            msg.msg_type = 'voice'
        else:
            msg.msg_type = 'file'
    return msg


@notes_bp.route('/')
@login_required
def index():
    messages = ChatMessage.query.order_by(ChatMessage.sent_at.desc()).limit(100).all()
    messages.reverse()

    sender_ids = list(set(m.sender_id for m in messages if m.sender_id))
    senders = {u.id: u for u in User.query.filter(User.id.in_(sender_ids)).all()} if sender_ids else {}

    for msg in messages:
        _classify(msg)
        msg.download_url = get_file_download_url(msg.file_id) if msg.file_id else None
        sender = senders.get(msg.sender_id)
        msg.sender_photo = sender.profile_photo if sender else None

    return render_template('notes/index.html', messages=messages)


@notes_bp.route('/send', methods=['POST'])
@login_required
def send():
    text  = request.form.get('text', '').strip()
    photo = request.files.get('photo')
    voice = request.files.get('voice')
    file  = request.files.get('file')

    udir = os.path.join('app', 'static', 'uploads')
    os.makedirs(udir, exist_ok=True)

    # ── Voice ──
    if voice and voice.filename:
        path = os.path.join(udir, f"voice_{voice.filename}")
        voice.save(path)
        try:
            send_voice_message(path, current_user.name)
        finally:
            if os.path.exists(path): os.remove(path)
        return jsonify({'ok': True, 'type': 'voice'})

    # ── Photo (+ optional text caption) ──
    if photo and photo.filename:
        path = os.path.join(udir, photo.filename)
        photo.save(path)
        try:
            send_photo_message(path, photo.filename, current_user.name, caption=text)
        finally:
            if os.path.exists(path): os.remove(path)
        return jsonify({'ok': True, 'type': 'photo'})

    # ── Generic file ──
    if file and file.filename:
        path = os.path.join(udir, file.filename)
        file.save(path)
        try:
            send_file_message(path, file.filename, current_user.name)
        finally:
            if os.path.exists(path): os.remove(path)
        return jsonify({'ok': True, 'type': 'file', 'file_name': file.filename})

    # ── Text only ──
    if text:
        # ── /clear command (teacher only) ──
        if text.strip() == '/clear' and current_user.role == 'teacher':
            all_msgs = ChatMessage.query.all()
            for msg in all_msgs:
                try:
                    requests.post(f"{_base()}/deleteMessage",
                                  json={'chat_id': _group(), 'message_id': msg.telegram_msg_id},
                                  timeout=10)
                except Exception:
                    pass
            ChatMessage.query.delete()
            db.session.commit()
            return jsonify({'ok': True, 'type': 'clear'})

        send_text_message(text, current_user.name)
        return jsonify({'ok': True, 'type': 'text'})

    return jsonify({'ok': False, 'error': 'Nothing to send.'})

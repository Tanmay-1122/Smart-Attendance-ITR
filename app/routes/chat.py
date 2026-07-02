from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from ..models import User, PrivateMessage
from .. import db
from datetime import datetime

chat_bp = Blueprint('chat', __name__, url_prefix='/chat')


@chat_bp.route('/<int:user_id>')
@login_required
def private_chat(user_id):
    other_user = db.get_or_404(User, user_id)
    if other_user.id == current_user.id:
        return "Cannot chat with yourself", 400

    # Mark messages from this user as read
    PrivateMessage.query.filter_by(
        sender_id=user_id, receiver_id=current_user.id, read=False
    ).update({'read': True})
    db.session.commit()

    return render_template('chat/private.html', other_user=other_user)


@chat_bp.route('/api/<int:user_id>/messages')
@login_required
def get_messages(user_id):
    page = request.args.get('page', 1, type=int)
    per_page = 50

    messages = PrivateMessage.query.filter(
        ((PrivateMessage.sender_id == current_user.id) & (PrivateMessage.receiver_id == user_id)) |
        ((PrivateMessage.sender_id == user_id) & (PrivateMessage.receiver_id == current_user.id))
    ).order_by(PrivateMessage.sent_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    msgs = []
    for m in reversed(messages.items):
        msgs.append({
            'id': m.id,
            'sender_id': m.sender_id,
            'text': m.text,
            'sent_at': m.sent_at.strftime('%H:%M'),
            'is_mine': m.sender_id == current_user.id,
        })

    return jsonify({'messages': msgs, 'has_more': messages.has_next})


@chat_bp.route('/api/<int:user_id>/send', methods=['POST'])
@login_required
def send_message(user_id):
    data = request.get_json()
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'error': 'Empty message'}), 400

    msg = PrivateMessage(
        sender_id=current_user.id,
        receiver_id=user_id,
        text=text,
    )
    db.session.add(msg)
    db.session.commit()

    return jsonify({
        'ok': True,
        'message': {
            'id': msg.id,
            'sender_id': msg.sender_id,
            'text': msg.text,
            'sent_at': msg.sent_at.strftime('%H:%M'),
            'is_mine': True,
        }
    })


@chat_bp.route('/api/unread')
@login_required
def unread_counts():
    from sqlalchemy import func
    counts = db.session.query(
        PrivateMessage.sender_id,
        func.count(PrivateMessage.id)
    ).filter(
        PrivateMessage.receiver_id == current_user.id,
        PrivateMessage.read == False
    ).group_by(PrivateMessage.sender_id).all()

    return jsonify({str(uid): count for uid, count in counts})

import json
from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from ..models import PushSubscription, TeacherClass, StudentClass, Student, Homework, User
from .. import db
from ..tasks import run_async

notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')


@notifications_bp.route('/settings', methods=['GET'])
@login_required
def settings():
    return render_template('notifications/settings.html',
                           vapid_public_key=current_app.config.get('VAPID_PUBLIC_KEY', ''))


@notifications_bp.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    data = request.get_json()
    if not data or 'endpoint' not in data:
        return jsonify({'error': 'Invalid subscription'}), 400

    endpoint = data['endpoint']
    p256dh = data.get('keys', {}).get('p256dh', '')
    auth_key = data.get('keys', {}).get('auth', '')

    # Check if already subscribed
    existing = PushSubscription.query.filter_by(
        user_id=current_user.id, endpoint=endpoint
    ).first()

    if not existing:
        sub = PushSubscription(
            user_id=current_user.id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth_key=auth_key,
        )
        db.session.add(sub)
        db.session.commit()

    return jsonify({'ok': True})


@notifications_bp.route('/unsubscribe', methods=['POST'])
@login_required
def unsubscribe():
    data = request.get_json()
    endpoint = data.get('endpoint', '') if data else ''

    if endpoint:
        PushSubscription.query.filter_by(
            user_id=current_user.id, endpoint=endpoint
        ).delete()
        db.session.commit()

    return jsonify({'ok': True})


@run_async
def send_push_notification(user_id, title, body, url='/'):
    """Send web push notification to a user's subscribed browsers."""
    vapid_private = current_app.config.get('VAPID_PRIVATE_KEY', '')
    vapid_claims = {
        'sub': current_app.config.get('VAPID_EMAIL', 'mailto:admin@smartattend.com')
    }

    if not vapid_private:
        return

    subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subscriptions:
        return

    payload = json.dumps({
        'title': title,
        'body': body,
        'url': url,
    })

    from pywebpush import webpush, WebPushException
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {
                        'p256dh': sub.p256dh,
                        'auth': sub.auth_key,
                    }
                },
                data=payload,
                vapid_private_key=vapid_private,
                vapid_claims=vapid_claims,
            )
        except WebPushException as e:
            print(f"[PUSH] Failed for user {user_id}: {e}")
            # Remove expired subscriptions
            if '404' in str(e) or '410' in str(e):
                db.session.delete(sub)
                db.session.commit()
        except Exception as e:
            print(f"[PUSH] Error: {e}")


def notify_homework(homework_obj):
    """Send push notification to all enrolled students about new homework."""
    tc = db.session.get(TeacherClass, None)
    from ..models import TeacherClass as TC
    tc = TC.query.filter_by(name=homework_obj.class_name).first()
    if not tc:
        return

    enrollments = StudentClass.query.filter_by(class_id=tc.id).all()
    for sc in enrollments:
        student = sc.student
        if student and student.user:
            send_push_notification(
                student.user.id,
                'New Homework',
                f'{homework_obj.class_name}: {homework_obj.title}',
                f'/student/homework/{homework_obj.id}'
            )


def notify_leave_decision(leave_obj, status):
    """Send push notification about leave decision."""
    student = db.session.get(Student, leave_obj.student_id)
    if student and student.user:
        label = 'approved' if status == 'APPROVED' else 'rejected'
        send_push_notification(
            student.user.id,
            f'Leave Request {label.title()}',
            f'Your leave for {leave_obj.class_name} has been {label}.',
            '/leave/history'
        )


def notify_marks(user_id, subject_name, marks_obtained, total_marks):
    """Send push notification about exam marks."""
    send_push_notification(
        user_id,
        'Exam Result Published',
        f'{subject_name}: {marks_obtained}/{total_marks}',
        '/student/marks'
    )

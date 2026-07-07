import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ..models import LeaveRequest, Student, TeacherClass, StudentClass
from .. import db
from ..email import send_leave_decision_email

leave_bp = Blueprint('leave', __name__, url_prefix='/leave')


@leave_bp.route('/request', methods=['GET', 'POST'])
@login_required
def request_leave():
    student = Student.query.filter_by(user_id=current_user.id).first()
    if not student:
        flash('No student profile found.')
        return redirect(url_for('student.dashboard'))

    enrolled = StudentClass.query.filter_by(student_id=student.id).first()
    if not enrolled:
        flash('You must be enrolled in a class to request leave.')
        return redirect(url_for('student.classes'))

    if request.method == 'POST':
        class_name = request.form.get('class_name', '').strip()
        start_date_str = request.form.get('start_date', '').strip()
        end_date_str = request.form.get('end_date', '').strip()
        reason = request.form.get('reason', '').strip()

        if not class_name or not start_date_str or not end_date_str or not reason:
            flash('All fields are required.')
            return redirect(url_for('leave.request_leave'))

        try:
            start_date = datetime.date.fromisoformat(start_date_str)
            end_date = datetime.date.fromisoformat(end_date_str)
        except ValueError:
            flash('Invalid date format.')
            return redirect(url_for('leave.request_leave'))

        if end_date < start_date:
            flash('End date cannot be before start date.')
            return redirect(url_for('leave.request_leave'))

        if start_date < datetime.date.today():
            flash('Cannot request leave for past dates.')
            return redirect(url_for('leave.request_leave'))

        # Find the teacher for this class
        tc = TeacherClass.query.filter_by(name=class_name).first()
        if not tc:
            flash('Class not found.')
            return redirect(url_for('leave.request_leave'))

        leave = LeaveRequest(
            student_id=student.id,
            class_name=class_name,
            teacher_id=tc.teacher_id,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
        )
        db.session.add(leave)
        db.session.commit()
        flash('Leave request submitted!')
        return redirect(url_for('leave.history'))

    # Get enrolled class names
    enrollments = StudentClass.query.filter_by(student_id=student.id).all()
    classes = [s.tc for s in enrollments if s.tc]

    return render_template('leave/request.html', classes=classes, today=datetime.date.today().isoformat())


@leave_bp.route('/history')
@login_required
def history():
    student = Student.query.filter_by(user_id=current_user.id).first()
    if not student:
        flash('No student profile found.')
        return redirect(url_for('student.dashboard'))

    requests = LeaveRequest.query.filter_by(student_id=student.id).order_by(LeaveRequest.created_at.desc()).all()
    return render_template('leave/history.html', leave_requests=requests)


@leave_bp.route('/pending')
@login_required
def pending():
    if current_user.role != 'teacher':
        flash('Access denied.')
        return redirect(url_for('student.dashboard'))

    my_class_ids = [tc.id for tc in TeacherClass.query.filter_by(teacher_id=current_user.id).all()]
    my_class_names = [tc.name for tc in TeacherClass.query.filter_by(teacher_id=current_user.id).all()]

    requests = LeaveRequest.query.filter(
        LeaveRequest.class_name.in_(my_class_names),
        LeaveRequest.status == 'PENDING'
    ).order_by(LeaveRequest.created_at.desc()).all()

    return render_template('leave/pending.html', leave_requests=requests)


@leave_bp.route('/approve/<int:request_id>', methods=['POST'])
@login_required
def approve(request_id):
    if current_user.role != 'teacher':
        flash('Access denied.')
        return redirect(url_for('student.dashboard'))

    leave = db.get_or_404(LeaveRequest, request_id)
    if leave.teacher_id != current_user.id:
        flash('Access denied.')
        return redirect(url_for('leave.pending'))

    leave.status = 'APPROVED'
    leave.decided_at = datetime.datetime.now()
    leave.teacher_note = request.form.get('note', '').strip() or None
    db.session.commit()

    # Send email notification
    try:
        student = db.session.get(Student, leave.student_id)
        if student and student.user:
            send_leave_decision_email(
                student.user.email, student.user.name,
                'APPROVED', leave.class_name,
                leave.start_date.isoformat(), leave.end_date.isoformat(),
                leave.teacher_note
            )
            if student.parent_email:
                send_leave_decision_email(
                    student.parent_email, student.user.name,
                    'APPROVED', leave.class_name,
                    leave.start_date.isoformat(), leave.end_date.isoformat(),
                    leave.teacher_note
                )
    except Exception as e:
        print(f"[EMAIL] Leave approval email error: {e}")

    # Send push notification
    try:
        from .notifications import notify_leave_decision
        notify_leave_decision(leave, 'APPROVED')
    except Exception as e:
        print(f"[PUSH] Leave approval push error: {e}")

    flash('Leave request approved.')
    return redirect(url_for('leave.pending'))


@leave_bp.route('/reject/<int:request_id>', methods=['POST'])
@login_required
def reject(request_id):
    if current_user.role != 'teacher':
        flash('Access denied.')
        return redirect(url_for('student.dashboard'))

    leave = db.get_or_404(LeaveRequest, request_id)
    if leave.teacher_id != current_user.id:
        flash('Access denied.')
        return redirect(url_for('leave.pending'))

    leave.status = 'REJECTED'
    leave.decided_at = datetime.datetime.now()
    leave.teacher_note = request.form.get('note', '').strip() or None
    db.session.commit()

    # Send email notification
    try:
        student = db.session.get(Student, leave.student_id)
        if student and student.user:
            send_leave_decision_email(
                student.user.email, student.user.name,
                'REJECTED', leave.class_name,
                leave.start_date.isoformat(), leave.end_date.isoformat(),
                leave.teacher_note
            )
            if student.parent_email:
                send_leave_decision_email(
                    student.parent_email, student.user.name,
                    'REJECTED', leave.class_name,
                    leave.start_date.isoformat(), leave.end_date.isoformat(),
                    leave.teacher_note
                )
    except Exception as e:
        print(f"[EMAIL] Leave rejection email error: {e}")

    # Send push notification
    try:
        from .notifications import notify_leave_decision
        notify_leave_decision(leave, 'REJECTED')
    except Exception as e:
        print(f"[PUSH] Leave rejection push error: {e}")

    flash('Leave request rejected.')
    return redirect(url_for('leave.pending'))

import datetime
from collections import defaultdict
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import func
from ..models import AttendanceRecord, Student, TeacherClass, StudentClass, User
from .. import db

analytics_bp = Blueprint('analytics', __name__, url_prefix='/analytics')


@analytics_bp.route('/')
@login_required
def index():
    if current_user.role == 'teacher':
        return redirect(url_for('analytics.teacher_overview'))
    return redirect(url_for('analytics.student_overview'))


@analytics_bp.route('/student')
@login_required
def student_overview():
    student = Student.query.filter_by(user_id=current_user.id).first()
    if not student:
        flash('No student profile found.')
        return redirect(url_for('student.dashboard'))

    enrolled = StudentClass.query.filter_by(student_id=student.id).all()
    enrolled_class_names = [s.tc.name for s in enrolled if s.tc]

    return render_template('analytics/dashboard.html',
                           view='student',
                           student=student,
                           enrolled_classes=enrolled_class_names)


@analytics_bp.route('/class/<int:class_id>')
@login_required
def class_overview(class_id):
    if current_user.role != 'teacher':
        flash('Access denied.')
        return redirect(url_for('student.dashboard'))

    tc = db.get_or_404(TeacherClass, class_id)
    if tc.teacher_id != current_user.id:
        flash('Access denied.')
        return redirect(url_for('teacher.dashboard'))

    return render_template('analytics/dashboard.html',
                           view='class',
                           tc=tc)


@analytics_bp.route('/api/student/<int:student_id>/data')
@login_required
def student_data(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({'error': 'Student not found'}), 404

    records = AttendanceRecord.query.filter_by(student_id=student_id).order_by(AttendanceRecord.date).all()

    # Daily attendance over time (last 60 days)
    today = datetime.date.today()
    daily = {}
    for r in records:
        if r.date and (today - r.date).days <= 60:
            daily[r.date.isoformat()] = r.status

    dates = sorted(daily.keys())
    daily_series = [{'date': d, 'status': daily[d]} for d in dates]

    # Status distribution
    status_counts = {'PRESENT': 0, 'REVIEW': 0, 'ABSENT': 0}
    for r in records:
        if r.status in status_counts:
            status_counts[r.status] += 1

    # Class-wise breakdown
    class_stats = {}
    for r in records:
        cn = r.class_name
        if cn not in class_stats:
            class_stats[cn] = {'total': 0, 'present': 0, 'absent': 0, 'review': 0}
        class_stats[cn]['total'] += 1
        if r.status in class_stats[cn]:
            class_stats[cn][r.status.lower()] += 1

    # Weekly pattern (Mon-Sat)
    weekly = [0] * 6  # Mon=0 .. Sat=5
    weekly_total = [0] * 6
    for r in records:
        if r.date:
            dow = r.date.weekday()
            if dow < 6:  # Mon-Sat only
                weekly_total[dow] += 1
                if r.status == 'PRESENT':
                    weekly[dow] += 1

    weekly_pct = [round(weekly[i] / weekly_total[i] * 100) if weekly_total[i] > 0 else 0 for i in range(6)]

    total = len(records)
    present = sum(1 for r in records if r.status == 'PRESENT')
    percentage = round(present / total * 100) if total else 0

    return jsonify({
        'daily': daily_series,
        'status_counts': status_counts,
        'class_stats': class_stats,
        'weekly_pct': weekly_pct,
        'total': total,
        'present': present,
        'percentage': percentage,
    })


@analytics_bp.route('/api/class/<int:class_id>/data')
@login_required
def class_data(class_id):
    tc = db.session.get(TeacherClass, class_id)
    if not tc or tc.teacher_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    enrollments = StudentClass.query.filter_by(class_id=class_id).all()
    student_ids = [sc.student_id for sc in enrollments]

    records = AttendanceRecord.query.filter(
        AttendanceRecord.student_id.in_(student_ids),
        AttendanceRecord.class_name == tc.name
    ).all() if student_ids else []

    # Per-student stats
    student_stats = {}
    for r in records:
        sid = r.student_id
        if sid not in student_stats:
            student_stats[sid] = {'total': 0, 'present': 0, 'absent': 0, 'review': 0}
        student_stats[sid]['total'] += 1
        if r.status in student_stats[sid]:
            student_stats[sid][r.status.lower()] += 1

    student_list = []
    for sid, stats in student_stats.items():
        student = db.session.get(Student, sid)
        name = student.user.name if student and student.user else 'Unknown'
        pct = round(stats['present'] / stats['total'] * 100) if stats['total'] else 0
        student_list.append({
            'id': sid, 'name': name,
            'total': stats['total'],
            'present': stats['present'],
            'absent': stats['absent'],
            'review': stats['review'],
            'pct': pct,
            'at_risk': pct < 75 and stats['total'] > 0,
        })

    # Daily trend (last 60 days)
    today = datetime.date.today()
    daily = defaultdict(lambda: {'present': 0, 'total': 0})
    for r in records:
        if r.date and (today - r.date).days <= 60:
            daily[r.date.isoformat()]['total'] += 1
            if r.status == 'PRESENT':
                daily[r.date.isoformat()]['present'] += 1

    dates = sorted(daily.keys())
    daily_series = [{'date': d, 'pct': round(daily[d]['present'] / daily[d]['total'] * 100) if daily[d]['total'] else 0} for d in dates]

    # Overall stats
    total_records = len(records)
    total_present = sum(1 for r in records if r.status == 'PRESENT')
    overall_pct = round(total_present / total_records * 100) if total_records else 0
    at_risk = sum(1 for s in student_list if s['at_risk'])

    return jsonify({
        'students': student_list,
        'daily': daily_series,
        'overall_pct': overall_pct,
        'total_records': total_records,
        'at_risk_count': at_risk,
    })

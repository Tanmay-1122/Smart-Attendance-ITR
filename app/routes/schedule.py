import datetime
import math
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from ..models import ClassSchedule, TeacherClass, StudentClass, Student, User
from .. import db

schedule_bp = Blueprint('schedule', __name__, url_prefix='/schedule')

DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
DAY_ABBR = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def _attach_slot_metrics(schedules):
    """Calculate visual metrics for each schedule slot."""
    for s in schedules:
        start_mins = s.start_time.hour * 60 + s.start_time.minute
        end_mins = s.end_time.hour * 60 + s.end_time.minute
        duration_mins = end_mins - start_mins
        s.top_offset = s.start_time.minute / 60.0  # 0-1 fraction past the hour
        s.duration_hours = duration_mins / 60.0
    return schedules


def _organize_by_day(schedules):
    """Group schedules by day_of_week, sorted by start_time."""
    by_day = {i: [] for i in range(7)}
    for s in schedules:
        by_day[s.day_of_week].append(s)
    for day in by_day:
        by_day[day].sort(key=lambda x: (x.start_time.hour, x.start_time.minute))
    return by_day


@schedule_bp.route('/')
@login_required
def timetable():
    if current_user.role == 'student':
        student = Student.query.filter_by(user_id=current_user.id).first()
        if not student:
            flash('No student profile found.')
            return redirect(url_for('student.dashboard'))

        enrolled = StudentClass.query.filter_by(student_id=student.id).all()
        if not enrolled:
            flash('You must be enrolled in a class to view the timetable.')
            return redirect(url_for('student.classes'))

        class_ids = [e.class_id for e in enrolled]
        schedules = ClassSchedule.query.options(
            joinedload(ClassSchedule.tc).joinedload(TeacherClass.teacher)
        ).filter(ClassSchedule.class_id.in_(class_ids)).all()
        class_name = ', '.join(e.tc.name for e in enrolled if e.tc)
    elif current_user.role == 'teacher':
        my_class_ids = [tc.id for tc in TeacherClass.query.filter_by(teacher_id=current_user.id).all()]
        schedules = ClassSchedule.query.options(
            joinedload(ClassSchedule.tc).joinedload(TeacherClass.teacher)
        ).filter(ClassSchedule.class_id.in_(my_class_ids)).all() if my_class_ids else []
        class_name = None
    elif current_user.role in ('hod', 'principal'):
        schedules = ClassSchedule.query.options(
            joinedload(ClassSchedule.tc).joinedload(TeacherClass.teacher)
        ).all()
        class_name = None
    else:
        schedules = []
        class_name = None

    _attach_slot_metrics(schedules)
    by_day = _organize_by_day(schedules)

    return render_template('schedule/timetable.html',
                           by_day=by_day, days=DAYS, day_abbr=DAY_ABBR,
                           class_name=class_name,
                           now=datetime.datetime.now())


@schedule_bp.route('/manage')
@login_required
def manage():
    if current_user.role not in ('teacher', 'hod', 'principal'):
        flash('Access denied.')
        return redirect(url_for('student.dashboard'))

    if current_user.role == 'teacher':
        classes = TeacherClass.query.filter_by(teacher_id=current_user.id).order_by(TeacherClass.name).all()
    else:
        classes = TeacherClass.query.order_by(TeacherClass.name).all()

    my_class_ids = [tc.id for tc in classes]
    schedules = ClassSchedule.query.filter(ClassSchedule.class_id.in_(my_class_ids)).all() if my_class_ids else []

    by_class = {}
    for tc in classes:
        by_class[tc.id] = [s for s in schedules if s.class_id == tc.id]
        by_class[tc.id].sort(key=lambda x: (x.day_of_week, x.start_time))

    return render_template('schedule/manage.html', classes=classes, by_class=by_class, days=DAYS)


@schedule_bp.route('/add', methods=['POST'])
@login_required
def add():
    if current_user.role not in ('teacher', 'hod', 'principal'):
        flash('Access denied.')
        return redirect(url_for('student.dashboard'))

    class_id = request.form.get('class_id', type=int)
    day_of_week = request.form.get('day_of_week', type=int)
    start_time_str = request.form.get('start_time', '').strip()
    end_time_str = request.form.get('end_time', '').strip()
    room = request.form.get('room', '').strip()

    if not class_id or day_of_week is None or not start_time_str or not end_time_str:
        flash('All fields are required.')
        return redirect(url_for('schedule.manage'))

    tc = db.session.get(TeacherClass, class_id)
    if not tc:
        flash('Class not found.')
        return redirect(url_for('schedule.manage'))
    if current_user.role == 'teacher' and tc.teacher_id != current_user.id:
        flash('Access denied.')
        return redirect(url_for('schedule.manage'))

    try:
        start_time = datetime.time.fromisoformat(start_time_str)
        end_time = datetime.time.fromisoformat(end_time_str)
    except ValueError:
        flash('Invalid time format.')
        return redirect(url_for('schedule.manage'))

    if end_time <= start_time:
        flash('End time must be after start time.')
        return redirect(url_for('schedule.manage'))

    # Check for conflicts
    existing = ClassSchedule.query.filter_by(class_id=class_id, day_of_week=day_of_week).all()
    for s in existing:
        if start_time < s.end_time and end_time > s.start_time:
            flash('This time slot conflicts with an existing schedule.')
            return redirect(url_for('schedule.manage'))

    schedule = ClassSchedule(
        class_id=class_id,
        teacher_id=current_user.id,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        room=room or None,
    )
    db.session.add(schedule)
    db.session.commit()
    flash('Schedule added!')
    return redirect(url_for('schedule.manage'))


@schedule_bp.route('/edit/<int:schedule_id>', methods=['POST'])
@login_required
def edit(schedule_id):
    if current_user.role not in ('teacher', 'hod', 'principal'):
        return jsonify({'error': 'Access denied'}), 403

    schedule = db.get_or_404(ClassSchedule, schedule_id)
    if current_user.role == 'teacher' and schedule.teacher_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400

    day_of_week = data.get('day_of_week', schedule.day_of_week)
    start_time_str = data.get('start_time', '')
    end_time_str = data.get('end_time', '')
    room = data.get('room', schedule.room or '')

    if not start_time_str or not end_time_str:
        return jsonify({'error': 'Start and end times required'}), 400

    try:
        start_time = datetime.time.fromisoformat(start_time_str)
        end_time = datetime.time.fromisoformat(end_time_str)
    except ValueError:
        return jsonify({'error': 'Invalid time format'}), 400

    if end_time <= start_time:
        return jsonify({'error': 'End time must be after start time'}), 400

    # Check conflicts (exclude self)
    existing = ClassSchedule.query.filter(
        ClassSchedule.id != schedule.id,
        ClassSchedule.class_id == schedule.class_id,
        ClassSchedule.day_of_week == day_of_week,
    ).all()
    for s in existing:
        if start_time < s.end_time and end_time > s.start_time:
            return jsonify({'error': 'Time conflict with existing schedule'}), 409

    schedule.day_of_week = day_of_week
    schedule.start_time = start_time
    schedule.end_time = end_time
    schedule.room = room or None
    db.session.commit()

    return jsonify({'success': True})


@schedule_bp.route('/delete/<int:schedule_id>', methods=['POST'])
@login_required
def delete(schedule_id):
    schedule = db.get_or_404(ClassSchedule, schedule_id)
    if current_user.role == 'teacher' and schedule.teacher_id != current_user.id:
        flash('Access denied.')
        return redirect(url_for('schedule.manage'))

    db.session.delete(schedule)
    db.session.commit()
    flash('Schedule removed.')
    return redirect(url_for('schedule.manage'))


@schedule_bp.route('/api/today')
@login_required
def today():
    today_dow = datetime.date.today().weekday()
    if current_user.role == 'student':
        student = Student.query.filter_by(user_id=current_user.id).first()
        if not student:
            return jsonify([])
        enrolled = StudentClass.query.filter_by(student_id=student.id).all()
        if not enrolled:
            return jsonify([])
        class_ids = [e.class_id for e in enrolled]
        schedules = ClassSchedule.query.options(
            joinedload(ClassSchedule.tc).joinedload(TeacherClass.teacher)
        ).filter(
            ClassSchedule.class_id.in_(class_ids),
            ClassSchedule.day_of_week == today_dow
        ).all()
    elif current_user.role in ('hod', 'principal'):
        schedules = ClassSchedule.query.options(
            joinedload(ClassSchedule.tc).joinedload(TeacherClass.teacher)
        ).filter(ClassSchedule.day_of_week == today_dow).all()
    else:
        my_class_ids = [tc.id for tc in TeacherClass.query.filter_by(teacher_id=current_user.id).all()]
        schedules = ClassSchedule.query.options(
            joinedload(ClassSchedule.tc).joinedload(TeacherClass.teacher)
        ).filter(
            ClassSchedule.class_id.in_(my_class_ids),
            ClassSchedule.day_of_week == today_dow
        ).all() if my_class_ids else []

    schedules.sort(key=lambda x: x.start_time)
    result = []
    for s in schedules:
        tc = s.tc
        result.append({
            'class_name': tc.name if tc else 'Unknown',
            'start_time': s.start_time.strftime('%H:%M'),
            'end_time': s.end_time.strftime('%H:%M'),
            'room': s.room or '',
            'teacher_name': tc.teacher.name if tc and tc.teacher else '',
        })
    return jsonify(result)

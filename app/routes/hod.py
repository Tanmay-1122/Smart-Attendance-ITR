import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ..models import User, Student, Department, TeacherClass, StudentClass, AttendanceRecord, LeaveRequest
from .. import db

hod_bp = Blueprint('hod', __name__, url_prefix='/hod')


def hod_required(f):
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != 'hod':
            flash('Access denied. HOD privileges required.')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@hod_bp.route('/dashboard')
@hod_required
def dashboard():
    dept = db.session.get(Department, current_user.department_id)
    if not dept:
        flash('No department assigned. Contact admin.')
        return redirect(url_for('auth.login'))

    teachers = User.query.filter_by(role='teacher', department_id=dept.id).all()
    students = Student.query.join(User).filter(User.department_id == dept.id).all()
    classes = TeacherClass.query.filter(
        TeacherClass.teacher_id.in_([t.id for t in teachers])
    ).all() if teachers else []

    total_students = len(students)
    total_teachers = len(teachers)
    total_classes = len(classes)

    today = datetime.date.today()
    today_records = AttendanceRecord.query.filter(
        AttendanceRecord.date == today,
        AttendanceRecord.student_id.in_([s.id for s in students])
    ).all() if students else []
    today_present = sum(1 for r in today_records if r.status == 'PRESENT')
    today_absent = sum(1 for r in today_records if r.status == 'ABSENT')

    # Attendance by class
    class_attendance = []
    for tc in classes:
        class_students = Student.query.join(StudentClass).filter(
            StudentClass.class_id == tc.id
        ).all()
        if class_students:
            total = len(class_students)
            present = AttendanceRecord.query.filter(
                AttendanceRecord.date == today,
                AttendanceRecord.student_id.in_([s.id for s in class_students]),
                AttendanceRecord.class_name == tc.name,
                AttendanceRecord.status == 'PRESENT'
            ).count()
            pct = round(present / total * 100, 1) if total else 0
            class_attendance.append({'name': tc.name, 'total': total, 'present': present, 'pct': pct})

    # Pending leave requests
    pending_leaves = LeaveRequest.query.filter(
        LeaveRequest.teacher_id.in_([t.id for t in teachers]),
        LeaveRequest.status == 'PENDING'
    ).order_by(LeaveRequest.created_at.desc()).limit(10).all() if teachers else []

    return render_template('hod/dashboard.html',
                           dept=dept,
                           total_students=total_students,
                           total_teachers=total_teachers,
                           total_classes=total_classes,
                           today_present=today_present,
                           today_absent=today_absent,
                           class_attendance=class_attendance,
                           pending_leaves=pending_leaves,
                           today=today)


@hod_bp.route('/teachers')
@hod_required
def teachers():
    dept = db.session.get(Department, current_user.department_id)
    if not dept:
        flash('No department assigned.')
        return redirect(url_for('auth.login'))

    search = request.args.get('search', '').strip()
    query = User.query.filter_by(role='teacher', department_id=dept.id)
    if search:
        query = query.filter(User.name.ilike(f'%{search}%') | User.email.ilike(f'%{search}%'))
    teachers_list = query.order_by(User.name).all()

    # Get class count per teacher
    teacher_stats = []
    for t in teachers_list:
        class_count = TeacherClass.query.filter_by(teacher_id=t.id).count()
        student_count = db.session.query(StudentClass).join(TeacherClass).filter(
            TeacherClass.teacher_id == t.id
        ).count()
        teacher_stats.append({'user': t, 'classes': class_count, 'students': student_count})

    return render_template('hod/teachers.html', dept=dept, teachers=teacher_stats, search=search)


@hod_bp.route('/students')
@hod_required
def students():
    dept = db.session.get(Department, current_user.department_id)
    if not dept:
        flash('No department assigned.')
        return redirect(url_for('auth.login'))

    search = request.args.get('search', '').strip()
    query = Student.query.join(User).filter(User.department_id == dept.id)
    if search:
        query = query.filter(User.name.ilike(f'%{search}%') | User.email.ilike(f'%{search}%') | Student.roll_number.ilike(f'%{search}%'))
    students_list = query.order_by(User.name).all()

    # Enrolled classes count per student
    student_data = []
    for s in students_list:
        enrolled = StudentClass.query.filter_by(student_id=s.id).count()
        student_data.append({'student': s, 'user': s.user, 'enrolled': enrolled})

    return render_template('hod/students.html', dept=dept, students=student_data, search=search)


@hod_bp.route('/teachers/update-subjects', methods=['POST'])
@hod_required
def update_teacher_subjects():
    dept = db.session.get(Department, current_user.department_id)
    if not dept:
        return {'error': 'No department assigned'}, 400

    user_id = request.form.get('user_id', type=int)
    subjects = request.form.get('subjects', '').strip()

    teacher = db.session.get(User, user_id)
    if not teacher or teacher.role != 'teacher' or teacher.department_id != dept.id:
        flash('Invalid teacher.')
        return redirect(url_for('hod.teachers'))

    teacher.subjects = subjects if subjects else None
    db.session.commit()
    flash(f'Subjects updated for {teacher.name}.')
    return redirect(url_for('hod.teachers'))

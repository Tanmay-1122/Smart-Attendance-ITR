import datetime
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from ..models import User, Student, Department, TeacherClass, AttendanceRecord, LeaveRequest
from .. import db

principal_bp = Blueprint('principal', __name__, url_prefix='/principal')


def principal_required(f):
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != 'principal':
            flash('Access denied. Principal privileges required.')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@principal_bp.route('/dashboard')
@principal_required
def dashboard():
    today = datetime.date.today()

    total_students = User.query.filter_by(role='student').count()
    total_teachers = User.query.filter_by(role='teacher').count()
    total_hods = User.query.filter_by(role='hod').count()
    total_departments = Department.query.count()

    departments = Department.query.order_by(Department.name).all()

    dept_stats = []
    for dept in departments:
        dept_users = User.query.filter_by(department_id=dept.id)
        dept_students = Student.query.join(User).filter(User.department_id == dept.id).all()
        dept_teachers = User.query.filter_by(role='teacher', department_id=dept.id).count()
        dept_hod = User.query.filter_by(role='hod', department_id=dept.id).first()
        student_ids = [s.id for s in dept_students]

        today_present = 0
        today_absent = 0
        if student_ids:
            today_records = AttendanceRecord.query.filter(
                AttendanceRecord.date == today,
                AttendanceRecord.student_id.in_(student_ids)
            ).all()
            today_present = sum(1 for r in today_records if r.status == 'PRESENT')
            today_absent = sum(1 for r in today_records if r.status == 'ABSENT')

        total_students_in_dept = len(dept_students)
        attendance_pct = round(today_present / total_students_in_dept * 100, 1) if total_students_in_dept else 0

        dept_stats.append({
            'dept': dept,
            'hod': dept_hod,
            'students': total_students_in_dept,
            'teachers': dept_teachers,
            'today_present': today_present,
            'today_absent': today_absent,
            'attendance_pct': attendance_pct,
        })

    today_all_records = AttendanceRecord.query.filter_by(date=today).all()
    overall_present = sum(1 for r in today_all_records if r.status == 'PRESENT')
    overall_absent = sum(1 for r in today_all_records if r.status == 'ABSENT')
    overall_total = overall_present + overall_absent
    overall_attendance_pct = round(overall_present / overall_total * 100, 1) if overall_total else 0

    pending_leaves_all = LeaveRequest.query.filter_by(status='PENDING').order_by(
        LeaveRequest.created_at.desc()
    ).limit(10).all()

    return render_template('principal/dashboard.html',
                           total_students=total_students,
                           total_teachers=total_teachers,
                           total_hods=total_hods,
                           total_departments=total_departments,
                           overall_present=overall_present,
                           overall_absent=overall_absent,
                           overall_attendance_pct=overall_attendance_pct,
                           dept_stats=dept_stats,
                           pending_leaves=pending_leaves_all,
                           today=today)

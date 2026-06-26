from flask import Blueprint, render_template
from flask_login import login_required, current_user
from ..models import AttendanceRecord, Student

student_bp = Blueprint('student', __name__, url_prefix='/student')

@student_bp.route('/dashboard')
@login_required
def dashboard():
    student = Student.query.filter_by(user_id=current_user.id).first()
    records = []
    if student:
        records = AttendanceRecord.query.filter_by(
            student_id=student.id
        ).order_by(AttendanceRecord.date.desc()).all()

    return render_template('student/dashboard.html', records=records)
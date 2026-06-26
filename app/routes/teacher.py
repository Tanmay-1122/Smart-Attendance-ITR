import os
import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ..models import AttendanceRecord, Student
from .. import db

teacher_bp = Blueprint('teacher', __name__, url_prefix='/teacher')


@teacher_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('teacher/dashboard.html')


@teacher_bp.route('/scan', methods=['POST'])
@login_required
def scan():
    photos = []
    for i in ['photo1', 'photo2', 'photo3']:
        f = request.files[i]
        path = os.path.join('app/static/uploads', f.filename)
        f.save(path)
        photos.append(path)

    class_name = request.form['class_name']

    # placeholder until face engine is ready
    results = []
    students = Student.query.all()
    for s in students:
        results.append({
            'student_id': s.id,
            'name':       s.user.name,
            'roll_number': s.roll_number,
            'status':     'PRESENT',
            'best_score': 0.99,
            'seen_in':    '3/3'
        })

    for path in photos:
        if os.path.exists(path):
            os.remove(path)

    return render_template('teacher/results.html',
                           results=results,
                           class_name=class_name,
                           date=datetime.date.today())


@teacher_bp.route('/save_attendance', methods=['POST'])
@login_required
def save_attendance():
    class_name = request.form['class_name']
    students   = Student.query.all()

    for student in students:
        key = f'status_{student.id}'
        if key in request.form:
            status = request.form[key]

            existing = AttendanceRecord.query.filter_by(
                student_id=student.id,
                class_name=class_name,
                date=datetime.date.today()
            ).first()

            if existing:
                existing.status = status
            else:
                record = AttendanceRecord(
                    student_id=student.id,
                    class_name=class_name,
                    date=datetime.date.today(),
                    status=status,
                    score=0.0
                )
                db.session.add(record)

    db.session.commit()
    flash('Attendance saved!')
    return redirect(url_for('teacher.dashboard'))
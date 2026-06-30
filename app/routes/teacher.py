import os
import base64 as b64lib
import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, current_app, jsonify
from flask_login import login_required, current_user
from ..models import AttendanceRecord, Student, Homework, TeacherClass, StudentClass
from .. import db
from ..face_engine.voting import process_three_photos
from ..telegram.bot import send_homework, get_file_download_url
from ..ai_summary import summarize_homework, extract_text_from_file
import pandas as pd

teacher_bp = Blueprint('teacher', __name__, url_prefix='/teacher')

@teacher_bp.route('/dashboard')
@login_required
def dashboard():
    classes = TeacherClass.query.filter_by(teacher_id=current_user.id).order_by(TeacherClass.created_at.desc()).all()
    preselected = request.args.get('class', '')
    return render_template('teacher/dashboard.html', classes=classes, preselected=preselected)

@teacher_bp.route('/classes')
@login_required
def classes():
    classes = TeacherClass.query.filter_by(teacher_id=current_user.id).order_by(TeacherClass.created_at.desc()).all()
    return render_template('teacher/classes.html', classes=classes)

@teacher_bp.route('/classes/add', methods=['POST'])
@login_required
def add_class():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    if not name:
        flash('Class name is required.')
        return redirect(url_for('teacher.classes'))
    existing = TeacherClass.query.filter_by(teacher_id=current_user.id, name=name).first()
    if existing:
        flash('A class with this name already exists.')
        return redirect(url_for('teacher.classes'))
    new_class = TeacherClass(teacher_id=current_user.id, name=name, description=description or None)
    db.session.add(new_class)
    db.session.commit()
    flash(f'Class "{name}" created!')
    return redirect(url_for('teacher.classes'))

@teacher_bp.route('/classes/delete/<int:class_id>', methods=['POST'])
@login_required
def delete_class(class_id):
    tc = db.get_or_404(TeacherClass, class_id)
    if tc.teacher_id != current_user.id:
        flash('You can only delete your own classes.')
        return redirect(url_for('teacher.classes'))
    StudentClass.query.filter_by(class_id=tc.id).delete()
    db.session.delete(tc)
    db.session.commit()
    flash('Class deleted.')
    return redirect(url_for('teacher.classes'))

@teacher_bp.route('/classes/all')
@login_required
def all_classes():
    classes = TeacherClass.query.order_by(TeacherClass.name).all()
    return jsonify([{'id': c.id, 'name': c.name, 'description': c.description} for c in classes])

@teacher_bp.route('/classes/<int:class_id>')
@login_required
def class_detail(class_id):
    tc = db.get_or_404(TeacherClass, class_id)
    if tc.teacher_id != current_user.id:
        flash('Access denied.')
        return redirect(url_for('teacher.classes'))

    enrollments = StudentClass.query.filter_by(class_id=tc.id).all()

    student_ids = [sc.student_id for sc in enrollments if sc.student]
    records = AttendanceRecord.query.filter(
        AttendanceRecord.student_id.in_(student_ids),
        AttendanceRecord.class_name == tc.name
    ).all() if student_ids else []

    stats_map = {}
    for r in records:
        sid = r.student_id
        if sid not in stats_map:
            stats_map[sid] = {'total': 0, 'present': 0, 'absent': 0, 'review': 0}
        stats_map[sid]['total'] += 1
        if r.status == 'PRESENT':
            stats_map[sid]['present'] += 1
        elif r.status == 'ABSENT':
            stats_map[sid]['absent'] += 1
        elif r.status == 'REVIEW':
            stats_map[sid]['review'] += 1

    students_with_stats = []
    for sc in enrollments:
        student = sc.student
        if not student:
            continue
        s = stats_map.get(student.id, {'total': 0, 'present': 0, 'absent': 0, 'review': 0})
        pct = round(s['present'] / s['total'] * 100) if s['total'] else 0
        students_with_stats.append({
            'student': student,
            'enrollment': sc,
            'total': s['total'],
            'present': s['present'],
            'absent': s['absent'],
            'review': s['review'],
            'pct': pct
        })

    return render_template('teacher/class_detail.html', tc=tc, students=students_with_stats)

@teacher_bp.route('/classes/<int:class_id>/unenroll/<int:student_id>', methods=['POST'])
@login_required
def unenroll_student(class_id, student_id):
    tc = db.get_or_404(TeacherClass, class_id)
    if tc.teacher_id != current_user.id:
        flash('Access denied.')
        return redirect(url_for('teacher.classes'))
    sc = StudentClass.query.filter_by(class_id=class_id, student_id=student_id).first()
    if sc:
        db.session.delete(sc)
        db.session.commit()
        flash('Student removed from class.')
    return redirect(url_for('teacher.class_detail', class_id=class_id))

@teacher_bp.route('/scan', methods=['POST'])
@login_required
def scan():
    class_name = request.form.get('class_name', '').strip()
    if not class_name:
        flash('Please enter a class name.')
        return redirect(url_for('teacher.dashboard'))

    tc = TeacherClass.query.filter_by(teacher_id=current_user.id, name=class_name).first()
    if not tc:
        flash('Invalid class. Please select a class from your list.')
        return redirect(url_for('teacher.dashboard'))

    upload_dir = os.path.join('app', 'static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)

    photos = []
    # Accept base64 photos captured from the camera UI
    for i in ['1', '2', '3']:
        raw = request.form.get(f'photo{i}_data', '')
        if not raw:
            continue
        if ',' in raw:
            raw = raw.split(',', 1)[1]
        try:
            img_bytes = b64lib.b64decode(raw)
            path = os.path.join(upload_dir, f'scan_{current_user.id}_{i}.jpg')
            with open(path, 'wb') as fh:
                fh.write(img_bytes)
            photos.append(path)
        except Exception as e:
            print(f"[SCAN] Failed to decode photo {i}: {e}")

    if len(photos) < 3:
        for p in photos:
            if os.path.exists(p):
                os.remove(p)
        flash('Could not read all 3 photos. Please try again.')
        return redirect(url_for('teacher.dashboard'))

    # Log enrolled students for debugging
    enrolled = StudentClass.query.filter_by(class_id=tc.id).count()
    print(f"[SCAN] Running scan for class '{class_name}' (id={tc.id}) | enrolled students: {enrolled}")

    results = []
    try:
        results = process_three_photos(photos, class_name, class_id=tc.id)
        print(f"[SCAN] Scan complete — {len(results)} result(s)")
    except Exception as e:
        import traceback
        print(f"[SCAN] Engine error: {e}")
        traceback.print_exc()
        flash(f"Scan error: {str(e)}")
    finally:
        for path in photos:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    return render_template('teacher/results.html',
                           results=results,
                           class_name=class_name,
                           date=datetime.date.today())


@teacher_bp.route('/save_attendance', methods=['POST'])
@login_required
def save_attendance():
    # Identify student IDs from form status fields
    student_ids = []
    for key in request.form.keys():
        if key.startswith('status_'):
            try:
                student_ids.append(int(key.split('_')[1]))
            except ValueError:
                continue

    for student_id in student_ids:
        status = request.form[f'status_{student_id}']
        score_val = request.form.get(f'score_{student_id}', '0.0')
        enrolled_class = request.form.get(f'enrolled_class_{student_id}', '').strip()
        try:
            score = float(score_val)
        except ValueError:
            score = 0.0

        # Skip students not enrolled in any class
        if not enrolled_class or enrolled_class == 'Not enrolled':
            continue

        class_name = enrolled_class

        existing = AttendanceRecord.query.filter_by(
            student_id=student_id,
            class_name=class_name,
            date=datetime.date.today()
        ).first()

        if existing:
            existing.status = status
            existing.score = score
        else:
            record = AttendanceRecord(
                student_id=student_id,
                class_name=class_name,
                date=datetime.date.today(),
                status=status,
                score=score
            )
            db.session.add(record)

    db.session.commit()
    flash('Attendance saved successfully!')
    return redirect(url_for('teacher.dashboard'))

@teacher_bp.route('/export')
@login_required
def export():
    class_name = request.args.get('class_name', '').strip()
    if not class_name:
        classes = TeacherClass.query.filter_by(teacher_id=current_user.id).order_by(TeacherClass.name).all()
        return render_template('teacher/export.html', classes=classes)

    tc = TeacherClass.query.filter_by(teacher_id=current_user.id, name=class_name).first()
    if not tc:
        flash('Invalid class.')
        return redirect(url_for('teacher.export'))

    records = AttendanceRecord.query.filter_by(class_name=class_name).all()

    data = []
    for r in records:
        student_name = r.student.user.name if (r.student and r.student.user) else "Unknown"
        roll_number = r.student.roll_number if r.student else ""
        data.append({
            'Student Name': student_name,
            'Roll Number': roll_number,
            'Class Name': r.class_name,
            'Date': r.date.strftime('%Y-%m-%d') if r.date else "",
            'Status': r.status,
            'AI Match Score': r.score
        })

    if not data:
        flash(f'No records found for class: {class_name}')
        return render_template('teacher/export.html')

    df = pd.DataFrame(data)
    csv_data = df.to_csv(index=False)

    response = make_response(csv_data)
    response.headers["Content-Disposition"] = f"attachment; filename={class_name}_attendance.csv"
    response.headers["Content-Type"] = "text/csv"
    return response


@teacher_bp.route('/homework', methods=['GET', 'POST'])
@login_required
def homework():
    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        class_name  = request.form.get('class_name', '').strip()
        due_date    = request.form.get('due_date', '').strip()
        file        = request.files.get('homework_file')

        if not title or not class_name:
            flash('Title and class name are required.')
            return redirect(url_for('teacher.homework'))

        tc = TeacherClass.query.filter_by(teacher_id=current_user.id, name=class_name).first()
        if not tc:
            flash('Invalid class. Please select a class from your list.')
            return redirect(url_for('teacher.homework'))

        upload_dir = os.path.join('app', 'static', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)

        file_path = None
        file_name = None
        if file and file.filename:
            file_name = file.filename
            file_path = os.path.join(upload_dir, file_name)
            file.save(file_path)

        success, hw = send_homework(
            title=title,
            description=description,
            class_name=class_name,
            teacher_name=current_user.name,
            teacher_id=current_user.id,
            file_path=file_path,
            file_name=file_name,
            due_date=due_date if due_date else None,
        )

        # Auto-generate AI summary
        if success and hw:
            file_text = None
            if file_path and os.path.exists(file_path):
                file_text = extract_text_from_file(file_path, file_name or '')
            summary = summarize_homework(title, description, file_text)
            if summary:
                hw.summary = summary
                db.session.commit()

        if file_path and os.path.exists(file_path):
            os.remove(file_path)

        if success:
            flash('Homework posted!')
        else:
            flash('Failed to post homework to Telegram.')

        return redirect(url_for('teacher.homework'))

    # GET — show form + recent homework
    recent = Homework.query.order_by(Homework.created_at.desc()).limit(20).all()
    classes = TeacherClass.query.filter_by(teacher_id=current_user.id).order_by(TeacherClass.name).all()
    return render_template('teacher/homework.html', homework_list=recent, classes=classes)


@teacher_bp.route('/homework/delete/<int:hw_id>', methods=['POST'])
@login_required
def delete_homework(hw_id):
    hw = db.get_or_404(Homework, hw_id)
    if hw.teacher_id != current_user.id:
        flash('You can only delete your own homework.')
        return redirect(url_for('teacher.homework'))

    # Delete from Telegram
    if hw.telegram_msg_id:
        try:
            import requests
            requests.post(f"https://api.telegram.org/bot{current_app.config['TELEGRAM_BOT_TOKEN']}/deleteMessage",
                          json={'chat_id': current_app.config['TELEGRAM_GROUP_ID'],
                                'message_id': hw.telegram_msg_id},
                          timeout=10)
        except Exception:
            pass

    db.session.delete(hw)
    db.session.commit()
    flash('Homework deleted.')
    return redirect(url_for('teacher.homework'))
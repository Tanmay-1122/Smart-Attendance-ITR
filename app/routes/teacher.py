import os
import uuid
import base64 as b64lib
import datetime
import json
from urllib.parse import urlencode
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, current_app, jsonify
from flask_login import login_required, current_user
from ..models import AttendanceRecord, Student, Homework, TeacherClass, StudentClass, MarksRecord
from .. import db
from ..telegram.bot import send_homework, get_file_download_url
from ..ai_summary import summarize_homework, extract_text_from_file
from ..email import send_attendance_summary_email, send_homework_alert_email, send_marks_email
from ..marks_ocr import extract_marks_from_image
from werkzeug.utils import secure_filename
import pandas as pd

teacher_bp = Blueprint('teacher', __name__, url_prefix='/teacher')

@teacher_bp.route('/dashboard')
@login_required
def dashboard():
    classes = TeacherClass.query.filter_by(teacher_id=current_user.id).order_by(TeacherClass.created_at.desc()).all()
    preselected = request.args.get('class', '')
    classes_json = json.dumps([{'id': c.id, 'name': c.name} for c in classes])
    return render_template('teacher/dashboard.html', classes=classes, preselected=preselected, classes_json=classes_json)

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
        from ..face_client import scan_faces

        student_embeddings = {}
        enrolled_students = StudentClass.query.filter_by(class_id=tc.id).all()
        for sc in enrolled_students:
            student = sc.student
            if student and student.face_embedding:
                try:
                    emb_data = json.loads(student.face_embedding)
                    if emb_data and isinstance(emb_data[0], list):
                        student_embeddings[student.id] = emb_data
                    else:
                        student_embeddings[student.id] = [emb_data]
                except Exception:
                    pass

        if not student_embeddings:
            flash('No enrolled students with face data found.')
            return redirect(url_for('teacher.dashboard'))

        api_result = scan_faces(photos, student_embeddings)

        names = {}
        for sc in enrolled_students:
            student = sc.student
            if student and student.user:
                names[student.id] = student.user.name

        rolls = {}
        for sc in enrolled_students:
            student = sc.student
            if student:
                rolls[student.id] = student.roll_number

        for r in api_result.get('results', []):
            sid = r['student_id']
            results.append({
                'student_id': sid,
                'name': names.get(sid, 'Unknown'),
                'roll_number': rolls.get(sid, ''),
                'enrolled_class': class_name,
                'status': r['status'],
                'best_score': r['best_score'],
                'seen_in': r['seen_in'],
            })

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

    # Send attendance summary emails to students and parents
    try:
        for student_id in student_ids:
            student = db.session.get(Student, student_id)
            if not student or not student.user:
                continue
            if not student.user.email_notifications:
                continue

            # Build records for this student today
            today_records = AttendanceRecord.query.filter_by(
                student_id=student_id, date=datetime.date.today()
            ).all()
            email_records = [{
                'class_name': r.class_name,
                'date': r.date.strftime('%d %b %Y') if r.date else '',
                'status': r.status,
            } for r in today_records]

            # Calculate overall percentage
            all_records = AttendanceRecord.query.filter_by(student_id=student_id).all()
            att_map = {}
            for r in all_records:
                if r.date:
                    att_map[r.date.isoformat()] = r.status
            total_present = sum(1 for v in att_map.values() if v == 'PRESENT')
            total_days = len(att_map)
            percentage = round(total_present / total_days * 100) if total_days else 0

            # Send to student
            send_attendance_summary_email(
                student.user.email, student.user.name,
                email_records, percentage
            )

            # Send to parent if configured
            if student.parent_email:
                send_attendance_summary_email(
                    student.parent_email, student.user.name,
                    email_records, percentage
                )
    except Exception as e:
        print(f"[EMAIL] Attendance summary error: {e}")

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


@teacher_bp.route('/student-panel')
@login_required
def student_panel():
    all_students = Student.query.all()

    my_classes = TeacherClass.query.filter_by(teacher_id=current_user.id).order_by(TeacherClass.created_at.desc()).all()

    class_data = []
    for tc in my_classes:
        enrollments = StudentClass.query.filter_by(class_id=tc.id).all()
        enrolled_students = []
        for sc in enrollments:
            if sc.student and sc.student.user:
                enrolled_students.append(sc.student)
        class_data.append({
            'class': tc,
            'students': enrolled_students,
            'count': len(enrolled_students)
        })

    enrolled_student_ids = set()
    for tc in my_classes:
        for sc in StudentClass.query.filter_by(class_id=tc.id).all():
            enrolled_student_ids.add(sc.student_id)

    unenrolled = [s for s in all_students if s.id not in enrolled_student_ids]

    return render_template('teacher/student_panel.html',
                           all_students=all_students,
                           class_data=class_data,
                           unenrolled=unenrolled)


@teacher_bp.route('/student-panel/enroll', methods=['POST'])
@login_required
def panel_enroll_student():
    student_id = request.form.get('student_id', type=int)
    class_id = request.form.get('class_id', type=int)
    if not student_id or not class_id:
        flash('Invalid request.')
        return redirect(url_for('teacher.student_panel'))

    tc = db.get_or_404(TeacherClass, class_id)
    if tc.teacher_id != current_user.id:
        flash('Access denied.')
        return redirect(url_for('teacher.student_panel'))

    student = db.get_or_404(Student, student_id)
    existing = StudentClass.query.filter_by(student_id=student_id, class_id=class_id).first()
    if existing:
        flash('Student is already enrolled in this class.')
        return redirect(url_for('teacher.student_panel'))

    existing_any = StudentClass.query.filter_by(student_id=student_id).first()
    if existing_any:
        flash('Student is already enrolled in another class. Remove them first.')
        return redirect(url_for('teacher.student_panel'))

    sc = StudentClass(student_id=student_id, class_id=class_id)
    db.session.add(sc)
    db.session.commit()
    flash(f'{student.user.name} enrolled in {tc.name}.')
    return redirect(url_for('teacher.student_panel'))


@teacher_bp.route('/student-panel/unenroll', methods=['POST'])
@login_required
def panel_unenroll_student():
    student_id = request.form.get('student_id', type=int)
    class_id = request.form.get('class_id', type=int)
    if not student_id or not class_id:
        flash('Invalid request.')
        return redirect(url_for('teacher.student_panel'))

    tc = db.get_or_404(TeacherClass, class_id)
    if tc.teacher_id != current_user.id:
        flash('Access denied.')
        return redirect(url_for('teacher.student_panel'))

    sc = StudentClass.query.filter_by(student_id=student_id, class_id=class_id).first()
    if sc:
        db.session.delete(sc)
        db.session.commit()
        flash('Student removed from class.')
    return redirect(url_for('teacher.student_panel'))


@teacher_bp.route('/student-panel/delete/<int:student_id>', methods=['POST'])
@login_required
def panel_delete_student(student_id):
    student = db.get_or_404(Student, student_id)
    user = student.user
    name = user.name if user else 'Unknown'

    # Check that the student is enrolled in at least one of this teacher's classes
    my_class_ids = [tc.id for tc in TeacherClass.query.filter_by(teacher_id=current_user.id).all()]
    enrolled_in_my_class = StudentClass.query.filter(
        StudentClass.student_id == student.id,
        StudentClass.class_id.in_(my_class_ids)
    ).first()
    if not enrolled_in_my_class:
        flash('You can only delete students enrolled in your classes.')
        return redirect(url_for('teacher.student_panel'))

    StudentClass.query.filter_by(student_id=student.id).delete()
    AttendanceRecord.query.filter_by(student_id=student.id).delete()
    db.session.delete(student)
    if user:
        db.session.delete(user)
    db.session.commit()
    flash(f'Student account "{name}" has been deleted. They can re-register if needed.')
    return redirect(url_for('teacher.student_panel'))


@teacher_bp.route('/attendance')
@login_required
def attendance_records():
    class_name = request.args.get('class_name', '').strip()
    page = request.args.get('page', 1, type=int)
    my_classes = TeacherClass.query.filter_by(teacher_id=current_user.id).order_by(TeacherClass.name).all()

    if not class_name:
        class_stats = []
        for tc in my_classes:
            records = AttendanceRecord.query.filter_by(class_name=tc.name).all()
            dates = sorted(set(r.date for r in records if r.date), reverse=True)
            present = sum(1 for r in records if r.status == 'PRESENT')
            review = sum(1 for r in records if r.status == 'REVIEW')
            absent = sum(1 for r in records if r.status == 'ABSENT')
            class_stats.append({
                'class': tc,
                'total_records': len(records),
                'sessions': len(dates),
                'present': present,
                'review': review,
                'absent': absent,
            })
        return render_template('teacher/attendance.html', classes=my_classes, class_stats=class_stats)

    tc = TeacherClass.query.filter_by(teacher_id=current_user.id, name=class_name).first()
    if not tc:
        flash('Invalid class.')
        return redirect(url_for('teacher.attendance_records'))

    pagination = AttendanceRecord.query.filter_by(class_name=class_name).order_by(AttendanceRecord.date.desc()).paginate(page=page, per_page=20, error_out=False)

    by_date = {}
    for r in pagination.items:
        d = r.date
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(r)

    args_no_page = request.args.copy()
    args_no_page.pop('page', None)
    url_without_page = urlencode(args_no_page.items(multi=True))
    return render_template('teacher/attendance_detail.html', tc=tc, by_date=by_date, total_records=pagination.total, pagination=pagination, url_without_page=url_without_page)


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
            file_name = secure_filename(file.filename)
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

            # Send homework alert emails to enrolled students
            try:
                tc = TeacherClass.query.filter_by(teacher_id=current_user.id, name=class_name).first()
                if tc:
                    enrollments = StudentClass.query.filter_by(class_id=tc.id).all()
                    for sc in enrollments:
                        student = sc.student
                        if student and student.user and student.user.email_notifications:
                            send_homework_alert_email(
                                student.user.email, student.user.name,
                                title, class_name, current_user.name,
                                due_date=due_date
                            )
                            if student.parent_email:
                                send_homework_alert_email(
                                    student.parent_email, student.user.name,
                                    title, class_name, current_user.name,
                                    due_date=due_date
                                )
            except Exception as e:
                print(f"[EMAIL] Homework alert error: {e}")

            # Send push notifications
            try:
                from ..routes.notifications import notify_homework
                notify_homework(hw)
            except Exception as e:
                print(f"[PUSH] Homework push error: {e}")
        else:
            flash('Failed to post homework to Telegram.')

        return redirect(url_for('teacher.homework'))

    # GET — show form + paginated homework
    page = request.args.get('page', 1, type=int)
    pagination = Homework.query.order_by(Homework.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    classes = TeacherClass.query.filter_by(teacher_id=current_user.id).order_by(TeacherClass.name).all()
    args_no_page = request.args.copy()
    args_no_page.pop('page', None)
    url_without_page = urlencode(args_no_page.items(multi=True))
    return render_template('teacher/homework.html', homework_list=pagination.items, classes=classes, pagination=pagination, url_without_page=url_without_page)


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


# ---------- Continuous Individual Scan API ----------

@teacher_bp.route('/api/face_api_status')
@login_required
def face_api_status():
    from ..face_client import check_api_health
    ok = check_api_health()
    return jsonify({'available': ok, 'url': current_app.config.get('HF_FACE_API_URL', '')})


@teacher_bp.route('/api/scan_single', methods=['POST'])
@login_required
def scan_single():
    class_name = request.form.get('class_name', '').strip()
    photo_data = request.form.get('photo_data', '')

    if not class_name or not photo_data:
        return jsonify({'error': 'Missing class_name or photo_data'}), 400

    tc = TeacherClass.query.filter_by(teacher_id=current_user.id, name=class_name).first()
    if not tc:
        return jsonify({'error': 'Invalid class'}), 400

    upload_dir = os.path.join('app', 'static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)

    if ',' in photo_data:
        photo_data = photo_data.split(',', 1)[1]

    try:
        img_bytes = b64lib.b64decode(photo_data)
        path = os.path.join(upload_dir, f'single_scan_{current_user.id}.jpg')
        with open(path, 'wb') as fh:
            fh.write(img_bytes)
    except Exception:
        return jsonify({'error': 'Failed to decode photo'}), 400

    try:
        import json
        from ..face_client import identify_face

        student_embeddings = {}
        enrolled_students = StudentClass.query.filter_by(class_id=tc.id).all()
        for sc in enrolled_students:
            student = sc.student
            if student and student.face_embedding:
                try:
                    emb_data = json.loads(student.face_embedding)
                    if emb_data and isinstance(emb_data[0], list):
                        student_embeddings[student.id] = emb_data
                    else:
                        student_embeddings[student.id] = [emb_data]
                except Exception:
                    pass

        if not student_embeddings:
            return jsonify({'matched': False, 'reason': 'No enrolled students with face data'})

        result = identify_face(path, student_embeddings)
        sid = result.get('student_id')

        if sid:
            student = db.session.get(Student, sid)
            student_name = student.user.name if student and student.user else 'Unknown'
            roll = student.roll_number if student else ''
            result['name'] = student_name
            result['roll_number'] = roll
        else:
            result['name'] = None
            result['roll_number'] = None

        result['class_name'] = class_name

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


@teacher_bp.route('/api/mark_present', methods=['POST'])
@login_required
def mark_present():
    student_id = request.form.get('student_id', type=int)
    class_name = request.form.get('class_name', '').strip()
    score = request.form.get('score', 0.0, type=float)

    if not student_id or not class_name:
        return jsonify({'error': 'Missing student_id or class_name'}), 400

    tc = TeacherClass.query.filter_by(teacher_id=current_user.id, name=class_name).first()
    if not tc:
        return jsonify({'error': 'Invalid class'}), 400

    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({'error': 'Student not found'}), 404

    # Check if already marked present today
    existing = AttendanceRecord.query.filter_by(
        student_id=student_id,
        class_name=class_name,
        date=datetime.date.today()
    ).first()

    if existing:
        if existing.status == 'PRESENT':
            return jsonify({
                'success': True,
                'already_present': True,
                'name': student.user.name if student.user else 'Unknown',
                'score': existing.score,
            })
        existing.status = 'PRESENT'
        existing.score = score
    else:
        record = AttendanceRecord(
            student_id=student_id,
            class_name=class_name,
            date=datetime.date.today(),
            status='PRESENT',
            score=score,
        )
        db.session.add(record)

    db.session.commit()

    # Send email notification
    try:
        if student.user and student.user.email_notifications:
            from ..email import send_attendance_summary_email
            today_records = AttendanceRecord.query.filter_by(
                student_id=student_id, date=datetime.date.today()
            ).all()
            email_records = [{
                'class_name': r.class_name,
                'date': r.date.strftime('%d %b %Y') if r.date else '',
                'status': r.status,
            } for r in today_records]
            all_records = AttendanceRecord.query.filter_by(student_id=student_id).all()
            att_map = {}
            for r in all_records:
                if r.date:
                    att_map[r.date.isoformat()] = r.status
            total_present = sum(1 for v in att_map.values() if v == 'PRESENT')
            total_days = len(att_map)
            percentage = round(total_present / total_days * 100) if total_days else 0
            send_attendance_summary_email(
                student.user.email, student.user.name,
                email_records, percentage
            )
            if student.parent_email:
                send_attendance_summary_email(
                    student.parent_email, student.user.name,
                    email_records, percentage
                )
    except Exception as e:
        print(f"[EMAIL] Attendance summary error: {e}")

    name = student.user.name if student.user else 'Unknown'
    return jsonify({
        'success': True,
        'already_present': False,
        'name': name,
        'score': score,
        'student_id': student_id,
    })


@teacher_bp.route('/api/today_present')
@login_required
def today_present():
    class_name = request.args.get('class_name', '').strip()
    if not class_name:
        return jsonify({'error': 'Missing class_name'}), 400

    tc = TeacherClass.query.filter_by(teacher_id=current_user.id, name=class_name).first()
    if not tc:
        return jsonify({'error': 'Invalid class'}), 400

    records = AttendanceRecord.query.filter_by(
        class_name=class_name,
        date=datetime.date.today()
    ).all()

    students = []
    for r in records:
        student = r.student
        if student and student.user:
            students.append({
                'student_id': student.id,
                'name': student.user.name,
                'roll_number': student.roll_number,
                'score': r.score,
                'status': r.status,
            })

    return jsonify({'students': students})


# ---------- Marks Scanning & Auto-Sending ----------

@teacher_bp.route('/marks')
@login_required
def marks():
    classes = TeacherClass.query.filter_by(teacher_id=current_user.id).order_by(TeacherClass.name).all()
    page = request.args.get('page', 1, type=int)
    pagination = db.session.query(
        MarksRecord.scan_session_id, MarksRecord.subject, MarksRecord.exam_type,
        MarksRecord.class_name, MarksRecord.created_at
    ).filter(
        MarksRecord.sent == True,
        MarksRecord.class_name.in_([c.name for c in classes])
    ).distinct().order_by(MarksRecord.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    args_no_page = request.args.copy()
    args_no_page.pop('page', None)
    url_without_page = urlencode(args_no_page.items(multi=True))
    return render_template('teacher/marks.html', classes=classes, sent_sessions=pagination.items, pagination=pagination, url_without_page=url_without_page)


@teacher_bp.route('/marks/scan', methods=['POST'])
@login_required
def marks_scan():
    class_name = request.form.get('class_name', '').strip()
    subject = request.form.get('subject', '').strip()
    exam_type = request.form.get('exam_type', 'exam').strip()
    image_file = request.files.get('marksheet_image')

    if not all([class_name, subject, image_file]):
        flash('Class name, subject, and marksheet image are required.')
        return redirect(url_for('teacher.marks'))

    tc = TeacherClass.query.filter_by(teacher_id=current_user.id, name=class_name).first()
    if not tc:
        flash('Invalid class.')
        return redirect(url_for('teacher.marks'))

    upload_dir = os.path.join('app', 'static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    filename = f'markscan_{current_user.id}_{uuid.uuid4().hex[:8]}.jpg'
    filepath = os.path.join(upload_dir, filename)
    image_file.save(filepath)

    extracted = extract_marks_from_image(filepath)
    if not extracted:
        if os.path.exists(filepath):
            os.remove(filepath)
        flash('Could not extract marks from the image. Please try a clearer photo.')
        return redirect(url_for('teacher.marks'))

    enrolled_students = StudentClass.query.filter_by(class_id=tc.id).all()
    enrolled_map = {}
    for sc in enrolled_students:
        student = sc.student
        if student and student.user:
            enrolled_map[student.roll_number] = student
            enrolled_map[student.user.name.lower().strip()] = student

    matched = []
    unmatched = []
    for entry in extracted:
        roll = str(entry.get('roll_number', '')).strip()
        name = str(entry.get('name', '')).strip()
        student = enrolled_map.get(roll) or enrolled_map.get(name.lower())
        if student:
            matched.append({
                'student_id': student.id,
                'roll_number': student.roll_number,
                'name': student.user.name,
                'marks_obtained': entry['marks_obtained'],
                'total_marks': entry['total_marks'],
                'percentage': entry.get('percentage'),
            })
        else:
            unmatched.append(entry)

    session_id = uuid.uuid4().hex[:12]

    return render_template('teacher/marks_preview.html',
                           class_name=class_name,
                           subject=subject,
                           exam_type=exam_type,
                           session_id=session_id,
                           matched=matched,
                           unmatched=unmatched,
                           image_path=f'/static/uploads/{filename}')


@teacher_bp.route('/marks/send', methods=['POST'])
@login_required
def marks_send():
    class_name = request.form.get('class_name', '').strip()
    subject = request.form.get('subject', '').strip()
    exam_type = request.form.get('exam_type', 'exam').strip()
    session_id = request.form.get('session_id', '').strip()

    if not session_id:
        flash('Session ID missing.')
        return redirect(url_for('teacher.marks'))

    student_ids = request.form.getlist('student_ids[]')
    marks_values = request.form.getlist('marks_obtained[]')
    total_values = request.form.getlist('total_marks[]')
    pct_values = request.form.getlist('percentage[]')

    saved_count = 0
    for i, sid in enumerate(student_ids):
        try:
            marks = float(marks_values[i]) if i < len(marks_values) else 0
            total = float(total_values[i]) if i < len(total_values) else 0
            pct = float(pct_values[i]) if i < len(pct_values) and pct_values[i] else None
        except (ValueError, IndexError):
            continue

        record = MarksRecord(
            student_id=int(sid),
            class_name=class_name,
            subject=subject,
            exam_type=exam_type,
            marks_obtained=marks,
            total_marks=total,
            percentage=pct,
            scan_session_id=session_id,
            sent=False,
        )
        db.session.add(record)
        saved_count += 1

    db.session.commit()

    # Send notifications
    sent_count = 0
    for i, sid in enumerate(student_ids):
        try:
            marks = float(marks_values[i]) if i < len(marks_values) else 0
            total = float(total_values[i]) if i < len(total_values) else 0
            pct = float(pct_values[i]) if i < len(pct_values) and pct_values[i] else None
        except (ValueError, IndexError):
            continue

        student = db.session.get(Student, int(sid))
        if not student or not student.user:
            continue

        try:
            send_marks_email(
                to=student.user.email,
                name=student.user.name,
                subject_name=subject,
                exam_type=exam_type,
                marks_obtained=marks,
                total_marks=total,
                percentage=pct,
                class_name=class_name,
            )
            if student.parent_email:
                send_marks_email(
                    to=student.parent_email,
                    name=student.user.name,
                    subject_name=subject,
                    exam_type=exam_type,
                    marks_obtained=marks,
                    total_marks=total,
                    percentage=pct,
                    class_name=class_name,
                )
            from ..routes.notifications import notify_marks
            notify_marks(student.user.id, subject, marks, total)

            record = MarksRecord.query.filter_by(
                scan_session_id=session_id, student_id=int(sid)
            ).first()
            if record:
                record.sent = True

            sent_count += 1
        except Exception as e:
            print(f"[MARKS] Failed to notify student {sid}: {e}")

    db.session.commit()

    flash(f'Saved {saved_count} records and sent notifications to {sent_count} students!')
    return redirect(url_for('teacher.marks'))
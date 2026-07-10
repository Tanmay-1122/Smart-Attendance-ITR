import base64
import json
import datetime
import os
from urllib.parse import urlencode
from collections import defaultdict
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import func
from ..models import AttendanceRecord, Student, Homework, TeacherClass, StudentClass, MarksRecord
from .. import db
from ..telegram.bot import get_file_download_url
from ..ai_summary import summarize_homework, extract_text_from_file

student_bp = Blueprint('student', __name__, url_prefix='/student')


@student_bp.route('/dashboard')
@login_required
def dashboard():
    student = Student.query.filter_by(user_id=current_user.id).first()

    enrolled_class_names = []
    if student:
        enrolled = StudentClass.query.filter_by(student_id=student.id).all()
        enrolled_class_names = [s.tc.name for s in enrolled if s.tc]

    records = []
    att_map = {}
    percentage = 0
    streak = 0
    best_streak = 0
    class_stats = {}
    total_present = total_absent = total_review = 0

    if student:
        base_query = AttendanceRecord.query.filter_by(student_id=student.id)
        if enrolled_class_names:
            base_query = base_query.filter(AttendanceRecord.class_name.in_(enrolled_class_names))

        records = base_query.order_by(AttendanceRecord.date.desc()).limit(10).all()

        all_dates = base_query.with_entities(
            AttendanceRecord.date,
            func.max(AttendanceRecord.status)
        ).group_by(AttendanceRecord.date).all()

        for date_val, status in all_dates:
            if date_val:
                att_map[date_val.isoformat()] = status

        total_present = sum(1 for v in att_map.values() if v == 'PRESENT')
        total_review = sum(1 for v in att_map.values() if v == 'REVIEW')
        total_absent = sum(1 for v in att_map.values() if v == 'ABSENT')
        total_days = total_present + total_review + total_absent
        percentage = round(total_present / total_days * 100) if total_days else 0

        today = datetime.date.today()
        day = today
        while True:
            if day.weekday() == 6:
                day -= datetime.timedelta(days=1)
                continue
            if att_map.get(day.isoformat()) == 'PRESENT':
                streak += 1
                day -= datetime.timedelta(days=1)
            else:
                break

        cur = 0
        for iso in sorted(att_map):
            dt = datetime.date.fromisoformat(iso)
            if dt.weekday() == 6:
                continue
            if att_map[iso] == 'PRESENT':
                cur += 1
                best_streak = max(best_streak, cur)
            else:
                cur = 0

        class_rows = base_query.with_entities(
            AttendanceRecord.class_name,
            func.count(AttendanceRecord.id).label('total'),
            func.sum(func.cast(AttendanceRecord.status == 'PRESENT', db.Integer)).label('present')
        ).group_by(AttendanceRecord.class_name).all()

        class_stats = {
            cn: {
                'total': t,
                'present': p or 0,
                'pct': round((p or 0) / t * 100) if t else 0
            }
            for cn, t, p in class_rows
        }

    return render_template('student/dashboard.html',
                           records=records,
                           attendance_json=json.dumps(att_map),
                           percentage=percentage,
                           streak=streak,
                           best_streak=best_streak,
                           class_stats=class_stats,
                           total_present=total_present,
                           total_review=total_review,
                           total_absent=total_absent,
                           enrolled=bool(student and student.face_embedding))


@student_bp.route('/enroll')
@login_required
def enroll():
    return render_template('student/enroll.html')

@student_bp.route('/save_embedding', methods=['POST'])
@login_required
def save_embedding():
    data = request.get_json()
    if not data or 'images' not in data:
        return jsonify({'error': 'No image data provided'}), 400

    images_data = data['images']
    roll_number = data.get('roll_number')

    if len(images_data) != 5:
        return jsonify({'error': 'Exactly 5 photos required'}), 400

    upload_dir = os.path.join('app', 'static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)

    photo_paths = []
    for idx, image_data in enumerate(images_data):
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        try:
            img_bytes = base64.b64decode(image_data)
            path = os.path.join(upload_dir, f'enroll_{current_user.id}_{idx}.jpg')
            with open(path, 'wb') as fh:
                fh.write(img_bytes)
            photo_paths.append(path)
        except Exception:
            return jsonify({'error': f'Failed to decode photo {idx+1}'}), 400

    try:
        from ..face_client import enroll_student
        result = enroll_student(photo_paths, current_user.id)
        embeddings = result.get('embeddings', [])
    except Exception as e:
        return jsonify({'error': f'Enrollment failed: {str(e)}'}), 500
    finally:
        for p in photo_paths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    if not embeddings:
        return jsonify({'error': 'No face detected in any photo. Make sure your face is clearly visible.'}), 400

    student = Student.query.filter_by(user_id=current_user.id).first()
    if not student:
        student = Student(user_id=current_user.id, roll_number=roll_number or '')
        db.session.add(student)
    elif roll_number:
        student.roll_number = roll_number

    student.face_embedding = json.dumps(embeddings)
    db.session.commit()

    return jsonify({'success': True, 'message': f'Face enrolled with {len(embeddings)} photos!'})


@student_bp.route('/classes')
@login_required
def classes():
    student = Student.query.filter_by(user_id=current_user.id).first()
    all_classes = TeacherClass.query.order_by(TeacherClass.name).all()
    enrolled_ids = set()
    enrolled_classes = []
    if student:
        enrolled = StudentClass.query.filter_by(student_id=student.id).all()
        enrolled_classes = enrolled
        enrolled_ids = {s.class_id for s in enrolled}
    return render_template('student/classes.html',
                           all_classes=all_classes,
                           enrolled_classes=enrolled_classes,
                           enrolled_ids=enrolled_ids)

@student_bp.route('/classes/enroll/<int:class_id>', methods=['POST'])
@login_required
def enroll_class(class_id):
    student = Student.query.filter_by(user_id=current_user.id).first()
    if not student:
        flash('Please enroll your face first.')
        return redirect(url_for('student.enroll'))
    tc = db.get_or_404(TeacherClass, class_id)
    existing = StudentClass.query.filter_by(student_id=student.id, class_id=tc.id).first()
    if existing:
        flash('You are already enrolled in this class.')
    else:
        # Check if already enrolled in another class
        current_enrollment = StudentClass.query.filter_by(student_id=student.id).first()
        if current_enrollment:
            flash(f'You are already enrolled in "{current_enrollment.tc.name}". Unenroll first to join another class.')
            return redirect(url_for('student.classes'))
        sc = StudentClass(student_id=student.id, class_id=tc.id)
        db.session.add(sc)
        db.session.commit()
        flash(f'Enrolled in "{tc.name}"!')
    return redirect(url_for('student.classes'))

@student_bp.route('/classes/unenroll/<int:class_id>', methods=['POST'])
@login_required
def unenroll_class(class_id):
    student = Student.query.filter_by(user_id=current_user.id).first()
    if student:
        sc = StudentClass.query.filter_by(student_id=student.id, class_id=class_id).first()
        if sc:
            db.session.delete(sc)
            db.session.commit()
            flash('Unenrolled from class.')
    return redirect(url_for('student.classes'))


@student_bp.route('/homework')
@login_required
def homework():
    page = request.args.get('page', 1, type=int)
    pagination = Homework.query.order_by(Homework.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    all_hw = pagination.items
    for hw in all_hw:
        hw.download_url = get_file_download_url(hw.file_id) if hw.file_id else None
    args_no_page = request.args.copy()
    args_no_page.pop('page', None)
    url_without_page = urlencode(args_no_page.items(multi=True))
    return render_template('student/homework.html', homework_list=all_hw, pagination=pagination, url_without_page=url_without_page)


@student_bp.route('/homework/<int:hw_id>')
@login_required
def homework_detail(hw_id):
    hw = db.get_or_404(Homework, hw_id)
    hw.download_url = get_file_download_url(hw.file_id) if hw.file_id else None
    return render_template('student/homework_detail.html', hw=hw)


@student_bp.route('/homework/calendar_data')
@login_required
def homework_calendar_data():
    """Return homework dates for the calendar view."""
    all_hw = Homework.query.all()
    data = {}
    for hw in all_hw:
        if hw.created_at:
            key = hw.created_at.strftime('%Y-%m-%d')
            if key not in data:
                data[key] = []
            data[key].append({
                'id': hw.id,
                'title': hw.title,
                'class_name': hw.class_name,
                'has_file': bool(hw.file_id),
            })
    return jsonify(data)


@student_bp.route('/homework/<int:hw_id>/summarize', methods=['POST'])
@login_required
def homework_summarize(hw_id):
    """Generate AI summary for a homework assignment."""
    hw = db.get_or_404(Homework, hw_id)

    if hw.summary:
        return jsonify({'ok': True, 'summary': hw.summary})

    file_text = None
    if hw.file_id and hw.file_name:
        download_url = get_file_download_url(hw.file_id)
        if download_url:
            import tempfile, requests
            try:
                resp = requests.get(download_url, timeout=30)
                if resp.ok:
                    ext = hw.file_name.rsplit('.', 1)[-1].lower() if '.' in hw.file_name else ''
                    if ext in {'txt', 'md'}:
                        with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
                            tmp.write(resp.content)
                            file_text = extract_text_from_file(tmp.name, hw.file_name)
                            os.unlink(tmp.name)
            except Exception:
                pass

    summary = summarize_homework(hw.title, hw.description, file_text)
    if summary:
        hw.summary = summary
        db.session.commit()
        return jsonify({'ok': True, 'summary': summary})

    return jsonify({'ok': False, 'error': 'Failed to generate summary.'})


@student_bp.route('/marks')
@login_required
def marks():
    student = Student.query.filter_by(user_id=current_user.id).first()
    if not student:
        return render_template('student/marks.html', records=[], pagination=None)

    page = request.args.get('page', 1, type=int)
    pagination = MarksRecord.query.filter_by(student_id=student.id).order_by(MarksRecord.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    records = pagination.items
    args_no_page = request.args.copy()
    args_no_page.pop('page', None)
    url_without_page = urlencode(args_no_page.items(multi=True))
    return render_template('student/marks.html', records=records, pagination=pagination, url_without_page=url_without_page)

import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ..models import Announcement, StudentClass, Student, TeacherClass
from .. import db

announcements_bp = Blueprint('announcements', __name__, url_prefix='/announcements')


@announcements_bp.route('/')
@login_required
def index():
    query = Announcement.query

    if current_user.role == 'student':
        student = Student.query.filter_by(user_id=current_user.id).first()
        enrolled_class = None
        if student:
            sc = StudentClass.query.filter_by(student_id=student.id).first()
            if sc and sc.tc:
                enrolled_class = sc.tc.name

        # Show ALL announcements + CLASS announcements for enrolled class
        if enrolled_class:
            query = query.filter(
                (Announcement.target == 'ALL') |
                ((Announcement.target == 'CLASS') & (Announcement.target_class == enrolled_class))
            )
        else:
            query = query.filter(Announcement.target == 'ALL')

    elif current_user.role == 'teacher':
        my_class_names = [tc.name for tc in TeacherClass.query.filter_by(teacher_id=current_user.id).all()]
        query = query.filter(
            (Announcement.target == 'ALL') |
            ((Announcement.target == 'CLASS') & (Announcement.target_class.in_(my_class_names))) |
            (Announcement.author_id == current_user.id)
        )
    # Admin sees everything

    announcements = query.order_by(Announcement.pinned.desc(), Announcement.created_at.desc()).all()
    return render_template('announcements/index.html', announcements=announcements)


@announcements_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if current_user.role == 'student':
        flash('Only teachers and admins can create announcements.')
        return redirect(url_for('announcements.index'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        body = request.form.get('body', '').strip()
        target = request.form.get('target', 'ALL')
        target_class = request.form.get('target_class', '').strip()
        priority = request.form.get('priority', 'NORMAL')

        if not title or not body:
            flash('Title and body are required.')
            return redirect(url_for('announcements.create'))

        if target == 'CLASS' and not target_class:
            flash('Please select a class for class-specific announcements.')
            return redirect(url_for('announcements.create'))

        ann = Announcement(
            author_id=current_user.id,
            title=title,
            body=body,
            target=target,
            target_class=target_class if target == 'CLASS' else None,
            priority=priority,
        )
        db.session.add(ann)
        db.session.commit()
        flash('Announcement posted!')
        return redirect(url_for('announcements.index'))

    classes = TeacherClass.query.filter_by(teacher_id=current_user.id).all() if current_user.role == 'teacher' else []

    return render_template('announcements/create.html', classes=classes)


@announcements_bp.route('/delete/<int:ann_id>', methods=['POST'])
@login_required
def delete(ann_id):
    ann = db.get_or_404(Announcement, ann_id)
    if ann.author_id != current_user.id and not current_user.is_admin:
        flash('Access denied.')
        return redirect(url_for('announcements.index'))

    db.session.delete(ann)
    db.session.commit()
    flash('Announcement deleted.')
    return redirect(url_for('announcements.index'))


@announcements_bp.route('/pin/<int:ann_id>', methods=['POST'])
@login_required
def pin(ann_id):
    if not current_user.is_admin:
        flash('Only admins can pin announcements.')
        return redirect(url_for('announcements.index'))

    ann = db.get_or_404(Announcement, ann_id)
    ann.pinned = not ann.pinned
    db.session.commit()
    flash('Announcement ' + ('pinned' if ann.pinned else 'unpinned') + '.')
    return redirect(url_for('announcements.index'))

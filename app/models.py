import json
import datetime
from . import db, login_manager
from flask_login import UserMixin

class Department(db.Model):
    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)

    def __repr__(self):
        return f'<Department {self.name}>'


class User(UserMixin, db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100))
    email         = db.Column(db.String(100), unique=True)
    password      = db.Column(db.String(200))
    role          = db.Column(db.String(10))   # 'student', 'teacher', 'hod', 'principal'
    is_admin      = db.Column(db.Boolean, default=False)
    profile_photo = db.Column(db.String(200), nullable=True)  # filename in uploads/
    email_notifications = db.Column(db.Boolean, default=True)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=True)

    department = db.relationship('Department', backref='members', foreign_keys=[department_id])

    @property
    def avatar_url(self):
        if self.profile_photo:
            return f'/static/uploads/{self.profile_photo}'
        return None

class Student(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('user.id'))
    roll_number    = db.Column(db.String(20))
    face_embedding = db.Column(db.Text)   # stored as JSON string of 512 numbers
    parent_email   = db.Column(db.String(100), nullable=True)

    # relationship to User
    user = db.relationship('User', backref=db.backref('student', uselist=False))

    @property
    def embeddings_list(self):
        if not self.face_embedding:
            return []
        data = json.loads(self.face_embedding)
        if not data:
            return []
        if isinstance(data[0], list):
            return data
        return [data]

class AttendanceRecord(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    class_name = db.Column(db.String(50))
    date       = db.Column(db.Date)
    status     = db.Column(db.String(10))   # PRESENT / REVIEW / ABSENT
    score      = db.Column(db.Float)

    # relationship to Student
    student = db.relationship('Student', backref='attendance_records')

class ChatMessage(db.Model):
    __tablename__   = 'chat_message'
    id              = db.Column(db.Integer, primary_key=True)
    telegram_msg_id = db.Column(db.Integer, nullable=False)
    sender_name     = db.Column(db.String(100), nullable=False)
    sender_id       = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    text            = db.Column(db.Text, nullable=True)
    file_id         = db.Column(db.String(200), nullable=True)
    file_name       = db.Column(db.String(200), nullable=True)
    sent_at         = db.Column(db.DateTime, default=datetime.datetime.now)

class Homework(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    title           = db.Column(db.String(200), nullable=False)
    description     = db.Column(db.Text, nullable=True)
    class_name      = db.Column(db.String(50), nullable=False)
    teacher_name    = db.Column(db.String(100), nullable=False)
    teacher_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    file_id         = db.Column(db.String(200), nullable=True)
    file_name       = db.Column(db.String(200), nullable=True)
    file_type       = db.Column(db.String(20), nullable=True)   # photo, document, etc
    telegram_msg_id = db.Column(db.Integer, nullable=True)
    summary         = db.Column(db.Text, nullable=True)
    created_at      = db.Column(db.DateTime, default=datetime.datetime.now)
    due_date        = db.Column(db.Date, nullable=True)

class PrivateMessage(db.Model):
    __tablename__ = 'private_message'
    id            = db.Column(db.Integer, primary_key=True)
    sender_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    text          = db.Column(db.Text, nullable=False)
    sent_at       = db.Column(db.DateTime, default=datetime.datetime.now)
    read          = db.Column(db.Boolean, default=False)

    sender   = db.relationship('User', foreign_keys=[sender_id], backref='sent_private_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_private_messages')

class TeacherClass(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    teacher_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name        = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(300), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.datetime.now)
    teacher     = db.relationship('User', backref=db.backref('classes', lazy='dynamic'))

class StudentClass(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    student_id  = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    class_id    = db.Column(db.Integer, db.ForeignKey('teacher_class.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.datetime.now)
    student     = db.relationship('Student', backref=db.backref('enrolled_classes', lazy='dynamic'))
    tc          = db.relationship('TeacherClass', backref=db.backref('students', lazy='dynamic'))

class PasswordResetToken(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)

class LeaveRequest(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    student_id   = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    class_name   = db.Column(db.String(50), nullable=False)
    teacher_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    start_date   = db.Column(db.Date, nullable=False)
    end_date     = db.Column(db.Date, nullable=False)
    reason       = db.Column(db.Text, nullable=False)
    status       = db.Column(db.String(10), default='PENDING')  # PENDING / APPROVED / REJECTED
    teacher_note = db.Column(db.Text, nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.datetime.now)
    decided_at   = db.Column(db.DateTime, nullable=True)

    student = db.relationship('Student', backref='leave_requests')
    teacher = db.relationship('User', backref='received_leave_requests')

class Announcement(db.Model):
    id               = db.Column(db.Integer, primary_key=True)
    author_id        = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title            = db.Column(db.String(200), nullable=False)
    body             = db.Column(db.Text, nullable=False)
    target           = db.Column(db.String(20), default='ALL')  # ALL / CLASS
    target_class     = db.Column(db.String(50), nullable=True)
    priority         = db.Column(db.String(10), default='NORMAL')  # NORMAL / HIGH / URGENT
    pinned           = db.Column(db.Boolean, default=False)
    created_at       = db.Column(db.DateTime, default=datetime.datetime.now)
    expires_at       = db.Column(db.DateTime, nullable=True)

    author = db.relationship('User', backref='authored_announcements')

class ClassSchedule(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    class_id    = db.Column(db.Integer, db.ForeignKey('teacher_class.id'), nullable=False)
    teacher_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Mon .. 6=Sun
    start_time  = db.Column(db.Time, nullable=False)
    end_time    = db.Column(db.Time, nullable=False)
    room        = db.Column(db.String(50), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.datetime.now)

    tc = db.relationship('TeacherClass', backref='schedules')

class PushSubscription(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    endpoint   = db.Column(db.Text, nullable=False)
    p256dh     = db.Column(db.Text, nullable=False)
    auth_key   = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)


class MarksRecord(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    student_id      = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    class_name      = db.Column(db.String(100), nullable=False)
    subject         = db.Column(db.String(100), nullable=False)
    exam_type       = db.Column(db.String(50), default='exam')
    marks_obtained  = db.Column(db.Float, nullable=False)
    total_marks     = db.Column(db.Float, nullable=False)
    percentage      = db.Column(db.Float, nullable=True)
    scan_session_id = db.Column(db.String(36), nullable=False)
    sent            = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime, default=datetime.datetime.now)

    student = db.relationship('Student', backref='marks_records')

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
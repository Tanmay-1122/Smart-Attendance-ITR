import json
import datetime
from . import db, login_manager
from flask_login import UserMixin

class User(UserMixin, db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100))
    email         = db.Column(db.String(100), unique=True)
    password      = db.Column(db.String(200))
    role          = db.Column(db.String(10))   # 'student' or 'teacher'
    profile_photo = db.Column(db.String(200), nullable=True)  # filename in uploads/

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

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
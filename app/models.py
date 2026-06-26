from . import db, login_manager
from flask_login import UserMixin

class User(UserMixin, db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(100))
    email    = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))
    role     = db.Column(db.String(10))   # 'student' or 'teacher'

class Student(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('user.id'))
    roll_number    = db.Column(db.String(20))
    face_embedding = db.Column(db.Text)   # stored as encrypted JSON string

class AttendanceRecord(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    class_name = db.Column(db.String(50))
    date       = db.Column(db.Date)
    status     = db.Column(db.String(10))   # PRESENT / REVIEW / ABSENT
    score      = db.Column(db.Float)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
    
import datetime
from collections import defaultdict
from flask import current_app
from sqlalchemy import func
from .models import Student, AttendanceRecord, MarksRecord, WeeklyRemark, WeeklyReportLog
from .email import send_weekly_parent_report
from .whatsapp import send_whatsapp
from . import db


def get_week_range(reference_date=None):
    """Return (monday, friday) for the week containing reference_date."""
    if reference_date is None:
        reference_date = datetime.date.today()
    monday = reference_date - datetime.timedelta(days=reference_date.weekday())
    friday = monday + datetime.timedelta(days=4)
    return monday, friday


def get_previous_week_range():
    """Return (monday, friday) for the previous week."""
    today = datetime.date.today()
    # Go back to last Friday then get its week
    last_friday = today - datetime.timedelta(days=today.weekday() + 3)
    return get_week_range(last_friday)


def build_student_report(student, week_start, week_end):
    """Build weekly report data for a single student."""
    report = {
        'student_name': student.user.name,
        'roll_number': student.roll_number,
        'week_start': week_start,
        'week_end': week_end,
    }

    # Attendance for the week
    att_records = AttendanceRecord.query.filter(
        AttendanceRecord.student_id == student.id,
        AttendanceRecord.date >= week_start,
        AttendanceRecord.date <= week_end,
    ).order_by(AttendanceRecord.date).all()

    total = len(att_records)
    present = sum(1 for r in att_records if r.status == 'PRESENT')
    absent = sum(1 for r in att_records if r.status == 'ABSENT')
    review = sum(1 for r in att_records if r.status == 'REVIEW')

    report['attendance'] = {
        'records': [{'class_name': r.class_name, 'date': r.date.isoformat(), 'status': r.status} for r in att_records],
        'total': total,
        'present': present,
        'absent': absent,
        'review': review,
        'percentage': round(present / total * 100) if total else 0,
    }

    # Marks for the week
    week_start_dt = datetime.datetime.combine(week_start, datetime.time.min)
    week_end_dt = datetime.datetime.combine(week_end, datetime.time.max)
    marks_records = MarksRecord.query.filter(
        MarksRecord.student_id == student.id,
        MarksRecord.created_at >= week_start_dt,
        MarksRecord.created_at <= week_end_dt,
    ).order_by(MarksRecord.created_at).all()

    report['marks'] = [{
        'subject': m.subject,
        'class_name': m.class_name,
        'exam_type': m.exam_type,
        'marks_obtained': m.marks_obtained,
        'total_marks': m.total_marks,
        'percentage': m.percentage,
    } for m in marks_records]

    # Remarks for the week
    remarks = WeeklyRemark.query.filter(
        WeeklyRemark.student_id == student.id,
        WeeklyRemark.week_start == week_start,
    ).all()

    report['remarks'] = [{
        'remark': r.remark,
        'teacher_name': r.teacher.name,
    } for r in remarks]

    return report


def generate_and_send_weekly_reports():
    """Main entry point — called by scheduler every Saturday."""
    print("[REPORT] Starting weekly report generation...")
    week_start, week_end = get_previous_week_range()
    print(f"[REPORT] Target week: {week_start} to {week_end}")

    students = Student.query.filter(
        (Student.parent_email.isnot(None)) | (Student.parent_phone.isnot(None))
    ).all()

    sent_count = 0
    for student in students:
        report = build_student_report(student, week_start, week_end)

        email_sent = False
        whatsapp_sent = False
        errors = []

        # Send email
        if student.parent_email:
            try:
                send_weekly_parent_report(
                    to=student.parent_email,
                    student_name=student.user.name,
                    report=report,
                )
                email_sent = True
            except Exception as e:
                errors.append(f"Email: {e}")

        # Send WhatsApp
        if student.parent_phone:
            wa_body = format_whatsapp_report(report)
            try:
                send_whatsapp(to_phone=student.parent_phone, body=wa_body)
                whatsapp_sent = True
            except Exception as e:
                errors.append(f"WhatsApp: {e}")

        # Log
        log = WeeklyReportLog(
            student_id=student.id,
            week_start=week_start,
            email_sent=email_sent,
            whatsapp_sent=whatsapp_sent,
            error_log='; '.join(errors) if errors else None,
        )
        db.session.add(log)
        sent_count += 1

    db.session.commit()
    print(f"[REPORT] Done. Processed {sent_count} student(s).")


def format_whatsapp_report(report):
    """Format a concise WhatsApp message from report data."""
    att = report['attendance']
    lines = []
    lines.append(f"*Weekly Report — {report['student_name']}*")
    lines.append(f"Week: {report['week_start']} to {report['week_end']}")
    lines.append("")

    lines.append(f"*Attendance:* {att['present']}/{att['total']} ({att['percentage']}%)")
    if att['absent'] > 0:
        absent_dates = [r['date'] for r in att['records'] if r['status'] == 'ABSENT']
        if absent_dates:
            lines.append(f"Absent on: {', '.join(absent_dates)}")

    if report['marks']:
        lines.append("")
        lines.append("*Tests/Marks:*")
        for m in report['marks']:
            pct = f"{m['percentage']:.1f}%" if m['percentage'] else 'N/A'
            lines.append(f"- {m['subject']}: {m['marks_obtained']}/{m['total_marks']} ({pct})")

    if report['remarks']:
        lines.append("")
        lines.append("*Teacher Remarks:*")
        for r in report['remarks']:
            lines.append(f"- {r['remark']}")

    lines.append("")
    lines.append("SmartAttend — AI-powered attendance management")

    return '\n'.join(lines)

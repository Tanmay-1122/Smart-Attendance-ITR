import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app
from .tasks import run_async


@run_async
def send_email(to, subject, html_body):
    """Send an HTML email via SMTP. Returns True on success."""
    smtp_host = current_app.config.get('SMTP_HOST', '')
    if not smtp_host:
        print("[EMAIL] SMTP not configured, skipping email to", to)
        return False

    smtp_port = int(current_app.config.get('SMTP_PORT', 587))
    smtp_user = current_app.config.get('SMTP_USER', '')
    smtp_pass = current_app.config.get('SMTP_PASS', '')
    smtp_from = current_app.config.get('SMTP_FROM', smtp_user)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = smtp_from
    msg['To'] = to
    msg.attach(MIMEText(html_body, 'html'))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls(context=context)
            if smtp_user:
                server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, [to], msg.as_string())
        print(f"[EMAIL] Sent to {to}: {subject}")
        return True
    except Exception as e:
        print(f"[EMAIL] Failed to send to {to}: {e}")
        return False


def send_password_reset_email(to, name, reset_url):
    """Send password reset email."""
    html = f"""
    <div style="font-family:Inter,-apple-system,BlinkMacSystemFont,sans-serif;max-width:480px;margin:0 auto;padding:32px;">
      <div style="background:linear-gradient(135deg,#6366F1,#7C3AED);border-radius:16px;padding:32px;text-align:center;color:#fff;margin-bottom:24px;">
        <h1 style="margin:0;font-size:1.4rem;font-weight:800;">SmartAttend</h1>
        <p style="margin:8px 0 0;opacity:0.8;font-size:0.9rem;">Password Reset Request</p>
      </div>
      <div style="background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:24px;">
        <p style="color:#374151;font-size:0.95rem;margin:0 0 16px;">Hi <strong>{name}</strong>,</p>
        <p style="color:#374151;font-size:0.95rem;margin:0 0 16px;">We received a request to reset your password. Click the button below to set a new password:</p>
        <div style="text-align:center;margin:24px 0;">
          <a href="{reset_url}" style="background:linear-gradient(135deg,#6366F1,#7C3AED);color:#fff;text-decoration:none;padding:12px 32px;border-radius:8px;font-weight:700;font-size:0.95rem;display:inline-block;">Reset Password</a>
        </div>
        <p style="color:#9CA3AF;font-size:0.82rem;margin:0;">This link expires in 1 hour. If you didn't request this, you can safely ignore this email.</p>
      </div>
      <p style="text-align:center;color:#9CA3AF;font-size:0.75rem;margin-top:16px;">SmartAttend — AI-powered attendance management</p>
    </div>
    """
    return send_email(to, 'Reset your SmartAttend password', html)


def send_attendance_summary_email(to, name, records, percentage):
    """Send attendance summary email."""
    rows = ''
    for r in records:
        color = '#10B981' if r['status'] == 'PRESENT' else '#F59E0B' if r['status'] == 'REVIEW' else '#EF4444'
        rows += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #F3F4F6;font-size:0.88rem;">{r['class_name']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #F3F4F6;font-size:0.88rem;">{r['date']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #F3F4F6;"><span style="color:{color};font-weight:700;font-size:0.82rem;">{r['status']}</span></td>
        </tr>"""

    html = f"""
    <div style="font-family:Inter,-apple-system,BlinkMacSystemFont,sans-serif;max-width:480px;margin:0 auto;padding:32px;">
      <div style="background:linear-gradient(135deg,#6366F1,#7C3AED);border-radius:16px;padding:24px;text-align:center;color:#fff;margin-bottom:24px;">
        <h1 style="margin:0;font-size:1.2rem;font-weight:800;">Attendance Summary</h1>
        <p style="margin:8px 0 0;opacity:0.8;font-size:0.85rem;">Your attendance: {percentage}%</p>
      </div>
      <div style="background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:20px;">
        <p style="color:#374151;font-size:0.95rem;margin:0 0 12px;">Hi <strong>{name}</strong>, here's your recent attendance:</p>
        <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
          <thead>
            <tr style="background:#F9FAFB;">
              <th style="padding:8px 12px;text-align:left;font-size:0.75rem;color:#6B7280;text-transform:uppercase;letter-spacing:0.05em;">Class</th>
              <th style="padding:8px 12px;text-align:left;font-size:0.75rem;color:#6B7280;text-transform:uppercase;letter-spacing:0.05em;">Date</th>
              <th style="padding:8px 12px;text-align:left;font-size:0.75rem;color:#6B7280;text-transform:uppercase;letter-spacing:0.05em;">Status</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
        {"<p style='color:#EF4444;font-size:0.88rem;font-weight:600;'>Your attendance is below 75%. Attend more classes to avoid exam restrictions.</p>" if percentage < 75 else ""}
      </div>
      <p style="text-align:center;color:#9CA3AF;font-size:0.75rem;margin-top:16px;">SmartAttend — AI-powered attendance management</p>
    </div>
    """
    return send_email(to, f'Attendance Summary — {percentage}%', html)


def send_homework_alert_email(to, name, hw_title, class_name, teacher_name, due_date=None):
    """Send homework notification email."""
    due_str = f"<p style='color:#F59E0B;font-weight:600;font-size:0.88rem;margin:0 0 12px;'>Due: {due_date}</p>" if due_date else ""

    html = f"""
    <div style="font-family:Inter,-apple-system,BlinkMacSystemFont,sans-serif;max-width:480px;margin:0 auto;padding:32px;">
      <div style="background:linear-gradient(135deg,#6366F1,#7C3AED);border-radius:16px;padding:24px;text-align:center;color:#fff;margin-bottom:24px;">
        <h1 style="margin:0;font-size:1.2rem;font-weight:800;">New Homework Assigned</h1>
      </div>
      <div style="background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:24px;">
        <p style="color:#374151;font-size:0.95rem;margin:0 0 8px;">Hi <strong>{name}</strong>,</p>
        <p style="color:#374151;font-size:0.95rem;margin:0 0 16px;">A new homework has been posted in <strong>{class_name}</strong>:</p>
        <div style="background:#EEF2FF;border-radius:8px;padding:16px;margin-bottom:16px;">
          <div style="font-weight:700;font-size:1rem;color:#1E1B4B;">{hw_title}</div>
          <div style="font-size:0.85rem;color:#6B7280;margin-top:4px;">Teacher: {teacher_name}</div>
        </div>
        {due_str}
        <p style="color:#9CA3AF;font-size:0.82rem;margin:0;">Log in to SmartAttend to view full details.</p>
      </div>
      <p style="text-align:center;color:#9CA3AF;font-size:0.75rem;margin-top:16px;">SmartAttend — AI-powered attendance management</p>
    </div>
    """
    return send_email(to, f'New Homework: {hw_title}', html)


def send_marks_email(to, name, subject_name, exam_type, marks_obtained, total_marks, percentage, class_name):
    """Send marks/result notification email."""
    pct_str = f"{percentage:.1f}%" if percentage is not None else "N/A"
    color = '#10B981' if (percentage or 0) >= 75 else '#F59E0B' if (percentage or 0) >= 40 else '#EF4444'

    html = f"""
    <div style="font-family:Inter,-apple-system,BlinkMacSystemFont,sans-serif;max-width:480px;margin:0 auto;padding:32px;">
      <div style="background:linear-gradient(135deg,#6366F1,#7C3AED);border-radius:16px;padding:24px;text-align:center;color:#fff;margin-bottom:24px;">
        <h1 style="margin:0;font-size:1.2rem;font-weight:800;">Exam Result Published</h1>
        <p style="margin:8px 0 0;opacity:0.8;font-size:0.85rem;">{class_name} — {exam_type}</p>
      </div>
      <div style="background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:24px;">
        <p style="color:#374151;font-size:0.95rem;margin:0 0 16px;">Hi <strong>{name}</strong>,</p>
        <div style="background:#F9FAFB;border-radius:8px;padding:16px;margin-bottom:16px;">
          <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #F3F4F6;">
            <span style="color:#6B7280;font-size:0.88rem;">Subject</span>
            <span style="font-weight:700;font-size:0.95rem;color:#1E1B4B;">{subject_name}</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #F3F4F6;">
            <span style="color:#6B7280;font-size:0.88rem;">Marks Obtained</span>
            <span style="font-weight:700;font-size:0.95rem;color:#1E1B4B;">{marks_obtained} / {total_marks}</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:6px 0;">
            <span style="color:#6B7280;font-size:0.88rem;">Percentage</span>
            <span style="font-weight:700;font-size:1.1rem;color:{color};">{pct_str}</span>
          </div>
        </div>
        <p style="text-align:center;color:#9CA3AF;font-size:0.82rem;margin:0;">Log in to SmartAttend to view all your results.</p>
      </div>
      <p style="text-align:center;color:#9CA3AF;font-size:0.75rem;margin-top:16px;">SmartAttend — AI-powered attendance management</p>
    </div>
    """
    return send_email(to, f'Exam Result: {subject_name} — {marks_obtained}/{total_marks}', html)


def send_leave_decision_email(to, name, status, class_name, start_date, end_date, teacher_note=None):
    """Send leave request decision email."""
    color = '#10B981' if status == 'APPROVED' else '#EF4444'
    label = 'Approved' if status == 'APPROVED' else 'Rejected'
    note_html = f"<p style='color:#6B7280;font-size:0.88rem;margin:12px 0 0;font-style:italic;'>Teacher's note: {teacher_note}</p>" if teacher_note else ""

    html = f"""
    <div style="font-family:Inter,-apple-system,BlinkMacSystemFont,sans-serif;max-width:480px;margin:0 auto;padding:32px;">
      <div style="background:linear-gradient(135deg,{color},{color});border-radius:16px;padding:24px;text-align:center;color:#fff;margin-bottom:24px;">
        <h1 style="margin:0;font-size:1.2rem;font-weight:800;">Leave Request {label}</h1>
      </div>
      <div style="background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:24px;">
        <p style="color:#374151;font-size:0.95rem;margin:0 0 12px;">Hi <strong>{name}</strong>,</p>
        <p style="color:#374151;font-size:0.95rem;margin:0 0 12px;">Your leave request for <strong>{class_name}</strong> has been <strong style="color:{color};">{label.lower()}</strong>.</p>
        <div style="background:#F9FAFB;border-radius:8px;padding:12px;margin:12px 0;">
          <div style="font-size:0.88rem;color:#374151;"><strong>Period:</strong> {start_date} to {end_date}</div>
        </div>
        {note_html}
      </div>
      <p style="text-align:center;color:#9CA3AF;font-size:0.75rem;margin-top:16px;">SmartAttend — AI-powered attendance management</p>
    </div>
    """
    return send_email(to, f'Leave Request {label}', html)


def send_weekly_parent_report(to, student_name, report):
    """Send weekly consolidated report to parent."""
    att = report['attendance']
    color = '#10B981' if att['percentage'] >= 75 else '#F59E0B' if att['percentage'] >= 40 else '#EF4444'

    att_rows = ''
    for r in att['records']:
        c = '#10B981' if r['status'] == 'PRESENT' else '#F59E0B' if r['status'] == 'REVIEW' else '#EF4444'
        att_rows += f"""<tr><td style="padding:6px 10px;border-bottom:1px solid #F3F4F6;font-size:0.85rem;">{r['class_name']}</td><td style="padding:6px 10px;border-bottom:1px solid #F3F4F6;font-size:0.85rem;">{r['date']}</td><td style="padding:6px 10px;border-bottom:1px solid #F3F4F6;"><span style="color:{c};font-weight:700;font-size:0.8rem;">{r['status']}</span></td></tr>"""

    marks_html = ''
    if report['marks']:
        m_rows = ''
        for m in report['marks']:
            pct = f"{m['percentage']:.1f}%" if m['percentage'] else 'N/A'
            mc = '#10B981' if (m['percentage'] or 0) >= 75 else '#F59E0B' if (m['percentage'] or 0) >= 40 else '#EF4444'
            m_rows += f"""<tr><td style="padding:6px 10px;border-bottom:1px solid #F3F4F6;font-size:0.85rem;">{m['subject']}</td><td style="padding:6px 10px;border-bottom:1px solid #F3F4F6;font-size:0.85rem;">{m['exam_type']}</td><td style="padding:6px 10px;border-bottom:1px solid #F3F4F6;font-size:0.85rem;">{m['marks_obtained']}/{m['total_marks']}</td><td style="padding:6px 10px;border-bottom:1px solid #F3F4F6;"><span style="color:{mc};font-weight:700;font-size:0.85rem;">{pct}</span></td></tr>"""
        marks_html = f"""<div style="background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:20px;margin-bottom:16px;"><h3 style="margin:0 0 12px;font-size:0.95rem;color:#1E1B4B;">📝 Tests & Marks</h3><table style="width:100%;border-collapse:collapse;"><thead><tr style="background:#F9FAFB;"><th style="padding:6px 10px;text-align:left;font-size:0.75rem;color:#6B7280;">Subject</th><th style="padding:6px 10px;text-align:left;font-size:0.75rem;color:#6B7280;">Type</th><th style="padding:6px 10px;text-align:left;font-size:0.75rem;color:#6B7280;">Marks</th><th style="padding:6px 10px;text-align:left;font-size:0.75rem;color:#6B7280;">%</th></tr></thead><tbody>{m_rows}</tbody></table></div>"""

    remarks_html = ''
    if report['remarks']:
        r_items = ''.join(f'<div style="background:#FEF3C7;border-radius:8px;padding:10px;margin-bottom:8px;"><span style="font-size:0.85rem;color:#92400E;">💬 <strong>{r["teacher_name"]}:</strong> {r["remark"]}</span></div>' for r in report['remarks'])
        remarks_html = f"""<div style="background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:20px;margin-bottom:16px;"><h3 style="margin:0 0 12px;font-size:0.95rem;color:#1E1B4B;">💬 Teacher Remarks</h3>{r_items}</div>"""

    low_att_warning = ''
    if att['percentage'] < 75 and att['total'] > 0:
        low_att_warning = "<p style='color:#EF4444;font-size:0.88rem;font-weight:600;margin-top:12px;'>⚠ Attendance is below 75%. Please ensure regular attendance.</p>"

    html = f"""
    <div style="font-family:Inter,-apple-system,BlinkMacSystemFont,sans-serif;max-width:520px;margin:0 auto;padding:32px;">
      <div style="background:linear-gradient(135deg,#6366F1,#7C3AED);border-radius:16px;padding:24px;text-align:center;color:#fff;margin-bottom:24px;">
        <h1 style="margin:0;font-size:1.2rem;font-weight:800;">Weekly Report</h1>
        <p style="margin:8px 0 0;opacity:0.8;font-size:0.85rem;">{report['week_start']} — {report['week_end']}</p>
      </div>
      <div style="background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:20px;margin-bottom:16px;">
        <p style="color:#374151;font-size:0.95rem;margin:0 0 4px;">Hi <strong>{student_name}'s Parent</strong>,</p>
        <p style="color:#6B7280;font-size:0.85rem;margin:0 0 16px;">Here is {student_name}'s performance summary for this week.</p>

        <div style="background:#F9FAFB;border-radius:8px;padding:16px;text-align:center;margin-bottom:16px;">
          <div style="font-size:2rem;font-weight:800;color:{color};">{att['percentage']}%</div>
          <div style="font-size:0.8rem;color:#6B7280;margin-top:2px;">Weekly Attendance</div>
          <div style="font-size:0.75rem;color:#9CA3AF;margin-top:4px;">{att['present']} Present / {att['absent']} Absent / {att['review']} Review</div>
        </div>

        <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
          <thead>
            <tr style="background:#F9FAFB;">
              <th style="padding:6px 10px;text-align:left;font-size:0.75rem;color:#6B7280;text-transform:uppercase;">Class</th>
              <th style="padding:6px 10px;text-align:left;font-size:0.75rem;color:#6B7280;text-transform:uppercase;">Date</th>
              <th style="padding:6px 10px;text-align:left;font-size:0.75rem;color:#6B7280;text-transform:uppercase;">Status</th>
            </tr>
          </thead>
          <tbody>{att_rows}</tbody>
        </table>
        {low_att_warning}
      </div>
      {marks_html}
      {remarks_html}
      <p style="text-align:center;color:#9CA3AF;font-size:0.75rem;margin-top:16px;">SmartAttend — AI-powered attendance management</p>
    </div>
    """
    return send_email(to, f"Weekly Report — {student_name} — {att['percentage']}% Attendance", html)

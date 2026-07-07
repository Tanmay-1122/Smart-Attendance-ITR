"""
Run this on Render via:  python seed_accounts.py
Or trigger from admin panel: POST /admin/seed-default-accounts
"""
from app import create_app, db
from app.models import User, Department
from werkzeug.security import generate_password_hash


def seed():
    app = create_app()
    with app.app_context():
        db.create_all()
        count = 0

        depts_data = [
            ('Information Technology', 'IT'),
            ('Civil Engineering', 'CV'),
            ('Electronics & Telecommunication', 'E&TC'),
            ('Automation & Robotics', 'A&R'),
            ('Mechanical Engineering', 'ME'),
        ]
        for name, code in depts_data:
            if not Department.query.filter_by(code=code).first():
                db.session.add(Department(name=name, code=code))
                print(f'  Created department: {name}')

        if not User.query.filter_by(email='admin@college.edu').first():
            db.session.add(User(
                name='System Admin', email='admin@college.edu',
                password=generate_password_hash('Admin@123'),
                role='student', is_admin=True
            ))
            count += 1
            print('  Created admin: admin@college.edu / Admin@123')

        if not User.query.filter_by(role='principal').first():
            db.session.add(User(
                name='Dr. Principal Sharma', email='principal@college.edu',
                password=generate_password_hash('Principal@123'),
                role='principal'
            ))
            count += 1
            print('  Created principal: principal@college.edu / Principal@123')

        hods = [
            ('Dr. Arvind Patil', 'hod.it@college.edu', 'IT'),
            ('Dr. Sneha Deshmukh', 'hod.civil@college.edu', 'CV'),
            ('Dr. Rajesh Kulkarni', 'hod.entc@college.edu', 'E&TC'),
            ('Dr. Priya Joshi', 'hod.robotics@college.edu', 'A&R'),
            ('Dr. Vikram Singh', 'hod.mech@college.edu', 'ME'),
        ]
        for name, email, code in hods:
            if not User.query.filter_by(email=email).first():
                dept = Department.query.filter_by(code=code).first()
                if dept:
                    db.session.add(User(
                        name=name, email=email,
                        password=generate_password_hash('HOD@123'),
                        role='hod', department_id=dept.id
                    ))
                    count += 1
                    print(f'  Created HOD ({code}): {email} / HOD@123')

        db.session.commit()

        if count:
            print(f'\n{count} new accounts created.')
            print('\nAccount summary:')
            for u in User.query.all():
                roles = [u.role]
                if u.is_admin: roles.append('admin')
                dept_tag = f' [{u.department.code}]' if u.department else ''
                print(f'  {u.email:40s} | {"/".join(roles):20s}{dept_tag} | {u.name}')
        else:
            print('All accounts already exist. Nothing to seed.')


if __name__ == '__main__':
    seed()

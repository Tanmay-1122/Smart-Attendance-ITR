"""
First-time setup: Create an admin account from scratch.

Usage:  python init_admin.py
"""
import getpass
from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash

def main():
    app = create_app()
    with app.app_context():
        db.create_all()

        print("=== SmartAttend Admin Setup ===\n")
        name = input("Admin name: ").strip()
        email = input("Admin email: ").strip()
        password = getpass.getpass("Admin password: ")

        existing = User.query.filter_by(email=email).first()
        if existing:
            existing.is_admin = True
            existing.role = 'admin'
            db.session.commit()
            print(f'\nDone! Existing user {name} ({email}) is now an admin.')
        else:
            admin = User(
                name=name,
                email=email,
                password=generate_password_hash(password),
                role='student',
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print(f'\nDone! Admin account created: {name} ({email})')
            print('Log in and use the Admin Panel to manage teachers.')

if __name__ == '__main__':
    main()

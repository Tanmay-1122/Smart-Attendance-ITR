"""
Setup script: Grant admin privileges to an existing user.

Usage:  python make_admin.py <email>
Example: python make_admin.py admin@university.edu
"""
import sys
from app import create_app, db
from app.models import User

def make_admin(email):
    app = create_app()
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if not user:
            print(f'No user found with email: {email}')
            sys.exit(1)
        if user.is_admin:
            print(f'{user.name} ({email}) is already an admin.')
            sys.exit(0)
        user.is_admin = True
        db.session.commit()
        print(f'Success! {user.name} ({email}) is now an admin.')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python make_admin.py <email>')
        sys.exit(1)
    make_admin(sys.argv[1])

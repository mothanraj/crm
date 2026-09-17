"""Reset any user's password (including ADMIN) by email.

Usage (PowerShell, from backend/):
  .\\.venv\\Scripts\\python.exe scripts\\reset_admin_password.py --email mothanraj@gmail.com
  # prompts for new password (min 6 chars), hashes with bcrypt, updates users.password_hash

Admin reset API blocks ADMIN accounts, so this script is the supported path.
"""
import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True, help="Login email to reset")
    ap.add_argument("--password", default="", help="New password (else prompted securely)")
    args = ap.parse_args()

    email = args.email.lower().strip()
    password = args.password or getpass.getpass("New password (min 6 chars): ")
    if len(password) < 6:
        print("Password must be at least 6 characters")
        return 1

    db = SessionLocal()
    try:
        u = db.query(User).filter_by(email=email).first()
        if not u:
            print(f"Not found: {email}")
            return 1
        u.password_hash = hash_password(password)
        u.is_active = True
        db.commit()
        print(f"ok reset={u.email} active={u.is_active}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

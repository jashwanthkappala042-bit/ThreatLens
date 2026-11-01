"""Promote or demote a ThreatLens account.

Usage (from the project root):
    .\\.venv\\Scripts\\python.exe backend\\scripts\\make_admin.py analyst@example.com
    .\\.venv\\Scripts\\python.exe backend\\scripts\\make_admin.py --list
    .\\.venv\\Scripts\\python.exe backend\\scripts\\make_admin.py --revoke analyst@example.com

The script uses the same configuration and database as the API. Run it only
against a trusted local instance.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

from sqlalchemy import select  # noqa: E402

from app import create_app  # noqa: E402
from app.database import session_scope  # noqa: E402
from app.models import AuditLog, User  # noqa: E402


def list_users() -> int:
    with session_scope() as session:
        users = session.scalars(select(User).order_by(User.created_at)).all()
        if not users:
            print("No accounts exist yet. Register through the web interface first.")
            return 1
        print(f"{'ID':>4}  {'ROLE':<6}  {'EMAIL':<40}  DISPLAY NAME")
        for user in users:
            print(f"{user.id:>4}  {user.role:<6}  {user.email:<40}  {user.display_name}")
    return 0


def set_role(email: str, role: str) -> int:
    with session_scope() as session:
        user = session.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None:
            print(f"No account found for {email!r}. Use --list to see registered emails.")
            return 1
        if user.role == role:
            print(f"{user.email} already has role {role!r}.")
            return 0
        previous = user.role
        user.role = role
        session.add(
            AuditLog(
                user_id=user.id,
                action="admin.role_changed",
                detail=f"CLI changed role from {previous} to {role}",
            )
        )
        print(f"{user.email}: {previous} -> {role}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage ThreatLens account roles.")
    parser.add_argument("email", nargs="?", help="Email address of the account to promote.")
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="Demote the account to the regular user role instead of promoting it.",
    )
    parser.add_argument("--list", action="store_true", help="List accounts and their roles.")
    args = parser.parse_args()

    # create_app initialises the engine configured by DATABASE_URL.
    create_app()

    if args.list:
        return list_users()
    if not args.email:
        parser.print_help()
        return 2
    return set_role(args.email, "user" if args.revoke else "admin")


if __name__ == "__main__":
    raise SystemExit(main())

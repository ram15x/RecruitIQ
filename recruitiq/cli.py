import argparse
import getpass

from sqlalchemy import select

from .config import get_settings
from .db.models import Org, User
from .db.session import make_engine, make_session_factory
from .services import security


def create_admin(a):
    s = get_settings()
    factory = make_session_factory(make_engine(s.db_url))
    pw = a.password or getpass.getpass("password (min 10 chars): ")
    if len(pw) < 10:
        raise SystemExit("password too short")
    with factory() as db:
        org = db.scalar(select(Org).where(Org.name == a.org))
        if not org:
            org = Org(name=a.org)
            db.add(org)
            db.flush()
        db.add(User(username=a.username, password_hash=security.hash_password(pw), role="admin", org_id=org.id))
        db.commit()
    print(f"admin '{a.username}' created in '{a.org}'")


def main():
    ap = argparse.ArgumentParser(prog="recruitiq")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-admin")
    c.add_argument("--username", required=True)
    c.add_argument("--org", default="Main Organisation")
    c.add_argument("--password", help="leave out to be prompted; a password on the command line ends up in shell history")
    c.set_defaults(fn=create_admin)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..db.models import AuditLog, Org, User
from ..services import security

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db(request: Request):
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, token: str = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    uid = security.read_token(request.app.state.settings.jwt_secret, token)
    user = db.get(User, uid) if uid else None
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    return user


def admin_only(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user


def org_name(db: Session, org_id: int) -> str:
    o = db.get(Org, org_id)
    return o.name if o else ""


def audit(db: Session, user: User | None, action: str, entity: str = "", entity_id="", detail: str = "", org_id: int | None = None):
    # details are for ids and outcomes. never put a name, email or resume text here
    db.add(AuditLog(user_id=user.id if user else None, org_id=user.org_id if user else org_id, action=action,
                    entity=entity, entity_id=str(entity_id), detail=detail[:255]))
    db.commit()

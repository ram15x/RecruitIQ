import datetime as dt
import hashlib
import hmac
import time
import uuid
from collections import defaultdict

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
ALGO = "HS256"
# burns the same time on a login for a username that does not exist
DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(pw: str) -> str:
    return _hasher.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, pw)
    except (VerificationError, InvalidHashError):
        return False


def make_token(secret: str, user_id: int, minutes: int) -> str:
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)
    return jwt.encode({"sub": str(user_id), "typ": "user", "exp": exp}, secret, algorithm=ALGO)


def read_token(secret: str, token: str) -> int | None:
    try:
        d = jwt.decode(token, secret, algorithms=[ALGO])
        return int(d["sub"]) if d.get("typ") == "user" else None
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def make_interview_token(secret: str, interview_id: int, valid_until: dt.datetime) -> tuple[str, str]:
    """The link a candidate gets. It carries only an interview id and a random id, and it stops working after the
    window closes. A user token cannot be used here and the other way round, because of the 'typ' claim."""
    jti = uuid.uuid4().hex
    tok = jwt.encode({"iid": interview_id, "jti": jti, "typ": "interview", "exp": valid_until}, secret, algorithm=ALGO)
    return tok, jti


def read_interview_token(secret: str, token: str) -> dict | None:
    try:
        d = jwt.decode(token, secret, algorithms=[ALGO])
        return d if d.get("typ") == "interview" else None
    except jwt.PyJWTError:
        return None


def sign_body(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def check_signature(secret: str, body: bytes, header: str | None) -> bool:
    if not secret or not header:
        return False
    given = header.split("=", 1)[-1].strip()
    return hmac.compare_digest(sign_body(secret, body), given)


class LoginThrottle:
    """Lock a username out for a while after repeated failures. In memory and per process: fine for one container."""

    def __init__(self, max_fails=5, window=900):
        self.max_fails, self.window = max_fails, window
        self._fails = defaultdict(list)

    def _recent(self, name):
        cutoff = time.time() - self.window
        self._fails[name] = [t for t in self._fails[name] if t > cutoff]
        return self._fails[name]

    def blocked(self, name: str) -> bool:
        return len(self._recent(name)) >= self.max_fails

    def fail(self, name: str):
        self._recent(name).append(time.time())

    def clear(self, name: str):
        self._fails.pop(name, None)

"""Read job applications from a mailbox over IMAP (a Gmail account works with an app password and IMAP switched on).

It only reads and marks messages as seen. It never sends, deletes or moves anything. Attachments are taken by content, and
anything that is not a PDF, DOCX or plain text file is ignored.
"""
import email
import imaplib
import re
from dataclasses import dataclass, field
from email import policy
from email.utils import parseaddr

MAX_ATTACHMENT = 5_000_000
JOB_TAG = re.compile(r"(?:\[\s*job\s*[:#]?\s*(\d+)\s*\]|#(\d+)\b)", re.I)
NOISE = re.compile(r"(?:no-?reply|mailer-daemon|postmaster|notification|newsletter|do-?not-?reply)", re.I)


@dataclass
class Mail:
    uid: str
    sender_name: str
    sender_email: str
    subject: str
    body: str
    attachments: list = field(default_factory=list)  # (filename, bytes)


def job_id_from_subject(subject: str) -> int | None:
    m = JOB_TAG.search(subject or "")
    return int(next(g for g in m.groups() if g)) if m else None


def parse(uid: str, raw: bytes) -> Mail | None:
    msg = email.message_from_bytes(raw, policy=policy.default)
    name, addr = parseaddr(str(msg.get("From", "")))
    if not addr or NOISE.search(addr):
        return None
    body, atts = "", []
    for part in msg.walk():
        if part.is_multipart():
            continue
        fn = part.get_filename() or ""
        ctype = part.get_content_type()
        payload = part.get_payload(decode=True) or b""
        if fn:
            ok = fn.lower().endswith((".pdf", ".docx", ".txt")) or ctype in ("application/pdf", "text/plain")
            if ok and 0 < len(payload) <= MAX_ATTACHMENT:
                atts.append((fn, payload))
        elif ctype == "text/plain" and not body:
            body = payload.decode(part.get_content_charset() or "utf-8", "replace")
    return Mail(uid, name or addr.split("@")[0], addr.lower(), str(msg.get("Subject", "")), body, atts)


def fetch_unseen(host: str, user: str, password: str, folder: str = "INBOX", limit: int = 25, factory=None, port: int = 993):
    """Returns (mails, handle). Call mark_seen with the uids you processed, then close the handle."""
    conn = factory(host, port) if factory else imaplib.IMAP4_SSL(host, port)
    conn.login(user, password)
    conn.select(folder)
    status, data = conn.search(None, "UNSEEN")
    uids = (data[0].split() if status == "OK" and data and data[0] else [])[:limit]
    mails = []
    for uid in uids:
        # BODY.PEEK keeps the message unread until we have dealt with it
        status, parts = conn.fetch(uid, "(BODY.PEEK[])")
        if status != "OK" or not parts or not isinstance(parts[0], tuple):
            continue
        m = parse(uid.decode() if isinstance(uid, bytes) else str(uid), parts[0][1])
        if m:
            mails.append(m)
    return mails, conn


def mark_seen(conn, uids: list[str]):
    for uid in uids:
        conn.store(uid, "+FLAGS", "\\Seen")


def close(conn):
    try:
        conn.close()
    except Exception:
        pass
    try:
        conn.logout()
    except Exception:
        pass

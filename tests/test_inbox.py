import io
from dataclasses import replace
from email.message import EmailMessage

import docx
from fastapi.testclient import TestClient

from recruitiq.api.app import create_app
from recruitiq.services import inbox
from tests.conftest import JD, STRONG, WEAK, login


def mail(frm, subject, body="", attach=None):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = frm, "jobs@example.com", subject
    m.set_content(body or "Please find my resume attached.")
    for name, data in attach or []:
        kind = ("application", "pdf") if name.endswith(".pdf") else ("application", "octet-stream")
        m.add_attachment(data, maintype=kind[0], subtype=kind[1], filename=name)
    return m.as_bytes()


def docx_of(text):
    d = docx.Document()
    for line in text.splitlines():
        d.add_paragraph(line)
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


class FakeImap:
    boxes = {}

    def __init__(self, host, port=993):
        self.seen, self.logged = set(), False

    def login(self, u, p):
        if p != "right":
            raise OSError("bad login")

    def select(self, folder):
        return "OK", [b"1"]

    def search(self, charset, crit):
        ids = [str(i).encode() for i in self.boxes if i not in FakeImap.seen_all]
        return "OK", [b" ".join(ids)]

    def fetch(self, uid, spec):
        assert "PEEK" in spec  # must not mark messages read before we have handled them
        return "OK", [(b"x (BODY[]", self.boxes[int(uid)]), b")"]

    def store(self, uid, op, flag):
        FakeImap.seen_all.add(int(uid))
        return "OK", []

    def close(self): pass
    def logout(self): pass


def setup(settings, mails):
    FakeImap.boxes = dict(enumerate(mails, 1))
    FakeImap.seen_all = set()
    s = replace(settings, imap_user="jobs@example.com", imap_password="right")
    c = TestClient(create_app(s))
    c.__enter__()
    c.app.state.imap_factory = FakeImap
    return c


def test_parse_ignores_noise_and_reads_attachment():
    assert inbox.parse("1", mail("no-reply@x.com", "hi")) is None
    m = inbox.parse("1", mail("Asha Rao <asha@example.com>", "Application", attach=[("cv.docx", docx_of(STRONG)), ("photo.png", b"x" * 10)]))
    assert m.sender_email == "asha@example.com" and m.sender_name == "Asha Rao" and [a[0] for a in m.attachments] == ["cv.docx"]


def test_job_tag_in_subject():
    assert inbox.job_id_from_subject("Application [job:12] Asha") == 12
    assert inbox.job_id_from_subject("Re: #7 backend") == 7
    assert inbox.job_id_from_subject("hello") is None


def test_poll_creates_scored_applications_and_leaves_unmatched_unread(settings):
    c = setup(settings, [
        mail("Asha Rao <asha@example.com>", "Application for Backend Engineer", attach=[("cv.docx", docx_of(STRONG))]),
        mail("Vik <vik@example.com>", "[job:1] my resume", attach=[("cv.docx", docx_of(WEAK))]),
        mail("Lost <lost@example.com>", "Something else entirely", attach=[("cv.docx", docx_of(STRONG))]),
        mail("noreply@shop.com", "Your receipt"),
    ])
    try:
        h = login(c)
        job = c.post("/jobs", json={"title": "Backend Engineer", "description": JD}, headers=h).json()
        r = c.post("/admin/inbox/poll", headers=h).json()
        assert r["created"] == 2 and len(r["left_unread"]) == 1 and r["left_unread"][0]["from"] == "lost@example.com"
        rows = c.get(f"/jobs/{job['id']}/applications", headers=h).json()
        assert len(rows) == 2 and rows[0]["score"] > 70 > rows[1]["score"]
        assert FakeImap.seen_all == {1, 2}  # the unmatched one stays unread for a person
        full = c.get(f"/applications/{rows[0]['id']}?reveal=true", headers=h).json()
        assert full["identity"]["email"] == "asha@example.com"
        # a second poll finds nothing new except the unmatched one, and does not double anything
        r2 = c.post("/admin/inbox/poll", headers=h).json()
        assert r2["created"] == 0
    finally:
        c.__exit__(None, None, None)


def test_duplicate_application_is_marked_read_not_recreated(settings):
    c = setup(settings, [mail("Asha <asha@example.com>", "[job:1]", attach=[("cv.docx", docx_of(STRONG))])])
    try:
        h = login(c)
        c.post("/jobs", json={"title": "Backend Engineer", "description": JD}, headers=h)
        assert c.post("/admin/inbox/poll", headers=h).json()["created"] == 1
        FakeImap.seen_all.clear()  # pretend the mail came again
        r = c.post("/admin/inbox/poll", headers=h).json()
        assert r["created"] == 0 and r["already_applied"] == 1
    finally:
        c.__exit__(None, None, None)


def test_bad_password_and_missing_config_and_recruiter_cannot_poll(settings):
    c = setup(replace(settings), [])
    try:
        h = login(c)
        c.app.state.settings = replace(c.app.state.settings)
        assert c.post("/users", json={"username": "rec1", "password": "a long password here"}, headers=h).status_code == 201
        assert c.post("/admin/inbox/poll", headers=login(c, "rec1", "a long password here")).status_code == 403
    finally:
        c.__exit__(None, None, None)
    with TestClient(create_app(settings)) as c2:  # no mailbox settings at all
        assert c2.post("/admin/inbox/poll", headers=login(c2)).status_code == 400
    wrong = replace(settings, imap_user="jobs@example.com", imap_password="wrong")
    with TestClient(create_app(wrong)) as c3:
        c3.app.state.imap_factory = FakeImap
        r = c3.post("/admin/inbox/poll", headers=login(c3))
        assert r.status_code == 502 and "wrong" not in r.text

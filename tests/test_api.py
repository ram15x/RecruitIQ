import datetime as dt
import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from recruitiq.api.app import create_app
from tests.conftest import STRONG, WEAK, apply, login


def iso(minutes):
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)).isoformat()


def make_second_org(client, settings, tmp_path):
    """A second company on its own database file is not enough to test isolation, so add an org to the same db."""
    from recruitiq.db.models import Org, User
    from recruitiq.services import security
    s = client.app.state.session_factory()
    o = Org(name="Other Co")
    s.add(o)
    s.flush()
    s.add(User(username="other", password_hash=security.hash_password("another long password"), role="admin", org_id=o.id))
    s.commit()
    s.close()
    return login(client, "other", "another long password")


def test_health_and_auth_required(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/jobs").status_code == 401
    assert client.get("/jobs", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_login_wrong_password_then_throttled(client):
    for _ in range(5):
        assert client.post("/auth/login", data={"username": "admin1", "password": "bad bad bad"}).status_code == 401
    assert client.post("/auth/login", data={"username": "admin1", "password": "correct horse battery"}).status_code == 429


def test_job_skill_suggestion_and_override(client, auth, job):
    assert set(job["required"]) == {"python", "fastapi", "postgresql", "docker"} and job["min_years"] == 3
    r = client.post("/jobs", json={"title": "Other", "description": "x" * 30, "required": ["python"], "preferred": []}, headers=auth)
    assert r.json()["required"] == ["python"]


def test_consent_is_required(client, auth, job):
    assert apply(client, auth, job["id"], consent=False).status_code == 422


def test_application_is_scored_and_listed_blind_and_ranked(client, auth, job):
    a = apply(client, auth, job["id"]).json()
    b = apply(client, auth, job["id"], name="Vikram Nair", email="v@example.com", text=WEAK).json()
    assert a["score"] > b["score"] and a["candidate_ref"].startswith("C-")
    lst = client.get(f"/jobs/{job['id']}/applications", headers=auth).json()
    assert [x["id"] for x in lst] == [a["id"], b["id"]]
    assert "Asha" not in json.dumps(lst) and "example.com" not in json.dumps(lst)
    assert apply(client, auth, job["id"]).status_code == 409  # same person, same job


def test_identity_only_on_reveal_and_reveal_is_audited(client, auth, job):
    a = apply(client, auth, job["id"]).json()
    plain = client.get(f"/applications/{a['id']}", headers=auth).json()
    assert "identity" not in plain and "Asha" not in plain["what_the_scorer_saw"] and "asha@" not in json.dumps(plain)
    shown = client.get(f"/applications/{a['id']}?reveal=true", headers=auth).json()
    assert shown["identity"]["name"] == "Asha Rao"
    assert any(e["action"] == "identity_revealed" for e in client.get("/audit", headers=auth).json())


def test_decision_needs_a_real_reason(client, auth, job):
    a = apply(client, auth, job["id"]).json()
    assert client.post(f"/applications/{a['id']}/decision", json={"decision": "shortlist", "reason": "ok"}, headers=auth).status_code == 422
    r = client.post(f"/applications/{a['id']}/decision", json={"decision": "shortlist", "reason": "Shipped FastAPI on PostgreSQL at scale."}, headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "shortlisted" and r.json()["decision_reason"]


def test_other_org_cannot_see_or_touch_anything(client, settings, tmp_path, auth, job):
    a = apply(client, auth, job["id"]).json()
    other = make_second_org(client, settings, tmp_path)
    assert client.get("/jobs", headers=other).json() == []
    for url in (f"/jobs/{job['id']}/applications", f"/applications/{a['id']}", f"/jobs/{job['id']}/fairness"):
        assert client.get(url, headers=other).status_code == 404
    assert client.post(f"/applications/{a['id']}/decision", json={"decision": "reject", "reason": "not allowed at all"}, headers=other).status_code == 404
    assert client.delete("/candidates/1", headers=other).status_code == 404
    assert client.post(f"/jobs/{job['id']}/applications/json", headers=other,
                       json={"name": "X", "email": "x@x.com", "resume_text": STRONG, "consent": True}).status_code == 404


def test_recruiter_cannot_use_admin_endpoints(client, auth):
    assert client.post("/users", json={"username": "rec1", "password": "a long password here"}, headers=auth).status_code == 201
    rec = login(client, "rec1", "a long password here")
    assert client.get("/audit", headers=rec).status_code == 403
    assert client.post("/admin/retention/purge", headers=rec).status_code == 403
    assert client.post("/users", json={"username": "rec2", "password": "a long password here"}, headers=rec).status_code == 403


def test_webhook_needs_a_valid_signature(client, job):
    body = json.dumps({"job_id": job["id"], "name": "Asha Rao", "email": "w@example.com", "resume_text": STRONG, "consent": True}).encode()
    good = "sha256=" + hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
    assert client.post("/webhooks/intake", content=body).status_code == 401
    assert client.post("/webhooks/intake", content=body, headers={"x-signature": "sha256=" + "0" * 64}).status_code == 401
    assert client.post("/webhooks/intake", content=body + b" ", headers={"x-signature": good}).status_code == 401
    assert client.post("/webhooks/intake", content=body, headers={"x-signature": good}).status_code == 201


def test_webhook_disabled_without_a_secret(settings, job):
    pass  # covered below with its own app, since the secret is part of the settings fixture


def test_webhook_off_when_no_secret(tmp_path):
    from recruitiq.config import Settings
    s = Settings(db_url=f"sqlite:///{tmp_path / 'n.db'}", jwt_secret="x" * 32, bootstrap_user="admin1", bootstrap_password="correct horse battery", webhook_secret="")
    with TestClient(create_app(s)) as c:
        h = login(c)
        j = c.post("/jobs", json={"title": "Backend", "description": "Requirements\nPython and Docker."}, headers=h).json()
        body = json.dumps({"job_id": j["id"], "name": "A", "email": "a@b.com", "resume_text": STRONG, "consent": True}).encode()
        empty = "sha256=" + hmac.new(b"", body, hashlib.sha256).hexdigest()
        assert c.post("/webhooks/intake", content=body, headers={"x-signature": empty}).status_code == 401


def test_notifications_are_drafts_until_sent(client, auth, job):
    a = apply(client, auth, job["id"]).json()
    assert client.post(f"/applications/{a['id']}/notifications", json={"kind": "decision"}, headers=auth).status_code == 409  # no decision yet
    client.post(f"/applications/{a['id']}/decision", json={"decision": "shortlist", "reason": "Strong evidenced backend work."}, headers=auth)
    n = client.post(f"/applications/{a['id']}/notifications", json={"kind": "decision"}, headers=auth).json()
    assert n["status"] == "draft"
    r = client.post(f"/notifications/{n['id']}/send", headers=auth).json()
    assert r["status"] == "failed" and r["error"]  # no SMTP configured in tests, and it says so instead of pretending


def shortlisted(client, auth, job_id):
    a = apply(client, auth, job_id).json()
    client.post(f"/applications/{a['id']}/decision", json={"decision": "shortlist", "reason": "Strong evidenced backend work."}, headers=auth)
    return a


def test_interview_requires_shortlist_and_naive_time_is_rejected(client, auth, job):
    a = apply(client, auth, job["id"]).json()
    assert client.post(f"/applications/{a['id']}/interviews", json={"scheduled_at": iso(-1)}, headers=auth).status_code == 409
    client.post(f"/applications/{a['id']}/decision", json={"decision": "shortlist", "reason": "Strong evidenced backend work."}, headers=auth)
    assert client.post(f"/applications/{a['id']}/interviews", json={"scheduled_at": "2030-01-01T10:00:00"}, headers=auth).status_code == 422


def test_interview_window_and_one_shot_submit(client, auth, job):
    a = shortlisted(client, auth, job["id"])
    # in the future: the link exists but the portal stays closed
    future = client.post(f"/applications/{a['id']}/interviews", json={"scheduled_at": iso(120)}, headers=auth).json()
    tok = future["link"].rsplit("/", 1)[1]
    s = client.get(f"/portal/{tok}/session").json()
    assert s["state"] == "not_open" and "questions" not in s
    assert client.post(f"/portal/{tok}/start").status_code == 409
    # a fresh one that just opened
    now_ = client.post(f"/applications/{a['id']}/interviews", json={"scheduled_at": iso(-1)}, headers=auth).json()
    tok = now_["link"].rsplit("/", 1)[1]
    assert client.get(f"/portal/{tok}/session").json()["state"] == "ready"
    assert client.post(f"/portal/{tok}/submit", json={"answers": {"q1": "x"}}).status_code == 409  # not started
    st = client.post(f"/portal/{tok}/start").json()
    assert st["questions"]
    answers = {q["id"]: "I would measure first, then change one thing at a time, because guessing wastes days and hides the real cause." for q in st["questions"]}
    r = client.post(f"/portal/{tok}/submit", json={"answers": answers, "signals": {"tab_switches": 2, "paste_events": 1, "seconds_total": 600, "evil": "x"}})
    assert r.status_code == 200
    assert client.post(f"/portal/{tok}/submit", json={"answers": answers}).status_code == 409  # only once
    full = client.get(f"/applications/{a['id']}?reveal=true", headers=auth).json()
    iv = full["interviews"][-1]
    assert iv["status"] == "completed" and iv["analysis"]
    assert "integrity" not in json.dumps(iv["analysis"]).lower() or "score" not in iv["analysis"]


def test_bad_or_tampered_interview_link(client, auth, job):
    a = shortlisted(client, auth, job["id"])
    link = client.post(f"/applications/{a['id']}/interviews", json={"scheduled_at": iso(-1)}, headers=auth).json()["link"]
    tok = link.rsplit("/", 1)[1]
    assert client.get(f"/portal/{tok[:-3]}abc/session").status_code == 404
    assert client.get("/portal/garbage/session").status_code == 404


def test_expired_interview_link_is_dead(client, auth, job):
    a = shortlisted(client, auth, job["id"])
    link = client.post(f"/applications/{a['id']}/interviews", json={"scheduled_at": iso(-600), "duration_minutes": 30, "grace_minutes": 5}, headers=auth).json()["link"]
    assert client.get(f"/portal/{link.rsplit('/', 1)[1]}/session").status_code == 404


def test_fairness_endpoint_and_demographics_stay_out_of_scoring(client, auth, job):
    ids = []
    for k in range(4):
        r = apply(client, auth, job["id"], name=f"P{k}", email=f"p{k}@example.com").json()
        ids.append(r)
        before = r["score"]
        client.put(f"/applications/{r['id']}/demographic", json={"group_label": "A" if k % 2 else "B"}, headers=auth)
        assert client.get(f"/applications/{r['id']}", headers=auth).json()["score"] == before
    rep = client.get(f"/jobs/{job['id']}/fairness?stage=model", headers=auth).json()
    assert rep["stage"] == "model" and "note" in rep and rep["flagged"] == []


def test_erase_and_purge(client, auth, job, settings):
    a = apply(client, auth, job["id"]).json()
    cid = int(a["candidate_ref"].split("-")[1])
    assert client.delete(f"/candidates/{cid}", headers=auth).json() == {"erased": cid}
    assert client.get(f"/applications/{a['id']}", headers=auth).status_code == 404
    # purge: push one candidate past its retention date
    b = apply(client, auth, job["id"], name="Old", email="old@example.com").json()
    from recruitiq.db.models import Candidate
    s = client.app.state.session_factory()
    c = s.get(Candidate, int(b["candidate_ref"].split("-")[1]))
    c.retention_until = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    s.commit(); s.close()
    assert client.post("/admin/retention/purge", headers=auth).json() == {"removed": 1}


def test_pdf_report_hides_identity_unless_asked(client, auth, job):
    a = apply(client, auth, job["id"]).json()
    r = client.get(f"/applications/{a['id']}/report.pdf", headers=auth)
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and b"Asha" not in r.content


def test_upload_rejects_wrong_type_and_big_files(client, auth, job):
    r = client.post(f"/jobs/{job['id']}/applications", headers=auth, data={"name": "A", "email": "a@b.com", "consent": "true"},
                    files={"file": ("cv.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")})
    assert r.status_code in (400, 415, 422)
    r = client.post(f"/jobs/{job['id']}/applications", headers=auth, data={"name": "A", "email": "a@b.com", "consent": "true"},
                    files={"file": ("cv.txt", STRONG.encode(), "text/plain")})
    assert r.status_code == 201 and r.json()["score"] > 60


def test_dashboard(client, auth, job):
    apply(client, auth, job["id"])
    d = client.get("/dashboard", headers=auth).json()
    assert d["open_jobs"] == 1

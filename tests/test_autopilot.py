from recruitiq.services import notify
from tests.conftest import STRONG, WEAK, apply

POLICY = {"acknowledge": True, "auto_invite_min": 70, "interview_mode": "written", "window_hours": 48}


def _job(client, auth, jd, autopilot=None):
    body = {"title": "Backend Engineer", "description": jd}
    if autopilot is not None:
        body["autopilot"] = autopilot
    r = client.post("/jobs", json=body, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def _sent(monkeypatch, client):
    sent = []
    st = client.app.state.settings if hasattr(client.app.state, "settings") else None
    assert st is not None

    def fake(settings, n):
        sent.append(n.subject)
        return True, ""
    monkeypatch.setattr("recruitiq.api.app._mailer", fake)
    for k, v in dict(smtp_host="smtp.test", smtp_user="u", smtp_password="p", mail_from="hr@test").items():
        monkeypatch.setattr(st, k, v)
    return sent


def test_policy_is_validated(client, auth):
    from tests.conftest import JD
    r = client.post("/jobs", json={"title": "Backend Engineer", "description": JD, "autopilot": {"auto_invite_min": 500}}, headers=auth)
    assert r.status_code in (400, 422)


def test_off_by_default_nothing_is_sent(client, auth, job, monkeypatch):
    sent = _sent(monkeypatch, client)
    assert apply(client, auth, job["id"]).status_code in (200, 201)
    assert sent == []
    t = client.get("/todo", headers=auth).json()
    assert t["counts"]["suggested_acceptances"] + t["counts"]["borderline"] + t["counts"]["flagged"] >= 1


def test_strong_clean_resume_is_invited_and_weak_one_is_not_rejected(client, auth, monkeypatch):
    from tests.conftest import JD
    job = _job(client, auth, JD, POLICY)
    sent = _sent(monkeypatch, client)
    s = apply(client, auth, job["id"], text=STRONG).json()
    w = apply(client, auth, job["id"], name="Vikram Nair", email="v@example.com", text=WEAK).json()
    apps = {a["id"]: a for a in client.get(f"/jobs/{job['id']}/applications", headers=auth).json()}
    assert apps[s["id"]]["status"] == "interview_invited"
    assert apps[w["id"]]["status"] == "scored"  # never rejected by itself
    assert len(sent) >= 2  # an acknowledgement for each, plus the invite
    assert not any("unfortunately" in x.lower() for x in sent)


def test_bulk_decision_guards(client, auth, job):
    ids = [apply(client, auth, job["id"], name=f"Cand {i}", email=f"c{i}@example.com", text=WEAK).json()["id"] for i in range(2)]
    body = {"application_ids": ids, "decision": "reject", "reason": "Does not meet the stated requirements", "confirm_count": 1, "send": False}
    assert client.post("/bulk-decision", json=body, headers=auth).status_code == 409
    body["confirm_count"] = 2
    r = client.post("/bulk-decision", json=body, headers=auth).json()
    assert r["decided"] == 2
    again = client.post("/bulk-decision", json=body, headers=auth).json()
    assert again["decided"] == 0 and again["skipped_not_pending"] == 2


def test_bulk_decision_is_org_scoped(client, auth, job, settings, tmp_path):
    from tests.test_api import make_second_org
    other = make_second_org(client, settings, tmp_path)
    aid = apply(client, auth, job["id"]).json()["id"]
    body = {"application_ids": [aid], "decision": "reject", "reason": "Does not meet the stated requirements", "confirm_count": 1, "send": False}
    r = client.post("/bulk-decision", json=body, headers=other).json()
    assert r["decided"] == 0


def test_notify_received_wording():
    s, b = notify.received("Asha Rao", "Backend Engineer")
    assert "Backend Engineer" in s + b

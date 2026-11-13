import pytest
from fastapi.testclient import TestClient

from recruitiq.api.app import create_app
from recruitiq.config import Settings

BOOT = ("admin1", "correct horse battery")
JD = ("Backend Engineer\nRequirements\n3+ years building production APIs. Python, FastAPI, PostgreSQL, Docker.\n"
      "Nice to have\nKubernetes, AWS, Kafka")

STRONG = """Asha Rao
asha.rao@example.com | +91 98765 43210
Summary
Backend engineer with 6 years of experience building APIs.
Skills
Python, FastAPI, PostgreSQL, Docker, Kubernetes
Experience
Senior Engineer, Acme (Jan 2021 - Present)
Built a FastAPI service on PostgreSQL that cut p95 latency by 40%. Containerised it with Docker and deployed on AWS for twelve internal teams.
Engineer, Beta Corp (2019 - 2021)
Wrote Python services and CI checks on every pull request, and moved batch jobs onto Kafka.
Education
B.Tech, Anna University (2015 - 2019)
"""
WEAK = """Vikram Nair
vik@example.com
Summary
Nurse with 4 years of experience on a surgical ward.
Experience
Staff Nurse, City Hospital (2020 - Present)
Looked after twelve inpatients per shift, gave scheduled medication and kept accurate patient charts for the whole ward.
"""


@pytest.fixture()
def settings(tmp_path):
    return Settings(db_url=f"sqlite:///{tmp_path / 't.db'}", jwt_secret="test-secret-0123456789abcdef-0123456789",
                    bootstrap_user=BOOT[0], bootstrap_password=BOOT[1], webhook_secret="hook-secret", public_url="http://testserver")


@pytest.fixture()
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def login(client, user=BOOT[0], pw=BOOT[1]):
    r = client.post("/auth/login", data={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def auth(client):
    return login(client)


@pytest.fixture()
def job(client, auth):
    r = client.post("/jobs", json={"title": "Backend Engineer", "description": JD}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def apply(client, auth, job_id, name="Asha Rao", email="asha@example.com", text=STRONG, consent=True):
    return client.post(f"/jobs/{job_id}/applications/json", headers=auth,
                       json={"name": name, "email": email, "resume_text": text, "consent": consent})

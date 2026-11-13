from fastapi.testclient import TestClient

from recruitiq.api.app import create_app
from recruitiq.core import evidence, gaps
from recruitiq.core.jobspec import JobSpec
from recruitiq.core.scoring import Scorer
from tests.conftest import JD, STRONG, apply, login
from tests.test_api import make_second_org

TEXT = """Skills
Python, Kafka
Experience
Built an event pipeline on Apache Kafka that handled 40k messages per second for the payments team. Ran the on-call rota.
Led a team of 4 engineers.
"""


class TestEvidenceSearch:
    def test_returns_only_real_lines_work_history_first(self):
        r = evidence.search("kafka", TEXT)
        assert [x.in_skills_list for x in r] == [False, True]
        assert all(x.text in TEXT for x in r)

    def test_alias_and_phrase_and_nothing_made_up(self):
        assert evidence.search("apache kafka", TEXT) and evidence.search("led a team", TEXT)
        assert evidence.search("terraform", TEXT) == [] and evidence.search("k8s", TEXT) == []

    def test_every_word_of_a_phrase_must_be_present(self):
        assert evidence.search("kafka payments", TEXT) and not evidence.search("kafka nursing", TEXT)

    def test_alias_spelling_matches(self):
        assert evidence.search("postgres", "Experience\nDesigned the PostgreSQL schema for returns and wrote the migrations.\n")


class TestGaps:
    job = JobSpec.from_text("Backend Engineer", JD)

    def test_gain_is_exact_arithmetic(self):
        # only the required-skills part counts here, so the effect of one skill is arithmetic we can check by scoring again
        sc = Scorer(weights={"required": 1.0, "preferred": 0.0, "experience": 0.0, "similarity": 0.0})
        job = JobSpec.from_text("x", "Requirements\nPython and FastAPI.", required=["python", "fastapi"], preferred=[])
        listed = "Skills\nPython, FastAPI\nExperience\nWrote Python tooling for the finance team and kept it running for three years in production.\n"
        shown = listed.replace("Wrote Python tooling", "Wrote FastAPI and Python tooling")
        r1, r2 = sc.score(listed, job), sc.score(shown, job)
        g = next(x for x in gaps.score_gaps(r1.as_dict()) if x["skill"] == "fastapi")
        assert round(r1.score + g["gain"], 1) == r2.score

    def test_nothing_missing_means_no_skill_gaps(self):
        res = Scorer().score(STRONG, self.job, ["Asha Rao"]).as_dict()
        assert not [g for g in gaps.score_gaps(res) if g["kind"] == "required"]

    def test_compare_lines_up_skills(self):
        sc = Scorer()
        a, b = sc.score(STRONG, self.job).as_dict(), sc.score("Experience\nNurse on a ward for several years, looking after patients every shift in a hospital.\n" * 3, self.job).as_dict()
        c = gaps.compare(a, b)
        assert {r["skill"] for r in c["skills"]} >= {"python", "fastapi", "kafka"}
        assert c["components"]["required"]["a"] > c["components"]["required"]["b"]


def test_pool_search_is_blind_org_scoped_and_validated(client, auth, job, settings, tmp_path):
    apply(client, auth, job["id"])
    r = client.get(f"/jobs/{job['id']}/search", params={"q": "kafka"}, headers=auth).json()
    assert r["searched"] == 1 and r["matches"][0]["candidate_ref"].startswith("C-")
    blob = str(r)
    assert "Asha" not in blob and "example.com" not in blob and "98765" not in blob
    assert client.get(f"/jobs/{job['id']}/search", params={"q": "x"}, headers=auth).status_code == 422
    other = make_second_org(client, settings, tmp_path)
    assert client.get(f"/jobs/{job['id']}/search", params={"q": "kafka"}, headers=other).status_code == 404


def test_compare_endpoint_needs_same_org_and_job(client, auth, job, settings, tmp_path):
    a = apply(client, auth, job["id"]).json()
    b = apply(client, auth, job["id"], name="B Person", email="b@example.com").json()
    assert client.get(f"/jobs/{job['id']}/compare", params={"a": a["id"], "b": b["id"]}, headers=auth).status_code == 200
    assert client.get(f"/jobs/{job['id']}/compare", params={"a": a["id"], "b": 999}, headers=auth).status_code == 404
    other = make_second_org(client, settings, tmp_path)
    assert client.get(f"/jobs/{job['id']}/compare", params={"a": a["id"], "b": b["id"]}, headers=other).status_code == 404


def test_demo_seed_runs_once_and_only_when_asked(settings, tmp_path):
    from dataclasses import replace
    s = replace(settings, demo=True)
    for expected in (8, 8):  # a restart on the same database must not double it
        with TestClient(create_app(s)) as c:
            h = login(c)
            jobs = c.get("/jobs", headers=h).json()
            assert len(jobs) == 1 and len(c.get(f"/jobs/{jobs[0]['id']}/applications", headers=h).json()) == expected
            assert c.get("/health").json()["demo"] is True
    with TestClient(create_app(replace(settings, db_url=f"sqlite:///{tmp_path / 'fresh.db'}", demo=False))) as c:
        assert c.get("/jobs", headers=login(c)).json() == []


def test_demo_data_behaves_as_described(settings):
    from dataclasses import replace
    with TestClient(create_app(replace(settings, demo=True))) as c:
        h = login(c)
        j = c.get("/jobs", headers=h).json()[0]
        rows = c.get(f"/jobs/{j['id']}/applications", headers=h).json()
        assert rows[0]["score"] >= 70 and rows[0]["status"] == "shortlisted"
        flagged = [r for r in rows if r["needs_review"]]
        assert len(flagged) >= 2 and all(r["score"] < 55 for r in flagged)  # the stuffed and the injected resumes

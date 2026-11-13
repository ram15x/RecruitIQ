import datetime as dt
import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import ROOT, Settings, get_settings
from ..core import evidence, fairness, gaps, pii
from ..core.injection import Flag
from ..core.jobspec import JobSpec
from ..core.scoring import Scorer
from ..core.skills import default_ontology
from ..db.models import Application, Candidate, Demographic, Interview, Job, Notification, Org, User, now
from ..db.session import make_engine, make_session_factory
from ..services import interview as iv
from ..services import llm, notify, report, resume_text, security
from . import schemas
from .deps import admin_only, audit, current_user, get_db, org_name

log = logging.getLogger("recruitiq.api")
PORTAL = ROOT / "portal" / "index.html"
SELECTED = ("shortlisted", "interview_invited", "interviewed")
CONSENT_VERSION = "v1"


def ref(candidate_id: int) -> str:
    return f"C-{candidate_id:04d}"


def create_app(settings: Settings | None = None, scorer: Scorer | None = None) -> FastAPI:
    settings = settings or get_settings()
    if len(settings.jwt_secret) < 16:
        raise RuntimeError("set RECRUITIQ_JWT_SECRET to a random string of at least 16 characters")

    @asynccontextmanager
    async def lifespan(app):
        app.state.engine = make_engine(settings.db_url)
        app.state.session_factory = make_session_factory(app.state.engine)
        _bootstrap(app.state.session_factory, settings)
        if settings.demo:
            from .. import demo
            demo.seed(app.state.session_factory, app.state.scorer)
        yield
        app.state.engine.dispose()

    app = FastAPI(title="RecruitIQ", version="2.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.scorer = scorer or Scorer()
    app.state.throttle = security.LoginThrottle()
    # no wildcard origin: the dashboard talks to the API from the server side, and a browser origin is only allowed if you list it
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    def health():
        return {"status": "ok", "demo": settings.demo}

    # ------------------------------------------------------------------ auth
    @app.post("/auth/login", response_model=schemas.Token)
    def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
        name = form.username.strip().lower()
        if app.state.throttle.blocked(name):
            raise HTTPException(429, "too many failed attempts, try again later")
        user = db.scalar(select(User).where(func.lower(User.username) == name))
        ok = security.verify_password(form.password, user.password_hash if user else security.DUMMY_HASH)
        if not (user and user.active and ok):
            app.state.throttle.fail(name)
            audit(db, None, "login_failed", "user", name)
            raise HTTPException(401, "wrong username or password")
        app.state.throttle.clear(name)
        audit(db, user, "login", "user", user.id)
        return schemas.Token(access_token=security.make_token(settings.jwt_secret, user.id, settings.jwt_minutes))

    @app.get("/me", response_model=schemas.UserOut)
    def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
        return schemas.UserOut(id=user.id, username=user.username, role=user.role, org_id=user.org_id, org_name=org_name(db, user.org_id))

    @app.post("/users", response_model=schemas.UserOut, status_code=201)
    def add_user(body: schemas.UserIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
        u = User(username=body.username, password_hash=security.hash_password(body.password), role=body.role, org_id=admin.org_id)
        db.add(u)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "username already taken")
        audit(db, admin, "user_created", "user", u.id)
        return schemas.UserOut(id=u.id, username=u.username, role=u.role, org_id=u.org_id, org_name=org_name(db, u.org_id))

    # ------------------------------------------------------------------ jobs
    def _job(db, user, job_id) -> Job:
        j = db.scalar(select(Job).where(Job.id == job_id, Job.org_id == user.org_id))
        if not j:
            raise HTTPException(404, "job not found")
        return j

    def _job_out(j):
        return schemas.JobOut(id=j.id, title=j.title, description=j.description, required=j.required, preferred=j.preferred,
                              min_years=j.min_years, status=j.status, created_at=j.created_at)

    @app.post("/jobs/parse")
    def parse_job(body: schemas.JobIn, user: User = Depends(current_user)):
        """Preview the skills we would pull out of a description, so a person can fix them before saving."""
        spec = JobSpec.from_text(body.title, body.description, required=body.required, preferred=body.preferred, min_years=body.min_years)
        return {"required": spec.required, "preferred": spec.preferred, "min_years": spec.min_years}

    @app.post("/jobs", response_model=schemas.JobOut, status_code=201)
    def create_job(body: schemas.JobIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
        spec = JobSpec.from_text(body.title, body.description, required=body.required, preferred=body.preferred, min_years=body.min_years)
        j = Job(org_id=user.org_id, title=body.title.strip(), description=body.description, required=spec.required,
                preferred=spec.preferred, min_years=spec.min_years, created_by=user.id)
        db.add(j)
        db.commit()
        audit(db, user, "job_created", "job", j.id)
        return _job_out(j)

    @app.get("/jobs", response_model=list[schemas.JobOut])
    def list_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)):
        return [_job_out(j) for j in db.scalars(select(Job).where(Job.org_id == user.org_id).order_by(Job.id.desc()))]

    @app.post("/jobs/{job_id}/close", response_model=schemas.JobOut)
    def close_job(job_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
        j = _job(db, user, job_id)
        j.status = "closed"
        db.commit()
        audit(db, user, "job_closed", "job", j.id)
        return _job_out(j)

    # ------------------------------------------------------------- applications
    def _ingest(db: Session, org_id: int, job: Job, name: str, email: str, text: str, source: str, consent: bool,
                user: User | None, file_flags: list | None = None) -> Application:
        if not consent:
            raise HTTPException(422, "the candidate's consent to process their application is required")
        if job.status != "open":
            raise HTTPException(409, "this job is closed")
        text = (text or "").strip()
        if len(text) < 30:
            raise HTTPException(422, "no readable resume text")
        email = email.strip().lower()
        cand = db.scalar(select(Candidate).where(Candidate.org_id == org_id, Candidate.email == email))
        retention = now() + dt.timedelta(days=settings.retention_days)
        if cand:
            cand.resume_text, cand.name = text, name.strip()
            cand.retention_until = retention
        else:
            cand = Candidate(org_id=org_id, name=name.strip(), email=email, source=source, resume_text=text,
                             consent_version=CONSENT_VERSION, retention_until=retention)
            db.add(cand)
            db.flush()
        if db.scalar(select(Application).where(Application.job_id == job.id, Application.candidate_id == cand.id)):
            db.rollback()
            raise HTTPException(409, "this candidate has already applied for this job")
        spec = JobSpec(job.title, job.description, job.required, job.preferred, job.min_years)
        extra = [Flag("hidden_text", n, "review") for n in file_flags or []]
        res = app.state.scorer.score(text, spec, [cand.name], extra)
        a = Application(org_id=org_id, job_id=job.id, candidate_id=cand.id, status="scored", score=res.score, band=res.band,
                        needs_review=res.needs_review, result=res.as_dict())
        db.add(a)
        db.commit()
        audit(db, user, "application_scored", "application", a.id, f"job {job.id} score {res.score}", org_id=org_id)
        return a

    def _app(db, user, app_id) -> Application:
        a = db.scalar(select(Application).where(Application.id == app_id, Application.org_id == user.org_id))
        if not a:
            raise HTTPException(404, "application not found")
        return a

    def _summary(a: Application):
        return {"id": a.id, "candidate_ref": ref(a.candidate_id), "score": a.score, "band": a.band, "status": a.status,
                "needs_review": a.needs_review, "flags": len(a.result.get("flags", [])),
                "components": a.result.get("components", {}), "created_at": a.created_at.isoformat()}

    @app.post("/jobs/{job_id}/applications", status_code=201)
    async def apply(job_id: int, name: str = Form(...), email: str = Form(...), consent: bool = Form(...),
                    resume_text_field: str = Form("", alias="resume_text"), file: UploadFile | None = File(None),
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
        job = _job(db, user, job_id)
        text, file_flags = resume_text_field, []
        if file is not None:
            try:
                raw = await file.read(settings.max_upload_mb * 1_000_000 + 1)
                text, file_flags = resume_text.extract_ex(raw, file.filename or "", settings.max_upload_mb * 1_000_000)
            except resume_text.UploadError as e:
                raise HTTPException(422, str(e))
        a = _ingest(db, user.org_id, job, name, email, text, "upload", consent, user, file_flags)
        return _summary(a)

    @app.post("/jobs/{job_id}/applications/json", status_code=201)
    def apply_json(job_id: int, body: schemas.ApplicantIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
        job = _job(db, user, job_id)
        return _summary(_ingest(db, user.org_id, job, body.name, body.email, body.resume_text, body.source, body.consent, user))

    @app.post("/webhooks/intake", status_code=201)
    async def webhook(request: Request, db: Session = Depends(get_db)):
        """For a form tool or n8n. The body must be signed: header X-Signature: sha256=<hmac of the raw body>."""
        raw = await request.body()
        if not security.check_signature(settings.webhook_secret, raw, request.headers.get("x-signature")):
            raise HTTPException(401, "bad or missing signature")
        try:
            body = schemas.WebhookIn.model_validate(json.loads(raw))
        except Exception:
            raise HTTPException(422, "invalid payload")
        job = db.get(Job, body.job_id)
        if not job:
            raise HTTPException(404, "job not found")
        a = _ingest(db, job.org_id, job, body.name, body.email, body.resume_text, body.source, body.consent, None)
        return {"id": a.id, "candidate_ref": ref(a.candidate_id)}

    @app.get("/jobs/{job_id}/applications")
    def ranked(job_id: int, status_: str | None = None, needs_review: bool | None = None, min_score: float = 0,
               user: User = Depends(current_user), db: Session = Depends(get_db)):
        _job(db, user, job_id)
        stmt = select(Application).where(Application.job_id == job_id, Application.org_id == user.org_id, Application.score >= min_score)
        if status_:
            stmt = stmt.where(Application.status == status_)
        if needs_review is not None:
            stmt = stmt.where(Application.needs_review == needs_review)
        rows = db.scalars(stmt.order_by(Application.score.desc(), Application.id))
        # names are not in the list on purpose. reviewers read the evidence first and reveal identity when they need it
        return [_summary(a) for a in rows]

    @app.get("/jobs/{job_id}/search")
    def search_pool(job_id: int, q: str, limit: int = 3, user: User = Depends(current_user), db: Session = Depends(get_db)):
        """Find resumes in this job's pool that say something. Returns the resume's own lines, nothing generated, no names."""
        _job(db, user, job_id)
        q = q.strip()[:200]
        if len(q) < 2:
            raise HTTPException(422, "type a skill or a phrase")
        o = default_ontology()
        rows = []
        for a in db.scalars(select(Application).where(Application.job_id == job_id, Application.org_id == user.org_id)):
            c = a.candidate
            lines = evidence.search(q, pii.mask(c.resume_text, [c.name]).text, o, limit=min(max(limit, 1), 5))
            if lines:
                rows.append({"id": a.id, "candidate_ref": ref(a.candidate_id), "score": a.score, "status": a.status,
                             "in_work_history": sum(1 for ln in lines if not ln.in_skills_list),
                             "lines": [{"text": ln.text, "only_in_skills_list": ln.in_skills_list} for ln in lines]})
        rows.sort(key=lambda r: (-r["in_work_history"], -r["score"]))
        return {"query": q, "matches": rows, "searched": db.scalar(select(func.count()).select_from(Application).where(
            Application.job_id == job_id, Application.org_id == user.org_id))}

    @app.get("/jobs/{job_id}/compare")
    def compare_two(job_id: int, a: int, b: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
        _job(db, user, job_id)
        rows = [db.scalar(select(Application).where(Application.id == i, Application.job_id == job_id, Application.org_id == user.org_id)) for i in (a, b)]
        if not all(rows):
            raise HTTPException(404, "application not found")
        out = gaps.compare(rows[0].result, rows[1].result)
        out["a"], out["b"] = ref(rows[0].candidate_id), ref(rows[1].candidate_id)
        out["scores"] = {"a": rows[0].score, "b": rows[1].score}
        return out

    @app.get("/applications/{app_id}")
    def application(app_id: int, reveal: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
        a = _app(db, user, app_id)
        c = a.candidate
        out = _summary(a) | {"job_id": a.job_id, "result": a.result, "decision_reason": a.decision_reason,
                             "decided_at": a.decided_at.isoformat() if a.decided_at else None,
                             "gaps": gaps.score_gaps(a.result),
                             "what_the_scorer_saw": pii.mask(c.resume_text, [c.name]).text,
                             "interviews": [{"id": i.id, "status": i.status, "scheduled_at": i.scheduled_at.isoformat(),
                                             "questions": i.questions, "answers": i.answers if reveal else None,
                                             "analysis": i.analysis} for i in a.interviews]}
        if reveal:
            out["identity"] = {"name": c.name, "email": c.email}
            out["resume_text"] = c.resume_text
            audit(db, user, "identity_revealed", "application", a.id)
        return out

    @app.post("/applications/{app_id}/decision")
    def decide(app_id: int, body: schemas.DecisionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
        a = _app(db, user, app_id)
        a.status = {"shortlist": "shortlisted", "reject": "rejected", "hold": "on_hold"}[body.decision]
        a.decided_by, a.decided_at, a.decision_reason = user.id, now(), body.reason.strip()
        db.commit()
        audit(db, user, "decision", "application", a.id, body.decision)
        return _summary(a) | {"decision_reason": a.decision_reason}

    @app.get("/applications/{app_id}/report.pdf")
    def pdf(app_id: int, reveal: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
        a = _app(db, user, app_id)
        job = db.get(Job, a.job_id)
        ident = {"name": a.candidate.name, "email": a.candidate.email} if reveal else None
        data = report.build_pdf(ref(a.candidate_id), job.title, a.result, a.status, a.decision_reason, ident)
        audit(db, user, "report_downloaded", "application", a.id, "identity shown" if reveal else "")
        return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="review_{ref(a.candidate_id)}.pdf"'})

    # ---------------------------------------------------------- notifications
    @app.post("/applications/{app_id}/notifications", status_code=201)
    def draft_notification(app_id: int, body: schemas.NotifyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
        """Creates a draft only. Nothing is emailed until a person sends it."""
        a = _app(db, user, app_id)
        if a.status not in ("shortlisted", "rejected"):
            raise HTTPException(409, "record a shortlist or reject decision first")
        job = db.get(Job, a.job_id)
        subject, text = notify.decision(a.candidate.name, job.title, a.status)
        n = Notification(org_id=user.org_id, application_id=a.id, to_email=a.candidate.email, subject=subject, body=text, created_by=user.id)
        db.add(n)
        db.commit()
        audit(db, user, "notification_drafted", "notification", n.id)
        return {"id": n.id, "to": n.to_email, "subject": n.subject, "body": n.body, "status": n.status}

    @app.post("/notifications/{nid}/send")
    def send_notification(nid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
        n = db.scalar(select(Notification).where(Notification.id == nid, Notification.org_id == user.org_id))
        if not n:
            raise HTTPException(404, "notification not found")
        if n.status == "sent":
            raise HTTPException(409, "already sent")
        ok, err = _mailer(settings, n)
        n.status, n.error = ("sent", "") if ok else ("failed", err)
        n.sent_at = now() if ok else None
        db.commit()
        audit(db, user, "notification_sent" if ok else "notification_failed", "notification", n.id, err)
        return {"id": n.id, "status": n.status, "error": n.error}

    # -------------------------------------------------------------- interviews
    @app.post("/applications/{app_id}/interviews", status_code=201)
    def schedule(app_id: int, body: schemas.InterviewIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
        a = _app(db, user, app_id)
        if a.status not in ("shortlisted", "interview_invited"):
            raise HTTPException(409, "an interview can only be scheduled after a person has shortlisted the application")
        job = db.get(Job, a.job_id)
        o = default_ontology()
        evidenced = [r["skill"] for r in a.result.get("required", []) + a.result.get("preferred", []) if r["status"] == "evidenced"]
        groups = {s: o.skills[s]["group"] for s in o.skills}
        qs = iv.build_questions(job.title, evidenced, job.required, groups)
        better = llm.refine_questions(settings.llm_api_key, job.title, job.required, [q["text"] for q in qs if q["category"] == "role"])
        if better:
            roles = [q for q in qs if q["category"] == "role"]
            for q, t in zip(roles, better):
                q["text"] = t
        sched = body.scheduled_at.astimezone(dt.timezone.utc)
        ends = sched + dt.timedelta(minutes=body.grace_minutes + body.duration_minutes)
        i = Interview(application_id=a.id, org_id=user.org_id, token_jti="pending", scheduled_at=sched, grace_minutes=body.grace_minutes,
                      duration_minutes=body.duration_minutes, questions=qs)
        db.add(i)
        db.flush()
        token, jti = security.make_interview_token(settings.jwt_secret, i.id, ends)
        i.token_jti = jti
        a.status = "interview_invited"
        link = f"{settings.public_url.rstrip('/')}/interview/{token}"
        subject, text = notify.invite(a.candidate.name, job.title, sched.strftime("%d %B %Y, %H:%M UTC"), link, body.duration_minutes, body.grace_minutes)
        n = Notification(org_id=user.org_id, application_id=a.id, to_email=a.candidate.email, subject=subject, body=text, created_by=user.id)
        db.add(n)
        db.commit()
        audit(db, user, "interview_scheduled", "interview", i.id)
        return {"interview_id": i.id, "link": link, "notification_id": n.id, "questions": qs}

    def _session(db, token) -> tuple[Interview, dict]:
        d = security.read_interview_token(settings.jwt_secret, token)
        i = db.get(Interview, d["iid"]) if d else None
        if not (d and i and i.token_jti == d["jti"]):
            raise HTTPException(404, "this link is not valid")
        return i, d

    def _state(i: Interview) -> dict:
        t = now()
        sched = i.scheduled_at if i.scheduled_at.tzinfo else i.scheduled_at.replace(tzinfo=dt.timezone.utc)
        if i.status == "cancelled":
            return {"state": "cancelled"}
        if i.status == "completed":
            return {"state": "completed"}
        if t < sched:
            return {"state": "not_open", "opens_in_seconds": int((sched - t).total_seconds())}
        if i.status == "started":
            started = i.started_at if i.started_at.tzinfo else i.started_at.replace(tzinfo=dt.timezone.utc)
            left = int((started + dt.timedelta(minutes=i.duration_minutes) - t).total_seconds())
            return {"state": "open" if left > -120 else "expired", "seconds_left": max(left, 0)}
        if t > sched + dt.timedelta(minutes=i.grace_minutes):
            return {"state": "expired"}
        return {"state": "ready", "seconds_left": i.duration_minutes * 60}

    @app.get("/interview/{token}", response_class=HTMLResponse)
    def portal(token: str):
        return HTMLResponse(PORTAL.read_text(encoding="utf-8"))

    @app.get("/portal/{token}/session")
    def portal_session(token: str, db: Session = Depends(get_db)):
        i, _ = _session(db, token)
        st = _state(i)
        out = dict(st)
        if st["state"] in ("ready", "open"):
            out["questions"] = i.questions
            out["minutes"] = i.duration_minutes
        return out

    @app.post("/portal/{token}/start")
    def portal_start(token: str, db: Session = Depends(get_db)):
        i, _ = _session(db, token)
        st = _state(i)
        if st["state"] not in ("ready", "open"):
            raise HTTPException(409, f"interview is {st['state']}")
        if i.status == "scheduled":
            i.status, i.started_at = "started", now()
            db.commit()
            audit(db, None, "interview_started", "interview", i.id, org_id=i.org_id)
        return _state(i) | {"questions": i.questions}

    @app.post("/portal/{token}/submit")
    def portal_submit(token: str, body: schemas.SubmitIn, db: Session = Depends(get_db)):
        i, _ = _session(db, token)
        st = _state(i)
        if i.status != "started" or st["state"] not in ("open",):
            raise HTTPException(409, f"interview is {st['state']}")
        i.answers = body.answers
        i.signals = {k: body.signals[k] for k in ("tab_switches", "paste_events", "seconds_total") if k in body.signals and isinstance(body.signals[k], (int, float))}
        i.analysis = iv.analyse(i.questions, body.answers, i.signals)
        i.status, i.completed_at = "completed", now()
        a = db.get(Application, i.application_id)
        a.status = "interviewed"
        db.commit()
        audit(db, None, "interview_completed", "interview", i.id, org_id=i.org_id)
        return {"state": "completed"}

    # ---------------------------------------------------------------- fairness
    @app.put("/applications/{app_id}/demographic")
    def set_demographic(app_id: int, body: schemas.DemographicIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
        a = _app(db, user, app_id)
        if a.demographic:
            a.demographic.group_label = body.group_label.strip()
        else:
            db.add(Demographic(application_id=a.id, group_label=body.group_label.strip()))
        db.commit()
        audit(db, user, "demographic_recorded", "application", a.id)
        return {"ok": True}

    @app.get("/jobs/{job_id}/fairness")
    def fairness_report(job_id: int, stage: str = "human", min_group: int = 10, user: User = Depends(current_user), db: Session = Depends(get_db)):
        """stage=model checks what the score alone would have selected (70 and above). stage=human checks what people decided."""
        _job(db, user, job_id)
        apps = list(db.scalars(select(Application).join(Demographic).where(Application.job_id == job_id, Application.org_id == user.org_id)))
        if stage == "model":
            rows = [(a.demographic.group_label, a.score >= 70) for a in apps]
        else:
            rows = [(a.demographic.group_label, a.status in SELECTED) for a in apps if a.status in SELECTED + ("rejected",)]
        rep = fairness.impact_report(rows, min_group=min_group)
        rep["stage"] = stage
        rep["note"] = ("Voluntary self-reported groups, used only here and never in scoring. A flag is a reason to look at the process, "
                       "not proof of bias, and a clear result is not proof of fairness.")
        return rep

    # ----------------------------------------------------------------- admin
    @app.delete("/candidates/{cid}")
    def erase(cid: int, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
        c = db.scalar(select(Candidate).where(Candidate.id == cid, Candidate.org_id == admin.org_id))
        if not c:
            raise HTTPException(404, "candidate not found")
        db.delete(c)
        db.commit()
        audit(db, admin, "candidate_erased", "candidate", cid)
        return {"erased": cid}

    @app.post("/admin/retention/purge")
    def purge(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
        old = list(db.scalars(select(Candidate).where(Candidate.org_id == admin.org_id, Candidate.retention_until < now())))
        for c in old:
            db.delete(c)
        db.commit()
        audit(db, admin, "retention_purge", "candidate", "", f"{len(old)} removed")
        return {"removed": len(old)}

    @app.get("/audit")
    def audit_log(limit: int = 100, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
        from ..db.models import AuditLog
        rows = db.scalars(select(AuditLog).where(AuditLog.org_id == admin.org_id).order_by(AuditLog.id.desc()).limit(min(limit, 500)))
        return [{"at": r.at.isoformat(), "user_id": r.user_id, "action": r.action, "entity": r.entity, "entity_id": r.entity_id, "detail": r.detail} for r in rows]

    @app.get("/dashboard")
    def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
        by_status = dict(db.execute(select(Application.status, func.count()).where(Application.org_id == user.org_id).group_by(Application.status)).all())
        open_jobs = db.scalar(select(func.count()).select_from(Job).where(Job.org_id == user.org_id, Job.status == "open"))
        awaiting = db.scalar(select(func.count()).select_from(Application).where(Application.org_id == user.org_id, Application.status == "scored"))
        flagged = db.scalar(select(func.count()).select_from(Application).where(Application.org_id == user.org_id, Application.needs_review.is_(True)))
        return {"open_jobs": open_jobs, "by_status": by_status, "awaiting_a_decision": awaiting, "flagged_for_review": flagged}

    return app


def _mailer(settings: Settings, n: Notification):
    return notify.send(settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password,
                       settings.mail_from, n.to_email, n.subject, n.body)


def _bootstrap(factory, settings: Settings):
    with factory() as db:
        if db.scalar(select(func.count()).select_from(User)) == 0:
            if settings.bootstrap_user and settings.bootstrap_password:
                org = db.scalar(select(Org)) or Org(name="Main Organisation")
                db.add(org)
                db.flush()
                db.add(User(username=settings.bootstrap_user, password_hash=security.hash_password(settings.bootstrap_password), role="admin", org_id=org.id))
                db.commit()
                log.info("created first admin '%s'", settings.bootstrap_user)
            else:
                log.warning("no users yet. run: python -m recruitiq.cli create-admin")


def app_factory() -> FastAPI:
    # uvicorn recruitiq.api.app:app_factory --factory
    return create_app()

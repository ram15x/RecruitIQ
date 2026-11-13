import datetime as dt

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now():
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class Org(Base):
    __tablename__ = "orgs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="recruiter")  # admin | recruiter
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    required: Mapped[list] = mapped_column(JSON, default=list)
    preferred: Mapped[list] = mapped_column(JSON, default=list)
    min_years: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="open")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(30), default="manual")
    resume_text: Mapped[str] = mapped_column(Text, default="")
    # consent is recorded when the application is created, with the wording version the candidate saw
    consent_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    consent_version: Mapped[str] = mapped_column(String(20), default="v1")
    retention_until: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_candidate_org_email"),)
    applications: Mapped[list["Application"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("job_id", "candidate_id", name="uq_application_job_candidate"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    # new -> scored -> (shortlisted | rejected | on_hold) -> interview_invited -> interviewed
    status: Mapped[str] = mapped_column(String(20), default="scored")
    score: Mapped[float] = mapped_column(default=0.0)
    band: Mapped[str] = mapped_column(String(20), default="")
    needs_review: Mapped[bool] = mapped_column(default=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    # only a person sets these, and the reason is required
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    candidate: Mapped[Candidate] = relationship(back_populates="applications")
    interviews: Mapped[list["Interview"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    demographic: Mapped["Demographic | None"] = relationship(back_populates="application", cascade="all, delete-orphan", uselist=False)


class Interview(Base):
    __tablename__ = "interviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    token_jti: Mapped[str] = mapped_column(String(40), unique=True)
    scheduled_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    grace_minutes: Mapped[int] = mapped_column(default=15)
    duration_minutes: Mapped[int] = mapped_column(default=45)
    status: Mapped[str] = mapped_column(String(12), default="scheduled")  # scheduled | started | completed | cancelled
    mode: Mapped[str] = mapped_column(String(10), default="written")  # written | voice
    record_video: Mapped[bool] = mapped_column(default=False)
    questions: Mapped[list] = mapped_column(JSON, default=list)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    signals: Mapped[dict] = mapped_column(JSON, default=dict)
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    application: Mapped[Application] = relationship(back_populates="interviews")


class Media(Base):
    """An audio or video answer. Played back by a person, never analysed by software. Deleted with the candidate."""
    __tablename__ = "media"
    __table_args__ = (UniqueConstraint("interview_id", "question_id", name="uq_media_interview_question"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), index=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    question_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(6))  # audio | video
    mime: Mapped[str] = mapped_column(String(40))
    size: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Demographic(Base):
    """Voluntary, self-reported, collected on a separate form. Used only by the fairness report. Never read by scoring."""
    __tablename__ = "demographics"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), unique=True)
    group_label: Mapped[str] = mapped_column(String(60))
    application: Mapped[Application] = relationship(back_populates="demographic")


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    application_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_email: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft | sent | failed
    error: Mapped[str] = mapped_column(String(255), default="")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    org_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40))
    entity: Mapped[str] = mapped_column(String(40), default="")
    entity_id: Mapped[str] = mapped_column(String(40), default="")
    detail: Mapped[str] = mapped_column(String(255), default="")

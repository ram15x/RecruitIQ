import datetime as dt
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    org_id: int
    org_name: str


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=60, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)
    role: str = "recruiter"

    @field_validator("role")
    @classmethod
    def _role(cls, v):
        if v not in ("admin", "recruiter"):
            raise ValueError("role must be admin or recruiter")
        return v


class JobIn(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=20, max_length=20000)
    # leave both lists out to have them suggested from the description. send them to use exactly what you wrote
    required: list[str] | None = None
    preferred: list[str] | None = None
    min_years: float | None = Field(default=None, ge=0, le=40)


class JobOut(BaseModel):
    id: int
    title: str
    description: str
    required: list[str]
    preferred: list[str]
    min_years: float | None
    status: str
    created_at: dt.datetime


class ApplicantIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    resume_text: str = Field(min_length=1, max_length=60000)
    consent: bool
    source: str = "manual"


class DecisionIn(BaseModel):
    decision: str
    reason: str = Field(min_length=10, max_length=2000)

    @field_validator("decision")
    @classmethod
    def _d(cls, v):
        if v not in ("shortlist", "reject", "hold"):
            raise ValueError("decision must be shortlist, reject or hold")
        return v


class InterviewIn(BaseModel):
    scheduled_at: dt.datetime
    duration_minutes: int = Field(default=45, ge=10, le=180)
    grace_minutes: int = Field(default=15, ge=0, le=120)

    @field_validator("scheduled_at")
    @classmethod
    def _tz(cls, v):
        if v.tzinfo is None:
            raise ValueError("scheduled_at needs a time zone, for example 2026-12-01T10:00:00+05:30")
        return v


class SubmitIn(BaseModel):
    answers: dict[str, str]
    signals: dict[str, Any] = {}

    @field_validator("answers")
    @classmethod
    def _len(cls, v):
        if len(v) > 20 or any(len(x) > 6000 for x in v.values()):
            raise ValueError("too many answers or an answer is too long")
        return v


class DemographicIn(BaseModel):
    group_label: str = Field(min_length=1, max_length=60)


class NotifyIn(BaseModel):
    kind: str

    @field_validator("kind")
    @classmethod
    def _k(cls, v):
        if v not in ("decision",):
            raise ValueError("kind must be decision")
        return v


class WebhookIn(BaseModel):
    job_id: int
    name: str
    email: EmailStr
    resume_text: str = Field(min_length=1, max_length=60000)
    consent: bool
    source: str = "webhook"


class AskIn(BaseModel):
    question: str = Field(min_length=4, max_length=300)

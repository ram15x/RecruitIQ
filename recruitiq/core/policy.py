"""What the software may do on its own for a job, and what it must hand to a person.

The split is deliberate:
  automatic   receiving, scoring, flagging, acknowledging, inviting strong clean matches to an interview, running the interview,
              reading the answers, ranking
  a person    every rejection, every acceptance after the interview, and anything flagged or borderline

An interview invitation is an offer a person can cancel, so it can be automatic. A rejection hurts someone and is the thing
the law watches (GDPR Article 22, the EU AI Act, NYC Local Law 144), so it is never automatic. The software only prepares a
batch of "suggested rejections" that a person confirms with one click and one reason.
"""
from dataclasses import asdict, dataclass


@dataclass
class Autopilot:
    acknowledge: bool = False              # email "we got your application" to everyone
    auto_invite_min: float | None = None   # strong, clean matches at or above this score are invited automatically. None = off
    interview_mode: str = "written"        # written | voice
    record_video: bool = False
    window_hours: int = 72                 # how long the invited candidate has to start the interview
    review_answers: bool = True            # have a model read submitted answers (only if a key is set)
    suggest_reject_below: float = 40.0     # clean applications under this go into the one-click "suggested rejections" batch
    suggest_accept_from: float = 70.0      # clean applications at or above this are suggested for acceptance when auto-invite is off

    @classmethod
    def from_dict(cls, d: dict | None) -> "Autopilot":
        d = d or {}
        base = cls()
        known = {k: d[k] for k in asdict(base) if k in d}
        p = cls(**{**asdict(base), **known})
        p.validate()
        return p

    def validate(self):
        if self.auto_invite_min is not None and not 50 <= self.auto_invite_min <= 100:
            raise ValueError("auto_invite_min must be between 50 and 100, or off")
        if self.interview_mode not in ("written", "voice"):
            raise ValueError("interview_mode must be written or voice")
        if not 1 <= self.window_hours <= 168:
            raise ValueError("window_hours must be between 1 and 168")
        if not 0 <= self.suggest_reject_below <= 60:
            raise ValueError("suggest_reject_below must be between 0 and 60")
        if not 50 <= self.suggest_accept_from <= 100:
            raise ValueError("suggest_accept_from must be between 50 and 100")
        if self.auto_invite_min is not None and self.auto_invite_min < self.suggest_reject_below:
            raise ValueError("auto_invite_min cannot be below the rejection suggestion line")
        self.record_video = bool(self.record_video and self.interview_mode == "voice")

    def as_dict(self) -> dict:
        return asdict(self)


def bucket(status: str, score: float, needs_review: bool, p: Autopilot) -> str | None:
    """Which "needs you" list an undecided application belongs in. None means nothing is needed from a person right now."""
    if status != "scored":
        return None
    if needs_review:
        return "flagged"
    if score < p.suggest_reject_below:
        return "suggested_rejections"
    if score >= p.suggest_accept_from:
        return "suggested_acceptances"
    return "borderline"

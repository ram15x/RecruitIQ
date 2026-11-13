"""Explainable resume scoring.

The score is a weighted sum of four parts, each of which is shown to the reviewer along with the evidence:

  required skills   0.45   credit per skill: evidenced in the work history 1.0, only in a skills list 0.4,
                           a closely related skill 0.35, absent 0.
  preferred skills  0.15   same credits.
  experience        0.20   observed years from date ranges against the minimum in the job spec.
  text similarity   0.20   TF-IDF cosine by default, or a dense model if one is plugged in.

The weights are choices, not something learned from hiring outcomes, and they are returned with every result.
No language model is involved, nothing here reads names or contact details (the text is masked first), and the
output is a ranking aid. It is never an accept or reject decision.
"""
from dataclasses import asdict, dataclass, field

from . import copied, injection, pii
from .experience import work_years
from .jobspec import JobSpec
from .similarity import Similarity, TfidfSimilarity
from .skills import Ontology, default_ontology

WEIGHTS = {"required": 0.45, "preferred": 0.15, "experience": 0.20, "similarity": 0.20}
CREDIT = {"evidenced": 1.0, "listed": 0.4, "related": 0.35, "missing": 0.0}
# a thin extraction usually means a scanned or image-only file, not a bad candidate, so say that instead of scoring it low
MIN_CHARS = 400


@dataclass
class SkillResult:
    skill: str
    status: str  # evidenced | listed | related | missing
    credit: float
    evidence: list = field(default_factory=list)
    via: str | None = None  # the related skill that counted, when status is "related"


@dataclass
class ScoreResult:
    score: float
    band: str
    components: dict
    weights: dict
    required: list
    preferred: list
    years: dict
    redactions: dict
    flags: list
    needs_review: bool
    notes: list
    similarity_method: str

    def as_dict(self):
        return asdict(self)


def band(score: float) -> str:
    # these cut points are for ordering a review queue. nothing is rejected on the basis of a band
    if score >= 70:
        return "strong match"
    if score >= 50:
        return "possible match"
    return "weak match"


class Scorer:
    def __init__(self, ontology: Ontology | None = None, similarity: Similarity | None = None, weights: dict | None = None):
        self.o = ontology or default_ontology()
        self.sim = similarity or TfidfSimilarity()
        self.w = weights or WEIGHTS

    def _skill(self, name: str, hits: dict) -> SkillResult:
        h = hits.get(name)
        if h:
            return SkillResult(name, h.level, CREDIT[h.level], h.evidence)
        for near in sorted(self.o.near.get(name, ())):
            if near in hits:
                return SkillResult(name, "related", CREDIT["related"], hits[near].evidence, via=near)
        return SkillResult(name, "missing", 0.0)

    def score(self, resume_text: str, job: JobSpec, candidate_names: list[str] | None = None, extra_flags: list | None = None) -> ScoreResult:
        masked = pii.mask(resume_text, candidate_names, replace=False)
        text, n_copied = copied.remove_copied(masked.text, job.description)
        notes = []
        hits = self.o.extract(text)
        flags = injection.scan(resume_text, hits) + list(extra_flags or [])
        if n_copied:
            flags.append(injection.Flag("copies_job_description", f"{n_copied} lines repeat the job description word for word and were not counted as the candidate's experience", "review"))

        req = [self._skill(s, hits) for s in job.required]
        pref = [self._skill(s, hits) for s in job.preferred]
        req_part = sum(r.credit for r in req) / len(req) if req else None
        pref_part = sum(r.credit for r in pref) / len(pref) if pref else None

        yrs = work_years(text)
        if job.min_years:
            exp_part = min(yrs["years"] / job.min_years, 1.0)
        else:
            exp_part = None
        sim_part = self.sim.score(text, job.description)

        # components that do not apply (no preferred skills listed, no years requirement) drop out and the remaining
        # weights are rescaled, so a job without them is not capped below 100
        parts = {"required": req_part, "preferred": pref_part, "experience": exp_part, "similarity": sim_part}
        active = {k: v for k, v in parts.items() if v is not None}
        total_w = sum(self.w[k] for k in active)
        final = 100.0 * sum(self.w[k] * v for k, v in active.items()) / total_w if total_w else 0.0

        thin = len(text.strip()) < MIN_CHARS
        if thin:
            notes.append("Very little text could be read from this file. It may be a scan or an image, so the score "
                         "is probably too low. Check the original.")
        if not req and not job.required:
            notes.append("The job has no required skills defined, so the score leans on text similarity only.")
        if yrs["stated"] and yrs["years"] and abs(yrs["stated"] - yrs["years"]) >= 3:
            notes.append(f"The resume says {yrs['stated']:g} years of experience, the dates add up to {yrs['years']:g}.")
        # most of the required skills appear only in a keyword list, with no work attached to them
        listed_only = [r for r in req if r.status == "listed"]
        if len(req) >= 3 and len(listed_only) / len(req) >= 0.75:
            flags.append(injection.Flag("skills_without_evidence",
                                        f"{len(listed_only)} of {len(req)} required skills appear only in a skills list, not in the work history",
                                        "review"))
        needs_review = bool(flags) or thin
        return ScoreResult(
            score=round(final, 1), band=band(final),
            components={k: (None if v is None else round(100 * v, 1)) for k, v in parts.items()},
            weights={k: round(self.w[k] / total_w, 3) for k in active} if total_w else {},
            required=[asdict(r) for r in req], preferred=[asdict(r) for r in pref],
            years=yrs, redactions=masked.redactions,
            flags=[asdict(f) for f in flags], needs_review=needs_review, notes=notes,
            similarity_method=self.sim.name)

    def rank(self, resumes: dict[str, str], job: JobSpec, names: dict[str, list[str]] | None = None):
        """Score a pool and order it. Ties and near-ties are broken by text similarity then required coverage."""
        results = {k: self.score(t, job, (names or {}).get(k)) for k, t in resumes.items()}
        order = sorted(results, key=lambda k: (-results[k].score, -(results[k].components["similarity"] or 0), k))
        return [(k, results[k]) for k in order]

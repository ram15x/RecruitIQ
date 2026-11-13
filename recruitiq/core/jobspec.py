import re
from dataclasses import dataclass, field

from .skills import Ontology, default_ontology

PREFERRED_MARK = re.compile(r"^\s*(?:preferred|nice[- ]to[- ]have|good to have|bonus|plus|desirable|optional)\b[^\n]*$", re.I | re.M)
REQUIRED_MARK = re.compile(r"^\s*(?:requirements?|required|must[- ]have|qualifications|what you(?:'ll)? need|responsibilities|skills)\b[^\n]*$", re.I | re.M)
YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.I)


@dataclass
class JobSpec:
    title: str
    description: str
    required: list[str] = field(default_factory=list)
    preferred: list[str] = field(default_factory=list)
    min_years: float | None = None

    @classmethod
    def from_text(cls, title: str, description: str, ontology: Ontology | None = None,
                  required: list[str] | None = None, preferred: list[str] | None = None,
                  min_years: float | None = None) -> "JobSpec":
        """Build a spec. HR can pass explicit lists (preferred, because it is their call). When they do not, we
        suggest them from the text: skills under a 'nice to have' style heading are preferred, the rest required."""
        o = ontology or default_ontology()

        def norm(lst):
            out = []
            for s in lst or []:
                c = o.canonical(s) or s.strip().lower()
                if c and c not in out:
                    out.append(c)
            return out

        if required is None and preferred is None:
            marks = sorted([(m.start(), "pref") for m in PREFERRED_MARK.finditer(description)] +
                           [(m.start(), "req") for m in REQUIRED_MARK.finditer(description)])
            req_text, pref_text, last, kind = [], [], 0, "req"
            for pos, k in marks:
                (pref_text if kind == "pref" else req_text).append(description[last:pos])
                last, kind = pos, k
            (pref_text if kind == "pref" else req_text).append(description[last:])
            req = list(o.extract("\n".join(req_text)))
            pref = [s for s in o.extract("\n".join(pref_text)) if s not in req]
            required, preferred = req, pref
        if min_years is None:
            ys = [int(y) for y in YEARS.findall(description)]
            min_years = float(min(ys)) if ys else None
        return cls(title, description, norm(required), [p for p in norm(preferred) if p not in norm(required)], min_years)

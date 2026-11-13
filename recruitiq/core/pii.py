"""Mask the things that should not influence a score before any scoring code sees the text.

This is rule based on purpose. It will not catch everything (a name nobody told us about, a hobby that hints at
age) so it is a reduction in exposure, not a guarantee. The fairness report in recruitiq/core/fairness.py is the
check on what is left.
"""
import re
from dataclasses import dataclass, field

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL = re.compile(r"(?:https?://|www\.)\S+|(?:linkedin|github|gitlab)\.com/\S+", re.I)
PHONE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,5}\)?[\s.-]?){2,4}\d{2,4}(?!\w)")
# lines like "Age: 27", "Date of birth: 04/05/1998", "Marital status: single", "Nationality: ..."
PERSONAL_LINE = re.compile(
    r"^\s*(?:age|date of birth|d\.?o\.?b\.?|birth ?date|marital status|gender|sex|nationality|religion|caste|"
    r"father'?s? name|mother'?s? name|passport(?: no\.?)?|visa status)\s*[:\-].*$", re.I | re.M)
TITLES = re.compile(r"\b(?:mr|mrs|ms|miss|mx|shri|smt|kumari)\.?\s+(?=(?-i:[A-Z]))", re.I)
PRONOUNS = {
    r"\bhe\b": "they", r"\bshe\b": "they", r"\bhim\b": "them", r"\bhis\b": "their",
    r"\bher\b": "their", r"\bhers\b": "theirs", r"\bherself\b": "themselves", r"\bhimself\b": "themselves",
}
# a year range of graduation is fine, a bare "born in 1995" is not
BORN = re.compile(r"\bborn (?:in|on)?\s*[\w\s,/-]{0,20}\d{4}", re.I)


@dataclass
class Masked:
    text: str
    redactions: dict = field(default_factory=dict)

    @property
    def total(self):
        return sum(self.redactions.values())


def _sub(pattern, repl, text, key, counts, flags=0):
    new, n = re.subn(pattern, repl, text, flags=flags) if isinstance(pattern, str) else pattern.subn(repl, text)
    if n:
        counts[key] = counts.get(key, 0) + n
    return new


def mask(text: str, names: list[str] | None = None, replace: bool = True) -> Masked:
    """Return the text with contact details, personal-status lines, titles, gendered pronouns and the candidate's
    own name replaced by neutral tokens. `names` are the names we know belong to the candidate."""
    # replace=False removes the masked parts entirely instead of leaving a placeholder. the scorer uses that, because a
    # placeholder is still text, and its length or count could leak into a similarity number
    tag = (lambda t: t) if replace else (lambda t: "")
    counts: dict = {}
    out = text or ""
    out = _sub(EMAIL, tag("[email]"), out, "email", counts)
    out = _sub(URL, tag("[link]"), out, "link", counts)
    out = _sub(PERSONAL_LINE, tag("[personal detail removed]"), out, "personal_line", counts)
    out = _sub(BORN, tag("[personal detail removed]"), out, "personal_line", counts)
    out = _sub(TITLES, "", out, "title", counts)
    from .skills import default_ontology
    known = {a for spec in default_ontology().skills.values() for a in spec["aliases"]}
    for name in names or []:
        # a name part that is also a skill word (someone called Chef, or "Docker Jones" as a joke name) is removed only
        # as part of the whole name, so it cannot delete a real skill from the work history
        for part in {name.strip(), *[p for p in name.split() if len(p) > 2 and p.lower() not in known]}:
            if part:
                out = _sub(re.compile(re.escape(part), re.I), tag("[candidate]"), out, "name", counts)
    for pat, repl in PRONOUNS.items():
        out = _sub(re.compile(pat, re.I), repl, out, "pronoun", counts)
    # phones last, after links and emails are gone, so we do not eat digits inside them
    hits = []

    def _phone(m):
        raw = m.group().strip()
        digits = re.sub(r"\D", "", raw)
        # year ranges (2019-2023) and plain numbers are not phones. a phone has a + or at least 10 digits
        if re.fullmatch(r"(?:19|20)\d{2}\s*[-/]\s*(?:(?:19|20)\d{2}|\d{2})", raw):
            return m.group()
        if (raw.startswith("+") and 8 <= len(digits) <= 15) or 10 <= len(digits) <= 15:
            hits.append(1)
            return tag("[phone]")
        return m.group()

    new = PHONE.sub(_phone, out)
    if hits:
        counts["phone"] = counts.get("phone", 0) + len(hits)
    new = re.sub(r"(\[candidate\])(?:\s+\[candidate\])+", r"\1", new)
    new = re.sub(r"[ \t]+\n", "\n", new)
    return Masked(new, counts)

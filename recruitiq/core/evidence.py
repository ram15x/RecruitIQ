"""Search inside resumes and return the lines that match, word for word.

This is retrieval without generation on purpose. Nothing is summarised or rewritten, so the answer to "who has Kafka work
in their history" is a list of real lines from real resumes, and anything the resume does not say simply does not come back.
A query that names a skill we know also matches that skill's other spellings (k8s finds kubernetes).
"""
import re
from dataclasses import dataclass

from .skills import Ontology, _alias_regex, default_ontology

STOP = {"the", "a", "an", "of", "in", "on", "for", "and", "or", "to", "with", "has", "have", "had", "who", "any", "is", "are", "at", "by"}


@dataclass
class Line:
    text: str
    matched: list
    in_skills_list: bool


def _lines(text: str) -> list[tuple[str, bool]]:
    """Resume lines and sentences, each flagged with whether it sits in a skills section (so it is only a keyword list)."""
    out, in_skills = [], False
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        head = s.lower().rstrip(":")
        if len(s) < 40 and re.fullmatch(r"[a-z &/]+", head):
            in_skills = head in ("skills", "technical skills", "core skills", "key skills", "tools", "technologies")
            continue
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z])", s):
            if len(sent) >= 8:
                out.append((sent.strip(), in_skills))
    return out


def terms(query: str, o: Ontology | None = None) -> list[list[str]]:
    """Each inner list is one thing the user asked for, with its alternative spellings. A line must match every group."""
    o = o or default_ontology()
    q = query.strip().lower()
    groups, used = [], set()
    # whole known phrases first, so "machine learning" is one term and not two
    for name, spec in o.skills.items():
        for a in spec["aliases"]:
            if len(a) > 1 and _alias_regex(a).search(q) and a not in used:
                groups.append(spec["aliases"])
                used.update(spec["aliases"])
                q = _alias_regex(a).sub(" ", q)
                break
    for w in re.findall(r"[a-z0-9][a-z0-9+#.\-]{1,}", q):
        if w not in STOP and w not in used:
            groups.append([w])
    return groups


def search(query: str, text: str, o: Ontology | None = None, limit: int = 3) -> list[Line]:
    groups = terms(query, o)
    if not groups:
        return []
    rx = [[_alias_regex(a) for a in g] for g in groups]
    found = []
    for line, in_skills in _lines(text):
        hit = []
        for g, alts in zip(groups, rx):
            m = next((a for a, r in zip(g, alts) if r.search(line)), None)
            if m is None:
                break
            hit.append(m)
        else:
            found.append(Line(line, hit, in_skills))
    # lines in the work history first, then the ones that are only keyword lists
    found.sort(key=lambda L: (L.in_skills_list, -len(L.text) // 40))
    return found[:limit]

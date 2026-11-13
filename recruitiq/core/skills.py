import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parents[2] / "data" / "skills.yaml"

# words that appear in a "skills" block heading, so we can tell a list of skills from a description of work
SKILL_HEADINGS = re.compile(r"^\s*(?:technical |key |core )?(?:skills?|technologies|tech stack|tools|competenc(?:y|ies))\b[^\n]*$", re.I | re.M)
OTHER_HEADINGS = re.compile(r"^\s*(?:experience|work experience|professional experience|employment|projects?|education|"
                            r"certifications?|achievements|summary|profile|objective|publications|awards)\b[^\n]*$", re.I | re.M)


def _alias_regex(alias: str) -> re.Pattern:
    # whole-word match that also works for c++, c#, .net, node.js, ci/cd. \b does not work next to + # . so we
    # use explicit look-around on "word-ish" characters instead
    return re.compile(r"(?<![\w+#.])" + re.escape(alias) + r"(?![\w+#]|\.\w)", re.I)


@dataclass
class SkillHit:
    skill: str
    group: str
    in_skills_list: bool = False
    in_experience: bool = False
    mentions: int = 0
    evidence: list = field(default_factory=list)  # short sentences from the experience part of the resume

    @property
    def level(self) -> str:
        # "evidenced" means it shows up where work is described, not only in a list of keywords
        return "evidenced" if self.in_experience else "listed"


class Ontology:
    def __init__(self, raw: dict):
        self.skills = {}
        self._rx = []
        for name, spec in raw.items():
            aliases = {name.lower(), *[str(a).lower() for a in spec.get("aliases", [])]}
            self.skills[name] = {"group": spec.get("group", "other"), "aliases": sorted(aliases), "related": list(spec.get("related", []))}
            for a in aliases:
                self._rx.append((name, _alias_regex(a)))
        # a related edge should work both ways: if python lists r as related, someone with r is near python
        self.near = {k: set(v["related"]) for k, v in self.skills.items()}
        for k, v in self.skills.items():
            for r in v["related"]:
                if r in self.near:
                    self.near[r].add(k)

    def canonical(self, text: str) -> str | None:
        """Map one phrase (a requirement typed by HR) to a canonical skill name, if it is one we know."""
        t = text.strip().lower()
        for name, rx in self._rx:
            if rx.fullmatch(t) or t == name:
                return name
        return None

    def split_sections(self, text: str):
        """Return (skills_block_text, rest_text). Skills blocks are the headed lists of keywords."""
        marks = sorted([(m.start(), m.end(), "skills") for m in SKILL_HEADINGS.finditer(text)] +
                       [(m.start(), m.end(), "other") for m in OTHER_HEADINGS.finditer(text)])
        skills_parts, rest_parts, last_end, kind = [], [], 0, "other"
        for start, end, k in marks:
            (skills_parts if kind == "skills" else rest_parts).append(text[last_end:start])
            last_end, kind = end, k
        (skills_parts if kind == "skills" else rest_parts).append(text[last_end:])
        return "\n".join(skills_parts), "\n".join(rest_parts)

    def extract(self, text: str, max_evidence: int = 2) -> dict[str, SkillHit]:
        skills_block, rest = self.split_sections(text)
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", rest) if len(s.strip()) > 25]
        hits: dict[str, SkillHit] = {}
        for name, rx in self._rx:
            n_skills = len(rx.findall(skills_block))
            n_rest = len(rx.findall(rest))
            if not n_skills and not n_rest:
                continue
            h = hits.setdefault(name, SkillHit(name, self.skills[name]["group"]))
            h.in_skills_list = h.in_skills_list or n_skills > 0
            h.in_experience = h.in_experience or n_rest > 0
            h.mentions += n_skills + n_rest
            if n_rest:
                for s in sentences:
                    if rx.search(s) and s not in h.evidence and len(h.evidence) < max_evidence:
                        h.evidence.append(s[:220])
        return hits


@lru_cache(maxsize=1)
def default_ontology() -> Ontology:
    return Ontology(yaml.safe_load(DATA.read_text(encoding="utf-8")))

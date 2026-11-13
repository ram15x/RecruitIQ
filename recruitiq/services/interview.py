"""Interview questions and a light analysis of the answers.

Nothing here scores a person. The analysis returns facts about each answer (how long, how specific, which skills
it touched) and the raw behaviour signals the portal recorded, and a reviewer reads them next to the answers.
There is deliberately no "AI-written" detector and no integrity score: those guess, and a wrong guess about a real
person is expensive. A paste count or a tab switch can have an ordinary explanation.
"""
import re

from ..core.skills import default_ontology

GENERAL = {
    "programming": ["Walk me through a system you built end to end. What did you decide, and what would you change now?",
                    "Tell me about a bug that was hard to find. How did you narrow it down?"],
    "data": ["Describe a time the data was not what you expected. What did you do about it?",
             "How do you decide a model or analysis is good enough to share?"],
    "ml": ["Describe a model you took from idea to something people used. Where did it go wrong?",
           "How do you check that a result is real and not an artefact of how you split or cleaned the data?"],
    "web": ["Tell me about a feature you shipped that users actually noticed. How did you build and test it?"],
    "devops": ["Tell me about an outage you were involved in. What changed afterwards?"],
    "cloud": ["Describe how you would deploy and monitor a small service you wrote. What would worry you first?"],
    "clinical": ["Describe a patient situation that changed quickly. What did you do first, and who did you involve?",
                 "How do you make sure documentation stays accurate when the ward is busy?"],
    "default": ["Describe the most challenging piece of work you did in the last two years and your part in it.",
                "Tell me about a time you disagreed with a colleague. How did it end?"],
}
SKILL_Q = "You list {skill}. Tell me about one specific piece of work where you used it: what the problem was, what you did yourself, and how you knew it worked."
CLOSING = "Is there anything in your application you would like to add or correct?"


def build_questions(job_title: str, evidenced_skills: list[str], required: list[str], groups: dict[str, str]) -> list[dict]:
    """Two questions from the groups of skills the job needs, up to two about skills the candidate evidenced (so the
    conversation is about their real work), and an open closing question."""
    seen, qs = [], []
    for s in required:
        g = groups.get(s, "default")
        if g not in seen:
            seen.append(g)
    for g in seen[:2] or ["default"]:
        for q in GENERAL.get(g, GENERAL["default"])[:1]:
            qs.append({"category": "role", "text": q})
    if len(qs) < 2:
        qs.append({"category": "role", "text": GENERAL["default"][1]})
    wanted = [s for s in evidenced_skills if s in required] or evidenced_skills
    for s in wanted[:2]:
        qs.append({"category": "your work", "text": SKILL_Q.format(skill=s), "skill": s})
    qs.append({"category": "closing", "text": CLOSING})
    for i, q in enumerate(qs, 1):
        q["id"] = i
    return qs


NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|x|ms|s|k|m|users|requests|hours|days|weeks|months|years|patients|engineers)?\b")
OWNERSHIP = re.compile(r"\b(?:i|my|me)\b", re.I)
REASONING = re.compile(r"\b(?:because|so that|therefore|as a result|which meant|trade-?off|instead of|decided|chose|learned|measured)\b", re.I)


def analyse(questions: list[dict], answers: dict, signals: dict | None = None) -> dict:
    o = default_ontology()
    per = []
    for q in questions:
        a = (answers.get(str(q["id"])) or answers.get(q["id"]) or "").strip()
        words = len(a.split())
        skills = sorted(o.extract(a))
        per.append({
            "question_id": q["id"], "words": words, "mentions_numbers": bool(NUMBER.search(a)),
            "uses_first_person": bool(OWNERSHIP.search(a)), "gives_reasons": len(REASONING.findall(a)),
            "skills_mentioned": skills, "empty": words == 0,
        })
    sig = signals or {}
    note = ("Tab switches, pastes and timings are recorded as they happened. They are not evidence of misconduct on their own: "
            "people check a note, copy their own text from a draft, or lose focus to a notification.")
    return {"answers": per, "signals": {k: sig.get(k) for k in ("tab_switches", "paste_events", "seconds_total") if k in sig}, "note": note}

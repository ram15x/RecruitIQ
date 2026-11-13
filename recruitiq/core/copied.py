"""Lines in a resume that are copied from the job description.

A job description says what the employer wants. Pasting it into a resume (often in white text) makes every required skill
look as if the candidate has done it. A line that repeats the job text word for word cannot be evidence about the candidate,
so it is left out before skills are read, and a person is told.
"""
import re

N = 4
SHARE = 0.6


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.]+", s.lower())


def _grams(words: list[str]) -> set:
    return {tuple(words[i:i + N]) for i in range(len(words) - N + 1)}


def remove_copied(resume: str, job_description: str) -> tuple[str, int]:
    """Returns the resume without lines taken from the job text, and how many lines were dropped."""
    jd = _grams(_words(job_description))
    if not jd:
        return resume, 0
    kept, dropped = [], 0
    for line in resume.splitlines():
        parts = [p for p in re.split(r"(?<=[.!?])\s+", line) if p.strip()] or [line]
        keep_parts = []
        for part in parts:
            g = _grams(_words(part))
            if g and len(g & jd) / len(g) >= SHARE:
                dropped += 1
            else:
                keep_parts.append(part)
        kept.append(" ".join(keep_parts))
    return "\n".join(kept), dropped

import datetime as dt
import re

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
RANGE = re.compile(
    r"(?:(?P<m1>[A-Za-z]{3,9})\.?\s+)?(?P<y1>(?:19|20)\d{2})\s*(?:-|–|—|to)\s*"
    r"(?:(?:(?P<m2>[A-Za-z]{3,9})\.?\s+)?(?P<y2>(?:19|20)\d{2})|(?P<now>present|current|now|till date|ongoing))", re.I)
STATED = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\b(?:\s+of)?\s+(?:professional\s+|relevant\s+|work\s+)?(?:experience|exp)", re.I)
EDU_WORDS = re.compile(r"\b(?:b\.?tech|b\.?e\.?|b\.?sc|m\.?tech|m\.?sc|mba|bachelor|master|ph\.?d|diploma|degree|university|college|school)\b", re.I)


def _month(s):
    return MONTHS.get((s or "")[:3].lower(), 1)


def work_years(text: str, today: dt.date | None = None) -> dict:
    """Estimate years of experience from date ranges, merging overlaps, skipping ranges on education lines.

    Returns {"years": float, "ranges": [(start, end)], "stated": float|None}. The date-range figure is what we
    can see in the document, the "stated" figure is what the candidate claims ("5 years of experience") and is
    reported but not used for scoring, because it is a claim.
    """
    today = today or dt.date.today()
    spans = []
    for line in text.splitlines():
        if EDU_WORDS.search(line) and not re.search(r"\b(?:intern|engineer|developer|analyst|nurse|manager|scientist|consultant)\b", line, re.I):
            continue
        for m in RANGE.finditer(line):
            y1 = int(m.group("y1"))
            a = dt.date(y1, _month(m.group("m1")), 1)
            if m.group("now"):
                b = today
            else:
                b = dt.date(int(m.group("y2")), _month(m.group("m2")) if m.group("m2") else 12, 1)
            if a <= b <= today + dt.timedelta(days=31):
                spans.append((a, min(b, today)))
    spans.sort()
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    years = sum((b - a).days for a, b in merged) / 365.25
    stated = [float(x) for x in STATED.findall(text)]
    return {"years": round(years, 1), "ranges": [(a.isoformat(), b.isoformat()) for a, b in merged],
            "stated": max(stated) if stated else None}

import datetime as dt
import re

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
# one date: "Jan 2021", "Jun '17", "01/2020", "2021". Two-digit years after an apostrophe are read as 20xx
_D = r"(?:(?:[A-Za-z]{3,9})\.?,?\s*(?:(?:19|20)\d{2}|'\d{2})|\d{1,2}[/.\-](?:19|20)\d{2}|(?:19|20)\d{2})"
RANGE = re.compile(r"(?P<a>" + _D + r")\s*(?:-|–|—|to)\s*(?:(?P<b>" + _D + r")|(?P<now>present|current|now|till date|ongoing))", re.I)
STATED = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\b(?:\s+of)?\s+(?:professional\s+|relevant\s+|work\s+)?(?:experience|exp)", re.I)
EDU_WORDS = re.compile(r"\b(?:b\.?tech|b\.?e\.?|b\.?sc|m\.?tech|m\.?sc|mba|bachelor|master|ph\.?d|diploma|degree|university|college|school)\b", re.I)


def _parse(d: str, end: bool):
    """Turn one date string into a date. A bare year means January at the start of a range and December at the end."""
    d = d.strip()
    m = re.fullmatch(r"(\d{1,2})[/.\-]((?:19|20)\d{2})", d)
    if m:
        mo, y = int(m.group(1)), int(m.group(2))
        return dt.date(y, mo, 1) if 1 <= mo <= 12 else None
    m = re.fullmatch(r"([A-Za-z]{3,9})\.?,?\s*(?:((?:19|20)\d{2})|'(\d{2}))", d)
    if m:
        mo = MONTHS.get(m.group(1)[:3].lower())
        y = int(m.group(2)) if m.group(2) else 2000 + int(m.group(3))
        return dt.date(y, mo, 1) if mo else None
    if re.fullmatch(r"(?:19|20)\d{2}", d):
        return dt.date(int(d), 12 if end else 1, 1)
    return None


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
            a = _parse(m.group("a"), end=False)
            b = today if m.group("now") else _parse(m.group("b"), end=True)
            if a and b and a <= b <= today + dt.timedelta(days=31):
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

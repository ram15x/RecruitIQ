"""What would move a score, worked out from a stored result.

The score is a weighted average, so the effect of one skill changing from "missing" to "shown in the work history" is exact
arithmetic, not an estimate. This is for the reviewer ("this person is close, and one thing holds them back"), not for the
candidate to game.
"""
CREDIT_EVIDENCED = 1.0


def score_gaps(result: dict, min_years: float | None = None) -> list[dict]:
    w = result["weights"]
    out = []
    for key in ("required", "preferred"):
        rows = result.get(key) or []
        if key not in w or not rows:
            continue
        per = 100.0 * w[key] / len(rows)
        for r in rows:
            if r["status"] == "evidenced":
                continue
            out.append({"kind": key, "skill": r["skill"], "status": r["status"],
                        "gain": round(per * (CREDIT_EVIDENCED - r["credit"]), 1)})
    exp = result["components"].get("experience")
    if "experience" in w and exp is not None and exp < 100:
        out.append({"kind": "experience", "skill": "years of experience", "status": f"{result['years']['years']:g} years in dated roles",
                    "gain": round(w["experience"] * (100 - exp), 1)})
    return sorted(out, key=lambda g: -g["gain"])


def compare(a: dict, b: dict) -> dict:
    """Line up two stored results skill by skill."""
    def table(res, key):
        return {r["skill"]: r["status"] for r in res.get(key, [])}
    rows = []
    for key in ("required", "preferred"):
        ta, tb = table(a, key), table(b, key)
        for s in list(ta) + [s for s in tb if s not in ta]:
            rows.append({"kind": key, "skill": s, "a": ta.get(s, "n/a"), "b": tb.get(s, "n/a")})
    return {"skills": rows, "components": {k: {"a": a["components"].get(k), "b": b["components"].get(k)} for k in a["components"]},
            "years": {"a": a["years"]["years"], "b": b["years"]["years"]}}

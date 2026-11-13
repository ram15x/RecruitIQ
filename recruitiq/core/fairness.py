"""Selection-rate comparison across voluntary self-reported groups (the "four-fifths" screen).

A ratio under 0.8 against the group with the highest selection rate is a prompt to look closer, not a finding of
bias, and a ratio over 0.8 is not a clean bill of health. With small groups the numbers jump around, so groups under
`min_group` are reported but never flagged, and a Fisher exact p-value is shown next to each ratio.
"""
from math import comb


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """2x2 table [[a, b], [c, d]], exact two-sided p-value."""
    r1, r2, c1, n = a + b, c + d, a + c, a + b + c + d
    if n == 0:
        return 1.0
    denom = comb(n, c1)

    def p(x):
        return comb(r1, x) * comb(r2, c1 - x) / denom

    p_obs = p(a)
    lo, hi = max(0, c1 - r2), min(r1, c1)
    return min(1.0, sum(p(x) for x in range(lo, hi + 1) if p(x) <= p_obs + 1e-12))


def impact_report(rows: list[tuple[str, bool]], min_group: int = 10, threshold: float = 0.8) -> dict:
    """rows: (group_label, was_selected). Returns per-group rates and impact ratios against the highest-rate group."""
    groups: dict[str, list[int]] = {}
    for g, sel in rows:
        n_sel = groups.setdefault(g, [0, 0])
        n_sel[0] += 1
        n_sel[1] += 1 if sel else 0
    out = {g: {"applicants": n, "selected": s, "rate": (s / n if n else 0.0)} for g, (n, s) in groups.items()}
    usable = {g: v for g, v in out.items() if v["applicants"] >= min_group}
    top_group = max(usable, key=lambda g: usable[g]["rate"]) if usable else None
    top_rate = usable[top_group]["rate"] if top_group else 0.0
    flagged = []
    for g, v in out.items():
        small = v["applicants"] < min_group
        v["too_small_to_judge"] = small
        if top_group and top_rate > 0:
            v["ratio_to_top"] = round(v["rate"] / top_rate, 3)
        else:
            v["ratio_to_top"] = None
        if top_group and g != top_group and v["ratio_to_top"] is not None:
            t = out[top_group]
            v["fisher_p"] = round(fisher_two_sided(v["selected"], v["applicants"] - v["selected"],
                                                   t["selected"], t["applicants"] - t["selected"]), 4)
            if not small and v["ratio_to_top"] < threshold:
                flagged.append(g)
    warnings = []
    if not usable:
        warnings.append(f"No group has {min_group} or more applicants yet, so nothing can be judged.")
    if len(out) < 2:
        warnings.append("Only one group reported, nothing to compare.")
    return {"groups": out, "reference_group": top_group, "flagged": flagged, "threshold": threshold,
            "min_group": min_group, "warnings": warnings}

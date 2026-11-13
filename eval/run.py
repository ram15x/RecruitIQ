import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval import baselines, synth  # noqa: E402
from recruitiq.core.jobspec import JobSpec  # noqa: E402
from recruitiq.core.scoring import Scorer  # noqa: E402
from recruitiq.core.similarity import TfidfSimilarity  # noqa: E402
from recruitiq.core.skills import default_ontology  # noqa: E402

SEEDS = range(1, 21)
O = default_ontology()
SC = Scorer()
TF = TfidfSimilarity()


def ndcg(ranked_grades):
    dcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ranked_grades))
    ideal = sorted(ranked_grades, reverse=True)
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 1.0


def methods(role, job):
    jd = synth.ROLES[role]["jd"]
    jd_skills = job.required + job.preferred

    def legacy(text, names):
        rs = list(O.extract(text))
        return baselines.legacy_score(text, jd, rs, jd_skills)

    def tfidf_only(text, names):
        return 100 * TF.score(text, jd)

    def skills_presence(text, names):
        hits = O.extract(text)
        want = job.required + job.preferred
        return 100 * sum(1 for s in want if s in hits) / len(want)

    def new(text, names):
        return SC.score(text, job, names).score

    return {"legacy (v1 recipe)": legacy, "tf-idf only": tfidf_only, "skill keywords only": skills_presence, "new scorer": new}


def main():
    names_m = ["legacy (v1 recipe)", "tf-idf only", "skill keywords only", "new scorer"]
    agg = {m: {"ndcg": [], "pair": [], "bad_above_good": [], "top1_good": [], "per_kind": {}} for m in names_m}
    for role, r in synth.ROLES.items():
        job = JobSpec.from_text(r["title"], r["jd"])
        assert job.required == [O.canonical(s) or s for s in r["required"]] or set(job.required) >= set(r["required"]), (role, job.required)
        fns = methods(role, job)
        for seed in SEEDS:
            pool = synth.pool(role, seed)
            for m in names_m:
                scores = {k: fns[m](text, [name]) for k, (kind, text, name) in pool.items()}
                order = sorted(pool, key=lambda k: -scores[k])
                grades = [synth.GRADE[pool[k][0]] for k in order]
                a = agg[m]
                a["ndcg"].append(ndcg(grades))
                pairs = [(g1, g2) for i, g1 in enumerate(grades) for g2 in grades[i + 1:] if g1 != g2]
                a["pair"].append(sum(1 for g1, g2 in pairs if g1 > g2) / len(pairs))
                # does a keyword-stuffed or injected resume sit above a genuinely strong one?
                bad = [scores[k] for k in pool if pool[k][0] in ("stuffed", "injected")]
                good = [scores[k] for k in pool if pool[k][0] in ("strong", "paraphrased")]
                a["bad_above_good"].append(1.0 if max(bad) >= min(good) else 0.0)
                a["top1_good"].append(1.0 if pool[order[0]][0] in ("strong", "paraphrased", "hard_paraphrase") else 0.0)
                for k, (kind, _, _) in pool.items():
                    a["per_kind"].setdefault(kind, []).append(scores[k])
    out = {}
    for m, a in agg.items():
        out[m] = {"ndcg": statistics.mean(a["ndcg"]), "pairwise_order": statistics.mean(a["pair"]),
                  "stuffed_or_injected_beats_a_strong_resume": statistics.mean(a["bad_above_good"]),
                  "top_ranked_is_a_good_fit": statistics.mean(a["top1_good"]),
                  "mean_score_by_kind": {k: round(statistics.mean(v), 1) for k, v in a["per_kind"].items()}}
    n = len(list(synth.ROLES)) * len(SEEDS)

    # counterfactual: same resume, different name, pronouns and an added personal-details block
    from eval.synth import NAMES
    deltas = {m: [] for m in names_m}
    for role, r in synth.ROLES.items():
        job = JobSpec.from_text(r["title"], r["jd"])
        fns = methods(role, job)
        for seed in range(1, 6):
            for k, (kind, text, name) in synth.pool(role, seed).items():
                alt_name = next(n_ for n_, _ in NAMES if n_ != name)
                swapped = text.replace(name, alt_name).replace(name.split()[0].lower(), alt_name.split()[0].lower())
                swapped = swapped.replace(" She ", " He ").replace(" her ", " his ").replace(" He ", " She ") if " She " in text else swapped.replace(" He ", " She ").replace(" his ", " her ")
                swapped = "Age: 47\nMarital status: married\nNationality: Indian\n" + swapped
                for m in names_m:
                    deltas[m].append(abs(fns[m](text, [name]) - fns[m](swapped, [alt_name])))
    cf = {m: {"mean_abs_change": round(statistics.mean(d), 3), "max_abs_change": round(max(d), 3),
              "share_changed": round(sum(1 for x in d if x > 1e-9) / len(d), 3)} for m, d in deltas.items()}
    res = {"pools": n, "resumes_per_pool": 10, "methods": out, "counterfactual_name_pronoun_personal_details": cf,
           "legacy_rrf_term_constant": baselines.legacy_rrf_single_document()}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "benchmark.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()

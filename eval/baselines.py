"""The scoring recipe from the first version of RecruitIQ, ported so it can be compared on the same data.

Two honest notes. The first version asked an LLM to pull skills out of the resume and the job description. There is
no model here, so the skill lists are taken from the new ontology extractor instead, which is kinder to the old
method than the real thing was. And the "RRF" term is reproduced exactly as it was: fused over a single document.
"""
from rapidfuzz import fuzz

LEGACY_GRAPH = {
    "python": ["python3", "python programming", "numpy", "pandas", "scikit-learn"],
    "machine learning": ["ml", "deep learning", "neural networks", "cnn", "rnn", "llm", "genai"],
    "data science": ["data analytics", "data mining", "analytics", "business intelligence"],
    "sql": ["postgresql", "mysql", "database", "nosql", "mongodb"],
    "aws": ["amazon web services", "ec2", "s3", "lambda", "cloud computing"],
    "docker": ["container", "kubernetes", "k8s", "devops"],
    "react": ["reactjs", "nextjs", "frontend", "javascript"],
    "fastapi": ["fast api", "python api", "rest api"],
    "tensorflow": ["tf", "keras", "pytorch", "deep learning framework"],
}


def _norm(skill):
    s = skill.lower().strip()
    for canon, variants in LEGACY_GRAPH.items():
        if s == canon or s in variants:
            return canon
        for v in variants:
            if fuzz.ratio(s, v) > 85:
                return canon
    return s


def legacy_match_rate(resume_skills, jd_skills):
    r = [_norm(s) for s in resume_skills]
    j = [_norm(s) for s in jd_skills]
    return sum(1 for s in j if s in r) / len(j) if j else 0


def legacy_rrf_single_document(k=60):
    # the old code ranked ONE resume against itself in a dense list and a sparse list, then fused them
    scores = {}
    for ranking in ([(0, 1.0)], [(0, 1.0)]):
        for rank, (item, _) in enumerate(ranking):
            scores[item] = scores.get(item, 0) + 1 / (k + rank + 1)
    return list(scores.values())[0]


def jaccard(a, b):
    w1, w2 = set(a.lower().split()), set(b.lower().split())
    if not w1 or not w2:
        return 0.5
    return len(w1 & w2) / len(w1 | w2)


def legacy_score(resume_text, jd_text, resume_skills, jd_skills):
    rrf = legacy_rrf_single_document()
    skill = legacy_match_rate(resume_skills, jd_skills)
    sem = jaccard(resume_text[:2000], jd_text[:2000])
    return (rrf * 0.4 + skill * 0.4 + sem * 0.2) * 100

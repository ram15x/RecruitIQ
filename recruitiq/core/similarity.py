"""Text similarity between a resume and a job description.

Default is TF-IDF cosine, which needs nothing downloaded. If the sentence-transformers extra is installed, a dense
model can be plugged in. Both sit behind the same two-method interface so the scorer does not care which one it got.
"""
import math
import re
from collections import Counter
from typing import Protocol

TOKEN = re.compile(r"[a-z][a-z0-9+#.]*[a-z0-9+#]|[a-z]", re.I)
STOP = set("""a an and are as at be by for from has have in is it its of on or that the this to was were will with
you your we our they their their i my me not but also can may more most other such than then there these those
into over under per via using used use work worked working team teams experience years year strong good great
responsible responsibilities required requirements preferred ability able""".split())


def tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN.findall(text) if t.lower() not in STOP and len(t) > 1]


class Similarity(Protocol):
    name: str

    def score(self, resume: str, jd: str) -> float: ...


class TfidfSimilarity:
    name = "tfidf"

    def score(self, resume: str, jd: str) -> float:
        a, b = Counter(tokens(resume)), Counter(tokens(jd))
        if not a or not b:
            return 0.0
        vocab = set(a) | set(b)
        # with only two documents an idf term would be mostly noise, so use sublinear term frequency only
        va = {w: 1 + math.log(a[w]) for w in a}
        vb = {w: 1 + math.log(b[w]) for w in b}
        dot = sum(va[w] * vb[w] for w in vocab if w in va and w in vb)
        na = math.sqrt(sum(v * v for v in va.values()))
        nb = math.sqrt(sum(v * v for v in vb.values()))
        return dot / (na * nb) if na and nb else 0.0


class DenseSimilarity:
    """Wraps a sentence-transformers model. Install with: pip install 'recruitiq[dense]'. Not exercised by the
    benchmark in this repo because the model has to be downloaded; see README for how to run it yourself."""
    name = "dense"

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        self.name = f"dense:{model_name}"

    def score(self, resume: str, jd: str) -> float:
        e = self.model.encode([resume[:6000], jd[:6000]], normalize_embeddings=True)
        return float(max(0.0, min(1.0, (e[0] * e[1]).sum())))


def rrf(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal rank fusion over several ranked lists of ids. Only meaningful for ordering a pool of candidates,
    never as an absolute score: for a single document it always returns the same number whatever the document is."""
    out: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            out[item] = out.get(item, 0.0) + 1.0 / (k + rank + 1)
    return out

"""Lightweight BM25 retrieval over lending-policy clauses (swap for Qdrant hybrid search later)."""
from __future__ import annotations

import math
import re
from collections import Counter

from .schemas import PolicyHit
from .synthetic import POLICY_CLAUSES

_TOKEN = re.compile(r"[a-z0-9]+")


def _tok(s: str) -> list[str]:
    return _TOKEN.findall(s.lower())


class PolicyIndex:
    def __init__(self, clauses: list[dict] | None = None, k1: float = 1.5, b: float = 0.75) -> None:
        self.clauses = clauses or POLICY_CLAUSES
        self.k1, self.b = k1, b
        self.docs = [_tok(c["title"] + " " + c["text"]) for c in self.clauses]
        self.avgdl = sum(len(d) for d in self.docs) / len(self.docs)
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 3) -> list[PolicyHit]:
        q = _tok(query)
        scored = []
        for clause, doc in zip(self.clauses, self.docs):
            tf = Counter(doc)
            s = 0.0
            for t in q:
                if t not in tf:
                    continue
                s += self.idf.get(t, 0) * tf[t] * (self.k1 + 1) / (
                    tf[t] + self.k1 * (1 - self.b + self.b * len(doc) / self.avgdl))
            if s > 0:
                scored.append(PolicyHit(clause_id=clause["id"], title=clause["title"],
                                        text=clause["text"], score=round(s, 4)))
        return sorted(scored, key=lambda h: h.score, reverse=True)[:k]

    def get(self, clause_id: str) -> PolicyHit | None:
        for c in self.clauses:
            if c["id"] == clause_id:
                return PolicyHit(clause_id=c["id"], title=c["title"], text=c["text"], score=1.0)
        return None

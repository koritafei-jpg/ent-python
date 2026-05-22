"""混合检索的倒数排名融合（RRF）。"""

from __future__ import annotations

from entpy.search.backends.base import ScoredHit


def reciprocal_rank_fusion(
    *result_lists: list[ScoredHit],
    k: int = 60,
) -> list[ScoredHit]:
    scores: dict = {}
    meta: dict = {}
    for results in result_lists:
        for rank, hit in enumerate(results, start=1):
            scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (k + rank)
            if hit.id not in meta:
                meta[hit.id] = hit
    ordered = sorted(scores.items(), key=lambda x: -x[1])
    return [
        ScoredHit(id=doc_id, score=score, source="hybrid", text=meta[doc_id].text)
        for doc_id, score in ordered
    ]

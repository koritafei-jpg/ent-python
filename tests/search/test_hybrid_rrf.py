"""RRF 单元测试。"""

from entpy.search.backends.base import ScoredHit
from entpy.search.hybrid import reciprocal_rank_fusion


def test_rrf_merges_two_lists():
    a = [ScoredHit(1, 1.0, "bm25"), ScoredHit(2, 0.5, "bm25")]
    b = [ScoredHit(2, 0.9, "semantic"), ScoredHit(3, 0.8, "semantic")]
    fused = reciprocal_rank_fusion(a, b, k=60)
    ids = [h.id for h in fused]
    assert 2 in ids
    assert ids[0] == 2

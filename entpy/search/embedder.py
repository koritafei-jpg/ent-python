"""语义检索用的 Embedder 协议。"""

from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_sync(self, texts: list[str]) -> list[list[float]]: ...


class MockEmbedder:
    """测试用确定性 mock 向量。"""

    def __init__(self, dim: int = 8) -> None:
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return self.embed_sync(texts)

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        out = []
        for i, t in enumerate(texts):
            vec = [0.0] * self.dim
            vec[i % self.dim] = 1.0
            for j, c in enumerate(t[: self.dim]):
                vec[j % self.dim] += ord(c) / 1000.0
            out.append(vec)
        return out

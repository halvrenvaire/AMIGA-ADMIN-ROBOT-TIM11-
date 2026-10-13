"""Vector store berbasis FAISS (cosine similarity via inner product atas vektor ternormalisasi)."""
import json
from pathlib import Path

import faiss
import numpy as np

INDEX_FILE = "index.faiss"
META_FILE = "chunks.json"


def _normalize(vectors) -> np.ndarray:
    arr = np.asarray(vectors, dtype="float32")
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


class VectorStore:
    def __init__(self):
        self.index: faiss.Index | None = None
        self.chunks: list[dict] = []
        self.meta: dict = {}

    def build(self, chunks: list[dict], embeddings: list[list[float]], meta: dict | None = None) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Jumlah chunk dan embedding tidak sama")
        if not chunks:
            raise ValueError("Tidak ada chunk untuk di-index")
        vectors = _normalize(embeddings)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        self.index, self.chunks, self.meta = index, list(chunks), dict(meta or {})

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        if self.is_empty():
            return []
        k = min(top_k, len(self.chunks))
        scores, ids = self.index.search(_normalize(query_embedding), k)
        return [
            {**self.chunks[i], "score": float(s)}
            for s, i in zip(scores[0], ids[0])
            if i != -1
        ]

    def is_empty(self) -> bool:
        return self.index is None or self.index.ntotal == 0

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(path / INDEX_FILE))
        (path / META_FILE).write_text(
            json.dumps({"meta": self.meta, "chunks": self.chunks}, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "VectorStore":
        path = Path(path)
        store = cls()
        store.index = faiss.read_index(str(path / INDEX_FILE))
        data = json.loads((path / META_FILE).read_text(encoding="utf-8"))
        store.chunks, store.meta = data["chunks"], data["meta"]
        if store.index.ntotal != len(store.chunks):
            raise ValueError("Index FAISS dan metadata chunk tidak sinkron")
        return store

    @staticmethod
    def exists(path: str | Path) -> bool:
        path = Path(path)
        return (path / INDEX_FILE).is_file() and (path / META_FILE).is_file()

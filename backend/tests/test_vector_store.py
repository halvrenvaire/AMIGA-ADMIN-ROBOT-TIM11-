import numpy as np
import pytest

from app.services.vector_store import VectorStore


@pytest.fixture
def dummy():
    rng = np.random.default_rng(42)
    embeddings = rng.normal(size=(20, 64)).tolist()
    chunks = [{"content": f"chunk {i}", "source": "dummy.md", "origin": "local", "chunk_index": i}
              for i in range(20)]
    return chunks, embeddings


def test_search_finds_own_embedding_on_top(dummy):
    chunks, embeddings = dummy
    store = VectorStore()
    store.build(chunks, embeddings)
    for i in (0, 7, 19):
        top = store.search(embeddings[i], top_k=3)
        assert top[0]["chunk_index"] == i
        assert top[0]["score"] == pytest.approx(1.0, abs=1e-5)
        assert len(top) == 3


def test_save_load_gives_same_results(dummy, tmp_path):
    chunks, embeddings = dummy
    store = VectorStore()
    store.build(chunks, embeddings, meta={"last_indexed_at": "2026-10-13T00:00:00+00:00"})
    store.save(tmp_path)

    assert VectorStore.exists(tmp_path)
    loaded = VectorStore.load(tmp_path)
    assert loaded.meta == store.meta
    assert loaded.search(embeddings[5], 5) == store.search(embeddings[5], 5)


def test_empty_store():
    store = VectorStore()
    assert store.is_empty()
    assert store.search([0.1] * 64) == []


def test_build_rejects_mismatched_lengths(dummy):
    chunks, embeddings = dummy
    with pytest.raises(ValueError):
        VectorStore().build(chunks, embeddings[:-1])

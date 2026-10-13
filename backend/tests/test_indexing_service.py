import hashlib
import io
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.services.indexing_service import IndexingService


class FakeBedrock:
    """Embedding deterministik dari hash teks, tanpa memanggil AWS."""

    def __init__(self):
        self.calls = 0

    def embed(self, text: str) -> list[float]:
        self.calls += 1
        seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        return np.random.default_rng(seed).normal(size=16).tolist()


def _s3(files: dict[str, str]):
    client = MagicMock()
    client.get_paginator.return_value.paginate.return_value = [{"Contents": [{"Key": k} for k in files]}]
    client.get_object.side_effect = lambda Bucket, Key: {"Body": io.BytesIO(files[Key].encode())}
    return client


@pytest.fixture
def setup(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "sop.md").write_text("Bagian satu.\n\nBagian dua tentang QUEUED.", encoding="utf-8")
    s3 = _s3({
        "sop.md": "Bagian satu.\n\nBagian dua tentang QUEUED.",  # duplikat isi lokal
        "faq.txt": "FAQ: voucher bukan persetujuan pembayaran.",
    })
    bedrock = FakeBedrock()
    service = IndexingService(bedrock, index_dir=tmp_path / "index", docs_dir=docs,
                              s3_client=s3, bucket="bucket")
    return service, bedrock, tmp_path


def test_build_from_cold_start_dedupes_and_saves(setup):
    service, bedrock, tmp = setup
    status = service.build_index()
    assert status["indexed"] is True
    assert status["sources"] == ["local:sop.md", "s3:faq.txt"]  # sop.md di S3 dilewati
    assert status["total_chunks"] == bedrock.calls == 2
    assert (tmp / "index" / "index.faiss").is_file()
    assert status["last_indexed_at"]


def test_force_false_loads_from_disk_without_embedding(setup):
    service, bedrock, tmp = setup
    first = service.build_index()
    calls_after_first = bedrock.calls

    fresh = IndexingService(bedrock, index_dir=tmp / "index", docs_dir=tmp / "docs",
                            s3_client=service.s3, bucket="bucket")
    second = fresh.build_index(force=False)
    assert bedrock.calls == calls_after_first
    assert second["total_chunks"] == first["total_chunks"]
    assert second["last_indexed_at"] == first["last_indexed_at"]


def test_force_true_always_rebuilds_and_picks_up_new_docs(setup):
    service, bedrock, tmp = setup
    service.build_index()
    (tmp / "docs" / "baru.md").write_text("Dokumen baru tentang SoD.", encoding="utf-8")
    status = service.build_index(force=True)
    assert "local:baru.md" in status["sources"]
    assert "duration_seconds" in status
    assert service.get_store().search(FakeBedrock().embed("Dokumen baru tentang SoD."), 1)[0]["source"] == "baru.md"

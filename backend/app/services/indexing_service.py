"""Orkestrasi indexing RAG: load dokumen -> chunk -> embed -> simpan ke FAISS."""
import hashlib
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import boto3

from app.config import settings
from app.services.bedrock_client import BedrockClient
from app.services.chunker import chunk_documents
from app.services.document_loader import load_local_docs, load_s3_docs
from app.services.vector_store import VectorStore

log = logging.getLogger(__name__)

EMBED_WORKERS = 8


def _dedupe(docs: list[dict]) -> list[dict]:
    """Buang dokumen ganda.

    - Nama file sama di lokal dan S3: versi lokal (repo) yang dipakai, supaya salinan
      lama di S3 tidak ikut menjawab setelah SOP direvisi.
    - Isi identik dengan nama berbeda: hanya satu yang dipakai.
    """
    local_names = {Path(d["source"]).name for d in docs if d["origin"] == "local"}
    seen: set[str] = set()
    unique = []
    for doc in docs:
        if doc["origin"] == "s3" and Path(doc["source"]).name in local_names:
            log.info("Lewati %s (s3): versi lokal dengan nama sama yang dipakai", doc["source"])
            continue
        digest = hashlib.sha256(doc["content"].strip().encode()).hexdigest()
        if digest in seen:
            log.info("Lewati %s (%s): isi sama dengan dokumen lain", doc["source"], doc["origin"])
            continue
        seen.add(digest)
        unique.append(doc)
    return unique


class IndexingService:
    def __init__(
        self,
        bedrock: BedrockClient,
        index_dir: Path = settings.rag_index_dir,
        docs_dir: Path = settings.rag_docs_dir,
        s3_client=None,
        bucket: str = settings.aws_bucket,
    ):
        self.bedrock = bedrock
        self.index_dir = Path(index_dir)
        self.docs_dir = Path(docs_dir)
        self.bucket = bucket
        self.s3 = s3_client
        self._store = VectorStore()
        self._lock = threading.Lock()  # cegah dua reindex berjalan bersamaan

    def _s3_client(self):
        if self.s3 is None:
            self.s3 = boto3.client(
                "s3",
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key or None,
                aws_secret_access_key=settings.aws_secret_access_key or None,
            )
        return self.s3

    def build_index(self, force: bool = False) -> dict:
        with self._lock:
            if not force and VectorStore.exists(self.index_dir):
                self._store = VectorStore.load(self.index_dir)
                log.info("Index dimuat dari disk: %d chunk", len(self._store.chunks))
                return self.status()

            started = time.perf_counter()
            docs = load_local_docs(self.docs_dir) + load_s3_docs(self.bucket, self._s3_client())
            docs = _dedupe(docs)
            log.info("Dokumen dimuat: %s", [f"{d['source']} ({d['origin']})" for d in docs])

            chunks = chunk_documents(docs)
            # Embedding dipanggil paralel: tiap panggilan ke us-east-1 butuh ~2 detik
            with ThreadPoolExecutor(max_workers=EMBED_WORKERS) as pool:
                embeddings = []
                for i, vector in enumerate(pool.map(self.bedrock.embed, [c["content"] for c in chunks]), start=1):
                    embeddings.append(vector)
                    if i % 10 == 0 or i == len(chunks):
                        log.info("Embedding %d/%d chunk", i, len(chunks))

            store = VectorStore()
            store.build(chunks, embeddings, meta={
                "last_indexed_at": datetime.now(timezone.utc).isoformat(),
                "embed_model": settings.embed_model,
            })
            store.save(self.index_dir)
            # Index baru langsung dipakai /ask tanpa restart server
            self._store = store
            duration = time.perf_counter() - started
            log.info("Index selesai dibangun: %d chunk dalam %.1f detik", len(chunks), duration)
            return {**self.status(), "duration_seconds": round(duration, 2)}

    def get_store(self) -> VectorStore:
        return self._store

    def status(self) -> dict:
        store = self._store
        sources = sorted({f"{c['origin']}:{c['source']}" for c in store.chunks})
        return {
            "indexed": not store.is_empty(),
            "total_chunks": len(store.chunks),
            "sources": sources,
            "last_indexed_at": store.meta.get("last_indexed_at"),
        }

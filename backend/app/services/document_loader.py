"""Memuat dokumen sumber RAG dari folder lokal dan dari S3 bucket."""
import io
import logging
from pathlib import Path

from pypdf import PdfReader

log = logging.getLogger(__name__)

TEXT_EXTENSIONS = (".md", ".txt")
S3_EXTENSIONS = (".md", ".txt", ".pdf")


def _pdf_to_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def load_local_docs(docs_path: str | Path) -> list[dict]:
    docs = []
    root = Path(docs_path)
    if not root.is_dir():
        log.warning("Folder dokumen lokal tidak ditemukan: %s", root)
        return docs
    for path in sorted(root.iterdir()):
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            log.warning("Gagal membaca %s: %s", path, e)
            continue
        if content.strip():
            docs.append({"content": content, "source": path.name, "origin": "local"})
    return docs


def load_s3_docs(bucket: str, client) -> list[dict]:
    docs = []
    if not bucket:
        return docs
    try:
        paginator = client.get_paginator("list_objects_v2")
        keys = [
            obj["Key"]
            for page in paginator.paginate(Bucket=bucket)
            for obj in page.get("Contents", [])
            if obj["Key"].lower().endswith(S3_EXTENSIONS)
        ]
    except Exception as e:
        log.warning("Gagal membaca daftar file S3 bucket %s: %s", bucket, e)
        return docs

    for key in keys:
        try:
            data = client.get_object(Bucket=bucket, Key=key)["Body"].read()
            content = _pdf_to_text(data) if key.lower().endswith(".pdf") else data.decode("utf-8")
        except Exception as e:
            log.warning("Gagal membaca s3://%s/%s: %s", bucket, key, e)
            continue
        if content.strip():
            docs.append({"content": content, "source": key, "origin": "s3"})
    return docs

import io
from unittest.mock import MagicMock

from app.config import settings
from app.services.chunker import chunk_documents, chunk_text
from app.services.document_loader import load_local_docs, load_s3_docs


def _s3_mock(files: dict[str, bytes]):
    client = MagicMock()
    client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": k} for k in files]}
    ]
    client.get_object.side_effect = lambda Bucket, Key: {"Body": io.BytesIO(files[Key])}
    return client


def test_load_local_reads_full_sop():
    docs = load_local_docs(settings.rag_docs_dir)
    sop = next(d for d in docs if d["source"] == "sop.md")
    expected = (settings.rag_docs_dir / "sop.md").read_text(encoding="utf-8")
    assert sop["content"] == expected
    assert sop["origin"] == "local"


def test_load_local_missing_folder_returns_empty(tmp_path):
    assert load_local_docs(tmp_path / "tidak-ada") == []


def test_load_s3_filters_extensions_and_skips_bad_files():
    client = _s3_mock({
        "a.md": b"# Dokumen A",
        "b.txt": "Catatan B".encode(),
        "gambar.png": b"\x89PNG",
        "rusak.txt": b"\xff\xfe\xfa",  # bukan UTF-8 valid
    })
    docs = load_s3_docs("bucket", client)
    assert [(d["source"], d["origin"]) for d in docs] == [("a.md", "s3"), ("b.txt", "s3")]


def test_load_s3_error_listing_returns_empty():
    client = MagicMock()
    client.get_paginator.side_effect = Exception("AccessDenied")
    assert load_s3_docs("bucket", client) == []


def _sop_chunks():
    return [c for c in chunk_documents(load_local_docs(settings.rag_docs_dir)) if c["source"] == "sop.md"]


def _body(chunk: str) -> str:
    return chunk.split("\n\n", 1)[1] if chunk.startswith("Bagian: ") else chunk


def test_sop_has_no_heading_only_chunks():
    for c in _sop_chunks():
        body = _body(c["content"])
        assert body.strip(), c["content"]
        assert not all(line.lstrip().startswith("#") for line in body.splitlines() if line.strip())


def test_sop_chunks_carry_section_heading_and_respect_size():
    chunks = _sop_chunks()
    assert all(len(c["content"]) <= 800 for c in chunks)
    assert all(c["content"].startswith("Bagian: ") for c in chunks)
    problem = next(c for c in chunks if "Dugaan penyalahgunaan akses" in c["content"])
    assert problem["content"].startswith("Bagian: 10. Penanganan Masalah")
    assert "| Masalah | Tindakan | Penanggung jawab |" in problem["content"]


def test_sop_chunks_split_on_line_boundaries_and_cover_all_content():
    source_lines = {l.strip() for l in (settings.rag_docs_dir / "sop.md").read_text(encoding="utf-8").splitlines()}
    chunked_lines = set()
    for c in _sop_chunks():
        for line in _body(c["content"]).splitlines():
            assert line.strip() in source_lines, f"baris terpotong: {line!r}"
            chunked_lines.add(line.strip())
    content_lines = {l for l in source_lines if l and not l.startswith("#")}
    assert content_lines <= chunked_lines


def test_sop_chunk_metadata():
    chunks = _sop_chunks()
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))
    assert all(c["origin"] == "local" for c in chunks)


def test_long_table_repeats_header_in_every_piece():
    rows = "\n".join(f"| Baris {i} | Isi tabel nomor {i} yang cukup panjang |" for i in range(40))
    text = "## Tabel\n\n| Kolom A | Kolom B |\n| --- | --- |\n" + rows
    chunks = chunk_text(text, chunk_size=400)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 400
        assert c.startswith("Bagian: Tabel\n\n| Kolom A | Kolom B |\n| --- | --- |\n| Baris")


def test_long_list_overlaps_one_line_between_pieces():
    text = "\n".join(f"{i}. Langkah prosedur nomor {i} yang harus diikuti." for i in range(1, 40))
    chunks = chunk_text(text, chunk_size=300)
    assert len(chunks) > 1
    for a, b in zip(chunks, chunks[1:]):
        assert a.splitlines()[-1] == b.splitlines()[0]


def test_plain_text_without_headings_has_no_prefix():
    chunks = chunk_text("Paragraf satu.\n\nParagraf dua.")
    assert chunks == ["Paragraf satu.\n\nParagraf dua."]

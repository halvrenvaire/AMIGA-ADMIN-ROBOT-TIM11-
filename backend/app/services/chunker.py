"""Memecah dokumen menjadi potongan kecil untuk embedding.

Strategi (sadar struktur Markdown):
1. Dokumen dibagi per bagian berdasarkan judul (#, ##, ###). Judul tidak pernah
   menjadi chunk sendiri; setiap chunk diawali "Bagian: <jalur judul>" supaya
   model tahu konteksnya.
2. Isi bagian dipecah per paragraf, lalu paragraf berurutan digabung sampai
   mendekati chunk_size.
3. Paragraf yang terlalu panjang dipecah di batas baris (tidak di tengah kata).
   Untuk tabel, baris judul tabel diulang di setiap potongan; untuk daftar/teks
   biasa, baris terakhir potongan sebelumnya diulang sebagai overlap.
Dokumen tanpa judul (mis. .txt atau PDF) tetap diproses dengan langkah 2-3.
"""
import re

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
TABLE_SEPARATOR = re.compile(r"^\s*\|?[\s:\-|]+\|?\s*$")


def _section_path(stack: list[tuple[int, str]]) -> str:
    # Judul dokumen (#) hanya dipakai bila belum ada sub-judul, agar prefix tetap ringkas
    titles = [title for level, title in stack if level >= 2] or [title for _, title in stack]
    return " > ".join(titles)


def _split_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []
    body: list[str] = []

    def flush() -> None:
        content = "\n".join(body).strip()
        if content:
            sections.append((_section_path(stack), content))
        body.clear()

    for line in text.splitlines():
        match = HEADING.match(line.strip())
        if match:
            flush()
            level = len(match.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, match.group(2)))
        else:
            body.append(line)
    flush()
    return sections


def _split_words(line: str, size: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for word in line.split():
        while len(word) > size:  # kata tunggal yang sangat panjang (jarang)
            if current:
                pieces.append(current)
                current = ""
            pieces.append(word[:size])
            word = word[size:]
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= size:
            current = f"{current} {word}"
        else:
            pieces.append(current)
            current = word
    if current:
        pieces.append(current)
    return pieces


def _split_long_paragraph(paragraph: str, budget: int) -> list[str]:
    lines = paragraph.split("\n")
    is_table = (
        len(lines) >= 2
        and lines[0].lstrip().startswith("|")
        and TABLE_SEPARATOR.match(lines[1]) is not None
    )
    header = lines[:2] if is_table else []
    header_len = len("\n".join(header)) + 1 if header else 0
    line_budget = max(budget - header_len, 50)

    body_lines: list[str] = []
    for line in lines[2:] if is_table else lines:
        body_lines.extend([line] if len(line) <= line_budget else _split_words(line, line_budget))

    pieces: list[str] = []
    current: list[str] = []
    for line in body_lines:
        if current and len("\n".join(header + current + [line])) > budget:
            pieces.append("\n".join(header + current))
            previous = current[-1]
            overlap_fits = len("\n".join(header + [previous, line])) <= budget
            current = [previous, line] if not is_table and overlap_fits else [line]
        else:
            current.append(line)
    if current:
        pieces.append("\n".join(header + current))
    return pieces


def chunk_text(text: str, chunk_size: int = 800) -> list[str]:
    chunks: list[str] = []
    for path, content in _split_sections(text):
        prefix = f"Bagian: {path}\n\n" if path else ""
        budget = max(chunk_size - len(prefix), 200)
        current = ""
        for paragraph in (p.strip() for p in re.split(r"\n\s*\n", content)):
            if not paragraph:
                continue
            if len(paragraph) > budget:
                pieces = _split_long_paragraph(paragraph, budget)
                # Kalimat pengantar pendek ikut ke potongan pertama bila masih muat
                if current and len(current) + 2 + len(pieces[0]) <= budget:
                    pieces[0] = f"{current}\n\n{pieces[0]}"
                elif current:
                    chunks.append(prefix + current)
                current = ""
                chunks.extend(prefix + piece for piece in pieces)
            elif not current:
                current = paragraph
            elif len(current) + 2 + len(paragraph) <= budget:
                current = f"{current}\n\n{paragraph}"
            else:
                chunks.append(prefix + current)
                current = paragraph
        if current:
            chunks.append(prefix + current)
    return chunks


def chunk_documents(docs: list[dict], chunk_size: int = 800) -> list[dict]:
    return [
        {"content": chunk, "source": doc["source"], "origin": doc["origin"], "chunk_index": i}
        for doc in docs
        for i, chunk in enumerate(chunk_text(doc["content"], chunk_size))
    ]

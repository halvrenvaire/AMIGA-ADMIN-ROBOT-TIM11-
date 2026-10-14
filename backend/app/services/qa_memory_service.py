"""Memori tanya-jawab /ask-agent.

Setiap tanya-jawab disimpan beserta embedding pertanyaannya. Saat ada pertanyaan
baru yang mirip, tanya-jawab lama dipakai sebagai referensi tambahan (SOP tetap
acuan utama). Yang tidak dipakai sebagai referensi:
- jawaban yang diberi 👎;
- tanya-jawab dari index SOP lama (sebelum /reindex terakhir).
"""
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import QAMemory

# Jawaban seperti ini tidak berguna sebagai referensi, jadi tidak disimpan
NOT_FOUND_PHRASES = (
    "tidak ada di dokumen",
    "tidak ada dalam dokumen",
    "tidak tersedia di dokumen",
    "tidak tersedia dalam dokumen",
    "tidak ditemukan di dokumen",
    "tidak ditemukan dalam dokumen",
    "tidak terdapat dalam dokumen",
    "tidak disebutkan dalam dokumen",
)


def is_not_found_answer(answer: str) -> bool:
    text = answer.lower()
    return any(phrase in text for phrase in NOT_FOUND_PHRASES)


class QAMemoryService:
    def __init__(self, db: Session):
        self.db = db

    def add(self, session_id: str, question: str, answer: str,
            embedding: list[float], index_version: str) -> int:
        row = QAMemory(session_id=session_id, question=question, answer=answer,
                       embedding=embedding, index_version=index_version)
        self.db.add(row)
        self.db.commit()
        return row.id

    def search(self, embedding: list[float], index_version: str,
               top_k: int = 3, min_score: float = 0.70) -> list[dict]:
        rows = self.db.scalars(
            select(QAMemory).where(
                QAMemory.index_version == index_version,
                QAMemory.feedback.is_distinct_from(-1),
            )
        ).all()
        if not rows:
            return []

        # Jumlah tanya-jawab PoC masih kecil, jadi cukup dihitung di memori
        matrix = np.asarray([r.embedding for r in rows], dtype="float32")
        query = np.asarray(embedding, dtype="float32")
        scores = matrix @ query / (np.linalg.norm(matrix, axis=1) * np.linalg.norm(query) + 1e-12)

        matches = [(float(s), r) for s, r in zip(scores, rows) if s >= min_score]
        # Jawaban 👍 didahulukan, lalu yang paling mirip
        matches.sort(key=lambda m: (m[1].feedback == 1, m[0]), reverse=True)
        return [
            {"id": r.id, "question": r.question, "answer": r.answer,
             "score": round(s, 4), "feedback": r.feedback}
            for s, r in matches[:top_k]
        ]

    def set_feedback(self, memory_id: int, helpful: bool) -> bool:
        row = self.db.get(QAMemory, memory_id)
        if row is None:
            return False
        row.feedback = 1 if helpful else -1
        self.db.commit()
        return True

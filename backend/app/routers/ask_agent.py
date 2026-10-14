"""Asisten SOP Agent: seperti /ask, ditambah memori tanya-jawab lintas sesi.

Pertanyaan lama yang mirip (beserta jawabannya) ikut dikirim ke model sebagai
referensi tambahan. Dokumen SOP tetap acuan utama.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.schemas.schemas import (
    AskAgentResponse, AskRequest, FeedbackRequest, FeedbackResponse, MemoryRef, SourceItem,
)
from app.services.bedrock_client import BedrockError
from app.services.history_service import HistoryService
from app.services.qa_memory_service import QAMemoryService, is_not_found_answer

router = APIRouter(tags=["Asisten SOP Agent"])

SYSTEM_PROMPT = """Kamu adalah asisten AMIGA Robot Admin untuk tim keuangan dan PIC klien.
Jawab HANYA berdasarkan konteks dokumen di bawah. Jika jawabannya tidak ada di konteks,
katakan terus terang bahwa informasinya tidak ada di dokumen SOP, jangan menebak.
Jawab dalam Bahasa Indonesia yang jelas dan ringkas.

Konteks dokumen:
{context}"""

MEMORY_SECTION = """

Tanya-jawab sebelumnya yang mirip (hanya referensi tambahan; jika bertentangan
dengan konteks dokumen, ikuti konteks dokumen):
{memory}"""


def _format_context(results: list[dict]) -> str:
    return "\n\n---\n\n".join(
        f"[{i}] (sumber: {r['source']})\n{r['content']}" for i, r in enumerate(results, start=1)
    )


def _format_memory(memory: list[dict]) -> str:
    return "\n\n".join(f"T: {m['question']}\nJ: {m['answer']}" for m in memory)


@router.post("/ask-agent", response_model=AskAgentResponse)
def ask_agent(body: AskRequest, request: Request, db: Session = Depends(get_db)):
    indexing = request.app.state.indexing
    bedrock = request.app.state.bedrock
    store = indexing.get_store()
    if store.is_empty():
        raise HTTPException(503, "Index dokumen belum siap. Jalankan POST /reindex terlebih dahulu.")

    history = HistoryService(db)
    memory_service = QAMemoryService(db)
    index_version = indexing.status()["last_indexed_at"] or "unknown"
    try:
        question_embedding = bedrock.embed(body.question)
        results = store.search(question_embedding, top_k=settings.rag_top_k)
        past = history.get_history(body.session_id, last_n=settings.rag_history_turns * 2)
        # Converse API mewajibkan percakapan dimulai dari pesan user
        while past and past[0]["role"] != "user":
            past.pop(0)

        # Pertanyaan lanjutan ("lalu setelah itu?") tidak bermakna tanpa percakapannya,
        # jadi memori hanya dipakai dan diisi untuk pertanyaan pertama di sebuah sesi
        is_follow_up = bool(past)
        memory = [] if is_follow_up else memory_service.search(
            question_embedding, index_version,
            top_k=settings.qa_memory_top_k, min_score=settings.qa_memory_min_score,
        )

        system_prompt = SYSTEM_PROMPT.format(context=_format_context(results))
        if memory:
            system_prompt += MEMORY_SECTION.format(memory=_format_memory(memory))
        answer = bedrock.generate(
            system_prompt,
            past + [{"role": "user", "content": body.question}],
            max_tokens=settings.rag_max_answer_tokens,
        )
    except BedrockError:
        raise HTTPException(503, "Layanan AI sedang tidak tersedia. Coba lagi beberapa saat lagi.")

    history.add_turn(body.session_id, body.question, answer)
    answer_id = None
    if is_follow_up:
        memory_note = (
            "Tidak disimpan ke memori: pertanyaan lanjutan di sesi yang sama. "
            "Gunakan session_id baru untuk pertanyaan baru."
        )
    elif is_not_found_answer(answer):
        memory_note = "Tidak disimpan ke memori: jawaban tidak ditemukan di dokumen SOP."
    else:
        answer_id = memory_service.add(
            body.session_id, body.question, answer, question_embedding, index_version
        )
        memory_note = "Disimpan ke memori. Gunakan answer_id untuk memberi 👍/👎."

    return AskAgentResponse(
        answer=answer,
        session_id=body.session_id,
        answer_id=answer_id,
        memory_note=memory_note,
        memory_refs=[
            MemoryRef(question=m["question"], score=m["score"], feedback=m["feedback"])
            for m in memory
        ],
        sources=[
            SourceItem(
                source=r["source"],
                origin=r["origin"],
                chunk_index=r["chunk_index"],
                score=round(r["score"], 4),
                preview=r["content"][:200],
            )
            for r in results
        ],
    )


@router.post("/ask-agent/feedback", response_model=FeedbackResponse)
def feedback(body: FeedbackRequest, db: Session = Depends(get_db)):
    """Beri 👍 (helpful=true) atau 👎 (helpful=false). Jawaban 👎 tidak dipakai lagi sebagai referensi."""
    if not QAMemoryService(db).set_feedback(body.answer_id, body.helpful):
        raise HTTPException(404, "Jawaban tidak ditemukan")
    return FeedbackResponse(answer_id=body.answer_id, feedback=1 if body.helpful else -1)

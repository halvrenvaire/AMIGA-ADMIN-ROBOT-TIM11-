from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.schemas.schemas import AskRequest, AskResponse, SourceItem
from app.services.bedrock_client import BedrockError
from app.services.history_service import HistoryService

router = APIRouter(tags=["Asisten SOP"])

SYSTEM_PROMPT = """Kamu adalah asisten AMIGA Robot Admin untuk tim keuangan dan PIC klien.
Jawab HANYA berdasarkan konteks dokumen di bawah. Jika jawabannya tidak ada di konteks,
katakan terus terang bahwa informasinya tidak ada di dokumen SOP, jangan menebak.
Jawab dalam Bahasa Indonesia yang jelas dan ringkas.

Konteks dokumen:
{context}"""


def _format_context(results: list[dict]) -> str:
    return "\n\n---\n\n".join(
        f"[{i}] (sumber: {r['source']})\n{r['content']}" for i, r in enumerate(results, start=1)
    )


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request, db: Session = Depends(get_db)):
    indexing = request.app.state.indexing
    bedrock = request.app.state.bedrock
    store = indexing.get_store()
    if store.is_empty():
        raise HTTPException(503, "Index dokumen belum siap. Jalankan POST /reindex terlebih dahulu.")

    history = HistoryService(db)
    try:
        results = store.search(bedrock.embed(body.question), top_k=settings.rag_top_k)
        past = history.get_history(body.session_id, last_n=settings.rag_history_turns * 2)
        # Converse API mewajibkan percakapan dimulai dari pesan user
        while past and past[0]["role"] != "user":
            past.pop(0)
        answer = bedrock.generate(
            SYSTEM_PROMPT.format(context=_format_context(results)),
            past + [{"role": "user", "content": body.question}],
            max_tokens=settings.rag_max_answer_tokens,
        )
    except BedrockError:
        raise HTTPException(503, "Layanan AI sedang tidak tersedia. Coba lagi beberapa saat lagi.")

    history.add_turn(body.session_id, body.question, answer)
    return AskResponse(
        answer=answer,
        session_id=body.session_id,
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

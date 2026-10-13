from fastapi import APIRouter, Request
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.schemas.schemas import HealthResponse, IndexStatus

router = APIRouter(tags=["Sistem"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db = "ok"
    except Exception:
        db = "unreachable"

    rag = IndexStatus(**request.app.state.indexing.status())
    return HealthResponse(
        status="ok" if db == "ok" and rag.indexed else "degraded",
        database=db,
        rag=rag,
        llm_model=settings.llm_model,
        embed_model=settings.embed_model,
    )

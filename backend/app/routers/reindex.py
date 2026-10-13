import secrets

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings
from app.schemas.schemas import ReindexResponse
from app.services.bedrock_client import BedrockError

router = APIRouter(tags=["Asisten SOP"])


@router.post("/reindex", response_model=ReindexResponse)
def reindex(request: Request, x_api_key: str | None = Header(default=None)):
    if not settings.reindex_api_key:
        raise HTTPException(503, "Reindex dinonaktifkan: REINDEX_API_KEY belum diisi di .env")
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.reindex_api_key):
        raise HTTPException(401, "X-API-Key tidak valid")
    try:
        result = request.app.state.indexing.build_index(force=True)
    except BedrockError:
        raise HTTPException(503, "Gagal membuat embedding. Index lama tetap dipakai.")
    except ValueError as e:
        raise HTTPException(422, str(e))
    return ReindexResponse(status="success", **result)

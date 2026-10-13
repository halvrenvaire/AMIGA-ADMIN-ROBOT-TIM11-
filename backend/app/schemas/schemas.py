from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(min_length=1, max_length=100)


class SourceItem(BaseModel):
    source: str
    origin: str
    chunk_index: int
    score: float
    preview: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    session_id: str


class IndexStatus(BaseModel):
    indexed: bool
    total_chunks: int
    sources: list[str]
    last_indexed_at: str | None


class ReindexResponse(IndexStatus):
    status: str
    duration_seconds: float


class HealthResponse(BaseModel):
    status: str
    database: str
    rag: IndexStatus
    llm_model: str
    embed_model: str

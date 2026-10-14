import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.routers import admin, ask, ask_agent, auth, clients, database, documents, health, reindex, review
from app.services.bedrock_client import BedrockClient
from app.services.extraction_service import InvoiceExtractor
from app.services.indexing_service import IndexingService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.bedrock = BedrockClient()
    app.state.indexing = IndexingService(app.state.bedrock)
    app.state.extractor = InvoiceExtractor(app.state.bedrock)
    try:
        # Muat index dari disk; bangun baru hanya bila belum pernah ada
        app.state.indexing.build_index(force=False)
    except Exception:
        # Server tetap hidup; /health melaporkan "degraded" dan /reindex bisa dicoba lagi
        log.exception("Index RAG gagal dibangun saat startup")
    yield


app = FastAPI(
    title="AMIGA Robot Admin API",
    description="Intelligent Vendor Invoice-to-Voucher Processing (PoC MAIN Hackathon 2026)",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(documents.router)
app.include_router(review.router)
app.include_router(admin.router)
app.include_router(ask.router)
app.include_router(ask_agent.router)
app.include_router(reindex.router)
app.include_router(database.router)

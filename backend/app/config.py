from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str
    jwt_secret: str = "dev-secret-ganti"
    jwt_expire_minutes: int = 480

    storage_backend: str = "local"  # "local" atau "s3" (memakai AWS_BUCKET)
    local_storage_dir: str = "../storage"  # relatif terhadap folder backend/

    aws_access_key: str = ""
    aws_secret_access_key: str = ""
    aws_bucket: str = ""
    aws_region: str = "ap-southeast-1"
    # Kosong = memakai LLM_MODEL (Nova Lite), yang bisa membaca PDF langsung
    extraction_model_id: str = ""
    extraction_max_tokens: int = 4096

    max_pdf_pages: int = 5
    max_upload_mb: int = 10

    # RAG /ask
    # Titan Text sudah end of life, jadi LLM memakai Amazon Nova (tersedia di ap-southeast-1).
    llm_model: str = "apac.amazon.nova-lite-v1:0"
    llm_region: str = "ap-southeast-1"
    # Titan Embeddings tidak tersedia di ap-southeast-1; hanya bisa dipanggil di us-east-1.
    embed_model: str = "amazon.titan-embed-text-v2:0"
    embed_region: str = "us-east-1"
    embed_dimension: int = 1024

    rag_docs_dir: Path = BACKEND_DIR.parent / "docs"
    rag_index_dir: Path = BACKEND_DIR / "data" / "faiss_index"
    rag_top_k: int = 8
    rag_history_turns: int = 3  # 3 pasang tanya-jawab terakhir = 6 pesan
    rag_max_answer_tokens: int = 1024
    reindex_api_key: str = ""

    # Memori tanya-jawab /ask-agent
    # Diukur dengan Titan Embed v2: pertanyaan berbeda maksud mencapai ~0,36, parafrase
    # dengan kata mirip ~0,80. Batas 0,70 menolak semua yang berbeda maksud.
    qa_memory_min_score: float = 0.70
    qa_memory_top_k: int = 3


settings = Settings()

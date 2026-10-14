"""Wrapper Amazon Bedrock: embedding (Titan Embeddings) dan generate jawaban (Nova)."""
import json

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings


class BedrockError(Exception):
    """Panggilan ke Bedrock gagal; router mengubahnya menjadi HTTP 503."""


class BedrockClient:
    def __init__(self):
        session = boto3.Session(
            aws_access_key_id=settings.aws_access_key or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
        # Embedding dan LLM berada di region berbeda (lihat app/config.py)
        self.embed_runtime = session.client("bedrock-runtime", region_name=settings.embed_region)
        self.llm_runtime = session.client("bedrock-runtime", region_name=settings.llm_region)

    def embed(self, text: str) -> list[float]:
        body = {"inputText": text, "dimensions": settings.embed_dimension, "normalize": True}
        try:
            response = self.embed_runtime.invoke_model(
                modelId=settings.embed_model,
                body=json.dumps(body),
                accept="application/json",
                contentType="application/json",
            )
        except (ClientError, BotoCoreError) as e:
            raise BedrockError(f"Embedding gagal: {e}") from e
        return json.loads(response["body"].read())["embedding"]

    def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 512,
        temperature: float = 0.3,
    ) -> str:
        """messages: [{"role": "user"|"assistant", "content": "..."}], diakhiri pesan user."""
        try:
            response = self.llm_runtime.converse(
                modelId=settings.llm_model,
                system=[{"text": system_prompt}],
                messages=[{"role": m["role"], "content": [{"text": m["content"]}]} for m in messages],
                inferenceConfig={"maxTokens": max_tokens, "temperature": temperature, "topP": 0.9},
            )
        except (ClientError, BotoCoreError) as e:
            raise BedrockError(f"Generate jawaban gagal: {e}") from e
        return response["output"]["message"]["content"][0]["text"].strip()

    def read_pdf(self, system_prompt: str, pdf_bytes: bytes, instruction: str, max_tokens: int) -> str:
        """Kirim PDF langsung ke model (Converse API, blok dokumen) dan kembalikan teks jawabannya."""
        try:
            response = self.llm_runtime.converse(
                modelId=settings.extraction_model_id or settings.llm_model,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [
                    {"document": {"format": "pdf", "name": "invoice", "source": {"bytes": pdf_bytes}}},
                    {"text": instruction},
                ]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": 0.0},
            )
        except (ClientError, BotoCoreError) as e:
            raise BedrockError(f"Membaca PDF gagal: {e}") from e
        return response["output"]["message"]["content"][0]["text"].strip()

"""Integration test ke Amazon Bedrock sungguhan (butuh kredensial AWS di .env).

Lewati dengan:  pytest -m "not integration"
"""
import pytest

from app.config import settings
from app.services.bedrock_client import BedrockClient

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    return BedrockClient()


def test_embed_returns_vector_with_configured_dimension(client):
    vector = client.embed("apa itu AMIGA")
    assert len(vector) == settings.embed_dimension
    assert all(isinstance(x, float) for x in vector)


def test_generate_returns_text(client):
    answer = client.generate(
        "Jawab singkat dalam Bahasa Indonesia.",
        [{"role": "user", "content": "Sebutkan satu warna bendera Indonesia."}],
        max_tokens=30,
    )
    assert isinstance(answer, str) and answer

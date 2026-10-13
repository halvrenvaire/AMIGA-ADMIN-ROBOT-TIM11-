"""Membuat Bedrock Knowledge Base untuk SOP AMIGA (S3 Vectors + Cohere multilingual).

Jalankan dari folder backend/:  .venv/bin/python scripts/setup_kb.py
Aman dijalankan berulang: resource yang sudah ada dipakai ulang, lalu sop.md
diunggah ulang dan disinkronkan. BEDROCK_KB_ID ditulis ke .env bila belum ada.
"""
import pathlib
import sys
import time

import boto3
from dotenv import dotenv_values, set_key

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND / ".env"
SOP_PATH = BACKEND.parent / "docs" / "sop.md"

env = dotenv_values(ENV_PATH)
REGION = env.get("AWS_REGION") or "ap-southeast-1"
BUCKET = env["AWS_BUCKET"]
ROLE_ARN = env["BEDROCK_KB_ROLE_ARN"]
STUDENT = BUCKET.split("-")[2]  # bedrock-kb-student11-... -> student11

VECTOR_BUCKET = f"bedrock-kb-{STUDENT}-vectors-v1"
INDEX_NAME = "amiga-sop-v1"
KB_NAME = f"bedrock-kb-{STUDENT}-amiga-sop-v1"
DATA_SOURCE_NAME = "amiga-sop-s3-v1"
EMBEDDING_MODEL = "cohere.embed-multilingual-v3"  # 1024 dimensi, mendukung Bahasa Indonesia

session = boto3.Session(
    aws_access_key_id=env["AWS_ACCESS_KEY"],
    aws_secret_access_key=env["AWS_SECRET_ACCESS_KEY"],
    region_name=REGION,
)
s3 = session.client("s3")
s3v = session.client("s3vectors")
agent = session.client("bedrock-agent")
account_id = session.client("sts").get_caller_identity()["Account"]


def step(msg: str) -> None:
    print(f"==> {msg}", flush=True)


def upload_sop() -> None:
    step(f"Unggah {SOP_PATH.name} ke s3://{BUCKET}/sop.md")
    s3.upload_file(str(SOP_PATH), BUCKET, "sop.md", ExtraArgs={"ContentType": "text/markdown"})


def ensure_vector_index() -> str:
    existing = [b["vectorBucketName"] for b in s3v.list_vector_buckets()["vectorBuckets"]]
    if VECTOR_BUCKET not in existing:
        step(f"Buat vector bucket {VECTOR_BUCKET}")
        s3v.create_vector_bucket(vectorBucketName=VECTOR_BUCKET)
    indexes = [i["indexName"] for i in s3v.list_indexes(vectorBucketName=VECTOR_BUCKET)["indexes"]]
    if INDEX_NAME not in indexes:
        step(f"Buat index {INDEX_NAME} (1024 dimensi, cosine)")
        s3v.create_index(
            vectorBucketName=VECTOR_BUCKET,
            indexName=INDEX_NAME,
            dataType="float32",
            dimension=1024,
            distanceMetric="cosine",
            metadataConfiguration={
                "nonFilterableMetadataKeys": ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
            },
        )
    return s3v.get_index(vectorBucketName=VECTOR_BUCKET, indexName=INDEX_NAME)["index"]["indexArn"]


def ensure_knowledge_base(index_arn: str) -> str:
    for kb in agent.list_knowledge_bases()["knowledgeBaseSummaries"]:
        if kb["name"] == KB_NAME:
            kb_id = kb["knowledgeBaseId"]
            break
    else:
        step(f"Buat Knowledge Base {KB_NAME}")
        kb_id = agent.create_knowledge_base(
            name=KB_NAME,
            description="SOP AMIGA Robot Admin (Kelompok 11)",
            roleArn=ROLE_ARN,
            knowledgeBaseConfiguration={
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": f"arn:aws:bedrock:{REGION}::foundation-model/{EMBEDDING_MODEL}",
                },
            },
            storageConfiguration={
                "type": "S3_VECTORS",
                "s3VectorsConfiguration": {"indexArn": index_arn},
            },
        )["knowledgeBase"]["knowledgeBaseId"]

    while (status := agent.get_knowledge_base(knowledgeBaseId=kb_id)["knowledgeBase"]["status"]) == "CREATING":
        time.sleep(3)
    if status != "ACTIVE":
        sys.exit(f"Knowledge Base berstatus {status}")
    return kb_id


def ensure_data_source(kb_id: str) -> str:
    for ds in agent.list_data_sources(knowledgeBaseId=kb_id)["dataSourceSummaries"]:
        if ds["name"] == DATA_SOURCE_NAME:
            return ds["dataSourceId"]
    step(f"Buat data source {DATA_SOURCE_NAME} -> s3://{BUCKET}/sop.md")
    return agent.create_data_source(
        knowledgeBaseId=kb_id,
        name=DATA_SOURCE_NAME,
        dataSourceConfiguration={
            "type": "S3",
            "s3Configuration": {
                "bucketArn": f"arn:aws:s3:::{BUCKET}",
                "bucketOwnerAccountId": account_id,
                "inclusionPrefixes": ["sop.md"],
            },
        },
        vectorIngestionConfiguration={
            "chunkingConfiguration": {
                # Cohere hanya membaca ~512 token per potongan, jadi SOP dipecah per 300 token
                "chunkingStrategy": "FIXED_SIZE",
                "fixedSizeChunkingConfiguration": {"maxTokens": 300, "overlapPercentage": 20},
            }
        },
    )["dataSource"]["dataSourceId"]


def sync(kb_id: str, ds_id: str) -> None:
    step("Sinkronisasi (ingestion) dokumen ke Knowledge Base")
    job_id = agent.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)["ingestionJob"]["ingestionJobId"]
    while True:
        job = agent.get_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job_id)["ingestionJob"]
        if job["status"] in ("COMPLETE", "FAILED", "STOPPED"):
            break
        time.sleep(3)
    print(f"    status: {job['status']}  statistik: {job.get('statistics')}")
    if job["status"] != "COMPLETE":
        sys.exit(f"Ingestion gagal: {job.get('failureReasons')}")


def main() -> None:
    upload_sop()
    index_arn = ensure_vector_index()
    kb_id = ensure_knowledge_base(index_arn)
    ds_id = ensure_data_source(kb_id)
    sync(kb_id, ds_id)
    if env.get("BEDROCK_KB_ID") != kb_id:
        set_key(str(ENV_PATH), "BEDROCK_KB_ID", kb_id, quote_mode="never")
        print("    BEDROCK_KB_ID ditulis ke .env")
    print(f"Selesai. Knowledge Base ID: {kb_id}")


if __name__ == "__main__":
    main()

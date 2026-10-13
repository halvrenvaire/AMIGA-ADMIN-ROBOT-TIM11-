from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os

from models import AskRequest, AskResponse
from rag_service import rag_service

# Create FastAPI app
app = FastAPI(
    title="AMIGA RAG API",
    description="RAG (Retrieval Augmented Generation) API using Amazon Bedrock",
    version="1.0.0"
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "AMIGA RAG API",
        "version": "1.0.0",
        "endpoints": {
            "/ask": "POST - Ask questions using RAG",
            "/health": "GET - Health check endpoint"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.post("/ask", response_model=AskResponse)
async def ask_endpoint(request: AskRequest):
    """
    Ask questions using RAG with Amazon Bedrock.
    
    This endpoint:
    - Retrieves relevant documents from S3 or context
    - Uses Bedrock embeddings for retrieval
    - Generates answers using Bedrock foundation models
    """
    try:
        result = rag_service.ask(
            question=request.question,
            bucket_name=request.bucket_name,
            document_key=request.document_key,
            context_docs=request.context_docs
        )
        
        return AskResponse(
            answer=result.get("answer", "No answer generated."),
            sources=result.get("sources"),
            context_used=result.get("context_used"),
            model_used=result.get("model_used")
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ask/simple")
async def ask_simple(request: AskRequest):
    """
    Simple version of /ask endpoint without Pydantic model validation.
    
    Use this for quick testing or when you want to handle validation manually.
    """
    try:
        result = rag_service.ask(
            question=request.question,
            bucket_name=request.bucket_name,
            document_key=request.document_key,
            context_docs=request.context_docs
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Run the app if executed directly
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
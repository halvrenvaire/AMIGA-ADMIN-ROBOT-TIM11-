from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class AskRequest(BaseModel):
    """Request model for /ask endpoint"""
    question: str
    bucket_name: Optional[str] = None
    document_key: Optional[str] = None
    context_docs: Optional[List[Dict[str, Any]]] = None  # Optional context documents


class AskResponse(BaseModel):
    """Response model for /ask endpoint"""
    answer: str
    sources: Optional[List[Dict[str, Any]]] = None
    context_used: Optional[List[str]] = None
    model_used: Optional[str] = None
    error: Optional[str] = None

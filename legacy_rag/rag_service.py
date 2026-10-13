import os
import json
import boto3
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from langchain_qdrant import QdrantVectorStore
from langchain_community.embeddings import BedrockEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


class QdrantVectorDB:
    """Qdrant vector database integration for RAG"""
    
    def __init__(self):
        self.qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        self.qdrant_api_key = os.getenv("QDRANT_API_KEY")
        self.qdrant_collection_name = os.getenv("QDRANT_COLLECTION_NAME", "amiga_rag_documents")
        self.aws_region = os.getenv("AWS_REGION", "ap-southeast-1")
        self.embedding_model_id = os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v1")
        
        # Initialize Qdrant client
        if self.qdrant_api_key:
            self.client = QdrantClient(
                url=self.qdrant_url,
                api_key=self.qdrant_api_key
            )
        else:
            self.client = QdrantClient(url=self.qdrant_url)
        
        # Initialize Bedrock embeddings (1536 dimensions for Titan Embeddings G1)
        self.bedrock_client = boto3.client("bedrock-runtime", region_name=self.aws_region)
        self.embeddings = BedrockEmbeddings(
            model_id=self.embedding_model_id,
            client=self.bedrock_client
        )
        
        # Dimension for Titan Text Embeddings G1
        self.embedding_dimension = 1536
        
        # Initialize vector store
        self.vector_store = None
        self._initialize_vector_store()
    
    def _initialize_vector_store(self):
        """Initialize Qdrant collection and vector store"""
        try:
            # Check if collection exists
            collections = self.client.get_collections().collections
            collection_names = [col.name for col in collections]
            
            if self.qdrant_collection_name not in collection_names:
                # Create collection with cosine similarity
                self.client.create_collection(
                    collection_name=self.qdrant_collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dimension,
                        distance=Distance.COSINE
                    )
                )
                print(f"Created Qdrant collection: {self.qdrant_collection_name}")
            
            # Initialize LangChain QdrantVectorStore
            self.vector_store = QdrantVectorStore(
                client=self.client,
                collection_name=self.qdrant_collection_name,
                embedding=self.embeddings
            )
            print(f"Connected to Qdrant collection: {self.qdrant_collection_name}")
            
        except Exception as e:
            print(f"Error initializing Qdrant: {e}")
            raise
    
    def add_documents(self, texts: List[str], metadatas: Optional[List[Dict]] = None):
        """Add documents to vector store"""
        if not texts:
            return
        
        if metadatas is None:
            metadatas = [{"source": "manual"}] * len(texts)
        
        # Use LangChain's add_documents
        from langchain_core.documents import Document
        documents = [
            Document(page_content=text, metadata=metadata)
            for text, metadata in zip(texts, metadatas)
        ]
        
        self.vector_store.add_documents(documents)
        print(f"Added {len(texts)} documents to Qdrant vector store")
    
    def similarity_search(self, query: str, k: int = 3) -> List[Any]:
        """Search for similar documents"""
        if self.vector_store is None:
            return []
        
        return self.vector_store.similarity_search(query, k=k)
    
    def add_document_from_text(self, text: str, source: str = "manual"):
        """Add a single document from text"""
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        chunks = text_splitter.split_text(text)
        
        metadatas = [{"source": source}] * len(chunks)
        self.add_documents(chunks, metadatas)
        
        return chunks
    
    def clear_collection(self):
        """Clear all documents from collection"""
        try:
            # Delete and recreate collection
            self.client.delete_collection(self.qdrant_collection_name)
            self._initialize_vector_store()
            print(f"Cleared Qdrant collection: {self.qdrant_collection_name}")
        except Exception as e:
            print(f"Error clearing collection: {e}")


class BedrockRAGService:
    """Service for Bedrock RAG operations with Qdrant"""
    
    def __init__(self):
        self.aws_access_key = os.getenv("AWS_ACCESS_KEY")
        self.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.aws_bucket = os.getenv("AWS_BUCKET")
        self.aws_region = os.getenv("AWS_REGION", "ap-southeast-1")
        self.embedding_model_id = os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v1")
        self.bedrock_model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.titan-text-express-v1")
        
        # Initialize Qdrant vector DB
        self.qdrant_db = QdrantVectorDB()
        
        # Initialize Bedrock clients
        self.session = boto3.Session(
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
            region_name=self.aws_region
        )
        
        self.bedrock_runtime = self.session.client("bedrock-runtime", region_name=self.aws_region)
        self.s3 = self.session.client("s3", region_name=self.aws_region)
        
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for text using Bedrock"""
        body = json.dumps({"inputText": text})
        
        response = self.bedrock_runtime.invoke_model(
            body=body,
            modelId=self.embedding_model_id,
            accept="application/json",
            contentType="application/json"
        )
        
        response_body = json.loads(response.get("body").read())
        return response_body.get("embedding")
    
    def retrieve_documents(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieve documents from Qdrant vector database"""
        try:
            docs = self.qdrant_db.similarity_search(query, k=top_k)
            results = []
            for doc in docs:
                results.append({
                    "text": doc.page_content,
                    "metadata": doc.metadata
                })
            return results
        except Exception as e:
            print(f"Error retrieving documents: {e}")
            return []
    
    def get_s3_document_content(self, bucket: str, key: str) -> Optional[str]:
        """Get document content from S3"""
        try:
            response = self.s3.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read().decode('utf-8')
            return content
        except Exception as e:
            print(f"Error getting S3 document: {e}")
            return None
    
    def process_s3_document(self, bucket: str, key: str) -> List[str]:
        """Process S3 document and add to vector store"""
        content = self.get_s3_document_content(bucket, key)
        if not content:
            return []
        
        # Add to vector store
        chunks = self.qdrant_db.add_document_from_text(
            content, 
            source=f"s3://{bucket}/{key}"
        )
        
        return chunks
    
    def generate_response(self, question: str, context: List[str]) -> str:
        """Generate response using Bedrock foundation model with context"""
        model_id = self.bedrock_model_id
        
        # Build prompt with context
        context_str = "\n\n".join(context) if context else "No context provided."
        prompt = f"""Based on the following context, answer the question.

Context:
{context_str}

Question: {question}

Answer:"""
        
        body = json.dumps({
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": 1024,
                "temperature": 0.7,
                "topP": 0.9
            }
        })
        
        response = self.bedrock_runtime.invoke_model(
            body=body,
            modelId=model_id,
            accept="application/json",
            contentType="application/json"
        )
        
        response_body = json.loads(response.get("body").read())
        return response_body.get("results", [{}])[0].get("outputText", "No answer generated.")
    
    def ask(self, question: str, bucket_name: Optional[str] = None, 
            document_key: Optional[str] = None, context_docs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Main method to process RAG query"""
        context = []
        sources = []
        
        # Option 1: Use context documents provided by user
        if context_docs:
            for doc in context_docs:
                text = doc.get("text", "")
                if text:
                    context.append(text)
                    sources.append({"source": doc.get("source", "unknown")})
        
        # Option 2: Process and retrieve from S3 document
        elif bucket_name and document_key:
            content = self.get_s3_document_content(bucket_name, document_key)
            if content:
                chunks = self.process_s3_document(bucket_name, document_key)
                context = chunks[:3]
                sources = [{"source": f"s3://{bucket_name}/{document_key}"}] * len(context)
        
        # Option 3: Retrieve from Qdrant vector database
        else:
            retrieved_docs = self.retrieve_documents(question, top_k=3)
            for doc in retrieved_docs:
                context.append(doc.get("text", ""))
                sources.append(doc.get("metadata", {}))
        
        # Generate response
        answer = self.generate_response(question, context[:5])
        
        return {
            "answer": answer,
            "sources": sources,
            "context_used": context[:5],
            "model_used": self.bedrock_model_id
        }
    
    def clear_vector_store(self):
        """Clear all documents from vector store"""
        self.qdrant_db.clear_collection()


# Global instance
rag_service = BedrockRAGService()

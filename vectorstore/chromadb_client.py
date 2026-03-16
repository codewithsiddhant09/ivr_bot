"""
ChromaDB client for vector storage and retrieval operations.
"""
import logging
import os
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional
import uuid

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from config import config
from utils.cache import embedding_cache, _embedding_lock, normalize_query
from utils.redis_cache import get_cache_service

logger = logging.getLogger(__name__)


class ChromaDBClient:
    """ChromaDB client for vector database operations."""
    
    def __init__(self):
        """Initialize ChromaDB client and embedding model."""
        try:
            # Store collection name
            self.collection_name = config.chromadb_collection_name
            
            # Ensure persist directory exists
            Path(config.chromadb_persist_directory).mkdir(parents=True, exist_ok=True)
            
            # Initialize ChromaDB client
            self.client = chromadb.PersistentClient(
                path=config.chromadb_persist_directory,
                settings=ChromaSettings(anonymized_telemetry=False)
            )
            
            # Initialize embeddings
            self.embeddings = HuggingFaceEmbeddings(
                model_name=config.embedding_model
            )
            
            # Get or create collection
            try:
                self.collection = self.client.get_collection(
                    name=config.chromadb_collection_name
                )
                logger.info(f"Loaded existing collection: {config.chromadb_collection_name}")
            except Exception:
                self.collection = self.client.create_collection(
                    name=config.chromadb_collection_name,
                    metadata={"description": "Privacy policy document chunks"}
                )
                logger.info(f"Created new collection: {config.chromadb_collection_name}")
            
            # Initialize text splitter
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap,
                length_function=len,
                separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB client: {e}")
            raise
    
    def load_and_chunk_document_from_text(self, text: str, metadata: Dict[str, Any]) -> List[Document]:
        """
        Load and chunk a document from text content.
        
        Args:
            text: Document text content
            metadata: Document metadata
            
        Returns:
            List of document chunks
        """
        try:
            # Split text into chunks
            chunks = self.text_splitter.split_text(text)
            
            # Create Document objects with metadata
            documents = []
            for i, chunk in enumerate(chunks):
                chunk_metadata = metadata.copy()
                chunk_metadata.update({
                    "chunk_id": i,
                    "chunk_size": len(chunk),
                    "total_chunks": len(chunks)
                })
                
                documents.append(Document(
                    page_content=chunk,
                    metadata=chunk_metadata
                ))
            
            logger.info(f"Created {len(documents)} document chunks")
            return documents
            
        except Exception as e:
            logger.error(f"Error chunking document: {e}")
            return []
    
    def add_documents(self, documents: List[Document]) -> bool:
        """
        Add documents to ChromaDB collection.
        
        Args:
            documents: List of document chunks to add
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not documents:
                logger.warning("No documents to add")
                return False
            
            # Prepare data for ChromaDB
            ids = [str(uuid.uuid4()) for _ in documents]
            texts = [doc.page_content for doc in documents]
            metadatas = [doc.metadata for doc in documents]
            
            # Generate embeddings
            embeddings = self.embeddings.embed_documents(texts)
            
            # Add to collection
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )
            
            logger.info(f"Successfully added {len(documents)} documents to ChromaDB")
            # Invalidate the cached count so next search sees the new docs
            self._count_ts = 0.0
            return True
            
        except Exception as e:
            logger.error(f"Error adding documents to ChromaDB: {e}")
            return False
    
    def search_similar_documents(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Search for similar documents using vector similarity.

        L1 = in-memory TTLCache (instant, per-process)
        L2 = Redis  ``rag:{sha256}``  TTL 6 h

        Args:
            query: Search query
            n_results: Number of results to return
        """
        from utils.cache import rag_cache, _rag_lock, normalize_query

        cache_key = (normalize_query(query), n_results)

        # --- L1 cache read (in-memory, thread-safe) ---
        with _rag_lock:
            cached = rag_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"RAG L1 HIT for query: '{query[:60]}'")
            return cached

        # --- L2 cache read (Redis) ---
        # Redis key incorporates n_results so different candidate counts don't collide
        redis_cache = get_cache_service()
        redis_key_text = f"{query}::n={n_results}"
        redis_value = redis_cache.get("rag", redis_key_text)
        if redis_value is not None:
            logger.debug(f"RAG L2 HIT for query: '{query[:60]}'")
            # Back-fill L1
            with _rag_lock:
                rag_cache[cache_key] = redis_value
            return redis_value

        try:
            # --- embed_query with per-query caching ---
            query_embedding = self._embed_query_cached(query)

            # Search in collection
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(n_results, self._get_collection_count_cached()),
                include=['documents', 'metadatas', 'distances']
            )

            # Format results
            formatted_results: List[Dict[str, Any]] = []
            if results['documents'] and results['documents'][0]:
                for i in range(len(results['documents'][0])):
                    formatted_results.append({
                        'content': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'distance': results['distances'][0][i]
                    })

            logger.debug(f"Found {len(formatted_results)} similar documents for query")

            # --- cache write L1 + L2 ---
            with _rag_lock:
                rag_cache[cache_key] = formatted_results
            redis_cache.set("rag", redis_key_text, formatted_results)

            return formatted_results

        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            return []

    # ------------------------------------------------------------------
    # Private caching helpers
    # ------------------------------------------------------------------

    def _embed_query_cached(self, query: str) -> List[float]:
        """
        Return the embedding vector for *query*, using the module-level
        embedding_cache to avoid redundant model inference.

        L1 = in-memory TTLCache (instant)
        L2 = Redis  ``embedding:{sha256}``  no TTL (deterministic)
        """
        cache_key = query  # embeddings are deterministic for identical strings

        # --- L1 read (in-memory) ---
        with _embedding_lock:
            cached = embedding_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Embedding L1 HIT for: '{query[:60]}'")
            return cached

        # --- L2 read (Redis) ---
        redis_cache = get_cache_service()
        redis_value = redis_cache.get("embedding", query)
        if redis_value is not None:
            logger.debug(f"Embedding L2 HIT for: '{query[:60]}'")
            # Back-fill L1
            with _embedding_lock:
                embedding_cache[cache_key] = redis_value
            return redis_value

        vector = self.embeddings.embed_query(query)

        # --- Write L1 + L2 ---
        with _embedding_lock:
            embedding_cache[cache_key] = vector
        redis_cache.set("embedding", query, vector)

        return vector

    def _get_collection_count_cached(self) -> int:
        """
        Return the collection document count.

        The count is stored as a plain instance attribute (_cached_count)
        and refreshed only when it is stale (older than 5 minutes), which
        means repeated calls within a session do not round-trip to ChromaDB.
        """
        import time

        now = time.monotonic()
        if not hasattr(self, '_cached_count') or (now - getattr(self, '_count_ts', 0)) > 300:
            try:
                self._cached_count: int = self.collection.count()
            except Exception as e:
                logger.error(f"Error getting collection count: {e}")
                self._cached_count = self._cached_count if hasattr(self, '_cached_count') else 0
            self._count_ts: float = now

        return self._cached_count

    def get_collection_count(self) -> int:
        """
        Get the number of documents in the collection.

        Returns:
            Document count
        """
        return self._get_collection_count_cached()

    def delete_collection(self) -> bool:
        """
        Delete the entire collection.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.delete_collection(name=config.chromadb_collection_name)
            logger.info(f"Deleted collection: {config.chromadb_collection_name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting collection: {e}")
            return False
    
    def reset_collection(self) -> bool:
        """
        Reset the collection by deleting and recreating it.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Delete existing collection
            try:
                self.client.delete_collection(name=config.chromadb_collection_name)
                logger.info(f"Deleted existing collection: {config.chromadb_collection_name}")
            except Exception:
                pass  # Collection might not exist
            
            # Create new collection
            self.collection = self.client.create_collection(
                name=config.chromadb_collection_name,
                metadata={"description": "Privacy policy document chunks"}
            )
            # Invalidate the cached count so next search re-fetches
            self._cached_count = 0
            self._count_ts = 0.0
            logger.info(f"Created new collection: {config.chromadb_collection_name}")
            return True
        except Exception as e:
            logger.error(f"Error resetting collection: {e}")
            return False
    
    def similarity_search(self, query: str, k: int = 3) -> List[Document]:
        """
        Search for similar documents (Langchain compatible interface).
        
        Args:
            query: Search query
            k: Number of results to return
            
        Returns:
            List of Document objects
        """
        try:
            results = self.search_similar_documents(query, n_results=k)
            documents = []
            for result in results:
                documents.append(Document(
                    page_content=result['content'],
                    metadata=result['metadata']
                ))
            return documents
        except Exception as e:
            logger.error(f"Error in similarity search: {e}")
            return []
    
    def get_collection_info(self) -> Dict[str, Any]:
        """
        Get information about the collection.
        
        Returns:
            Collection information
        """
        try:
            count = self.get_collection_count()
            collection_info = {
                'name': config.chromadb_collection_name,
                'document_count': count,
                'embedding_model': config.embedding_model,
                'persist_directory': config.chromadb_persist_directory
            }
            return collection_info
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {}
    
    def is_collection_empty(self) -> bool:
        """
        Check if the collection is empty.
        
        Returns:
            True if collection is empty, False otherwise
        """
        return self.get_collection_count() == 0


# Singleton instance
_chromadb_client = None

def get_chromadb_client() -> ChromaDBClient:
    """Get or create the ChromaDB client singleton."""
    global _chromadb_client
    if _chromadb_client is None:
        _chromadb_client = ChromaDBClient()
    return _chromadb_client

"""
Cross-encoder reranker for improving retrieval accuracy.
Uses sentence-transformers to rerank documents based on query relevance.
"""
import logging
from typing import List, Dict, Any, Tuple
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)


class Reranker:
    """Cross-encoder based reranker for document retrieval."""
    
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L6-v2"):
        """
        Initialize the reranker with a cross-encoder model.
        
        Args:
            model_name: Name of the cross-encoder model to use
        """
        self.model_name = model_name
        self._model = None
        logger.info(f"Reranker initialized with model: {model_name}")
    
    @property
    def model(self) -> CrossEncoder:
        """
        Lazy load the cross-encoder model.
        
        Returns:
            Loaded CrossEncoder model
        """
        if self._model is None:
            try:
                logger.info(f"Loading cross-encoder model: {self.model_name}")
                self._model = CrossEncoder(self.model_name)
                logger.info("Cross-encoder model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load cross-encoder model: {e}")
                raise
        return self._model
    
    def rerank(
        self, 
        query: str, 
        documents: List[Dict[str, Any]], 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents based on their relevance to the query.
        
        Args:
            query: Search query
            documents: List of document dictionaries with 'content' and 'metadata'
            top_k: Number of top documents to return after reranking
            
        Returns:
            Reranked list of documents (top_k most relevant)
        """
        if not documents:
            logger.warning("No documents to rerank")
            return []
        
        try:
            # Prepare query-document pairs for cross-encoder
            pairs = [(query, doc['content']) for doc in documents]
            
            # Get relevance scores from cross-encoder
            logger.debug(f"Reranking {len(documents)} documents")
            scores = self.model.predict(pairs)
            
            # Combine documents with their scores
            scored_docs = [
                {**doc, 'rerank_score': float(score)}
                for doc, score in zip(documents, scores)
            ]
            
            # Sort by rerank score (descending) and return top_k
            reranked = sorted(
                scored_docs, 
                key=lambda x: x['rerank_score'], 
                reverse=True
            )[:top_k]
            
            logger.debug(
                f"Reranking complete. Top score: {reranked[0]['rerank_score']:.4f}, "
                f"Bottom score: {reranked[-1]['rerank_score']:.4f}"
            )
            
            return reranked
            
        except Exception as e:
            logger.error(f"Error during reranking: {e}")
            # Fallback: return original documents without reranking
            logger.warning("Falling back to original document order")
            return documents[:top_k]
    
    def rerank_with_scores(
        self, 
        query: str, 
        documents: List[Dict[str, Any]]
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Rerank documents and return them with their scores.
        
        Args:
            query: Search query
            documents: List of document dictionaries
            
        Returns:
            List of (document, score) tuples sorted by relevance
        """
        if not documents:
            return []
        
        try:
            pairs = [(query, doc['content']) for doc in documents]
            scores = self.model.predict(pairs)
            
            # Create list of (document, score) tuples
            doc_score_pairs = list(zip(documents, scores))
            
            # Sort by score (descending)
            sorted_pairs = sorted(
                doc_score_pairs,
                key=lambda x: x[1],
                reverse=True
            )
            
            return sorted_pairs
            
        except Exception as e:
            logger.error(f"Error during reranking with scores: {e}")
            return [(doc, 0.0) for doc in documents]


# Singleton instance
_reranker = None

def get_reranker() -> Reranker:
    """Get or create the Reranker singleton."""
    global _reranker
    if _reranker is None:
        from config import config
        _reranker = Reranker(model_name=config.reranker_model)
    return _reranker

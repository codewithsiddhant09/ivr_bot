"""
Centralised Python-level caches for the VoiceBot server.

All cache instances are module-level singletons so they are shared across
the entire process regardless of import path.  Import the instances you
need directly:

    from utils.cache import (
        intent_cache,
        rag_cache,
        response_cache,
        embedding_cache,
        consent_cache,
        normalize_query,
    )

Cache sizing / TTL rationale
─────────────────────────────
intent_cache      300 entries / 30 min  – intents for unique query strings
rag_cache         150 entries / 10 min  – ChromaDB results; stale after doc updates
response_cache    200 entries / 60 min  – full LLM responses; safe to cache long
embedding_cache   512 entries / 60 min  – HuggingFace embed vectors; deterministic
consent_cache     256 entries / ∞ (LRU) – yes/no/keep/change: deterministic
"""

import re
import hashlib
import logging
import threading
from typing import Optional

from cachetools import TTLCache, LRUCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-safety locks
# Each cache gets its own lock so hot paths don't contend with cold ones.
# ---------------------------------------------------------------------------
_intent_lock = threading.Lock()
_rag_lock = threading.Lock()
_response_lock = threading.Lock()
_embedding_lock = threading.Lock()
_consent_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Cache instances
# ---------------------------------------------------------------------------

# Intent classification: (normalised_query,) → IntentType.value  (str)
intent_cache: TTLCache = TTLCache(maxsize=300, ttl=1800)  # 30 min

# RAG retrieval: (normalised_query, n_results) → List[Dict]
rag_cache: TTLCache = TTLCache(maxsize=150, ttl=600)  # 10 min

# Full LLM response: (normalised_query,) → str
response_cache: TTLCache = TTLCache(maxsize=200, ttl=3600)  # 60 min

# HuggingFace query embeddings: (query,) → List[float]
embedding_cache: TTLCache = TTLCache(maxsize=512, ttl=3600)  # 60 min

# Consent / schedule-change classification: (normalised_input,) → str
consent_cache: LRUCache = LRUCache(maxsize=256)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_query(text: str) -> str:
    """
    Normalise a query string for use as a cache key.

    Uses ``semantic_normalize`` from redis_cache to strip filler words so
    that "can you tell me a bit about your company" and "tell me about
    your company" produce the same key.
    """
    from utils.redis_cache import semantic_normalize
    return semantic_normalize(text)


def text_hash(text: str) -> str:
    """Return a short SHA-256 hex digest of *text* suitable as a cache key."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def get_cache_stats() -> dict:
    """Return current size and max-size for every cache (useful for monitoring)."""
    return {
        "intent":     {"size": len(intent_cache),    "maxsize": intent_cache.maxsize},
        "rag":        {"size": len(rag_cache),        "maxsize": rag_cache.maxsize},
        "response":   {"size": len(response_cache),   "maxsize": response_cache.maxsize},
        "embedding":  {"size": len(embedding_cache),  "maxsize": embedding_cache.maxsize},
        "consent":    {"size": len(consent_cache),    "maxsize": consent_cache.maxsize},
    }

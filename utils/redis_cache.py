"""
Production-grade Redis caching layer for the VoiceBot server.

Architecture
────────────
L1 = in-memory cachetools (instant, per-process, lost on restart)
L2 = Redis              (shared across processes, survives restarts)

The CacheService wraps Redis with:
  • normalisation + SHA-256 hashing for keys
  • msgpack serialisation for values (fast, compact)
  • graceful degradation: every Redis call is wrapped so a Redis outage
    never breaks the application — it just falls through to L1 / LLM.
  • configurable TTLs per prefix

Key format:  {prefix}:{sha256_hex}
Prefixes:
  intent            – TTL 24 h
  embedding         – no TTL  (deterministic)
  rag               – TTL 6 h
  response          – TTL 2 h
  intent_response   – TTL 6 h  (intent-level FAQ cache)
"""

import hashlib
import json
import logging
import math
import re
import time as _time
from typing import Any, Dict, List, Optional, Tuple

import redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Text helpers (same logic as utils/cache.normalize_query but standalone)
# ---------------------------------------------------------------------------

# Filler / padding words that don't change the semantic meaning of a query.
# Removing these ensures "can you tell me a bit about your company" and
# "tell me about your company" produce the same cache key.
_FILLER_WORDS = frozenset({
    # conversational openers / fillers
    "okay", "ok", "hey", "hi", "hello", "so", "well", "um", "uh", "hmm",
    "alright", "right", "sure", "yeah", "yes", "no", "please", "thanks",
    "thank", "you", "kindly",
    # padding verbs / auxiliaries
    "can", "could", "would", "will", "shall", "may", "might",
    "do", "does", "did",
    # padding pronouns / articles / prepositions that add no meaning
    "me", "i", "my", "a", "an", "the", "of", "to", "in", "for", "on",
    "with", "at", "by", "from", "is", "are", "was", "were", "be", "been",
    "it", "its", "this", "that", "those", "these",
    # padding adverbs
    "just", "also", "really", "actually", "basically", "simply",
    "bit", "little", "some", "more", "very", "quite",
    # question words that don't distinguish meaning when combined with content
    "tell", "know", "about", "give", "share", "explain", "describe",
})


def normalize_text(text: str) -> str:
    """
    Normalise a text string for use as a cache key seed.

    - lowercase
    - strip leading/trailing whitespace
    - collapse multiple spaces to one
    - remove punctuation except apostrophes
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def semantic_normalize(text: str) -> str:
    """
    Aggressively normalise text for cache-key purposes by stripping
    filler words so that semantically equivalent queries produce the
    same hash.

    Examples:
        "can you tell me a bit about your company"  → "company"
        "tell me about your company"                 → "company"
        "okay what is the location of a company"     → "what location company"
        "what services do you offer"                 → "what services offer"
        "what services do you provide"               → "what services provide"
    """
    text = normalize_text(text)
    words = [w for w in text.split() if w not in _FILLER_WORDS]
    # If stripping removes everything, fall back to basic normalization
    return " ".join(words) if words else text


def hash_text(text: str) -> str:
    """Full SHA-256 hex digest of *text*."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_key(prefix: str, raw_text: str) -> str:
    """Build a Redis key: ``{prefix}:{sha256(semantic_normalised_text)}``."""
    return f"{prefix}:{hash_text(semantic_normalize(raw_text))}"


# ---------------------------------------------------------------------------
# Default TTLs (seconds) — None means no expiry
# ---------------------------------------------------------------------------
DEFAULT_TTLS = {
    "intent":           86400,   # 24 hours
    "embedding":        None,    # never expires (deterministic)
    "rag":              21600,   # 6 hours
    "response":         7200,    # 2 hours
    "intent_response":  21600,   # 6 hours
}


# ---------------------------------------------------------------------------
# CacheService
# ---------------------------------------------------------------------------

class CacheService:
    """
    Async-safe Redis caching service with graceful fallback.

    All public methods swallow Redis exceptions so callers never need to
    worry about connectivity.  A ``connected`` flag lets callers skip Redis
    entirely after an initial connection failure.

    Usage::

        cache = CacheService(host="localhost", port=6379, db=2)
        cache.set("intent", "what services do you offer", "query")
        val = cache.get("intent", "what services do you offer")
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 2,
        password: Optional[str] = None,
    ):
        self.connected: bool = False
        self._client: Optional[redis.Redis] = None

        try:
            self._client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=False,  # we handle encoding ourselves
                socket_connect_timeout=3,
                socket_timeout=2,
                retry_on_timeout=True,
            )
            self._client.ping()
            self.connected = True
            logger.info(f"Redis cache connected ({host}:{port} db={db})")
        except Exception as e:
            logger.warning(f"Redis cache unavailable ({host}:{port}): {e}")
            logger.warning("Running without Redis L2 cache — in-memory only")
            self._client = None

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialise(value: Any) -> bytes:
        """Serialise a Python object to bytes via JSON."""
        return json.dumps(value, default=str).encode("utf-8")

    @staticmethod
    def _deserialise(raw: bytes) -> Any:
        """Deserialise bytes back to a Python object."""
        return json.loads(raw.decode("utf-8"))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, prefix: str, raw_text: str) -> Optional[Any]:
        """
        Retrieve a cached value.

        Returns ``None`` on miss or if Redis is unavailable.
        """
        if not self.connected or not self._client:
            return None
        try:
            key = make_key(prefix, raw_text)
            raw = self._client.get(key)
            if raw is None:
                return None
            return self._deserialise(raw)
        except Exception as e:
            logger.debug(f"Redis GET error ({prefix}): {e}")
            return None

    def get_by_key(self, key: str) -> Optional[Any]:
        """
        Retrieve a cached value using a pre-built key (e.g. intent_response keys).
        """
        if not self.connected or not self._client:
            return None
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            return self._deserialise(raw)
        except Exception as e:
            logger.debug(f"Redis GET error (key={key}): {e}")
            return None

    def set(
        self,
        prefix: str,
        raw_text: str,
        value: Any,
        ttl: Optional[int] = ...,          # sentinel: use default
    ) -> bool:
        """
        Store a value in Redis.

        If *ttl* is not supplied the default for the prefix is used.
        Pass ``ttl=None`` explicitly for no expiry.
        Returns True on success, False on failure / unavailable.
        """
        if not self.connected or not self._client:
            return False
        try:
            key = make_key(prefix, raw_text)
            data = self._serialise(value)

            # Resolve TTL
            if ttl is ...:
                ttl = DEFAULT_TTLS.get(prefix)

            if ttl is not None:
                self._client.setex(key, ttl, data)
            else:
                self._client.set(key, data)
            return True
        except Exception as e:
            logger.debug(f"Redis SET error ({prefix}): {e}")
            return False

    def set_by_key(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Store a value using a pre-built key."""
        if not self.connected or not self._client:
            return False
        try:
            data = self._serialise(value)
            if ttl is not None:
                self._client.setex(key, ttl, data)
            else:
                self._client.set(key, data)
            return True
        except Exception as e:
            logger.debug(f"Redis SET error (key={key}): {e}")
            return False

    def exists(self, prefix: str, raw_text: str) -> bool:
        """Check if a key exists. Returns False if Redis is unavailable."""
        if not self.connected or not self._client:
            return False
        try:
            return bool(self._client.exists(make_key(prefix, raw_text)))
        except Exception:
            return False

    def delete(self, prefix: str, raw_text: str) -> bool:
        """Delete a key. Returns True on success."""
        if not self.connected or not self._client:
            return False
        try:
            self._client.delete(make_key(prefix, raw_text))
            return True
        except Exception:
            return False

    def flush_prefix(self, prefix: str) -> int:
        """
        Delete all keys with the given prefix (e.g. flush all RAG caches).
        Uses SCAN to avoid blocking.
        Returns count of deleted keys.
        """
        if not self.connected or not self._client:
            return 0
        try:
            count = 0
            cursor = 0
            pattern = f"{prefix}:*"
            while True:
                cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    self._client.delete(*keys)
                    count += len(keys)
                if cursor == 0:
                    break
            logger.info(f"Flushed {count} keys with prefix '{prefix}'")
            return count
        except Exception as e:
            logger.warning(f"Redis flush_prefix error ({prefix}): {e}")
            return 0

    def get_stats(self) -> dict:
        """Return basic Redis info for monitoring."""
        if not self.connected or not self._client:
            return {"connected": False}
        try:
            info = self._client.info(section="keyspace")
            db_info = info.get(f"db{self._client.connection_pool.connection_kwargs.get('db', 0)}", {})
            return {
                "connected": True,
                "keys": db_info.get("keys", 0),
                "expires": db_info.get("expires", 0),
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}


# ---------------------------------------------------------------------------
# SemanticCache — embedding-based similarity matching
# ---------------------------------------------------------------------------

def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors. Pure Python, no numpy."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SemanticCache:
    """
    Embedding-based semantic cache that matches queries by vector similarity
    rather than exact text match.

    Architecture:
        - Stores entries in a Redis list ``sem_cache:entries`` as JSON objects
          containing {embedding, response, intent, query, timestamp}.
        - On lookup, computes cosine similarity between the incoming query
          embedding and every stored embedding.
        - If best match ≥ threshold → cache HIT, return stored response.
        - Max entries capped to prevent unbounded growth.

    This catches cases like:
        "what does your company do" ↔ "tell me about your company"
    that filler-word stripping alone cannot handle.

    Performance:
        - ~1-3ms for 200 entries (pure-Python cosine, 384-dim vectors)
        - Embedding is REUSED from the RAG pipeline (already computed)
        - So net cost = only the cosine scan, not an extra embedding call
    """

    REDIS_KEY = "sem_cache:entries"
    DEFAULT_THRESHOLD = 0.88
    DEFAULT_MAX_ENTRIES = 200
    DEFAULT_TTL = 7200  # 2 hours

    def __init__(
        self,
        cache_service: "CacheService",
        threshold: float = DEFAULT_THRESHOLD,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        ttl: int = DEFAULT_TTL,
    ):
        self._cache = cache_service
        self._threshold = threshold
        self._max_entries = max_entries
        self._ttl = ttl

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def find(self, query_embedding: List[float]) -> Optional[Dict[str, Any]]:
        """
        Search for a semantically similar cached entry.

        Args:
            query_embedding: The embedding vector of the incoming query.

        Returns:
            ``{"response": str, "intent": str, "query": str}`` on hit,
            or ``None`` on miss.
        """
        if not self._cache.connected or not self._cache._client:
            return None
        try:
            raw_entries = self._cache._client.lrange(self.REDIS_KEY, 0, -1)
            if not raw_entries:
                return None

            best_score = -1.0
            best_entry = None
            now = _time.time()

            for raw in raw_entries:
                entry = json.loads(raw.decode("utf-8"))

                # Skip expired entries
                if now - entry.get("ts", 0) > self._ttl:
                    continue

                score = _cosine_similarity(query_embedding, entry["emb"])
                if score > best_score:
                    best_score = score
                    best_entry = entry

            if best_score >= self._threshold and best_entry is not None:
                logger.info(
                    f"Semantic cache HIT ({best_score:.3f}): "
                    f"'{best_entry.get('q', '')[:60]}'"
                )
                return {
                    "response": best_entry["res"],
                    "intent": best_entry["int"],
                    "query": best_entry.get("q", ""),
                }

            logger.debug(f"Semantic cache MISS (best={best_score:.3f}, threshold={self._threshold})")
            return None

        except Exception as e:
            logger.debug(f"Semantic cache find error: {e}")
            return None

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def store(
        self,
        query: str,
        query_embedding: List[float],
        response: str,
        intent: str,
    ) -> bool:
        """
        Add a new entry to the semantic cache.

        Args:
            query: Original query text (for logging / debugging)
            query_embedding: Embedding vector
            response: The LLM-generated response
            intent: Intent classification result
        """
        if not self._cache.connected or not self._cache._client:
            return False
        try:
            entry = json.dumps({
                "q": query[:200],           # truncate for storage
                "emb": query_embedding,
                "res": response,
                "int": intent,
                "ts": _time.time(),
            }).encode("utf-8")

            pipe = self._cache._client.pipeline()
            pipe.lpush(self.REDIS_KEY, entry)
            pipe.ltrim(self.REDIS_KEY, 0, self._max_entries - 1)  # cap size
            pipe.execute()

            logger.debug(f"Semantic cache stored: '{query[:60]}' (intent={intent})")
            return True

        except Exception as e:
            logger.debug(f"Semantic cache store error: {e}")
            return False

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def cleanup_expired(self) -> int:
        """Remove expired entries. Call periodically if desired."""
        if not self._cache.connected or not self._cache._client:
            return 0
        try:
            raw_entries = self._cache._client.lrange(self.REDIS_KEY, 0, -1)
            now = _time.time()
            kept = []
            removed = 0
            for raw in raw_entries:
                entry = json.loads(raw.decode("utf-8"))
                if now - entry.get("ts", 0) <= self._ttl:
                    kept.append(raw)
                else:
                    removed += 1
            if removed > 0:
                pipe = self._cache._client.pipeline()
                pipe.delete(self.REDIS_KEY)
                for item in kept:
                    pipe.rpush(self.REDIS_KEY, item)
                pipe.execute()
                logger.info(f"Semantic cache cleanup: removed {removed} expired entries")
            return removed
        except Exception as e:
            logger.debug(f"Semantic cache cleanup error: {e}")
            return 0

    def count(self) -> int:
        """Return current entry count."""
        if not self._cache.connected or not self._cache._client:
            return 0
        try:
            return self._cache._client.llen(self.REDIS_KEY)
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_cache_instance: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """
    Get or create the module-level CacheService singleton.

    Uses settings from ``src/config/settings.py``.
    """
    global _cache_instance
    if _cache_instance is None:
        try:
            from config import config as cfg
            _cache_instance = CacheService(
                host=cfg.redis_host,
                port=cfg.redis_port,
                db=getattr(cfg, "redis_cache_db", 2),
                password=cfg.redis_password,
            )
        except Exception as e:
            logger.error(f"Failed to create CacheService: {e}")
            # Return a disconnected instance so callers never get None
            _cache_instance = CacheService(host="__invalid__", port=0)
    return _cache_instance


_semantic_cache_instance: Optional[SemanticCache] = None


def get_semantic_cache() -> SemanticCache:
    """Get or create the module-level SemanticCache singleton."""
    global _semantic_cache_instance
    if _semantic_cache_instance is None:
        _semantic_cache_instance = SemanticCache(get_cache_service())
    return _semantic_cache_instance

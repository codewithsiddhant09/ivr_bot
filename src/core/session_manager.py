# """
# Session management using Redis for caching queries and responses.
# """
# import json
# import logging
# import uuid
# import re
# from datetime import datetime, timedelta
# from typing import Optional, Dict, Any, Tuple, List
# import redis
# from uuid import uuid4
# from langchain_openai import ChatOpenAI

# from config import config

# logger = logging.getLogger(__name__)


# class SessionManager:
#     """Manages user sessions and query caching using Redis."""
    
#     def __init__(self):
#         """Initialize Redis connection and session management."""
#         self.redis_available = False
        
#         # In-memory fallback storage for when Redis is unavailable
#         self.memory_sessions = {}  # {session_id: session_data}
#         self.memory_contact_states = {}  # {session_id: state}
#         self.memory_contact_data = {}  # {session_id: data}
#         self.memory_history = {}  # {session_id: [messages]}
        
#         try:
#             self.redis_client = redis.Redis(
#                 host=config.redis_host,
#                 port=config.redis_port,
#                 db=config.redis_db,
#                 password=config.redis_password,
#                 decode_responses=config.redis_decode_responses
#             )
#             # Test connection
#             self.redis_client.ping()
#             self.redis_available = True
#             logger.info("Successfully connected to Redis")
            
#             # Initialize LLM for semantic matching
#             self.llm = ChatOpenAI(
#                 model="gpt-4.1-nano",
#                 temperature=0.0,
#                 openai_api_key=config.openai_api_key
#             )
#         except Exception as e:
#             logger.warning(f"Failed to connect to Redis: {e}")
#             logger.warning("Running without Redis - using in-memory session storage")
#             self.redis_client = None
#             self.llm = None
    
#     def create_session(self) -> str:
#         """
#         Create a new session and initialize with user details collection.
        
#         Returns:
#             Session ID
#         """
#         session_id = str(uuid4())
        
#         session_data = {
#             "created_at": datetime.now().isoformat(),
#             "last_activity": datetime.now().isoformat(),
#             "query_count": 0
#         }
        
#         if not self.redis_available:
#             # Store in memory
#             self.memory_sessions[session_id] = session_data
#             self.memory_contact_states[session_id] = "initial_collecting_name"
#             self.memory_history[session_id] = []
#             logger.info(f"Created new session in memory: {session_id}")
#             return session_id
        
#         try:
#             # Store session data with expiration
#             self.redis_client.setex(
#                 f"session:{session_id}",
#                 config.session_timeout,
#                 json.dumps(session_data)
#             )
            
#             # Initialize contact form state to collect user details
#             self.set_contact_form_state(session_id, "initial_collecting_name")
            
#             logger.info(f"Created new session: {session_id} with initial user details collection")
#             return session_id
#         except Exception as e:
#             logger.error(f"Failed to create session: {e}")
#             return session_id  # Return session ID even if Redis fails
    
#     def is_session_valid(self, session_id: str) -> bool:
#         """
#         Check if a session is valid and active.
        
#         Args:
#             session_id: Session identifier
            
#         Returns:
#             True if session is valid, False otherwise
#         """
#         if not self.redis_available:
#             return session_id in self.memory_sessions
        
#         try:
#             return self.redis_client.exists(f"session:{session_id}")
#         except Exception as e:
#             logger.error(f"Failed to check session validity: {e}")
#             return False
    
#     def update_session_activity(self, session_id: str) -> bool:
#         """
#         Update the last activity timestamp for a session.
        
#         Args:
#             session_id: Session identifier
            
#         Returns:
#             True if updated successfully, False otherwise
#         """
#         if not self.redis_available:
#             if session_id in self.memory_sessions:
#                 self.memory_sessions[session_id]["last_activity"] = datetime.now().isoformat()
#                 self.memory_sessions[session_id]["query_count"] = self.memory_sessions[session_id].get("query_count", 0) + 1
#                 return True
#             return False
        
#         try:
#             session_key = f"session:{session_id}"
#             session_data_str = self.redis_client.get(session_key)
            
#             if not session_data_str:
#                 return False
            
#             session_data = json.loads(session_data_str)
#             session_data["last_activity"] = datetime.now().isoformat()
#             session_data["query_count"] = session_data.get("query_count", 0) + 1
            
#             # Update with extended expiration
#             self.redis_client.setex(
#                 session_key,
#                 config.session_timeout,
#                 json.dumps(session_data)
#             )
#             return True
#         except Exception as e:
#             logger.error(f"Failed to update session activity: {e}")
#             return False
    
#     # ==================================================================================
#     # DEPRECATED: Redis caching methods - replaced by OpenAI's store parameter
#     # OpenAI now handles conversation storage with store=True in model_kwargs
#     # Keeping these methods commented for potential rollback
#     # ==================================================================================
    
#     # def cache_query_response(self, session_id: str, query: str, response: str) -> bool:
#     #     """
#     #     Cache a query-response pair for the session.
#     #     
#     #     Args:
#     #         session_id: Session identifier
#     #         query: User query
#     #         response: Bot response
#     #         
#     #     Returns:
#     #         True if cached successfully, False otherwise
#     #     """
#     #     try:
#     #         # Normalize query for consistent caching
#     #         normalized_query = self._normalize_query_for_cache(query)
#     #         cache_key = f"cache:{session_id}:{hash(normalized_query)}"
#     #         
#     #         cache_data = {
#     #             "original_query": query,
#     #             "normalized_query": normalized_query,
#     #             "response": response,
#     #             "timestamp": datetime.now().isoformat()
#     #         }
#     #         
#     #         # Cache with session timeout
#     #         self.redis_client.setex(
#     #             cache_key,
#     #             config.session_timeout,
#     #             json.dumps(cache_data)
#     #         )
#     #         
#     #         logger.debug(f"Cached query-response for session {session_id}")
#     #         return True
#     #     except Exception as e:
#     #         logger.error(f"Failed to cache query-response: {e}")
#     #         return False
#     # 
#     # def get_cached_response(self, session_id: str, query: str) -> Optional[str]:
#     #     """
#     #     Retrieve a cached response for a query in the session.
#     #     Uses semantic similarity to find similar cached queries.
#     #     
#     #     Args:
#     #         session_id: Session identifier
#     #         query: User query
#     #         
#     #     Returns:
#     #         Cached response if found, None otherwise
#     #     """
#     #     try:
#     #         # First try exact match
#     #         normalized_query = self._normalize_query_for_cache(query)
#     #         cache_key = f"cache:{session_id}:{hash(normalized_query)}"
#     #         
#     #         cached_data_str = self.redis_client.get(cache_key)
#     #         if cached_data_str:
#     #             cached_data = json.loads(cached_data_str)
#     #             logger.debug(f"Found exact cached response for session {session_id}")
#     #             return cached_data["response"]
#     #         
#     #         # If no exact match, try semantic similarity
#     #         return self._find_similar_cached_response(session_id, normalized_query)
#     #         
#     #     except Exception as e:
#     #         logger.error(f"Failed to retrieve cached response: {e}")
#     #         return None


#     # Conversation history helpers
#     def append_message_to_history(self, session_id: str, role: str, message: str) -> bool:
#         """
#         Append a message to the session conversation history stored in Redis as a list.

#         Args:
#             session_id: Session identifier
#             role: 'user' or 'bot'
#             message: Message text

#         Returns:
#             True if appended successfully, False otherwise
#         """
#         if not self.redis_available:
#             if session_id not in self.memory_history:
#                 self.memory_history[session_id] = []
#             entry = {"role": role, "message": message, "ts": datetime.now().isoformat()}
#             self.memory_history[session_id].append(entry)
#             return True
        
#         try:
#             history_key = f"session:{session_id}:history"
#             entry = json.dumps({"role": role, "message": message, "ts": datetime.now().isoformat()})
#             # Use RPUSH to keep messages in chronological order
#             self.redis_client.rpush(history_key, entry)
#             # Ensure history expires with session
#             self.redis_client.expire(history_key, config.session_timeout)
#             return True
#         except Exception as e:
#             logger.error(f"Failed to append message to history: {e}")
#             return False

#     def get_session_history(self, session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
#         """
#         Retrieve the conversation history for a session.

#         Args:
#             session_id: Session identifier
#             limit: Optional max number of recent messages to return (most recent last)

#         Returns:
#             List of history entries as dicts
#         """
#         if not self.redis_available:
#             history = self.memory_history.get(session_id, [])
#             if limit is not None and limit > 0:
#                 return history[-limit:]
#             return history
        
#         try:
#             history_key = f"session:{session_id}:history"
#             items = self.redis_client.lrange(history_key, 0, -1)
#             if not items:
#                 return []
#             parsed = [json.loads(item) for item in items]
#             if limit is not None and limit > 0:
#                 return parsed[-limit:]
#             return parsed
#         except Exception as e:
#             logger.error(f"Failed to get session history: {e}")
#             return []

#     def get_last_user_query(self, session_id: str, skip_current: bool = False) -> Optional[str]:
#         """
#         Return the most recent user message from session history.
        
#         Args:
#             session_id: Session identifier
#             skip_current: If True, skip the most recent message and return the previous one
        
#         Returns:
#             The last user query, or None if not found
#         """
#         try:
#             history = self.get_session_history(session_id, limit=20)
#             # iterate from the end backwards
#             count = 0
#             for entry in reversed(history):
#                 if entry.get('role') == 'user':
#                     if skip_current and count == 0:
#                         count += 1
#                         continue
#                     return entry.get('message')
#             return None
#         except Exception as e:
#             logger.error(f"Failed to get last user query: {e}")
#             return None
    
#     def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
#         """
#         Get session information.
        
#         Args:
#             session_id: Session identifier
            
#         Returns:
#             Session data if found, None otherwise
#         """
#         try:
#             session_data_str = self.redis_client.get(f"session:{session_id}")
#             if not session_data_str:
#                 return None
            
#             return json.loads(session_data_str)
#         except Exception as e:
#             logger.error(f"Failed to get session info: {e}")
#             return None
    
#     def clear_session(self, session_id: str) -> bool:
#         """
#         Clear all session data and cache.
        
#         Args:
#             session_id: Session identifier
            
#         Returns:
#             True if cleared successfully, False otherwise
#         """
#         if not self.redis_available:
#             # Clear from memory
#             self.memory_sessions.pop(session_id, None)
#             self.memory_contact_states.pop(session_id, None)
#             self.memory_contact_data.pop(session_id, None)
#             self.memory_history.pop(session_id, None)
#             logger.info(f"Cleared session from memory: {session_id}")
#             return True
        
#         try:
#             # Delete session data
#             session_key = f"session:{session_id}"
#             self.redis_client.delete(session_key)
            
#             # Delete all cached queries for this session
#             cache_pattern = f"cache:{session_id}:*"
#             cached_keys = self.redis_client.keys(cache_pattern)
            
#             if cached_keys:
#                 self.redis_client.delete(*cached_keys)
            
#             logger.info(f"Cleared session and cache for session {session_id}")
#             return True
#         except Exception as e:
#             logger.error(f"Failed to clear session: {e}")
#             return False
    
#     def get_all_sessions(self) -> list:
#         """
#         Get all active session IDs.
        
#         Returns:
#             List of session IDs
#         """
#         try:
#             session_keys = self.redis_client.keys("session:*")
#             return [key.replace("session:", "") for key in session_keys]
#         except Exception as e:
#             logger.error(f"Failed to get all sessions: {e}")
#             return []
    
#     def _normalize_query_for_cache(self, query: str) -> str:
#         """
#         Normalize a query for caching by removing punctuation, extra spaces, and lowercasing.
        
#         Args:
#             query: Original query string
            
#         Returns:
#             Normalized query string
#         """
#         # Convert to lowercase
#         normalized = query.lower().strip()
#         # Remove punctuation and extra spaces
#         normalized = re.sub(r'[^\w\s]', '', normalized)
#         normalized = re.sub(r'\s+', ' ', normalized)
#         return normalized
    
#     def _find_similar_cached_response(self, session_id: str, normalized_query: str) -> Optional[str]:
#         """
#         Find a semantically similar cached query using LLM.
        
#         Args:
#             session_id: Session identifier
#             normalized_query: Normalized query string
            
#         Returns:
#             Cached response if similar query found, None otherwise
#         """
#         try:
#             # Get all cached queries for this session
#             cache_pattern = f"cache:{session_id}:*"
#             cached_keys = self.redis_client.keys(cache_pattern)
            
#             # Skip LLM call if no cached queries exist
#             if not cached_keys:
#                 logger.debug("No cached queries to check - skipping semantic similarity")
#                 return None
            
#             # Retrieve all cached queries
#             cached_queries = []
#             for key in cached_keys:
#                 cached_data_str = self.redis_client.get(key)
#                 if cached_data_str:
#                     cached_data = json.loads(cached_data_str)
#                     cached_queries.append({
#                         'normalized_query': cached_data.get('normalized_query', ''),
#                         'original_query': cached_data.get('original_query', ''),
#                         'response': cached_data['response']
#                     })
            
#             # Skip LLM call if no valid cached queries
#             if not cached_queries:
#                 logger.debug("No valid cached queries - skipping semantic similarity")
#                 return None
            
#             # Use LLM to check semantic similarity against ALL cached queries in one call
#             similar_index = self._find_similar_query_index(normalized_query, cached_queries)
            
#             if similar_index is not None:
#                 logger.debug(f"Found semantically similar cached response for session {session_id}")
#                 return cached_queries[similar_index]['response']
            
#             return None
            
#         except Exception as e:
#             logger.error(f"Error finding similar cached response: {e}")
#             return None
    
#     def _find_similar_query_index(self, new_query: str, cached_queries: List[Dict[str, Any]]) -> Optional[int]:
#         """
#         Find if the new query is similar to any cached query using a single LLM call.
        
#         Args:
#             new_query: The new query to check
#             cached_queries: List of cached query dictionaries
            
#         Returns:
#             Index of the similar query, or None if no match
#         """
#         try:
#             if not cached_queries:
#                 return None
            
#             # Build a prompt that checks against all cached queries at once
#             cached_list = "\n".join([f"{i+1}. {q['normalized_query']}" for i, q in enumerate(cached_queries)])
            
#             prompt = f"""You are comparing a new user question against previous questions to find if it's asking about the same topic.

# New Question: "{new_query}"

# Previous Questions:
# {cached_list}

# If the new question is asking about the SAME TOPIC as any of the previous questions (even with different wording, or asking to repeat/clarify), respond with the NUMBER of that question.

# If the new question is about a DIFFERENT TOPIC from all previous questions, respond with "NONE".

# Examples:
# - "what are child safety measures" and "tell me about child safety" = SAME (respond with the number)
# - "what are cookies" and "what data do you collect" = DIFFERENT (respond with NONE)

# Respond with only the NUMBER (1, 2, 3, etc.) or NONE:"""

#             response = self.llm.invoke(prompt)
#             answer = response.content.strip().upper() if hasattr(response, 'content') else str(response).strip().upper()
            
#             # Parse the response
#             if 'NONE' in answer:
#                 return None
            
#             # Try to extract a number
#             import re
#             numbers = re.findall(r'\d+', answer)
#             if numbers:
#                 index = int(numbers[0]) - 1  # Convert to 0-based index
#                 if 0 <= index < len(cached_queries):
#                     logger.debug(f"Semantic match found: '{new_query}' matches cached query #{index+1}")
#                     return index
            
#             return None
            
#         except Exception as e:
#             logger.error(f"Error finding similar query index: {e}")
#             return None
    
#     def get_contact_form_state(self, session_id: str) -> str:
#         """
#         Get the current contact form state for a session.
        
#         Args:
#             session_id: Session identifier
            
#         Returns:
#             Contact form state (default: 'idle')
#         """
#         if not self.redis_available:
#             return self.memory_contact_states.get(session_id, "idle")
        
#         try:
#             state_key = f"session:{session_id}:contact_form_state"
#             state = self.redis_client.get(state_key)
#             return state if state else "idle"
#         except Exception as e:
#             logger.error(f"Failed to get contact form state: {e}")
#             return "idle"

#     def set_contact_form_state(self, session_id: str, state: str) -> bool:
#         """
#         Set the contact form state for a session.
        
#         Args:
#             session_id: Session identifier
#             state: New contact form state
            
#         Returns:
#             True if set successfully, False otherwise
#         """
#         if not self.redis_available:
#             self.memory_contact_states[session_id] = state
#             return True
        
#         try:
#             state_key = f"session:{session_id}:contact_form_state"
#             self.redis_client.setex(state_key, config.session_timeout, state)
#             return True
#         except Exception as e:
#             logger.error(f"Failed to set contact form state: {e}")
#             return False

#     def get_contact_form_data(self, session_id: str) -> dict:
#         """
#         Get the partially collected contact form data for a session.
        
#         Args:
#             session_id: Session identifier
            
#         Returns:
#             Contact form data dictionary
#         """
#         if not self.redis_available:
#             return self.memory_contact_data.get(session_id, {})
        
#         try:
#             data_key = f"session:{session_id}:contact_form_data"
#             data_str = self.redis_client.get(data_key)
#             return json.loads(data_str) if data_str else {}
#         except Exception as e:
#             logger.error(f"Failed to get contact form data: {e}")
#             return {}

#     def set_contact_form_data(self, session_id: str, data: dict) -> bool:
#         """
#         Set the contact form data for a session.
        
#         Args:
#             session_id: Session identifier
#             data: Contact form data dictionary
            
#         Returns:
#             True if set successfully, False otherwise
#         """
#         if not self.redis_available:
#             self.memory_contact_data[session_id] = data
#             return True
        
#         try:
#             data_key = f"session:{session_id}:contact_form_data"
#             self.redis_client.setex(data_key, config.session_timeout, json.dumps(data))
#             return True
#         except Exception as e:
#             logger.error(f"Failed to set contact form data: {e}")
#             return False

#     def clear_contact_form(self, session_id: str) -> bool:
#         """
#         Clear contact form state and data for a session.
        
#         Args:
#             session_id: Session identifier
            
#         Returns:
#             True if cleared successfully, False otherwise
#         """
#         try:
#             state_key = f"session:{session_id}:contact_form_state"
#             data_key = f"session:{session_id}:contact_form_data"
#             self.redis_client.delete(state_key, data_key)
#             return True
#         except Exception as e:
#             logger.error(f"Failed to clear contact form: {e}")
#             return False
    
#     def close(self):
#         """Close the Redis connection."""
#         try:
#             if hasattr(self, 'redis_client'):
#                 self.redis_client.close()
#                 logger.info("Redis connection closed")
#         except Exception as e:
#             logger.error(f"Error closing Redis connection: {e}")


# # Create a global session manager instance
# session_manager = SessionManager()

# # Create a global session manager instance
# session_manager = SessionManager()


"""
Session management using Redis for caching queries and responses.
"""
import json
import logging
import uuid
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List
import redis
from uuid import uuid4
from langchain_openai import ChatOpenAI

from config import config

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages user sessions and query caching using Redis."""
    
    def __init__(self):
        """Initialize Redis connection and session management."""
        self.redis_available = False
        
        # In-memory fallback storage for when Redis is unavailable
        self.memory_sessions = {}  # {session_id: session_data}
        self.memory_contact_states = {}  # {session_id: state}
        self.memory_contact_data = {}  # {session_id: data}
        self.memory_history = {}  # {session_id: [messages]}
        
        try:
            self.redis_client = redis.Redis(
                host=config.redis_host,
                port=config.redis_port,
                db=config.redis_db,
                password=config.redis_password,
                decode_responses=config.redis_decode_responses
            )
            # Test connection
            self.redis_client.ping()
            self.redis_available = True
            logger.info("Successfully connected to Redis")
            
            # Initialize LLM for semantic matching
            self.llm = ChatOpenAI(
                model="gpt-4.1-nano",
                temperature=0.0,
                openai_api_key=config.openai_api_key
            )
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            logger.warning("Running without Redis - using in-memory session storage")
            self.redis_client = None
            self.llm = None
    
    def create_session(self) -> str:
        """
        Create a new session and initialize with user details collection.
        
        Returns:
            Session ID
        """
        session_id = str(uuid4())
        
        session_data = {
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
            "query_count": 0
        }
        
        if not self.redis_available:
            # Store in memory
            self.memory_sessions[session_id] = session_data
            self.memory_contact_states[session_id] = "idle"
            self.memory_history[session_id] = []
            logger.info(f"Created new session in memory: {session_id}")
            return session_id
        
        try:
            # Store session data with expiration
            self.redis_client.setex(
                f"session:{session_id}",
                config.session_timeout,
                json.dumps(session_data)
            )
            
            # Initialize contact form state to idle (skip name/email/phone collection)
            self.set_contact_form_state(session_id, "idle")
            
            logger.info(f"Created new session: {session_id}")
            return session_id
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return session_id  # Return session ID even if Redis fails
    
    def is_session_valid(self, session_id: str) -> bool:
        """
        Check if a session is valid and active.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if session is valid, False otherwise
        """
        if not self.redis_available:
            return session_id in self.memory_sessions
        
        try:
            return self.redis_client.exists(f"session:{session_id}")
        except Exception as e:
            logger.error(f"Failed to check session validity: {e}")
            return False
    
    def update_session_activity(self, session_id: str) -> bool:
        """
        Update the last activity timestamp for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if updated successfully, False otherwise
        """
        if not self.redis_available:
            if session_id in self.memory_sessions:
                self.memory_sessions[session_id]["last_activity"] = datetime.now().isoformat()
                self.memory_sessions[session_id]["query_count"] = self.memory_sessions[session_id].get("query_count", 0) + 1
                return True
            return False
        
        try:
            session_key = f"session:{session_id}"
            session_data_str = self.redis_client.get(session_key)
            
            if not session_data_str:
                return False
            
            session_data = json.loads(session_data_str)
            session_data["last_activity"] = datetime.now().isoformat()
            session_data["query_count"] = session_data.get("query_count", 0) + 1
            
            # Update with extended expiration
            self.redis_client.setex(
                session_key,
                config.session_timeout,
                json.dumps(session_data)
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update session activity: {e}")
            return False
    
    # ==================================================================================
    # DEPRECATED: Redis caching methods - replaced by OpenAI's store parameter
    # OpenAI now handles conversation storage with store=True in model_kwargs
    # Keeping these methods commented for potential rollback
    # ==================================================================================
    
    # def cache_query_response(self, session_id: str, query: str, response: str) -> bool:
    #     """
    #     Cache a query-response pair for the session.
    #     
    #     Args:
    #         session_id: Session identifier
    #         query: User query
    #         response: Bot response
    #         
    #     Returns:
    #         True if cached successfully, False otherwise
    #     """
    #     try:
    #         # Normalize query for consistent caching
    #         normalized_query = self._normalize_query_for_cache(query)
    #         cache_key = f"cache:{session_id}:{hash(normalized_query)}"
    #         
    #         cache_data = {
    #             "original_query": query,
    #             "normalized_query": normalized_query,
    #             "response": response,
    #             "timestamp": datetime.now().isoformat()
    #         }
    #         
    #         # Cache with session timeout
    #         self.redis_client.setex(
    #             cache_key,
    #             config.session_timeout,
    #             json.dumps(cache_data)
    #         )
    #         
    #         logger.debug(f"Cached query-response for session {session_id}")
    #         return True
    #     except Exception as e:
    #         logger.error(f"Failed to cache query-response: {e}")
    #         return False
    # 
    # def get_cached_response(self, session_id: str, query: str) -> Optional[str]:
    #     """
    #     Retrieve a cached response for a query in the session.
    #     Uses semantic similarity to find similar cached queries.
    #     
    #     Args:
    #         session_id: Session identifier
    #         query: User query
    #         
    #     Returns:
    #         Cached response if found, None otherwise
    #     """
    #     try:
    #         # First try exact match
    #         normalized_query = self._normalize_query_for_cache(query)
    #         cache_key = f"cache:{session_id}:{hash(normalized_query)}"
    #         
    #         cached_data_str = self.redis_client.get(cache_key)
    #         if cached_data_str:
    #             cached_data = json.loads(cached_data_str)
    #             logger.debug(f"Found exact cached response for session {session_id}")
    #             return cached_data["response"]
    #         
    #         # If no exact match, try semantic similarity
    #         return self._find_similar_cached_response(session_id, normalized_query)
    #         
    #     except Exception as e:
    #         logger.error(f"Failed to retrieve cached response: {e}")
    #         return None


    # Conversation history helpers
    def append_message_to_history(self, session_id: str, role: str, message: str) -> bool:
        """
        Append a message to the session conversation history stored in Redis as a list.

        Args:
            session_id: Session identifier
            role: 'user' or 'bot'
            message: Message text

        Returns:
            True if appended successfully, False otherwise
        """
        if not self.redis_available:
            if session_id not in self.memory_history:
                self.memory_history[session_id] = []
            entry = {"role": role, "message": message, "ts": datetime.now().isoformat()}
            self.memory_history[session_id].append(entry)
            return True
        
        try:
            history_key = f"session:{session_id}:history"
            entry = json.dumps({"role": role, "message": message, "ts": datetime.now().isoformat()})
            # Use RPUSH to keep messages in chronological order
            self.redis_client.rpush(history_key, entry)
            # Ensure history expires with session
            self.redis_client.expire(history_key, config.session_timeout)
            return True
        except Exception as e:
            logger.error(f"Failed to append message to history: {e}")
            return False

    def get_session_history(self, session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retrieve the conversation history for a session.

        Args:
            session_id: Session identifier
            limit: Optional max number of recent messages to return (most recent last)

        Returns:
            List of history entries as dicts
        """
        if not self.redis_available:
            history = self.memory_history.get(session_id, [])
            if limit is not None and limit > 0:
                return history[-limit:]
            return history
        
        try:
            history_key = f"session:{session_id}:history"
            items = self.redis_client.lrange(history_key, 0, -1)
            if not items:
                return []
            parsed = [json.loads(item) for item in items]
            if limit is not None and limit > 0:
                return parsed[-limit:]
            return parsed
        except Exception as e:
            logger.error(f"Failed to get session history: {e}")
            return []

    def get_last_user_query(self, session_id: str, skip_current: bool = False) -> Optional[str]:
        """
        Return the most recent user message from session history.
        
        Args:
            session_id: Session identifier
            skip_current: If True, skip the most recent message and return the previous one
        
        Returns:
            The last user query, or None if not found
        """
        try:
            history = self.get_session_history(session_id, limit=20)
            # iterate from the end backwards
            count = 0
            for entry in reversed(history):
                if entry.get('role') == 'user':
                    if skip_current and count == 0:
                        count += 1
                        continue
                    return entry.get('message')
            return None
        except Exception as e:
            logger.error(f"Failed to get last user query: {e}")
            return None
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session information.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session data if found, None otherwise
        """
        try:
            session_data_str = self.redis_client.get(f"session:{session_id}")
            if not session_data_str:
                return None
            
            return json.loads(session_data_str)
        except Exception as e:
            logger.error(f"Failed to get session info: {e}")
            return None
    
    def clear_session(self, session_id: str) -> bool:
        """
        Clear all session data and cache.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if cleared successfully, False otherwise
        """
        if not self.redis_available:
            # Clear from memory
            self.memory_sessions.pop(session_id, None)
            self.memory_contact_states.pop(session_id, None)
            self.memory_contact_data.pop(session_id, None)
            self.memory_history.pop(session_id, None)
            logger.info(f"Cleared session from memory: {session_id}")
            return True
        
        try:
            # Delete session data
            session_key = f"session:{session_id}"
            self.redis_client.delete(session_key)
            
            # Delete all cached queries for this session
            cache_pattern = f"cache:{session_id}:*"
            cached_keys = self.redis_client.keys(cache_pattern)
            
            if cached_keys:
                self.redis_client.delete(*cached_keys)
            
            logger.info(f"Cleared session and cache for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear session: {e}")
            return False
    
    def get_all_sessions(self) -> list:
        """
        Get all active session IDs.
        
        Returns:
            List of session IDs
        """
        try:
            session_keys = self.redis_client.keys("session:*")
            return [key.replace("session:", "") for key in session_keys]
        except Exception as e:
            logger.error(f"Failed to get all sessions: {e}")
            return []
    
    def _normalize_query_for_cache(self, query: str) -> str:
        """
        Normalize a query for caching by removing punctuation, extra spaces, and lowercasing.
        
        Args:
            query: Original query string
            
        Returns:
            Normalized query string
        """
        # Convert to lowercase
        normalized = query.lower().strip()
        # Remove punctuation and extra spaces
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized
    
    def _find_similar_cached_response(self, session_id: str, normalized_query: str) -> Optional[str]:
        """
        Find a semantically similar cached query using LLM.
        
        Args:
            session_id: Session identifier
            normalized_query: Normalized query string
            
        Returns:
            Cached response if similar query found, None otherwise
        """
        try:
            # Get all cached queries for this session
            cache_pattern = f"cache:{session_id}:*"
            cached_keys = self.redis_client.keys(cache_pattern)
            
            # Skip LLM call if no cached queries exist
            if not cached_keys:
                logger.debug("No cached queries to check - skipping semantic similarity")
                return None
            
            # Retrieve all cached queries
            cached_queries = []
            for key in cached_keys:
                cached_data_str = self.redis_client.get(key)
                if cached_data_str:
                    cached_data = json.loads(cached_data_str)
                    cached_queries.append({
                        'normalized_query': cached_data.get('normalized_query', ''),
                        'original_query': cached_data.get('original_query', ''),
                        'response': cached_data['response']
                    })
            
            # Skip LLM call if no valid cached queries
            if not cached_queries:
                logger.debug("No valid cached queries - skipping semantic similarity")
                return None
            
            # Use LLM to check semantic similarity against ALL cached queries in one call
            similar_index = self._find_similar_query_index(normalized_query, cached_queries)
            
            if similar_index is not None:
                logger.debug(f"Found semantically similar cached response for session {session_id}")
                return cached_queries[similar_index]['response']
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding similar cached response: {e}")
            return None
    
    def _find_similar_query_index(self, new_query: str, cached_queries: List[Dict[str, Any]]) -> Optional[int]:
        """
        Find if the new query is similar to any cached query using a single LLM call.
        
        Args:
            new_query: The new query to check
            cached_queries: List of cached query dictionaries
            
        Returns:
            Index of the similar query, or None if no match
        """
        try:
            if not cached_queries:
                return None
            
            # Build a prompt that checks against all cached queries at once
            cached_list = "\n".join([f"{i+1}. {q['normalized_query']}" for i, q in enumerate(cached_queries)])
            
            prompt = f"""You are comparing a new user question against previous questions to find if it's asking about the same topic.

New Question: "{new_query}"

Previous Questions:
{cached_list}

If the new question is asking about the SAME TOPIC as any of the previous questions (even with different wording, or asking to repeat/clarify), respond with the NUMBER of that question.

If the new question is about a DIFFERENT TOPIC from all previous questions, respond with "NONE".

Examples:
- "what are child safety measures" and "tell me about child safety" = SAME (respond with the number)
- "what are cookies" and "what data do you collect" = DIFFERENT (respond with NONE)

Respond with only the NUMBER (1, 2, 3, etc.) or NONE:"""

            response = self.llm.invoke(prompt)
            answer = response.content.strip().upper() if hasattr(response, 'content') else str(response).strip().upper()
            
            # Parse the response
            if 'NONE' in answer:
                return None
            
            # Try to extract a number
            import re
            numbers = re.findall(r'\d+', answer)
            if numbers:
                index = int(numbers[0]) - 1  # Convert to 0-based index
                if 0 <= index < len(cached_queries):
                    logger.debug(f"Semantic match found: '{new_query}' matches cached query #{index+1}")
                    return index
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding similar query index: {e}")
            return None
    
    def get_contact_form_state(self, session_id: str) -> str:
        """
        Get the current contact form state for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Contact form state (default: 'idle')
        """
        if not self.redis_available:
            return self.memory_contact_states.get(session_id, "idle")
        
        try:
            state_key = f"session:{session_id}:contact_form_state"
            state = self.redis_client.get(state_key)
            return state if state else "idle"
        except Exception as e:
            logger.error(f"Failed to get contact form state: {e}")
            return "idle"

    def set_contact_form_state(self, session_id: str, state: str) -> bool:
        """
        Set the contact form state for a session.
        
        Args:
            session_id: Session identifier
            state: New contact form state
            
        Returns:
            True if set successfully, False otherwise
        """
        if not self.redis_available:
            self.memory_contact_states[session_id] = state
            return True
        
        try:
            state_key = f"session:{session_id}:contact_form_state"
            self.redis_client.setex(state_key, config.session_timeout, state)
            return True
        except Exception as e:
            logger.error(f"Failed to set contact form state: {e}")
            return False

    def get_contact_form_data(self, session_id: str) -> dict:
        """
        Get the partially collected contact form data for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Contact form data dictionary
        """
        if not self.redis_available:
            return self.memory_contact_data.get(session_id, {})
        
        try:
            data_key = f"session:{session_id}:contact_form_data"
            data_str = self.redis_client.get(data_key)
            return json.loads(data_str) if data_str else {}
        except Exception as e:
            logger.error(f"Failed to get contact form data: {e}")
            return {}

    def set_contact_form_data(self, session_id: str, data: dict) -> bool:
        """
        Set the contact form data for a session.
        
        Args:
            session_id: Session identifier
            data: Contact form data dictionary
            
        Returns:
            True if set successfully, False otherwise
        """
        if not self.redis_available:
            self.memory_contact_data[session_id] = data
            return True
        
        try:
            data_key = f"session:{session_id}:contact_form_data"
            self.redis_client.setex(data_key, config.session_timeout, json.dumps(data))
            return True
        except Exception as e:
            logger.error(f"Failed to set contact form data: {e}")
            return False

    # =========================================================================
    # PROJECT ENQUIRY STATE
    # =========================================================================

    def get_project_enquiry_state(self, session_id: str) -> str:
        """
        Get the current project enquiry state for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            'active' if currently collecting project details, 'idle' otherwise
        """
        if not self.redis_available:
            return self.memory_sessions.get(f"{session_id}:project_enquiry_state", "idle")
        
        try:
            state_key = f"session:{session_id}:project_enquiry_state"
            state = self.redis_client.get(state_key)
            return state if state else "idle"
        except Exception as e:
            logger.error(f"Failed to get project enquiry state: {e}")
            return "idle"

    def set_project_enquiry_state(self, session_id: str, state: str) -> bool:
        """
        Set the project enquiry state for a session.
        
        Args:
            session_id: Session identifier
            state: 'active' or 'idle'
            
        Returns:
            True if set successfully, False otherwise
        """
        if not self.redis_available:
            self.memory_sessions[f"{session_id}:project_enquiry_state"] = state
            return True
        
        try:
            state_key = f"session:{session_id}:project_enquiry_state"
            self.redis_client.setex(state_key, config.session_timeout, state)
            return True
        except Exception as e:
            logger.error(f"Failed to set project enquiry state: {e}")
            return False

    def get_project_enquiry_data(self, session_id: str) -> dict:
        """
        Get the collected project enquiry data for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Project enquiry data dictionary (e.g. original_query, project_details)
        """
        if not self.redis_available:
            return self.memory_sessions.get(f"{session_id}:project_enquiry_data", {})
        
        try:
            data_key = f"session:{session_id}:project_enquiry_data"
            data_str = self.redis_client.get(data_key)
            return json.loads(data_str) if data_str else {}
        except Exception as e:
            logger.error(f"Failed to get project enquiry data: {e}")
            return {}

    def set_project_enquiry_data(self, session_id: str, data: dict) -> bool:
        """
        Set the project enquiry data for a session.
        
        Args:
            session_id: Session identifier
            data: Project enquiry data dictionary
            
        Returns:
            True if set successfully, False otherwise
        """
        if not self.redis_available:
            self.memory_sessions[f"{session_id}:project_enquiry_data"] = data
            return True
        
        try:
            data_key = f"session:{session_id}:project_enquiry_data"
            self.redis_client.setex(data_key, config.session_timeout, json.dumps(data))
            return True
        except Exception as e:
            logger.error(f"Failed to set project enquiry data: {e}")
            return False

    def clear_project_enquiry(self, session_id: str) -> bool:
        """
        Clear project enquiry state and data for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if cleared successfully, False otherwise
        """
        if not self.redis_available:
            self.memory_sessions.pop(f"{session_id}:project_enquiry_state", None)
            self.memory_sessions.pop(f"{session_id}:project_enquiry_data", None)
            return True
        
        try:
            state_key = f"session:{session_id}:project_enquiry_state"
            data_key = f"session:{session_id}:project_enquiry_data"
            self.redis_client.delete(state_key, data_key)
            return True
        except Exception as e:
            logger.error(f"Failed to clear project enquiry: {e}")
            return False

    def clear_contact_form(self, session_id: str) -> bool:
        """
        Clear contact form state and data for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if cleared successfully, False otherwise
        """
        try:
            state_key = f"session:{session_id}:contact_form_state"
            data_key = f"session:{session_id}:contact_form_data"
            self.redis_client.delete(state_key, data_key)
            return True
        except Exception as e:
            logger.error(f"Failed to clear contact form: {e}")
            return False

    # =========================================================================
    # PENDING CONNECT STATE (bot offered to connect, waiting for user confirm)
    # =========================================================================

    def get_pending_connect(self, session_id: str) -> bool:
        """Check if bot is waiting for user to confirm a connect offer."""
        if not self.redis_available:
            return self.memory_sessions.get(f"{session_id}:pending_connect", False)
        try:
            key = f"session:{session_id}:pending_connect"
            val = self.redis_client.get(key)
            return val == "true"
        except Exception as e:
            logger.error(f"Failed to get pending_connect: {e}")
            return False

    def set_pending_connect(self, session_id: str, value: bool) -> bool:
        """Set or clear the pending connect flag."""
        if not self.redis_available:
            if value:
                self.memory_sessions[f"{session_id}:pending_connect"] = True
            else:
                self.memory_sessions.pop(f"{session_id}:pending_connect", None)
            return True
        try:
            key = f"session:{session_id}:pending_connect"
            if value:
                self.redis_client.setex(key, config.session_timeout, "true")
            else:
                self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Failed to set pending_connect: {e}")
            return False
    
    def close(self):
        """Close the Redis connection."""
        try:
            if hasattr(self, 'redis_client'):
                self.redis_client.close()
                logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")


# Create a global session manager instance
session_manager = SessionManager()

# Create a global session manager instance
session_manager = SessionManager()
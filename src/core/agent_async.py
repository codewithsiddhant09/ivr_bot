# """
# Async CrewAI agent for parallel intent classification, RAG retrieval, and response generation.
# Optimized for 2-3 second total response time.
# """
# import asyncio
# import logging
# from typing import Dict, Any, List, Optional, Tuple
# from enum import Enum
# from concurrent.futures import ThreadPoolExecutor
# import time

# from langchain_openai import ChatOpenAI

# from config import config
# from vectorstore.chromadb_client import ChromaDBClient, get_chromadb_client
# from utils.reranker import Reranker, get_reranker

# logger = logging.getLogger(__name__)

# # Thread pool for CPU-bound operations
# _executor = ThreadPoolExecutor(max_workers=4)


# class IntentType(Enum):
#     """Intent classification types."""
#     GREETING = "greeting"
#     CASUAL_CHAT = "casual_chat"
#     FOLLOWUP = "followup"
#     CONTACT_REQUEST = "contact_request"
#     FEEDBACK = "feedback"
#     QUERY = "query"
#     GOODBYE = "goodbye"
#     UNCLEAR = "unclear"


# class AsyncChatbotAgent:
#     """
#     Async agent with parallel processing for:
#     - Intent classification
#     - RAG document retrieval
#     - Response generation
#     - TTS preparation (background)
#     """
    
#     def __init__(self, chromadb_client: ChromaDBClient = None):
#         """Initialize the async chatbot agent."""
#         # Use singleton instances to avoid reloading models
#         self.chromadb_client = chromadb_client or get_chromadb_client()
        
#         # Initialize reranker if enabled - use singleton
#         self.reranker = None
#         if config.enable_reranking:
#             try:
#                 self.reranker = get_reranker()
#                 logger.info(f"Reranker initialized: {config.reranker_model}")
#             except Exception as e:
#                 logger.warning(f"Reranker init failed: {e}")
        
#         # Fast LLM for intent classification
#         self.fast_llm = ChatOpenAI(
#             model="gpt-4.1-nano",
#             temperature=0.1,
#             openai_api_key=config.openai_api_key,
#             max_tokens=50,  # Minimal tokens for intent
#             request_timeout=5  # Fast timeout
#         )
        
#         # Standard LLM for response generation
#         self.llm = ChatOpenAI(
#             model="gpt-4.1-nano",
#             temperature=0.3,
#             openai_api_key=config.openai_api_key,
#             max_tokens=300,
#             request_timeout=10
#         )
        
#         logger.info("AsyncChatbotAgent initialized with parallel processing")
    
#     async def classify_intent_async(self, user_input: str) -> IntentType:
#         """
#         Async intent classification with fast LLM.
#         Target: < 500ms
#         """
#         start = time.time()
        
#         try:
#             prompt = f"""Classify intent into ONE category:
# GREETING - saying hello/hi
# CASUAL_CHAT - "I'm doing great", "how are you" (casual)
# FOLLOWUP - "tell me more", "elaborate"
# CONTACT_REQUEST - "contact me", "call me", "connect me"
# FEEDBACK - "tell your team", "share this"
# QUERY - asking about services, projects, capabilities, identity
# GOODBYE - "bye", "thanks", ending

# Input: "{user_input}"

# Respond with ONLY the category name:"""

#             loop = asyncio.get_event_loop()
#             response = await loop.run_in_executor(
#                 _executor,
#                 lambda: self.fast_llm.invoke(prompt)
#             )
            
#             intent_text = response.content.strip().upper() if hasattr(response, 'content') else str(response).strip().upper()
            
#             elapsed = time.time() - start
#             logger.debug(f"Intent classification: {elapsed:.2f}s")
            
#             # Map to IntentType
#             if 'GREETING' in intent_text:
#                 return IntentType.GREETING
#             elif 'CASUAL' in intent_text:
#                 return IntentType.CASUAL_CHAT
#             elif 'FOLLOWUP' in intent_text:
#                 return IntentType.FOLLOWUP
#             elif 'CONTACT' in intent_text:
#                 return IntentType.CONTACT_REQUEST
#             elif 'FEEDBACK' in intent_text:
#                 return IntentType.FEEDBACK
#             elif 'QUERY' in intent_text:
#                 return IntentType.QUERY
#             elif 'GOODBYE' in intent_text:
#                 return IntentType.GOODBYE
#             else:
#                 return IntentType.UNCLEAR
                
#         except Exception as e:
#             logger.error(f"Intent classification error: {e}")
#             return self._fallback_intent(user_input)
    
#     def _fallback_intent(self, user_input: str) -> IntentType:
#         """Fast regex-based fallback for intent classification."""
#         user_lower = user_input.lower().strip()
        
#         if any(w in user_lower for w in ['hi', 'hello', 'hey']):
#             return IntentType.GREETING
#         elif any(w in user_lower for w in ['bye', 'goodbye', 'thanks', 'thank you']):
#             return IntentType.GOODBYE
#         elif any(w in user_lower for w in ['contact me', 'call me', 'connect me']):
#             return IntentType.CONTACT_REQUEST
#         elif any(w in user_lower for w in ['more info', 'tell me more', 'elaborate']):
#             return IntentType.FOLLOWUP
#         return IntentType.QUERY
    
#     async def retrieve_documents_async(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
#         """
#         Async document retrieval from ChromaDB.
#         Target: < 300ms
#         """
#         start = time.time()
        
#         try:
#             loop = asyncio.get_event_loop()
            
#             # Run ChromaDB search in executor
#             initial_n = config.rerank_candidates if self.reranker else n_results
#             results = await loop.run_in_executor(
#                 _executor,
#                 lambda: self.chromadb_client.search_similar_documents(query, initial_n)
#             )
            
#             # Filter by distance threshold
#             filtered = [r for r in results if r.get('distance', 0) < 1.7]
            
#             # Rerank if enabled
#             if self.reranker and filtered:
#                 filtered = await loop.run_in_executor(
#                     _executor,
#                     lambda: self.reranker.rerank(query, filtered, config.rerank_top_k)
#                 )
            
#             elapsed = time.time() - start
#             logger.debug(f"Document retrieval: {elapsed:.2f}s, {len(filtered)} docs")
            
#             return filtered[:n_results]
            
#         except Exception as e:
#             logger.error(f"Document retrieval error: {e}")
#             return []
    
#     async def generate_response_async(
#         self, 
#         query: str, 
#         intent: IntentType, 
#         context_docs: List[Dict[str, Any]],
#         fast_mode: bool = False
#     ) -> str:
#         """
#         Async response generation.
#         fast_mode: Skip LLM, return top doc directly (< 100ms)
#         normal_mode: Use LLM for contextual response (< 1s)
#         """
#         start = time.time()
        
#         try:
#             # Handle non-query intents quickly
#             if intent == IntentType.GREETING:
#                 return await self._handle_greeting_async(query)
#             elif intent == IntentType.CASUAL_CHAT:
#                 return await self._handle_casual_async(query)
#             elif intent == IntentType.GOODBYE:
#                 return "Thanks for chatting! Feel free to reach out anytime - we at TechGropse are always here to help!"
#             elif intent == IntentType.FEEDBACK:
#                 return "Got it! I'll make sure to pass this along to our team at TechGropse."
#             elif intent == IntentType.UNCLEAR:
#                 return "I'm not quite sure I follow. Could you tell me a bit more about what you're looking for?"
#             elif intent == IntentType.CONTACT_REQUEST:
#                 # Return trigger signal - chatbot_async will handle asking for availability
#                 return "TRIGGER_CONTACT_FORM"
            
#             # FAST MODE: Return top document directly
#             if fast_mode and context_docs:
#                 content = context_docs[0].get('content', '')
#                 # Return first 3 sentences
#                 sentences = content.split('.')[:3]
#                 elapsed = time.time() - start
#                 logger.debug(f"Fast mode response: {elapsed:.2f}s")
#                 return '. '.join(sentences) + '.'
            
#             # NORMAL MODE: LLM-powered contextual response
#             if not context_docs:
#                 return "I don't have specific information about that in our documents. Would you like me to connect you with our team?"
            
#             # Build context
#             context_text = "\n\n".join([
#                 f"[{doc.get('metadata', {}).get('source', 'Unknown')}]\n{doc['content'][:400]}"
#                 for doc in context_docs[:3]
#             ])
            
#             prompt = f"""You are Anup, TechGropse's friendly virtual assistant.

# Question: {query}

# Context:
# {context_text}

# Instructions:
# - Answer in 2-3 sentences max
# - Be conversational and warm
# - Use "we at TechGropse", "our" when referring to company
# - Only use information from context
# - No greetings like "Hi!"

# Response:"""

#             loop = asyncio.get_event_loop()
#             response = await loop.run_in_executor(
#                 _executor,
#                 lambda: self.llm.invoke(prompt)
#             )
            
#             result = response.content.strip() if hasattr(response, 'content') else str(response).strip()
            
#             elapsed = time.time() - start
#             logger.debug(f"LLM response: {elapsed:.2f}s")
            
#             return result
            
#         except Exception as e:
#             logger.error(f"Response generation error: {e}")
#             return "I'm having trouble processing that right now. Please try again."
    
#     async def _handle_greeting_async(self, user_input: str) -> str:
#         """Quick greeting response."""
#         if any(p in user_input.lower() for p in ['how are you', 'how r u']):
#             return "I'm doing great, thanks for asking! How about you?"
#         return "Hi! I'm Anup from TechGropse. How can I help you today?"
    
#     async def _handle_casual_async(self, user_input: str) -> str:
#         """Quick casual chat response."""
#         if any(p in user_input.lower() for p in ['how are you', 'how r u']):
#             return "I'm doing great, thanks! How about you?"
#         return "That's wonderful to hear! What can I help you with today?"
    
#     async def process_parallel(
#         self, 
#         user_input: str,
#         fast_mode: bool = False,
#         skip_intent: bool = False,
#         predicted_intent: IntentType = None
#     ) -> Dict[str, Any]:
#         """
#         PARALLEL PROCESSING PIPELINE
        
#         Runs Intent Classification and RAG Retrieval simultaneously.
#         Target total time: 1-2 seconds
        
#         Args:
#             user_input: User's message
#             fast_mode: Skip LLM for instant response
#             skip_intent: Use predicted_intent instead of classifying
#             predicted_intent: Pre-predicted intent (for interim processing)
        
#         Returns:
#             Dict with intent, response, context_docs, timing
#         """
#         total_start = time.time()
#         timing = {}
        
#         try:
#             # STEP 1: PARALLEL - Intent + RAG simultaneously
#             parallel_start = time.time()
            
#             if skip_intent and predicted_intent:
#                 # Use pre-predicted intent
#                 intent = predicted_intent
#                 # Only run RAG
#                 context_docs = await self.retrieve_documents_async(user_input)
#                 timing['parallel'] = time.time() - parallel_start
#             else:
#                 # Run both in parallel
#                 intent_task = asyncio.create_task(self.classify_intent_async(user_input))
#                 rag_task = asyncio.create_task(self.retrieve_documents_async(user_input))
                
#                 intent, context_docs = await asyncio.gather(intent_task, rag_task)
#                 timing['parallel'] = time.time() - parallel_start
            
#             logger.info(f"Parallel phase: {timing['parallel']:.2f}s (Intent: {intent.value}, Docs: {len(context_docs)})")
            
#             # STEP 2: Response Generation
#             response_start = time.time()
#             response = await self.generate_response_async(
#                 user_input, 
#                 intent, 
#                 context_docs,
#                 fast_mode=fast_mode
#             )
#             timing['response'] = time.time() - response_start
            
#             timing['total'] = time.time() - total_start
            
#             logger.info(f"Total processing: {timing['total']:.2f}s")
            
#             return {
#                 'intent': intent.value,
#                 'response': response,
#                 'context_docs': context_docs,
#                 'timing': timing,
#                 'user_input': user_input
#             }
            
#         except Exception as e:
#             logger.error(f"Parallel processing error: {e}")
#             return {
#                 'intent': 'error',
#                 'response': "I encountered an error. Please try again.",
#                 'context_docs': [],
#                 'timing': {'total': time.time() - total_start},
#                 'user_input': user_input
#             }
    
#     async def process_interim(self, partial_text: str) -> Dict[str, Any]:
#         """
#         Process interim (partial) speech for predictive analysis.
#         Returns quick predictions without full response generation.
        
#         Target: < 500ms
#         """
#         start = time.time()
        
#         try:
#             # Run intent classification only for interim
#             intent = await self.classify_intent_async(partial_text)
            
#             # For QUERY intent, start RAG prefetch in background
#             context_preview = []
#             if intent == IntentType.QUERY:
#                 # Quick RAG with minimal results
#                 context_preview = await self.retrieve_documents_async(partial_text, n_results=2)
            
#             return {
#                 'type': 'interim',
#                 'intent': intent.value,
#                 'partial_text': partial_text,
#                 'context_preview': [
#                     {'section': doc.get('metadata', {}).get('source', 'Unknown')[:50]}
#                     for doc in context_preview
#                 ],
#                 'timing': time.time() - start
#             }
            
#         except Exception as e:
#             logger.error(f"Interim processing error: {e}")
#             return {
#                 'type': 'interim',
#                 'intent': 'unknown',
#                 'partial_text': partial_text,
#                 'timing': time.time() - start
#             }


# # Singleton instance for reuse
# _agent_instance = None

# def get_async_agent() -> AsyncChatbotAgent:
#     """Get or create the async agent singleton."""
#     global _agent_instance
#     if _agent_instance is None:
#         _agent_instance = AsyncChatbotAgent()
#     return _agent_instance



"""
Async CrewAI agent for parallel intent classification, RAG retrieval, and response generation.
Optimized for 2-3 second total response time.
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import time

from langchain_openai import ChatOpenAI

from config import config
from vectorstore.chromadb_client import ChromaDBClient, get_chromadb_client
from utils.reranker import Reranker, get_reranker
from utils.cache import (
    intent_cache, _intent_lock,
    response_cache, _response_lock,
    normalize_query,
)
from utils.redis_cache import get_cache_service, get_semantic_cache

logger = logging.getLogger(__name__)

# Thread pool for CPU-bound operations
_executor = ThreadPoolExecutor(max_workers=4)


class IntentType(Enum):
    """Intent classification types."""
    GREETING = "greeting"
    CASUAL_CHAT = "casual_chat"
    FOLLOWUP = "followup"
    CONTACT_REQUEST = "contact_request"
    FEEDBACK = "feedback"
    PROJECT_ENQUIRY = "project_enquiry"
    QUERY = "query"
    GOODBYE = "goodbye"
    UNCLEAR = "unclear"


class AsyncChatbotAgent:
    """
    Async agent with parallel processing for:
    - Intent classification
    - RAG document retrieval
    - Response generation
    - TTS preparation (background)
    """
    
    def __init__(self, chromadb_client: ChromaDBClient = None):
        """Initialize the async chatbot agent."""
        # Use singleton instances to avoid reloading models
        self.chromadb_client = chromadb_client or get_chromadb_client()
        
        # Initialize reranker if enabled - use singleton
        self.reranker = None
        if config.enable_reranking:
            try:
                self.reranker = get_reranker()
                logger.info(f"Reranker initialized: {config.reranker_model}")
            except Exception as e:
                logger.warning(f"Reranker init failed: {e}")
        
        # Fast LLM for intent classification
        self.fast_llm = ChatOpenAI(
            model="gpt-4.1-nano",
            temperature=0.1,
            openai_api_key=config.openai_api_key,
            max_tokens=50,  # Minimal tokens for intent
            request_timeout=5  # Fast timeout
        )
        
        # Standard LLM for response generation
        self.llm = ChatOpenAI(
            model="gpt-4.1-nano",
            temperature=0.3,
            openai_api_key=config.openai_api_key,
            max_tokens=300,
            request_timeout=10
        )
        
        logger.info("AsyncChatbotAgent initialized with parallel processing")
    
    async def classify_intent_async(self, user_input: str) -> IntentType:
        """
        Async intent classification with fast LLM.

        L1 = in-memory TTLCache (instant, per-process)
        L2 = Redis  ``intent:{sha256}``  TTL 24 h
        Target: < 500ms (< 1ms on cache hit)
        """
        start = time.time()

        # --- L1 cache read (in-memory) ---
        cache_key = normalize_query(user_input)
        with _intent_lock:
            cached_value = intent_cache.get(cache_key)
        if cached_value is not None:
            logger.debug(f"Intent L1 HIT: '{user_input[:50]}' → {cached_value}")
            try:
                return IntentType(cached_value)
            except ValueError:
                pass  # stale/unknown value – fall through

        # --- L2 cache read (Redis) ---
        redis_cache = get_cache_service()
        redis_value = redis_cache.get("intent", user_input)
        if redis_value is not None:
            logger.debug(f"Intent L2 HIT: '{user_input[:50]}' → {redis_value}")
            try:
                result = IntentType(redis_value)
                # Back-fill L1
                with _intent_lock:
                    intent_cache[cache_key] = redis_value
                return result
            except ValueError:
                pass  # stale/unknown value – fall through to LLM

        try:
            prompt = f"""Classify intent into ONE category:
GREETING - saying hello/hi
CASUAL_CHAT - "I'm doing great", "how are you" (casual)
FOLLOWUP - "tell me more", "elaborate"
CONTACT_REQUEST - "contact me", "call me", "connect me", "reschedule", "change my meeting", "change my schedule", "book a call"
FEEDBACK - "tell your team", "share this"
PROJECT_ENQUIRY - user wants to build/develop an app, software, website, or project and is asking about it (e.g. "I want to build an app", "can you help me build a CRM", "I need an ecommerce website", "what tech stack for my project", "how long to build an app", "cost of building software")
QUERY - asking about company services, capabilities, identity, general info (NOT about building their own project)
GOODBYE - "bye", "thanks", ending

IMPORTANT: If the user is asking about building/developing THEIR OWN project or app, classify as PROJECT_ENQUIRY. If they are asking general questions about the company, classify as QUERY.
IMPORTANT: If the user wants to reschedule, change, or book a call/meeting, classify as CONTACT_REQUEST.

Input: "{user_input}"

Respond with ONLY the category name:"""

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                _executor,
                lambda: self.fast_llm.invoke(prompt)
            )

            intent_text = response.content.strip().upper() if hasattr(response, 'content') else str(response).strip().upper()

            elapsed = time.time() - start
            logger.debug(f"Intent classification: {elapsed:.2f}s")

            # Map to IntentType
            if 'GREETING' in intent_text:
                result_intent = IntentType.GREETING
            elif 'CASUAL' in intent_text:
                result_intent = IntentType.CASUAL_CHAT
            elif 'FOLLOWUP' in intent_text:
                result_intent = IntentType.FOLLOWUP
            elif 'CONTACT' in intent_text:
                result_intent = IntentType.CONTACT_REQUEST
            elif 'FEEDBACK' in intent_text:
                result_intent = IntentType.FEEDBACK
            elif 'PROJECT' in intent_text:
                result_intent = IntentType.PROJECT_ENQUIRY
            elif 'QUERY' in intent_text:
                result_intent = IntentType.QUERY
            elif 'GOODBYE' in intent_text:
                result_intent = IntentType.GOODBYE
            else:
                result_intent = IntentType.UNCLEAR

            # --- cache write (L1 + L2) ---
            with _intent_lock:
                intent_cache[cache_key] = result_intent.value
            redis_cache.set("intent", user_input, result_intent.value)

            return result_intent

        except Exception as e:
            logger.error(f"Intent classification error: {e}")
            return self._fallback_intent(user_input)
    
    def _fallback_intent(self, user_input: str) -> IntentType:
        """Fast regex-based fallback for intent classification."""
        user_lower = user_input.lower().strip()
        
        if any(w in user_lower for w in ['hi', 'hello', 'hey']):
            return IntentType.GREETING
        elif any(w in user_lower for w in ['bye', 'goodbye', 'thanks', 'thank you']):
            return IntentType.GOODBYE
        elif any(w in user_lower for w in ['contact me', 'call me', 'connect me']):
            return IntentType.CONTACT_REQUEST
        elif any(w in user_lower for w in ['more info', 'tell me more', 'elaborate']):
            return IntentType.FOLLOWUP
        elif any(w in user_lower for w in ['build an app', 'build a software', 'develop an app', 'build a website', 'create an app', 'need an app']):
            return IntentType.PROJECT_ENQUIRY
        return IntentType.QUERY
    
    async def retrieve_documents_async(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Async document retrieval from ChromaDB.
        Target: < 300ms
        """
        start = time.time()
        
        try:
            loop = asyncio.get_event_loop()
            
            # Run ChromaDB search in executor
            initial_n = config.rerank_candidates if self.reranker else n_results
            results = await loop.run_in_executor(
                _executor,
                lambda: self.chromadb_client.search_similar_documents(query, initial_n)
            )
            
            # Filter by distance threshold
            filtered = [r for r in results if r.get('distance', 0) < 1.7]
            
            # Rerank if enabled
            if self.reranker and filtered:
                filtered = await loop.run_in_executor(
                    _executor,
                    lambda: self.reranker.rerank(query, filtered, config.rerank_top_k)
                )
            
            elapsed = time.time() - start
            logger.debug(f"Document retrieval: {elapsed:.2f}s, {len(filtered)} docs")
            
            return filtered[:n_results]
            
        except Exception as e:
            logger.error(f"Document retrieval error: {e}")
            return []
    
    async def generate_response_async(
        self,
        query: str,
        intent: IntentType,
        context_docs: List[Dict[str, Any]],
        fast_mode: bool = False
    ) -> str:
        """
        Async response generation.

        For deterministic intents (GREETING, CASUAL_CHAT, GOODBYE, etc.) the
        result is returned immediately without any cache lookup — they are
        already O(1).

        For QUERY intent the full LLM response is cached at two levels:
          L1 = in-memory TTLCache  (normalised_query, intent)
          L2 = Redis  ``response:{sha256}``  TTL 2 h

        Additionally, *intent-level FAQ caching* stores the first QUERY
        response under ``intent_response:query`` so that subsequent QUERY
        questions that are semantically different but still FAQ-like can
        fall back to a pre-generated answer when both L1 and L2 miss.
        (TTL 6 h — long because the company info is relatively static.)

        fast_mode: Skip LLM, return top doc directly (< 100ms)
        normal_mode: LLM-powered contextual response (< 1s, ~1ms on cache hit)
        """
        start = time.time()

        try:
            # ----------------------------------------------------------------
            # Fast-path: deterministic responses — no cache needed
            # ----------------------------------------------------------------
            if intent == IntentType.GREETING:
                return await self._handle_greeting_async(query)
            elif intent == IntentType.CASUAL_CHAT:
                return await self._handle_casual_async(query)
            elif intent == IntentType.GOODBYE:
                return "Thanks for chatting! Feel free to reach out anytime - we at TechGropse are always here to help!"
            elif intent == IntentType.FEEDBACK:
                return "Got it! I'll make sure to pass this along to our team at TechGropse."
            elif intent == IntentType.UNCLEAR:
                return "I'm not quite sure I follow. Could you tell me a bit more about what you're looking for?"
            elif intent == IntentType.CONTACT_REQUEST:
                # Trigger signal — chatbot_async will handle scheduling form
                return "TRIGGER_CONTACT_FORM"
            elif intent == IntentType.PROJECT_ENQUIRY:
                # Trigger signal — chatbot_async will handle project enquiry flow
                return "TRIGGER_PROJECT_ENQUIRY"

            # FAST MODE: return top document directly (no LLM, no cache)
            if fast_mode and context_docs:
                content = context_docs[0].get('content', '')
                sentences = content.split('.')[:3]
                elapsed = time.time() - start
                logger.debug(f"Fast mode response: {elapsed:.2f}s")
                return '. '.join(sentences) + '.'

            # ----------------------------------------------------------------
            # QUERY intent: L1 → L2 → LLM
            # ----------------------------------------------------------------
            redis_cache = get_cache_service()
            cache_key = (normalize_query(query), intent.value)

            # --- L1 read (in-memory) ---
            with _response_lock:
                cached_response = response_cache.get(cache_key)
            if cached_response is not None:
                logger.debug(f"Response L1 HIT: '{query[:60]}' → intent={intent.value}")
                return cached_response

            # --- L2 read (Redis) ---
            redis_key_text = f"{query}::intent={intent.value}"
            redis_value = redis_cache.get("response", redis_key_text)
            if redis_value is not None:
                logger.debug(f"Response L2 HIT: '{query[:60]}' → intent={intent.value}")
                # Back-fill L1
                with _response_lock:
                    response_cache[cache_key] = redis_value
                return redis_value

            # NORMAL MODE: LLM-powered contextual response
            if not context_docs:
                no_docs_reply = (
                    "I don't have specific information about that in our documents. "
                    "Would you like me to connect you with our team?"
                )
                # Cache the no-docs reply so subsequent identical queries skip the check
                with _response_lock:
                    response_cache[cache_key] = no_docs_reply
                redis_cache.set("response", redis_key_text, no_docs_reply)
                return no_docs_reply

            # Build context from top-3 retrieved documents
            context_text = "\n\n".join([
                f"[{doc.get('metadata', {}).get('source', 'Unknown')}]\n{doc['content'][:400]}"
                for doc in context_docs[:3]
            ])

            prompt = f"""You are Anup, TechGropse's friendly virtual assistant.

Question: {query}

Context:
{context_text}

Instructions:
- Answer in 2-3 sentences max
- Be conversational and warm
- Use "we at TechGropse", "our" when referring to company
- Only use information from context
- No greetings like "Hi!"

Response:"""

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                _executor,
                lambda: self.llm.invoke(prompt)
            )

            result = response.content.strip() if hasattr(response, 'content') else str(response).strip()

            # --- cache write (L1 + L2) ---
            with _response_lock:
                response_cache[cache_key] = result
            redis_cache.set("response", redis_key_text, result)

            elapsed = time.time() - start
            logger.debug(f"LLM response (cached L1+L2): {elapsed:.2f}s")

            return result

        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return "I'm having trouble processing that right now. Please try again."
    
    async def _handle_greeting_async(self, user_input: str) -> str:
        """Quick greeting response."""
        if any(p in user_input.lower() for p in ['how are you', 'how r u']):
            return "I'm doing great, thanks for asking! How about you?"
        return "Hi! I'm Anup from TechGropse. How can I help you today?"
    
    async def _handle_casual_async(self, user_input: str) -> str:
        """Quick casual chat response."""
        if any(p in user_input.lower() for p in ['how are you', 'how r u']):
            return "I'm doing great, thanks! How about you?"
        return "That's wonderful to hear! What can I help you with today?"
    
    async def process_parallel(
        self, 
        user_input: str,
        fast_mode: bool = False,
        skip_intent: bool = False,
        predicted_intent: IntentType = None
    ) -> Dict[str, Any]:
        """
        PARALLEL PROCESSING PIPELINE
        
        Runs Intent Classification and RAG Retrieval simultaneously.
        Target total time: 1-2 seconds
        
        Before the parallel phase, checks the **semantic cache** using the
        query embedding (reused from L1/L2 embedding cache, so nearly free).
        If a semantically similar query was answered before (cosine ≥ 0.92),
        the cached response is returned instantly (~2-5 ms).

        Args:
            user_input: User's message
            fast_mode: Skip LLM for instant response
            skip_intent: Use predicted_intent instead of classifying
            predicted_intent: Pre-predicted intent (for interim processing)
        
        Returns:
            Dict with intent, response, context_docs, timing
        """
        total_start = time.time()
        timing = {}
        
        try:
            # ==============================================================
            # STEP 0: SEMANTIC CACHE CHECK (embedding-based similarity)
            # Cost: ~2-5ms (embedding from L1/L2 cache + cosine scan)
            # ==============================================================
            sem_cache = get_semantic_cache()
            query_embedding = None

            try:
                loop = asyncio.get_event_loop()
                query_embedding = await loop.run_in_executor(
                    _executor,
                    lambda: self.chromadb_client._embed_query_cached(user_input)
                )

                sem_hit = sem_cache.find(query_embedding)
                if sem_hit is not None:
                    timing['semantic_cache'] = time.time() - total_start
                    timing['total'] = timing['semantic_cache']
                    logger.info(
                        f"⚡ Semantic cache HIT: {timing['total']:.3f}s "
                        f"(matched: '{sem_hit['query'][:60]}')"
                    )
                    return {
                        'intent': sem_hit['intent'],
                        'response': sem_hit['response'],
                        'context_docs': [],
                        'timing': timing,
                        'user_input': user_input,
                        'cache_hit': 'semantic',
                    }
            except Exception as e:
                logger.debug(f"Semantic cache check skipped: {e}")

            # STEP 1: PARALLEL - Intent + RAG simultaneously
            parallel_start = time.time()
            
            if skip_intent and predicted_intent:
                # Use pre-predicted intent
                intent = predicted_intent
                # Only run RAG
                context_docs = await self.retrieve_documents_async(user_input)
                timing['parallel'] = time.time() - parallel_start
            else:
                # Run both in parallel
                intent_task = asyncio.create_task(self.classify_intent_async(user_input))
                rag_task = asyncio.create_task(self.retrieve_documents_async(user_input))
                
                intent, context_docs = await asyncio.gather(intent_task, rag_task)
                timing['parallel'] = time.time() - parallel_start
            
            logger.info(f"Parallel phase: {timing['parallel']:.2f}s (Intent: {intent.value}, Docs: {len(context_docs)})")
            
            # STEP 2: Response Generation
            response_start = time.time()
            response = await self.generate_response_async(
                user_input, 
                intent, 
                context_docs,
                fast_mode=fast_mode
            )
            timing['response'] = time.time() - response_start
            
            timing['total'] = time.time() - total_start
            
            logger.info(f"Total processing: {timing['total']:.2f}s")

            # ==============================================================
            # STEP 3: STORE in semantic cache (for future similar queries)
            # Only store meaningful QUERY/FOLLOWUP responses, not triggers
            # ==============================================================
            if (
                query_embedding is not None
                and intent.value in ('query', 'followup')
                and response not in ('TRIGGER_CONTACT_FORM', 'TRIGGER_PROJECT_ENQUIRY')
                and len(response) > 20
            ):
                sem_cache.store(
                    query=user_input,
                    query_embedding=query_embedding,
                    response=response,
                    intent=intent.value,
                )
            
            return {
                'intent': intent.value,
                'response': response,
                'context_docs': context_docs,
                'timing': timing,
                'user_input': user_input
            }
            
        except Exception as e:
            logger.error(f"Parallel processing error: {e}")
            return {
                'intent': 'error',
                'response': "I encountered an error. Please try again.",
                'context_docs': [],
                'timing': {'total': time.time() - total_start},
                'user_input': user_input
            }
    
    async def process_interim(self, partial_text: str) -> Dict[str, Any]:
        """
        Process interim (partial) speech for predictive analysis.
        Returns quick predictions without full response generation.
        
        Target: < 500ms
        """
        start = time.time()
        
        try:
            # Run intent classification only for interim
            intent = await self.classify_intent_async(partial_text)
            
            # For QUERY intent, start RAG prefetch in background
            context_preview = []
            if intent == IntentType.QUERY:
                # Quick RAG with minimal results
                context_preview = await self.retrieve_documents_async(partial_text, n_results=2)
            
            return {
                'type': 'interim',
                'intent': intent.value,
                'partial_text': partial_text,
                'context_preview': [
                    {'section': doc.get('metadata', {}).get('source', 'Unknown')[:50]}
                    for doc in context_preview
                ],
                'timing': time.time() - start
            }
            
        except Exception as e:
            logger.error(f"Interim processing error: {e}")
            return {
                'type': 'interim',
                'intent': 'unknown',
                'partial_text': partial_text,
                'timing': time.time() - start
            }


# Singleton instance for reuse
_agent_instance = None

def get_async_agent() -> AsyncChatbotAgent:
    """Get or create the async agent singleton."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = AsyncChatbotAgent()
    return _agent_instance

# """
# Async chatbot orchestrator for parallel processing pipeline.
# Coordinates intent, RAG, response generation, and TTS in parallel.
# """
# import asyncio
# import logging
# from typing import Dict, Any, Optional, Tuple
# import time

# from core.agent_async import AsyncChatbotAgent, IntentType, get_async_agent
# from core.session_manager import SessionManager, session_manager
# from core.contact_form_handler import ContactFormHandler
# from legacy.agent import ContactFormState

# logger = logging.getLogger(__name__)


# class AsyncChatBot:
#     """
#     Async chatbot with parallel processing pipeline.
#     Target: 2-3 second total response time including TTS.
#     """
    
#     def __init__(self):
#         """Initialize async chatbot with all components."""
#         self.agent = get_async_agent()
#         self.session_manager = session_manager
#         logger.info("AsyncChatBot initialized")
    
#     def start_session(self) -> Tuple[str, str]:
#         """
#         Start a new session.
#         Returns: (session_id, welcome_message)
#         """
#         session_id = self.session_manager.create_session()
#         welcome = "Hello! Welcome to TechGropse, I'm Anup, your virtual assistant. What's your name?"
#         logger.info(f"Started session: {session_id}")
#         return session_id, welcome
    
#     def end_session(self, session_id: str):
#         """End a session and cleanup."""
#         if session_id:
#             self.session_manager.clear_session(session_id)
#             logger.info(f"Ended session: {session_id}")
    
#     async def process_message_async(
#         self, 
#         user_input: str, 
#         session_id: str,
#         fast_mode: bool = False
#     ) -> Dict[str, Any]:
#         """
#         Process message with parallel processing pipeline.
        
#         Args:
#             user_input: User's message
#             session_id: Session identifier
#             fast_mode: Skip LLM for fastest response
            
#         Returns:
#             Dict with response, intent, timing info
#         """
#         total_start = time.time()
        
#         try:
#             if not session_id:
#                 raise ValueError("session_id is required")
            
#             # Update session activity
#             self.session_manager.update_session_activity(session_id)
            
#             # Append user message to history
#             try:
#                 self.session_manager.append_message_to_history(session_id, 'user', user_input)
#             except Exception:
#                 pass
            
#             # Check contact form state
#             form_state = self.session_manager.get_contact_form_state(session_id)
            
#             if form_state == ContactFormState.COMPLETED.value:
#                 self.session_manager.set_contact_form_state(session_id, ContactFormState.IDLE.value)
#                 form_state = ContactFormState.IDLE.value
            
#             # Handle contact form flow (not parallelized - sequential state machine)
#             if form_state != ContactFormState.IDLE.value:
#                 form_data = self.session_manager.get_contact_form_data(session_id)
#                 result = ContactFormHandler.handle_contact_form_step(
#                     form_state=form_state,
#                     user_input=user_input,
#                     form_data=form_data,
#                     session_id=session_id,
#                     mongodb_client=None
#                 )
                
#                 self.session_manager.set_contact_form_state(session_id, result['next_state'])
#                 self.session_manager.set_contact_form_data(session_id, result['form_data'])
                
#                 response = result['response']
                
#                 try:
#                     self.session_manager.append_message_to_history(session_id, 'bot', response)
#                 except Exception:
#                     pass
                
#                 return {
#                     'response': response,
#                     'intent': 'contact_form',
#                     'timing': {'total': time.time() - total_start},
#                     'session_id': session_id
#                 }
            
#             # PARALLEL PROCESSING PIPELINE
#             result = await self.agent.process_parallel(
#                 user_input=user_input,
#                 fast_mode=fast_mode
#             )
            
#             response = result.get('response', '')
#             intent = result.get('intent', '')
            
#             # Check for contact request trigger - immediately ask for availability
#             if intent == 'contact_request' or response == "TRIGGER_CONTACT_FORM":
#                 user_details = self.session_manager.get_contact_form_data(session_id) or {}
#                 user_details['original_query'] = user_input
                
#                 has_schedule = user_details.get('preferred_datetime') and user_details.get('timezone')
                
#                 if has_schedule:
#                     self.session_manager.set_contact_form_data(session_id, user_details)
#                     self.session_manager.set_contact_form_state(
#                         session_id, ContactFormState.ASKING_SCHEDULE_CHANGE.value
#                     )
#                     response = f"Sure! You previously scheduled a call for {user_details.get('preferred_datetime')} ({user_details.get('timezone')}). Would you like to keep this time or change it?"
#                 else:
#                     self.session_manager.set_contact_form_data(session_id, user_details)
#                     self.session_manager.set_contact_form_state(
#                         session_id, ContactFormState.COLLECTING_DATETIME.value
#                     )
#                     response = "Great! I'll connect you with our team. When would be the best time for them to reach out? Please include your timezone and country. For example: 'Tomorrow 3 PM IST India' or 'Monday 10 AM EST USA'"
                
#                 # Update result with the actual response
#                 result['response'] = response
            
#             # Append bot response to history
#             try:
#                 self.session_manager.append_message_to_history(session_id, 'bot', response)
#             except Exception:
#                 pass
            
#             result['session_id'] = session_id
#             result['timing']['total'] = time.time() - total_start
            
#             logger.info(f"Session {session_id}: Total={result['timing']['total']:.2f}s, Intent={intent}")
            
#             return result
            
#         except Exception as e:
#             logger.error(f"Error processing message: {e}")
#             return {
#                 'response': "I'm sorry, I encountered an error. Please try again.",
#                 'intent': 'error',
#                 'timing': {'total': time.time() - total_start},
#                 'session_id': session_id
#             }
    
#     async def process_interim_async(
#         self, 
#         partial_text: str, 
#         session_id: str
#     ) -> Dict[str, Any]:
#         """
#         Process interim (partial) speech with FULL RAG + TTS generation.
#         Runs complete pipeline in background while user is still speaking.
#         Final response is discarded if user changes their query.
        
#         Args:
#             partial_text: Partial transcription
#             session_id: Session identifier
            
#         Returns:
#             Dict with full response + pre-generated audio (cached)
#         """
#         start_time = time.time()
        
#         try:
#             # Check if partial text is substantial enough (at least 10 chars)
#             if len(partial_text) < 10:
#                 return {
#                     'type': 'interim',
#                     'intent': 'unknown',
#                     'partial_text': partial_text,
#                     'session_id': session_id,
#                     'ready': False
#                 }
            
#             logger.info(f"🚀 SPECULATIVE EXEC: Processing interim '{partial_text}' while user still speaking")
            
#             # Run FULL pipeline (same as final query)
#             # This generates complete response + audio in background
#             result = await self.process_message_async(
#                 user_input=partial_text,
#                 session_id=session_id,
#                 fast_mode=False  # Full processing
#             )
            
#             elapsed = time.time() - start_time
            
#             logger.info(f"✅ SPECULATIVE EXEC: Complete response ready in {elapsed:.2f}s (cached for final)")
            
#             # Mark this as speculative (may be discarded)
#             result['type'] = 'speculative'
#             result['partial_text'] = partial_text
#             result['ready'] = True
#             result['speculative_timing'] = elapsed
            
#             return result
            
#         except Exception as e:
#             logger.error(f"Speculative execution error: {e}")
#             return {
#                 'type': 'interim',
#                 'intent': 'unknown',
#                 'partial_text': partial_text,
#                 'session_id': session_id,
#                 'ready': False,
#                 'error': str(e)
#             }
    
#     def process_message_sync(self, user_input: str, session_id: str) -> str:
#         """
#         Synchronous wrapper for compatibility with existing code.
#         """
#         loop = asyncio.new_event_loop()
#         asyncio.set_event_loop(loop)
#         try:
#             result = loop.run_until_complete(
#                 self.process_message_async(user_input, session_id)
#             )
#             return result.get('response', 'Error processing message')
#         finally:
#             loop.close()


# # Singleton instance
# _chatbot_instance = None

# def get_async_chatbot() -> AsyncChatBot:
#     """Get or create the async chatbot singleton."""
#     global _chatbot_instance
#     if _chatbot_instance is None:
#         _chatbot_instance = AsyncChatBot()
#     return _chatbot_instance


"""
Async chatbot orchestrator for parallel processing pipeline.
Coordinates intent, RAG, response generation, and TTS in parallel.
"""
import asyncio
import hashlib
import logging
import threading
from typing import Dict, Any, Optional, Tuple
import time
from concurrent.futures import ThreadPoolExecutor

from langchain_openai import ChatOpenAI
from cachetools import TTLCache

from core.agent_async import AsyncChatbotAgent, IntentType, get_async_agent
from core.session_manager import SessionManager, session_manager
from core.contact_form_handler import ContactFormHandler
from legacy.agent import ContactFormState
from database.mongodb_client import MongoDBClient
from config import config

logger = logging.getLogger(__name__)

# Thread pool for LLM calls
_enquiry_executor = ThreadPoolExecutor(max_workers=2)

# ---------------------------------------------------------------------------
# Cache for _has_project_context_in_history
# Key: (session_id, history_hash, normalised_user_input)
# TTL: 2 minutes — short because history changes frequently within a session
# ---------------------------------------------------------------------------
_project_ctx_cache: TTLCache = TTLCache(maxsize=128, ttl=120)
_project_ctx_lock = threading.Lock()


def _history_hash(history: list) -> str:
    """Return a short hash of the serialised conversation history list."""
    raw = str([(e.get('role', ''), e.get('message', '')) for e in history])
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


class AsyncChatBot:
    """
    Async chatbot with parallel processing pipeline.
    Target: 2-3 second total response time including TTS.
    """
    
    def __init__(self):
        """Initialize async chatbot with all components."""
        self.agent = get_async_agent()
        self.session_manager = session_manager
        
        # Initialize MongoDB client for saving conversations and contact requests
        self.mongodb_client = None
        try:
            if config.mongodb_uri:
                self.mongodb_client = MongoDBClient(config.mongodb_uri, config.mongodb_database)
                logger.info("MongoDB client initialized for conversation storage")
            else:
                logger.warning("MongoDB URI not configured — conversations will not be saved")
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB client: {e}")
        
        # LLM for project enquiry decisions (reads history, decides next action)
        self.enquiry_llm = ChatOpenAI(
            model="gpt-4.1-nano",
            temperature=0.3,
            openai_api_key=config.openai_api_key,
            max_tokens=400,
            request_timeout=10
        )
        
        logger.info("AsyncChatBot initialized")
    
    def start_session(self) -> Tuple[str, str]:
        """
        Start a new session.
        Returns: (session_id, welcome_message)
        """
        session_id = self.session_manager.create_session()
        welcome = "Hello! Welcome to TechGropse. I'm Anup, your virtual assistant. How can I help you today?"
        
        # Save welcome message to history so it appears in the MongoDB conversation log
        try:
            self.session_manager.append_message_to_history(session_id, 'bot', welcome)
        except Exception:
            pass
        
        logger.info(f"Started session: {session_id}")
        return session_id, welcome
    
    def end_session(self, session_id: str):
        """End a session — save conversation to MongoDB, then cleanup."""
        if session_id:
            # Save conversation to MongoDB before clearing
            if self.mongodb_client:
                try:
                    history = self.session_manager.get_session_history(session_id)
                    user_details = self.session_manager.get_contact_form_data(session_id)
                    if history:
                        self.mongodb_client.save_session_conversation(
                            session_id=session_id,
                            conversation_history=history,
                            user_details=user_details
                        )
                        logger.info(f"Saved {len(history)} messages to MongoDB for session {session_id}")
                    else:
                        logger.info(f"No conversation history to save for session {session_id}")
                except Exception as e:
                    logger.error(f"Failed to save conversation to MongoDB: {e}")
            
            self.session_manager.clear_session(session_id)
            logger.info(f"Ended session: {session_id}")
    
    async def process_message_async(
        self, 
        user_input: str, 
        session_id: str,
        fast_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Process message with parallel processing pipeline.
        
        Args:
            user_input: User's message
            session_id: Session identifier
            fast_mode: Skip LLM for fastest response
            
        Returns:
            Dict with response, intent, timing info
        """
        total_start = time.time()
        
        try:
            if not session_id:
                raise ValueError("session_id is required")
            
            # Update session activity
            self.session_manager.update_session_activity(session_id)
            
            # Append user message to history
            try:
                self.session_manager.append_message_to_history(session_id, 'user', user_input)
            except Exception:
                pass
            
            # Check contact form state
            form_state = self.session_manager.get_contact_form_state(session_id)
            
            if form_state == ContactFormState.COMPLETED.value:
                self.session_manager.set_contact_form_state(session_id, ContactFormState.IDLE.value)
                form_state = ContactFormState.IDLE.value
            
            # Handle contact form flow (not parallelized - sequential state machine)
            if form_state != ContactFormState.IDLE.value:
                # --- Escape hatch: detect cancel / topic change ---
                # The bot should NEVER trap the user. If they ask something
                # unrelated, answer it. Form states are soft — not hard gates.
                wants_exit = ContactFormHandler.detect_form_cancellation(user_input, form_state)
                if wants_exit:
                    logger.info(f"[{session_id}] User left form flow (state={form_state}), processing normally")
                    self.session_manager.set_contact_form_state(session_id, ContactFormState.IDLE.value)
                    form_state = ContactFormState.IDLE.value
                    # Fall through to normal processing below
                
                # If still in form state (user did NOT cancel), route to form handler
                if form_state != ContactFormState.IDLE.value:
                    form_data = self.session_manager.get_contact_form_data(session_id)
                    result = ContactFormHandler.handle_contact_form_step(
                        form_state=form_state,
                        user_input=user_input,
                        form_data=form_data,
                        session_id=session_id,
                        mongodb_client=self.mongodb_client
                    )
                    
                    self.session_manager.set_contact_form_state(session_id, result['next_state'])
                    self.session_manager.set_contact_form_data(session_id, result['form_data'])
                    
                    response = result['response']
                    
                    try:
                        self.session_manager.append_message_to_history(session_id, 'bot', response)
                    except Exception:
                        pass
                    
                    return {
                        'response': response,
                        'intent': 'contact_form',
                        'timing': {'total': time.time() - total_start},
                        'session_id': session_id
                    }
            
            # =========================================================
            # PENDING CONNECT — bot offered to connect, check if user confirms
            # =========================================================
            if self.session_manager.get_pending_connect(session_id):
                consent = ContactFormHandler.understand_consent(user_input)
                
                if consent == 'yes':
                    # User confirmed — clear flag and trigger scheduling form
                    self.session_manager.set_pending_connect(session_id, False)
                    
                    user_details = self.session_manager.get_contact_form_data(session_id) or {}
                    user_details['original_query'] = user_input
                    
                    has_schedule = user_details.get('preferred_datetime') and user_details.get('timezone')
                    
                    if has_schedule:
                        self.session_manager.set_contact_form_data(session_id, user_details)
                        self.session_manager.set_contact_form_state(
                            session_id, ContactFormState.ASKING_SCHEDULE_CHANGE.value
                        )
                        response = f"Sure! You previously scheduled a call for {user_details.get('preferred_datetime')}. Would you like to keep this time or change it?"
                    else:
                        self.session_manager.set_contact_form_data(session_id, user_details)
                        self.session_manager.set_contact_form_state(
                            session_id, ContactFormState.COLLECTING_DATETIME.value
                        )
                        response = "Great! When would be the best time for our team to reach out?"
                    
                    try:
                        self.session_manager.append_message_to_history(session_id, 'bot', response)
                    except Exception:
                        pass
                    
                    return {
                        'response': response,
                        'intent': 'contact_form',
                        'timing': {'total': time.time() - total_start},
                        'session_id': session_id
                    }
                elif consent == 'no':
                    # User declined — clear flag, acknowledge, continue normally
                    self.session_manager.set_pending_connect(session_id, False)
                    response = "No problem at all! Is there anything else I can help you with?"
                    
                    try:
                        self.session_manager.append_message_to_history(session_id, 'bot', response)
                    except Exception:
                        pass
                    
                    return {
                        'response': response,
                        'intent': 'contact_declined',
                        'timing': {'total': time.time() - total_start},
                        'session_id': session_id
                    }
                else:
                    # Unclear — user likely moved on to a new question/topic
                    # Clear pending_connect and let the message flow through normal processing
                    self.session_manager.set_pending_connect(session_id, False)
                    logger.info(f"Pending connect: unclear consent for '{user_input}', clearing flag and processing normally")
                    # Fall through to normal processing pipeline below
            
            # =========================================================
            # PROJECT ENQUIRY FLOW — user is responding to follow-up
            # =========================================================
            project_state = self.session_manager.get_project_enquiry_state(session_id)
            
            if project_state == 'active':
                result = await self._handle_project_enquiry_response(
                    user_input=user_input,
                    session_id=session_id
                )
                
                response = result.get('response', '')
                
                try:
                    self.session_manager.append_message_to_history(session_id, 'bot', response)
                except Exception:
                    pass
                
                result['session_id'] = session_id
                result['timing'] = {'total': time.time() - total_start}
                
                logger.info(f"Session {session_id}: Project enquiry response, Total={result['timing']['total']:.2f}s")
                return result
            
            # PARALLEL PROCESSING PIPELINE
            result = await self.agent.process_parallel(
                user_input=user_input,
                fast_mode=fast_mode
            )
            
            response = result.get('response', '')
            intent = result.get('intent', '')
            
            # Check for contact request trigger - immediately ask for availability
            if intent == 'contact_request' or response == "TRIGGER_CONTACT_FORM":
                user_details = self.session_manager.get_contact_form_data(session_id) or {}
                user_details['original_query'] = user_input
                
                has_schedule = user_details.get('preferred_datetime') and user_details.get('timezone')
                
                if has_schedule:
                    self.session_manager.set_contact_form_data(session_id, user_details)
                    self.session_manager.set_contact_form_state(
                        session_id, ContactFormState.ASKING_SCHEDULE_CHANGE.value
                    )
                    response = f"Sure! You previously scheduled a call for {user_details.get('preferred_datetime')}. Would you like to keep this time or change it?"
                else:
                    self.session_manager.set_contact_form_data(session_id, user_details)
                    self.session_manager.set_contact_form_state(
                        session_id, ContactFormState.COLLECTING_DATETIME.value
                    )
                    response = "Great! I'll connect you with our team. When would be the best time for them to reach out?"
                
                # Update result with the actual response
                result['response'] = response
            
            # Check for project enquiry trigger — ask one follow-up about features
            if intent == 'project_enquiry' or response == "TRIGGER_PROJECT_ENQUIRY":
                # Before triggering follow-up, check if project details were already
                # discussed in this session. If yes, this is a follow-up question about
                # the existing project — answer it directly via RAG, don't re-ask.
                already_discussed = await self._has_project_context_in_history(session_id, user_input)
                
                if already_discussed:
                    # User already shared project details earlier — treat as a contextual query
                    logger.info(f"Project context already in history, treating as contextual QUERY")
                    result = await self._answer_project_followup_query(user_input, session_id)
                    response = result.get('response', '')
                    result['intent'] = 'project_enquiry_followup'
                else:
                    # First time project enquiry — ask for features
                    project_data = {
                        'original_query': user_input
                    }
                    self.session_manager.set_project_enquiry_data(session_id, project_data)
                    self.session_manager.set_project_enquiry_state(session_id, 'active')
                    
                    # Generate a natural follow-up question using LLM
                    response = await self._generate_project_followup(user_input)
                    result['response'] = response
                    result['intent'] = 'project_enquiry'
            
            # Append bot response to history
            try:
                self.session_manager.append_message_to_history(session_id, 'bot', response)
            except Exception:
                pass
            
            # If the bot response offers to connect with the team, set pending_connect
            # so the next "yes" from the user triggers the scheduling form
            response_lower = response.lower()
            if any(phrase in response_lower for phrase in [
                'connect you with', 'connect you to', 'schedule a call',
                'would you like us to contact', 'like to schedule',
                'connect with our team', 'connect with our experts',
                'reach out to you', 'get in touch',
                'would you like to connect', 'shall i connect',
                'like me to connect', 'want me to connect',
                'connect you with our', 'our team will',
                'set up a call', 'arrange a call',
                'book a call', 'schedule a meeting',
            ]):
                self.session_manager.set_pending_connect(session_id, True)
            
            result['session_id'] = session_id
            result['timing']['total'] = time.time() - total_start
            
            logger.info(f"Session {session_id}: Total={result['timing']['total']:.2f}s, Intent={intent}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return {
                'response': "I'm sorry, I encountered an error. Please try again.",
                'intent': 'error',
                'timing': {'total': time.time() - total_start},
                'session_id': session_id
            }
    
    # =========================================================================
    # PROJECT ENQUIRY HELPERS
    # =========================================================================

    async def _generate_project_followup(self, user_input: str) -> str:
        """
        Generate a natural follow-up question asking about project features/details.
        Uses LLM — no hardcoded question text.
        
        Args:
            user_input: The user's original project enquiry message
            
        Returns:
            A natural follow-up question string
        """
        try:
            prompt = f"""You are Anup, TechGropse's friendly virtual assistant. The user just expressed interest in building a project/app/software.

User's message: "{user_input}"

Your task: Ask ONE short, natural follow-up question to understand what features or functionality they want in their project. Keep it conversational, warm, and to the point (1-2 sentences max). Do not ask about budget, timeline, or platform — only about what the project should do (features/scope).

Response:"""

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                _enquiry_executor,
                lambda: self.enquiry_llm.invoke(prompt)
            )
            
            result = response.content.strip() if hasattr(response, 'content') else str(response).strip()
            logger.info(f"Project enquiry follow-up generated: {result[:80]}...")
            return result
            
        except Exception as e:
            logger.error(f"Error generating project follow-up: {e}")
            return "That sounds interesting! Could you tell me a bit more about the key features you'd like in your project?"

    async def _has_project_context_in_history(self, session_id: str, user_input: str) -> bool:
        """
        Check if the user has already discussed project details in this session.
        Uses LLM to read conversation history and decide if project context exists.

        Caching strategy
        ────────────────
        The result is cached by (session_id, history_hash, normalised_user_input)
        with a 2-minute TTL.  The history_hash changes whenever a new message is
        appended, so stale cache entries are naturally invalidated on the next
        turn.  This eliminates the LLM round-trip (~300-500 ms) on identical
        back-to-back calls within the same turn.

        Args:
            session_id: Session identifier
            user_input: The current user message

        Returns:
            True if project details were already discussed, False if fresh enquiry
        """
        try:
            # Get last 6 pairs (12 messages) of conversation history
            history = self.session_manager.get_session_history(session_id, limit=12)

            if not history or len(history) < 2:
                return False

            # --- cache read ---
            h_hash = _history_hash(history)
            norm_input = user_input.lower().strip()
            cache_key = (session_id, h_hash, norm_input)
            with _project_ctx_lock:
                cached_result = _project_ctx_cache.get(cache_key)
            if cached_result is not None:
                logger.debug(
                    f"Project-context cache HIT for session {session_id[:8]}… "
                    f"→ {cached_result}"
                )
                return cached_result

            # Format history for LLM
            history_text = ""
            for entry in history:
                role = "User" if entry.get('role') == 'user' else "Anup"
                history_text += f"{role}: {entry.get('message', '')}\n"

            prompt = f"""Analyze this conversation history between a user and Anup (TechGropse's assistant).

Conversation history:
{history_text}

The user's latest message: "{user_input}"

TASK: Has the user ALREADY discussed a project they want to build in the conversation above?
- Look for ANY earlier messages where the user talked about building/developing something, described features, or discussed project details.
- If a project was discussed AND the user's latest message relates to that same project (even indirectly, like "for my app?", "what about the cost?", "which technology?", "how long would it take?"), answer YES.
- Short follow-ups like "for my app?", "for this project?", "and the timeline?" are follow-ups if a project was discussed earlier — answer YES.
- Only answer NO if there is truly NO prior project discussion in the conversation history.

Respond with ONLY: YES or NO"""

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                _enquiry_executor,
                lambda: self.enquiry_llm.invoke(prompt)
            )

            answer = response.content.strip().upper() if hasattr(response, 'content') else str(response).strip().upper()

            result = 'YES' in answer
            logger.info(f"Project context in history check: {result} (answer: {answer})")

            # --- cache write ---
            with _project_ctx_lock:
                _project_ctx_cache[cache_key] = result

            return result

        except Exception as e:
            logger.error(f"Error checking project context in history: {e}")
            return False

    async def _answer_project_followup_query(self, user_input: str, session_id: str) -> Dict[str, Any]:
        """
        Answer a follow-up question about an existing project discussion.
        Uses conversation history + RAG to give a contextual, informed response.
        
        Args:
            user_input: The user's follow-up question
            session_id: Session identifier
            
        Returns:
            Dict with response, intent, context_docs, timing
        """
        start = time.time()
        
        try:
            # Get conversation history for context
            history = self.session_manager.get_session_history(session_id, limit=12)
            
            history_text = ""
            for entry in history:
                role = "User" if entry.get('role') == 'user' else "Anup"
                history_text += f"{role}: {entry.get('message', '')}\n"
            
            # Run RAG with the user's question for TechGropse-specific info
            context_docs = await self.agent.retrieve_documents_async(user_input)
            
            context_text = ""
            if context_docs:
                context_text = "\n\n".join([
                    f"[{doc.get('metadata', {}).get('source', 'Unknown')}]\n{doc['content'][:400]}"
                    for doc in context_docs[:3]
                ])
            
            response_prompt = f"""You are Anup, TechGropse's friendly virtual assistant.

The user has been discussing a project they want to build. Here is the conversation so far:
{history_text}

The user's latest question: "{user_input}"

Relevant TechGropse information:
{context_text if context_text else "No specific documents found, use your general knowledge about TechGropse as a software development company."}

Instructions:
- Answer the user's question directly based on the conversation context and the retrieved information
- The user has already described their project — do NOT ask for more features or project details
- Keep it conversational and helpful, 2-4 sentences max
- Use "we at TechGropse", "our team" when referring to the company
- If the question is about tech stack, timeline, cost, or approach — give a specific, helpful answer

Response:"""

            loop = asyncio.get_event_loop()
            response_result = await loop.run_in_executor(
                _enquiry_executor,
                lambda: self.enquiry_llm.invoke(response_prompt)
            )
            
            response = response_result.content.strip() if hasattr(response_result, 'content') else str(response_result).strip()
            
            elapsed = time.time() - start
            logger.info(f"Project follow-up query answered in {elapsed:.2f}s: {response[:80]}...")
            
            return {
                'response': response,
                'intent': 'project_enquiry_followup',
                'context_docs': context_docs,
                'timing': {'total': elapsed}
            }
            
        except Exception as e:
            logger.error(f"Error answering project follow-up query: {e}")
            return {
                'response': "That's a great question! Let me connect you with our team who can give you detailed guidance on this.",
                'intent': 'project_enquiry_followup',
                'context_docs': [],
                'timing': {'total': time.time() - start}
            }

    async def _handle_project_enquiry_response(
        self, 
        user_input: str, 
        session_id: str
    ) -> Dict[str, Any]:
        """
        Handle the user's response after we asked the project follow-up question.
        
        Uses LLM with last 6 message pairs to decide:
        1. User provided project details (even vague) → accept, run RAG, give enriched response
        2. User switched to a different topic → exit enquiry, process normally
        
        Args:
            user_input: User's response to the follow-up question
            session_id: Session identifier
            
        Returns:
            Dict with response, intent, timing
        """
        start = time.time()
        
        try:
            # Get last 6 pairs (12 messages) of conversation history
            history = self.session_manager.get_session_history(session_id, limit=12)
            
            # Format history for LLM context
            history_text = ""
            for entry in history:
                role = "User" if entry.get('role') == 'user' else "Anup"
                history_text += f"{role}: {entry.get('message', '')}\n"
            
            # Get stored project data
            project_data = self.session_manager.get_project_enquiry_data(session_id)
            original_query = project_data.get('original_query', '')
            
            # LLM decides: did the user provide project details or switch topics?
            decision_prompt = f"""You are analyzing a conversation. The user originally asked about building a project: "{original_query}"
The assistant asked a follow-up about features/details. Now the user has responded.

Recent conversation history:
{history_text}

The user's latest message: "{user_input}"

TASK: Classify the user's latest response into ONE of these:
- PROJECT_DETAILS: The user provided any details about their project (features, scope, description, even vague answers like "basic features", "standard stuff", "simple app", "just the usual features"). ANY response that relates to describing the project counts as PROJECT_DETAILS.
- SWITCHED_TOPIC: The user completely changed the subject and is asking about something unrelated to their project (e.g., "who are you?", "bye", "contact me", "what services do you offer?").

Respond with ONLY: PROJECT_DETAILS or SWITCHED_TOPIC"""

            loop = asyncio.get_event_loop()
            decision_response = await loop.run_in_executor(
                _enquiry_executor,
                lambda: self.enquiry_llm.invoke(decision_prompt)
            )
            
            decision = decision_response.content.strip().upper() if hasattr(decision_response, 'content') else str(decision_response).strip().upper()
            
            logger.info(f"Project enquiry decision: {decision} for input: '{user_input[:50]}...'")
            
            if 'SWITCHED' in decision:
                # User switched topics — exit project enquiry, reprocess normally
                self.session_manager.set_project_enquiry_state(session_id, 'idle')
                self.session_manager.clear_project_enquiry(session_id)
                
                logger.info(f"User switched topics during project enquiry, reprocessing normally")
                
                # Reprocess the message through the normal pipeline
                result = await self.agent.process_parallel(
                    user_input=user_input,
                    fast_mode=False
                )
                
                response = result.get('response', '')
                intent = result.get('intent', '')
                
                # Handle contact/other triggers from normal flow
                if intent == 'contact_request' or response == "TRIGGER_CONTACT_FORM":
                    user_details = self.session_manager.get_contact_form_data(session_id) or {}
                    user_details['original_query'] = user_input
                    self.session_manager.set_contact_form_data(session_id, user_details)
                    self.session_manager.set_contact_form_state(
                        session_id, ContactFormState.COLLECTING_DATETIME.value
                    )
                    response = "Great! I'll connect you with our team. When would be the best time for them to reach out?"
                    result['response'] = response
                
                return result
            
            # User provided project details — collect and generate enriched response via RAG
            self.session_manager.set_project_enquiry_state(session_id, 'idle')
            
            # Build a comprehensive query combining original enquiry + feature details
            combined_query = f"{original_query}. Features/details: {user_input}"
            
            # Run RAG with the combined context to get TechGropse-specific info
            context_docs = await self.agent.retrieve_documents_async(combined_query)
            
            # Build context from RAG results
            context_text = ""
            if context_docs:
                context_text = "\n\n".join([
                    f"[{doc.get('metadata', {}).get('source', 'Unknown')}]\n{doc['content'][:400]}"
                    for doc in context_docs[:3]
                ])
            
            # Generate a rich response using conversation history + RAG context
            response_prompt = f"""You are Anup, TechGropse's friendly virtual assistant.

The user wants to build a project. Here is the conversation so far:
{history_text}

User's original request: "{original_query}"
User's project details/features: "{user_input}"

Relevant TechGropse capabilities and services:
{context_text if context_text else "No specific documents found, use your general knowledge about TechGropse as a software development company."}

Instructions:
- Acknowledge the user's project idea and the details they shared
- Give a helpful, informed response about how TechGropse can help with this specific project
- Mention relevant services, technologies, or expertise from the context if available
- Keep it conversational and warm, 3-4 sentences max
- Use "we at TechGropse", "our team" when referring to the company
- Do NOT ask for more features/details — the user has already provided them
- End by asking if the user would like to schedule a call with our team to discuss further

Response:"""

            response_result = await loop.run_in_executor(
                _enquiry_executor,
                lambda: self.enquiry_llm.invoke(response_prompt)
            )
            
            response = response_result.content.strip() if hasattr(response_result, 'content') else str(response_result).strip()
            
            # Clear project enquiry data
            self.session_manager.clear_project_enquiry(session_id)
            
            # Set pending_connect so if user confirms, we trigger the scheduling form
            self.session_manager.set_pending_connect(session_id, True)
            
            elapsed = time.time() - start
            logger.info(f"Project enquiry resolved in {elapsed:.2f}s: {response[:80]}...")
            
            return {
                'response': response,
                'intent': 'project_enquiry',
                'context_docs': context_docs,
                'timing': {'total': elapsed}
            }
            
        except Exception as e:
            logger.error(f"Error handling project enquiry response: {e}")
            # Fallback — clear state and give a generic response
            self.session_manager.set_project_enquiry_state(session_id, 'idle')
            self.session_manager.clear_project_enquiry(session_id)
            return {
                'response': "Thanks for sharing! We at TechGropse have expertise in building projects like this. Would you like me to connect you with our team to discuss further?",
                'intent': 'project_enquiry',
                'context_docs': [],
                'timing': {'total': time.time() - start}
            }
    
    async def process_interim_async(
        self, 
        partial_text: str, 
        session_id: str
    ) -> Dict[str, Any]:
        """
        Process interim (partial) speech with FULL RAG + TTS generation.
        Runs complete pipeline in background while user is still speaking.
        Final response is discarded if user changes their query.
        
        Args:
            partial_text: Partial transcription
            session_id: Session identifier
            
        Returns:
            Dict with full response + pre-generated audio (cached)
        """
        start_time = time.time()
        
        try:
            # Check if partial text is substantial enough (at least 10 chars)
            if len(partial_text) < 10:
                return {
                    'type': 'interim',
                    'intent': 'unknown',
                    'partial_text': partial_text,
                    'session_id': session_id,
                    'ready': False
                }
            
            logger.info(f"🚀 SPECULATIVE EXEC: Processing interim '{partial_text}' while user still speaking")
            
            # Run FULL pipeline (same as final query)
            # This generates complete response + audio in background
            result = await self.process_message_async(
                user_input=partial_text,
                session_id=session_id,
                fast_mode=False  # Full processing
            )
            
            elapsed = time.time() - start_time
            
            logger.info(f"✅ SPECULATIVE EXEC: Complete response ready in {elapsed:.2f}s (cached for final)")
            
            # Mark this as speculative (may be discarded)
            result['type'] = 'speculative'
            result['partial_text'] = partial_text
            result['ready'] = True
            result['speculative_timing'] = elapsed
            
            return result
            
        except Exception as e:
            logger.error(f"Speculative execution error: {e}")
            return {
                'type': 'interim',
                'intent': 'unknown',
                'partial_text': partial_text,
                'session_id': session_id,
                'ready': False,
                'error': str(e)
            }
    
    def process_message_sync(self, user_input: str, session_id: str) -> str:
        """
        Synchronous wrapper for compatibility with existing code.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                self.process_message_async(user_input, session_id)
            )
            return result.get('response', 'Error processing message')
        finally:
            loop.close()


# Singleton instance
_chatbot_instance = None

def get_async_chatbot() -> AsyncChatBot:
    """Get or create the async chatbot singleton."""
    global _chatbot_instance
    if _chatbot_instance is None:
        _chatbot_instance = AsyncChatBot()
    return _chatbot_instance

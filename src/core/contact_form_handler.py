# """
# Contact form handling methods for ChatbotAgent.
# These methods handle the multi-step contact request form collection.
# """
# import logging
# from typing import Dict, Any, Optional
# from utils.validators import validate_email, validate_phone, validate_datetime, validate_name
# from database.mongodb_client import MongoDBClient
# from langchain_openai import ChatOpenAI
# from config import config

# logger = logging.getLogger(__name__)


# class ContactFormHandler:
#     """Handles contact form state and collection logic."""
    
#     # LLM instance for understanding natural language responses
#     _llm = None
    
#     @classmethod
#     def get_llm(cls):
#         """Get or create LLM instance."""
#         if cls._llm is None:
#             cls._llm = ChatOpenAI(
#                 model=config.openai_model,
#                 temperature=0.1,
#                 api_key=config.openai_api_key
#             )
#         return cls._llm
    
#     @staticmethod
#     def understand_consent(user_input: str) -> str:
#         """
#         Use LLM to understand if user is giving consent (yes/no).
        
#         Args:
#             user_input: User's natural language response
            
#         Returns:
#             'yes', 'no', or 'unclear'
#         """
#         try:
#             llm = ContactFormHandler.get_llm()
#             prompt = f"""You are analyzing a user's response to determine if they are giving consent to be contacted.

# User's response: "{user_input}"

# The user was asked: "Would you like us to contact you?"

# Classify the response as:
# - YES: if user agrees, accepts, or wants to be contacted (e.g., "yes", "sure", "please", "that would be great", "okay", "yeah", "go ahead", "I'd like that", "please do")
# - NO: if user declines or doesn't want to be contacted (e.g., "no", "nope", "not now", "no thanks", "I'm good", "not interested", "maybe later")
# - UNCLEAR: if the response doesn't clearly indicate yes or no

# Respond with ONLY: YES, NO, or UNCLEAR"""

#             response = llm.invoke(prompt)
#             result = response.content.strip().upper() if hasattr(response, 'content') else str(response).strip().upper()
            
#             if 'YES' in result:
#                 return 'yes'
#             elif 'NO' in result:
#                 return 'no'
#             else:
#                 return 'unclear'
#         except Exception as e:
#             logger.error(f"Error understanding consent: {e}")
#             # Fallback to simple check
#             user_lower = user_input.lower().strip()
#             if any(word in user_lower for word in ['yes', 'sure', 'ok', 'okay', 'yeah', 'please', 'go ahead']):
#                 return 'yes'
#             elif any(word in user_lower for word in ['no', 'nope', 'not', "don't", 'cancel']):
#                 return 'no'
#             return 'unclear'
    
#     @staticmethod
#     def understand_schedule_change(user_input: str) -> str:
#         """
#         Use LLM to understand if user wants to keep or change existing schedule.
        
#         Args:
#             user_input: User's natural language response
            
#         Returns:
#             'keep', 'change', or 'unclear'
#         """
#         try:
#             llm = ContactFormHandler.get_llm()
#             prompt = f"""You are analyzing a user's response to determine if they want to keep their existing scheduled time or change it.

# User's response: "{user_input}"

# The user was asked: "Would you like to keep this scheduled time or change it?"

# Classify the response as:
# - KEEP: if user wants to keep the same time (e.g., "keep it", "same time", "that's fine", "no change", "yes", "ok", "sounds good", "perfect", "that works")
# - CHANGE: if user wants to change/reschedule (e.g., "change", "different time", "reschedule", "new time", "update it", "modify", "no I want to change")
# - UNCLEAR: if the response doesn't clearly indicate keep or change

# Respond with ONLY: KEEP, CHANGE, or UNCLEAR"""

#             response = llm.invoke(prompt)
#             result = response.content.strip().upper() if hasattr(response, 'content') else str(response).strip().upper()
            
#             if 'KEEP' in result:
#                 return 'keep'
#             elif 'CHANGE' in result:
#                 return 'change'
#             else:
#                 return 'unclear'
#         except Exception as e:
#             logger.error(f"Error understanding schedule change: {e}")
#             # Fallback to simple check
#             user_lower = user_input.lower().strip()
#             if any(word in user_lower for word in ['change', 'different', 'new', 'reschedule', 'update', 'modify']):
#                 return 'change'
#             elif any(word in user_lower for word in ['keep', 'same', 'fine', 'ok', 'okay', 'yes', 'good', 'perfect', 'works']):
#                 return 'keep'
#             return 'unclear'
    
#     @staticmethod
#     def should_trigger_contact_form(context_docs: list, distance_threshold: float = 1.5) -> bool:
#         """
#         Determine if contact form should be triggered based on search results.
        
#         Args:
#             context_docs: Retrieved context documents
#             distance_threshold: Maximum acceptable distance for relevant results
            
#         Returns:
#             True if contact form should be triggered
#         """
#         # Trigger if no results or all results have poor similarity
#         if not context_docs:
#             return True
        
#         # Check if all results are beyond the threshold
#         relevant_count = sum(1 for doc in context_docs if doc.get('distance', 0) < distance_threshold)
#         return relevant_count == 0
    
#     @staticmethod
#     def parse_datetime_with_timezone(user_input: str) -> tuple:
#         """
#         Parse datetime, timezone and country from combined user input using LLM.
        
#         Args:
#             user_input: User's natural language response like "Tomorrow 3 PM IST, India"
            
#         Returns:
#             Tuple of (datetime_str, timezone_str, country_str) or (None, None, None) if parsing fails
#         """
#         try:
#             llm = ContactFormHandler.get_llm()
#             prompt = f"""You are parsing a user's availability response to extract date/time, timezone and country/location.

# User's response: "{user_input}"

# Extract:
# 1. DATE/TIME: The date and time they mentioned (e.g., "tomorrow 3 PM", "Monday 10 AM", "25th December 2pm")
# 2. TIMEZONE: Any timezone mentioned (e.g., IST, EST, PST, GMT, UTC+5:30)
# 3. COUNTRY: Any country or region mentioned (e.g., India, United States, UK, Australia). If no country is mentioned, return "Not specified".

# If the input is unclear or doesn't contain valid date/time info, respond with: INVALID

# Format your response as:
# DATETIME: <extracted datetime>
# TIMEZONE: <extracted timezone or "Not specified">
# COUNTRY: <extracted country or "Not specified">

# Examples:
# - Input: "tomorrow 3 pm ist india" → DATETIME: tomorrow 3 PM | TIMEZONE: IST | COUNTRY: India
# - Input: "Monday 10 AM EST" → DATETIME: Monday 10 AM | TIMEZONE: EST | COUNTRY: Not specified
# - Input: "next week" → DATETIME: next week | TIMEZONE: Not specified | COUNTRY: Not specified
# - Input: "hello" → INVALID"""

#             response = llm.invoke(prompt)
#             result = response.content.strip() if hasattr(response, 'content') else str(response).strip()
            
#             if 'INVALID' in result.upper():
#                 return (None, None, None)

#             # Parse the response
#             datetime_str = None
#             timezone_str = None
#             country_str = None

#             for line in result.split('\n'):
#                 line = line.strip()
#                 if line.upper().startswith('DATETIME:'):
#                     datetime_str = line.split(':', 1)[1].strip().split('|')[0].strip()
#                 elif line.upper().startswith('TIMEZONE:'):
#                     timezone_str = line.split(':', 1)[1].strip()
#                 elif line.upper().startswith('COUNTRY:'):
#                     country_str = line.split(':', 1)[1].strip()

#             if datetime_str:
#                 return (
#                     datetime_str,
#                     timezone_str if timezone_str else "Not specified",
#                     country_str if country_str else "Not specified"
#                 )
#             return (None, None, None)

#         except Exception as e:
#             logger.error(f"Error parsing datetime with timezone: {e}")
#             # Fallback: accept the input as datetime and check for common timezone abbreviations and country names
#             user_lower = user_input.lower()
#             common_timezones = ['ist', 'est', 'pst', 'cst', 'mst', 'gmt', 'utc', 'bst', 'cet', 'jst', 'aest']
#             common_countries = ['india', 'united states', 'usa', 'uk', 'united kingdom', 'australia', 'canada', 'germany', 'france', 'spain']

#             found_tz = None
#             for tz in common_timezones:
#                 if tz in user_lower:
#                     found_tz = tz.upper()
#                     break

#             found_country = None
#             for c in common_countries:
#                 if c in user_lower:
#                     # Normalize some common aliases
#                     if c == 'usa':
#                         found_country = 'United States'
#                     elif c == 'uk' or c == 'united kingdom':
#                         found_country = 'United Kingdom'
#                     else:
#                         found_country = c.title()
#                     break

#             # If input has some content, accept it
#             if len(user_input.strip()) > 2:
#                 return (
#                     user_input.strip(),
#                     found_tz if found_tz else "Not specified",
#                     found_country if found_country else "Not specified"
#                 )
#             return (None, None, None)
    
#     @staticmethod
#     def ask_for_contact_consent(original_query: str, is_explicit_request: bool = False) -> str:
#         """
#         Generate message asking user if they want to be contacted.
        
#         Args:
#             original_query: The query that triggered this
#             is_explicit_request: True if user explicitly asked to be contacted (e.g., "connect me")
            
#         Returns:
#             Consent request message
#         """
#         if is_explicit_request:
#             # User explicitly asked to be contacted - ask for availability directly
#             # (user details should already be collected in initial flow)
#             return "Great! I'll connect you with our team. When would be the best time for them to reach out? Please include your timezone and country. For example: 'Tomorrow 3 PM IST India' or 'Monday 10 AM EST USA'"
#         else:
#             # RAG fallback - no information found, ask for consent first
#             return f"""I don't have specific information about that in our current documents. However, I'd be happy to connect you with our team who can provide detailed assistance with your question about: "{original_query}"

# Would you like us to contact you?"""
    
#     @staticmethod
#     def handle_contact_form_step(
#         form_state: str,
#         user_input: str,
#         form_data: Dict[str, Any],
#         session_id: str,
#         mongodb_client: Optional[MongoDBClient]
#     ) -> Dict[str, Any]:
#         """
#         Handle a single step of the contact form collection.
        
#         Args:
#             form_state: Current form state
#             user_input: User's input
#             form_data: Partially collected form data
#             session_id: Session ID
#             mongodb_client: MongoDB client instance
            
#         Returns:
#             Dictionary with next_state, response, and updated form_data
#         """
#         from legacy.agent import ContactFormState
        
#         user_input = user_input.strip()
        
#         # Handle INITIAL collection (at session start)
#         if form_state == ContactFormState.INITIAL_COLLECTING_NAME.value:
#             is_valid, error = validate_name(user_input)
#             if not is_valid:
#                 return {
#                     'next_state': form_state,
#                     'response': f"{error} Please provide your full name:",
#                     'form_data': form_data
#                 }
#             form_data['name'] = user_input
#             return {
#                 'next_state': ContactFormState.INITIAL_COLLECTING_EMAIL.value,
#                 'response': f"Thanks, {user_input}! What's your email address?",
#                 'form_data': form_data
#             }
        
#         elif form_state == ContactFormState.INITIAL_COLLECTING_EMAIL.value:
#             is_valid, error = validate_email(user_input)
#             if not is_valid:
#                 return {
#                     'next_state': form_state,
#                     'response': f"{error} Please provide a valid email address:",
#                     'form_data': form_data
#                 }
#             form_data['email'] = user_input
#             return {
#                 'next_state': ContactFormState.INITIAL_COLLECTING_PHONE.value,
#                 'response': "Perfect! What's your mobile number? Please include your country code.",
#                 'form_data': form_data
#             }
        
#         elif form_state == ContactFormState.INITIAL_COLLECTING_PHONE.value:
#             is_valid, error = validate_phone(user_input)
#             if not is_valid:
#                 return {
#                     'next_state': form_state,
#                     'response': f"{error} Please provide your mobile number:",
#                     'form_data': form_data
#                 }
#             form_data['mobile'] = user_input
#             return {
#                 'next_state': ContactFormState.IDLE.value,
#                 'response': f"Thank you! I now have your details. How can I assist you today?",
#                 'form_data': form_data  # Keep the data for later use
#             }
        
#         # Handle consent (using LLM to understand natural language)
#         if form_state == ContactFormState.ASKING_CONSENT.value:
#             consent = ContactFormHandler.understand_consent(user_input)
            
#             if consent == 'yes':
#                 # User consents - check if they have existing schedule
#                 has_schedule = form_data.get('preferred_datetime') and form_data.get('timezone')
                
#                 if has_schedule:
#                     # User has existing schedule, ask if they want to keep or change
#                     existing_datetime = form_data.get('preferred_datetime')
#                     existing_timezone = form_data.get('timezone')
#                     return {
#                         'next_state': ContactFormState.ASKING_SCHEDULE_CHANGE.value,
#                         'response': f"Sure! You previously scheduled a call for {existing_datetime}. Would you like to keep this time or change it?",
#                         'form_data': form_data
#                     }
#                 else:
#                     # No existing schedule, ask for availability
#                     return {
#                         'next_state': ContactFormState.COLLECTING_DATETIME.value,
#                         'response': "Great! When would be the best time for our team to reach out? Please include your timezone and country. For example: 'Tomorrow 3 PM IST India' or 'Monday 10 AM EST USA'",
#                         'form_data': form_data
#                     }
#             elif consent == 'no':
#                 return {
#                     'next_state': ContactFormState.IDLE.value,
#                     'response': "No problem! Is there anything else I can help you with?",
#                     'form_data': form_data  # Preserve user data even if they decline
#                 }
#             else:
#                 # Unclear response, ask again
#                 return {
#                     'next_state': form_state,
#                     'response': "I didn't quite catch that. Would you like our team to contact you?",
#                     'form_data': form_data
#                 }
        
#         # Handle schedule change question
#         elif form_state == ContactFormState.ASKING_SCHEDULE_CHANGE.value:
#             decision = ContactFormHandler.understand_schedule_change(user_input)
            
#             if decision == 'keep':
#                 # Keep existing schedule, save and complete
#                 if mongodb_client:
#                     try:
#                         request_id = mongodb_client.create_contact_request(
#                             session_id=session_id,
#                             name=form_data['name'],
#                             email=form_data['email'],
#                             mobile=form_data['mobile'],
#                             preferred_datetime=form_data['preferred_datetime'],
#                             timezone=form_data['timezone'],
#                             original_query=form_data.get('original_query', 'Not specified'),
#                             country=form_data.get('country', 'Not specified')
#                         )
#                         if request_id:
#                             logger.info(f"Contact request saved: {request_id}")
#                     except Exception as e:
#                         logger.error(f"Error saving contact request: {e}")
                
#                 return {
#                     'next_state': ContactFormState.IDLE.value,
#                     'response': f"All set! We'll contact you at {form_data.get('preferred_datetime')} ({form_data.get('timezone')}, {form_data.get('country')}). Is there anything else I can help you with?",
#                     'form_data': form_data  # Preserve all data
#                 }
#             elif decision == 'change':
#                 # User wants to change, ask for new datetime (ask for timezone and country)
#                 return {
#                     'next_state': ContactFormState.COLLECTING_DATETIME.value,
#                     'response': "No problem! When would be the best time for our team to reach out? ",
#                     'form_data': form_data
#                 }
#             else:
#                 # Unclear response, ask again
#                 return {
#                     'next_state': form_state,
#                     'response': "I didn't quite understand. Would you like to keep the existing scheduled time, or would you prefer to change it?",
#                     'form_data': form_data
#                 }
        
#         # Collect name
#         elif form_state == ContactFormState.COLLECTING_NAME.value:
#             is_valid, error = validate_name(user_input)
#             if not is_valid:
#                 return {
#                     'next_state': form_state,
#                     'response': f"{error} Please provide your full name:",
#                     'form_data': form_data
#                 }
#             form_data['name'] = user_input
#             return {
#                 'next_state': ContactFormState.COLLECTING_EMAIL.value,
#                 'response': f"Thanks, {user_input}! What's your email address?",
#                 'form_data': form_data
#             }
        
#         # Collect email
#         elif form_state == ContactFormState.COLLECTING_EMAIL.value:
#             is_valid, error = validate_email(user_input)
#             if not is_valid:
#                 return {
#                     'next_state': form_state,
#                     'response': f"{error} Please provide a valid email address:",
#                     'form_data': form_data
#                 }
#             form_data['email'] = user_input
#             return {
#                 'next_state': ContactFormState.COLLECTING_PHONE.value,
#                 'response': "Perfect! What's your mobile number? Please include your country code.",
#                 'form_data': form_data
#             }
        
#         # Collect phone
#         elif form_state == ContactFormState.COLLECTING_PHONE.value:
#             is_valid, error = validate_phone(user_input)
#             if not is_valid:
#                 return {
#                     'next_state': form_state,
#                     'response': f"{error} Please provide your mobile number:",
#                     'form_data': form_data
#                 }
#             form_data['mobile'] = user_input
#             return {
#                 'next_state': ContactFormState.COLLECTING_DATETIME.value,
#                 'response': "Got it! When would you prefer us to contact you? Please include your timezone and country. For example: 'Tomorrow 3 PM IST India' or 'Monday 10 AM EST USA'",
#                 'form_data': form_data
#             }
        
#         # Collect datetime with timezone and country (combined in one step)
#         elif form_state == ContactFormState.COLLECTING_DATETIME.value:
#             # Parse datetime, timezone and country from the combined input
#             # User can say things like "Tomorrow 3 PM IST India" or "Monday 10 AM EST USA"
#             parsed_datetime, parsed_timezone, parsed_country = ContactFormHandler.parse_datetime_with_timezone(user_input)
            
#             if not parsed_datetime:
#                 return {
#                     'next_state': form_state,
#                     'response': "Please provide when you're available ",
#                     'form_data': form_data
#                 }
            
#             form_data['preferred_datetime'] = parsed_datetime
#             form_data['timezone'] = parsed_timezone if parsed_timezone else "Not specified"
#             form_data['country'] = parsed_country if parsed_country else "Not specified"
            
#             # Save to MongoDB
#             if mongodb_client:
#                 try:
#                     request_id = mongodb_client.create_contact_request(
#                         session_id=session_id,
#                         name=form_data['name'],
#                         email=form_data['email'],
#                         mobile=form_data['mobile'],
#                         preferred_datetime=form_data['preferred_datetime'],
#                         timezone=form_data['timezone'],
#                         original_query=form_data.get('original_query', 'Not specified'),
#                         country=form_data.get('country', 'Not specified')
#                     )
#                     if request_id:
#                         logger.info(f"Contact request saved: {request_id}")
#                     else:
#                         logger.error("Failed to save contact request")
#                 except Exception as e:
#                     logger.error(f"Error saving contact request: {e}")
            
#             # Preserve ALL user data including schedule for future requests
#             preserved_data = {
#                 'name': form_data.get('name'),
#                 'email': form_data.get('email'),
#                 'mobile': form_data.get('mobile'),
#                 'preferred_datetime': form_data.get('preferred_datetime'),
#                 'timezone': form_data.get('timezone'),
#                 'country': form_data.get('country')
#             }
            
#             # Set to IDLE so next query goes through normal flow
#             return {
#                 'next_state': ContactFormState.IDLE.value,
#                 'response': "All set! We've recorded your request and our team will contact you. Is there anything else I can help you with?",
#                 'form_data': preserved_data  # Keep ALL user data for future use
#             }
        
#         # Default fallback
#         return {
#             'next_state': ContactFormState.IDLE.value,
#             'response': "Something went wrong. Let's start over. How can I help you?",
#             'form_data': {}
#         }


"""
Contact form handling methods for ChatbotAgent.
These methods handle the multi-step contact request form collection.
"""
import logging
from typing import Dict, Any, Optional
from utils.validators import validate_email, validate_phone, validate_datetime, validate_name
from database.mongodb_client import MongoDBClient
from langchain_openai import ChatOpenAI
from config import config
from utils.cache import consent_cache, _consent_lock, normalize_query

logger = logging.getLogger(__name__)


class ContactFormHandler:
    """Handles contact form state and collection logic."""
    
    # LLM instance for understanding natural language responses
    _llm = None
    
    @classmethod
    def get_llm(cls):
        """Get or create LLM instance."""
        if cls._llm is None:
            cls._llm = ChatOpenAI(
                model=config.openai_model,
                temperature=0.1,
                api_key=config.openai_api_key
            )
        return cls._llm
    
    @staticmethod
    def detect_form_cancellation(user_input: str, current_state: str) -> bool:
        """
        Detect if user wants to cancel/abandon the current form flow,
        or is asking something completely unrelated (topic change).
        
        The bot should NEVER trap a user.  If they change topic, let them go.
        
        Args:
            user_input: User's natural language response
            current_state: Current form state name
            
        Returns:
            True if user wants to exit the form, False to continue the form flow
        """
        # Quick keyword check first to avoid unnecessary LLM calls
        cancel_phrases = [
            'leave it', 'skip', 'cancel', 'never mind', 'nevermind',
            'forget it', 'stop', 'quit', "don't want", "dont want",
            'no thanks', 'not interested', 'not now', 'maybe later',
            'drop it', 'abort', "i don't want to", "i dont want to",
            'back', 'go back', 'exit'
        ]
        user_lower = user_input.lower().strip()
        if any(phrase in user_lower for phrase in cancel_phrases):
            return True
        
        # Use LLM for ambiguous cases (topic changes like "tell me about yourself")
        try:
            llm = ContactFormHandler.get_llm()
            prompt = f"""The bot is in the middle of a scheduling/contact form (state: {current_state}).
The user just said: "{user_input}"

Is this message a DIRECT answer to the form question, or is the user asking/saying something UNRELATED?

CONTINUE — the message directly answers the form step:
  • a date/time ("tomorrow 3pm", "Monday morning", "next week")
  • an email, phone number, or name
  • a yes/no/consent answer ("yes", "sure", "no", "ok")
  • "keep it" / "change it" / "reschedule" (schedule decision)
  • any short affirmation or form-related value

EXIT — the message is about a DIFFERENT topic or cancels the form:
  • asking a question about the company ("where is your company", "what do you do")
  • asking about services, pricing, tech, features
  • any question or statement unrelated to providing contact/scheduling info
  • explicit cancellation ("forget it", "leave it")

Respond with ONLY: CONTINUE or EXIT"""

            response = llm.invoke(prompt)
            result = response.content.strip().upper() if hasattr(response, 'content') else str(response).strip().upper()
            
            if 'EXIT' in result:
                return True
            return False
        except Exception as e:
            logger.error(f"Error detecting form cancellation: {e}")
            return False
    
    @staticmethod
    def understand_consent(user_input: str) -> str:
        """
        Use LLM to understand if user is giving consent (yes/no).

        Results are cached by normalised input (LRU, unbounded TTL) because
        "yes", "sure", "no thanks" etc. always map to the same answer.

        Args:
            user_input: User's natural language response

        Returns:
            'yes', 'no', or 'unclear'
        """
        # --- cache read ---
        cache_key = ("consent", normalize_query(user_input))
        with _consent_lock:
            cached = consent_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Consent cache HIT: '{user_input}' → {cached}")
            return cached

        try:
            llm = ContactFormHandler.get_llm()
            prompt = f"""You are analyzing a user's response to determine if they are giving consent to be contacted or to proceed.

User's response: "{user_input}"

The user was asked if they want to connect with the team or schedule a call.

Classify the response as:
- YES: if user agrees, accepts, or wants to proceed (e.g., "yes", "sure", "please", "that would be great", "okay", "yeah", "go ahead", "yes go ahead", "I'd like that", "please do", "yes please", "do it", "let's do it", "absolutely", "of course", "why not", "sounds good", "perfect")
- NO: if user declines or doesn't want to proceed (e.g., "no", "nope", "not now", "no thanks", "I'm good", "not interested", "maybe later", "skip", "nevermind")
- UNCLEAR: ONLY if the response is completely unrelated or ambiguous

Important: Lean towards YES if the user seems even mildly positive. Only use UNCLEAR as a last resort.

Respond with ONLY: YES, NO, or UNCLEAR"""

            response = llm.invoke(prompt)
            result_text = response.content.strip().upper() if hasattr(response, 'content') else str(response).strip().upper()

            if 'YES' in result_text:
                result = 'yes'
            elif 'NO' in result_text:
                result = 'no'
            else:
                result = 'unclear'

            # --- cache write ---
            with _consent_lock:
                consent_cache[cache_key] = result

            return result

        except Exception as e:
            logger.error(f"Error understanding consent: {e}")
            # Fallback to simple keyword check
            user_lower = user_input.lower().strip()
            if any(word in user_lower for word in ['yes', 'sure', 'ok', 'okay', 'yeah', 'please', 'go ahead']):
                return 'yes'
            elif any(word in user_lower for word in ['no', 'nope', 'not', "don't", 'cancel']):
                return 'no'
            return 'unclear'
    
    @staticmethod
    def understand_schedule_change(user_input: str) -> str:
        """
        Use LLM to understand if user wants to keep or change existing schedule.

        Results are cached by normalised input (shared consent_cache, LRU)
        because "keep it", "change it" etc. always produce the same answer.

        Args:
            user_input: User's natural language response

        Returns:
            'keep', 'change', or 'unclear'
        """
        # --- cache read ---
        cache_key = ("schedule_change", normalize_query(user_input))
        with _consent_lock:
            cached = consent_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Schedule-change cache HIT: '{user_input}' → {cached}")
            return cached

        try:
            llm = ContactFormHandler.get_llm()
            prompt = f"""You are analyzing a user's response to determine if they want to keep their existing scheduled time or change it.

User's response: "{user_input}"

The user was asked: "Would you like to keep this scheduled time or change it?"

Classify the response as:
- KEEP: if user wants to keep the same time (e.g., "keep it", "same time", "that's fine", "no change", "yes", "ok", "sounds good", "perfect", "that works")
- CHANGE: if user wants to change/reschedule (e.g., "change", "different time", "reschedule", "new time", "update it", "modify", "no I want to change")
- UNCLEAR: if the response doesn't clearly indicate keep or change

Respond with ONLY: KEEP, CHANGE, or UNCLEAR"""

            response = llm.invoke(prompt)
            result_text = response.content.strip().upper() if hasattr(response, 'content') else str(response).strip().upper()

            if 'KEEP' in result_text:
                result = 'keep'
            elif 'CHANGE' in result_text:
                result = 'change'
            else:
                result = 'unclear'

            # --- cache write ---
            with _consent_lock:
                consent_cache[cache_key] = result

            return result

        except Exception as e:
            logger.error(f"Error understanding schedule change: {e}")
            # Fallback to simple keyword check
            user_lower = user_input.lower().strip()
            if any(word in user_lower for word in ['change', 'different', 'new', 'reschedule', 'update', 'modify']):
                return 'change'
            elif any(word in user_lower for word in ['keep', 'same', 'fine', 'ok', 'okay', 'yes', 'good', 'perfect', 'works']):
                return 'keep'
            return 'unclear'
    
    @staticmethod
    def should_trigger_contact_form(context_docs: list, distance_threshold: float = 1.5) -> bool:
        """
        Determine if contact form should be triggered based on search results.
        
        Args:
            context_docs: Retrieved context documents
            distance_threshold: Maximum acceptable distance for relevant results
            
        Returns:
            True if contact form should be triggered
        """
        # Trigger if no results or all results have poor similarity
        if not context_docs:
            return True
        
        # Check if all results are beyond the threshold
        relevant_count = sum(1 for doc in context_docs if doc.get('distance', 0) < distance_threshold)
        return relevant_count == 0
    
    @staticmethod
    def parse_datetime_with_timezone(user_input: str) -> tuple:
        """
        Parse datetime, timezone and country from combined user input using LLM.
        
        Args:
            user_input: User's natural language response like "Tomorrow 3 PM IST, India"
            
        Returns:
            Tuple of (datetime_str, timezone_str, country_str) or (None, None, None) if parsing fails
        """
        try:
            llm = ContactFormHandler.get_llm()
            prompt = f"""You are parsing a user's availability response to extract date/time, timezone and country/location.

User's response: "{user_input}"

Extract:
1. DATE/TIME: The date and time they mentioned (e.g., "tomorrow 3 PM", "Monday 10 AM", "25th December 2pm")
2. TIMEZONE: Any timezone mentioned (e.g., IST, EST, PST, GMT, UTC+5:30)
3. COUNTRY: Any country or region mentioned (e.g., India, United States, UK, Australia). If no country is mentioned, return "Not specified".

If the input is unclear or doesn't contain valid date/time info, respond with: INVALID

Format your response as:
DATETIME: <extracted datetime>
TIMEZONE: <extracted timezone or "Not specified">
COUNTRY: <extracted country or "Not specified">

Examples:
- Input: "tomorrow 3 pm ist india" → DATETIME: tomorrow 3 PM | TIMEZONE: IST | COUNTRY: India
- Input: "Monday 10 AM EST" → DATETIME: Monday 10 AM | TIMEZONE: EST | COUNTRY: Not specified
- Input: "next week" → DATETIME: next week | TIMEZONE: Not specified | COUNTRY: Not specified
- Input: "hello" → INVALID"""

            response = llm.invoke(prompt)
            result = response.content.strip() if hasattr(response, 'content') else str(response).strip()
            
            if 'INVALID' in result.upper():
                return (None, None, None)

            # Parse the response
            datetime_str = None
            timezone_str = None
            country_str = None

            for line in result.split('\n'):
                line = line.strip()
                if line.upper().startswith('DATETIME:'):
                    datetime_str = line.split(':', 1)[1].strip().split('|')[0].strip()
                elif line.upper().startswith('TIMEZONE:'):
                    timezone_str = line.split(':', 1)[1].strip()
                elif line.upper().startswith('COUNTRY:'):
                    country_str = line.split(':', 1)[1].strip()

            if datetime_str:
                return (
                    datetime_str,
                    timezone_str if timezone_str else "Not specified",
                    country_str if country_str else "Not specified"
                )
            return (None, None, None)

        except Exception as e:
            logger.error(f"Error parsing datetime with timezone: {e}")
            # Fallback: accept the input as datetime and check for common timezone abbreviations and country names
            user_lower = user_input.lower()
            common_timezones = ['ist', 'est', 'pst', 'cst', 'mst', 'gmt', 'utc', 'bst', 'cet', 'jst', 'aest']
            common_countries = ['india', 'united states', 'usa', 'uk', 'united kingdom', 'australia', 'canada', 'germany', 'france', 'spain']

            found_tz = None
            for tz in common_timezones:
                if tz in user_lower:
                    found_tz = tz.upper()
                    break

            found_country = None
            for c in common_countries:
                if c in user_lower:
                    # Normalize some common aliases
                    if c == 'usa':
                        found_country = 'United States'
                    elif c == 'uk' or c == 'united kingdom':
                        found_country = 'United Kingdom'
                    else:
                        found_country = c.title()
                    break

            # If input has some content, accept it
            if len(user_input.strip()) > 2:
                return (
                    user_input.strip(),
                    found_tz if found_tz else "Not specified",
                    found_country if found_country else "Not specified"
                )
            return (None, None, None)
    
    @staticmethod
    def ask_for_contact_consent(original_query: str, is_explicit_request: bool = False) -> str:
        """
        Generate message asking user if they want to be contacted.
        
        Args:
            original_query: The query that triggered this
            is_explicit_request: True if user explicitly asked to be contacted (e.g., "connect me")
            
        Returns:
            Consent request message
        """
        if is_explicit_request:
            # User explicitly asked to be contacted - ask for availability directly
            # (user details should already be collected in initial flow)
            return "Great! I'll connect you with our team. When would be the best time for them to reach out?"
        else:
            # RAG fallback - no information found, ask for consent first
            return f"""I don't have specific information about that in our current documents. However, I'd be happy to connect you with our team who can provide detailed assistance with your question about: "{original_query}"

Would you like us to contact you?"""
    
    @staticmethod
    def handle_contact_form_step(
        form_state: str,
        user_input: str,
        form_data: Dict[str, Any],
        session_id: str,
        mongodb_client: Optional[MongoDBClient]
    ) -> Dict[str, Any]:
        """
        Handle a single step of the contact form collection.
        
        Args:
            form_state: Current form state
            user_input: User's input
            form_data: Partially collected form data
            session_id: Session ID
            mongodb_client: MongoDB client instance
            
        Returns:
            Dictionary with next_state, response, and updated form_data
        """
        from legacy.agent import ContactFormState
        
        user_input = user_input.strip()
        
        # Handle INITIAL collection (at session start)
        if form_state == ContactFormState.INITIAL_COLLECTING_NAME.value:
            is_valid, error = validate_name(user_input)
            if not is_valid:
                return {
                    'next_state': form_state,
                    'response': f"{error} Please provide your full name:",
                    'form_data': form_data
                }
            form_data['name'] = user_input
            return {
                'next_state': ContactFormState.INITIAL_COLLECTING_EMAIL.value,
                'response': f"Thanks, {user_input}! What's your email address?",
                'form_data': form_data
            }
        
        elif form_state == ContactFormState.INITIAL_COLLECTING_EMAIL.value:
            is_valid, error = validate_email(user_input)
            if not is_valid:
                return {
                    'next_state': form_state,
                    'response': f"{error} Please provide a valid email address:",
                    'form_data': form_data
                }
            form_data['email'] = user_input
            return {
                'next_state': ContactFormState.INITIAL_COLLECTING_PHONE.value,
                'response': "Perfect! What's your mobile number? Please include your country code.",
                'form_data': form_data
            }
        
        elif form_state == ContactFormState.INITIAL_COLLECTING_PHONE.value:
            is_valid, error = validate_phone(user_input)
            if not is_valid:
                return {
                    'next_state': form_state,
                    'response': f"{error} Please provide your mobile number:",
                    'form_data': form_data
                }
            form_data['mobile'] = user_input
            return {
                'next_state': ContactFormState.IDLE.value,
                'response': f"Thank you! I now have your details. How can I assist you today?",
                'form_data': form_data  # Keep the data for later use
            }
        
        # Handle consent (using LLM to understand natural language)
        if form_state == ContactFormState.ASKING_CONSENT.value:
            consent = ContactFormHandler.understand_consent(user_input)
            
            if consent == 'yes':
                # User consents - check if they have existing schedule
                has_schedule = form_data.get('preferred_datetime') and form_data.get('timezone')
                
                if has_schedule:
                    # User has existing schedule, ask if they want to keep or change
                    existing_datetime = form_data.get('preferred_datetime')
                    existing_timezone = form_data.get('timezone')
                    return {
                        'next_state': ContactFormState.ASKING_SCHEDULE_CHANGE.value,
                        'response': f"Sure! You previously scheduled a call for {existing_datetime}. Would you like to keep this time or change it?",
                        'form_data': form_data
                    }
                else:
                    # No existing schedule, ask for availability
                    return {
                        'next_state': ContactFormState.COLLECTING_DATETIME.value,
                        'response': "Great! When would be the best time for our team to reach out?",
                        'form_data': form_data
                    }
            elif consent == 'no':
                return {
                    'next_state': ContactFormState.IDLE.value,
                    'response': "No problem! Is there anything else I can help you with?",
                    'form_data': form_data  # Preserve user data even if they decline
                }
            else:
                # Unclear response, ask again
                return {
                    'next_state': form_state,
                    'response': "I didn't quite catch that. Would you like our team to contact you?",
                    'form_data': form_data
                }
        
        # Handle schedule change question
        elif form_state == ContactFormState.ASKING_SCHEDULE_CHANGE.value:
            decision = ContactFormHandler.understand_schedule_change(user_input)
            
            if decision == 'keep':
                # Keep existing schedule, save and complete
                if mongodb_client:
                    try:
                        request_id = mongodb_client.create_contact_request(
                            session_id=session_id,
                            name=form_data.get('name', 'Not provided'),
                            email=form_data.get('email', 'Not provided'),
                            mobile=form_data.get('mobile', 'Not provided'),
                            preferred_datetime=form_data['preferred_datetime'],
                            timezone=form_data['timezone'],
                            original_query=form_data.get('original_query', 'Not specified'),
                            country=form_data.get('country', 'Not specified')
                        )
                        if request_id:
                            logger.info(f"Contact request saved: {request_id}")
                    except Exception as e:
                        logger.error(f"Error saving contact request: {e}")
                
                return {
                    'next_state': ContactFormState.IDLE.value,
                    'response': f"All set! We'll contact you at {form_data.get('preferred_datetime')} ({form_data.get('timezone')}, {form_data.get('country')}). Is there anything else I can help you with?",
                    'form_data': form_data  # Preserve all data
                }
            elif decision == 'change':
                # User wants to change, ask for new datetime (ask for timezone and country)
                return {
                    'next_state': ContactFormState.COLLECTING_DATETIME.value,
                    'response': "No problem! When would be the best time for our team to reach out?",
                    'form_data': form_data
                }
            else:
                # Unclear response, ask again
                return {
                    'next_state': form_state,
                    'response': "I didn't quite understand. Would you like to keep the existing scheduled time, or would you prefer to change it?",
                    'form_data': form_data
                }
        
        # Collect name
        elif form_state == ContactFormState.COLLECTING_NAME.value:
            is_valid, error = validate_name(user_input)
            if not is_valid:
                return {
                    'next_state': form_state,
                    'response': f"{error} Please provide your full name:",
                    'form_data': form_data
                }
            form_data['name'] = user_input
            return {
                'next_state': ContactFormState.COLLECTING_EMAIL.value,
                'response': f"Thanks, {user_input}! What's your email address?",
                'form_data': form_data
            }
        
        # Collect email
        elif form_state == ContactFormState.COLLECTING_EMAIL.value:
            is_valid, error = validate_email(user_input)
            if not is_valid:
                return {
                    'next_state': form_state,
                    'response': f"{error} Please provide a valid email address:",
                    'form_data': form_data
                }
            form_data['email'] = user_input
            return {
                'next_state': ContactFormState.COLLECTING_PHONE.value,
                'response': "Perfect! What's your mobile number? Please include your country code.",
                'form_data': form_data
            }
        
        # Collect phone
        elif form_state == ContactFormState.COLLECTING_PHONE.value:
            is_valid, error = validate_phone(user_input)
            if not is_valid:
                return {
                    'next_state': form_state,
                    'response': f"{error} Please provide your mobile number:",
                    'form_data': form_data
                }
            form_data['mobile'] = user_input
            return {
                'next_state': ContactFormState.COLLECTING_DATETIME.value,
                'response': "Got it! When would you prefer us to contact you?",
                'form_data': form_data
            }
        
        # Collect datetime with timezone and country (combined in one step)
        elif form_state == ContactFormState.COLLECTING_DATETIME.value:
            # Parse datetime, timezone and country from the combined input
            # User can say things like "Tomorrow 3 PM IST India" or "Monday 10 AM EST USA"
            parsed_datetime, parsed_timezone, parsed_country = ContactFormHandler.parse_datetime_with_timezone(user_input)
            
            if not parsed_datetime:
                return {
                    'next_state': form_state,
                    'response': "Please provide your availability.",
                    'form_data': form_data
                }
            
            form_data['preferred_datetime'] = parsed_datetime
            form_data['timezone'] = parsed_timezone if parsed_timezone else "Not specified"
            form_data['country'] = parsed_country if parsed_country else "Not specified"
            
            # Save to MongoDB
            if mongodb_client:
                try:
                    request_id = mongodb_client.create_contact_request(
                        session_id=session_id,
                        name=form_data.get('name', 'Not provided'),
                        email=form_data.get('email', 'Not provided'),
                        mobile=form_data.get('mobile', 'Not provided'),
                        preferred_datetime=form_data['preferred_datetime'],
                        timezone=form_data['timezone'],
                        original_query=form_data.get('original_query', 'Not specified'),
                        country=form_data.get('country', 'Not specified')
                    )
                    if request_id:
                        logger.info(f"Contact request saved: {request_id}")
                    else:
                        logger.error("Failed to save contact request")
                except Exception as e:
                    logger.error(f"Error saving contact request: {e}")
            
            # Preserve ALL user data including schedule for future requests
            preserved_data = {
                'name': form_data.get('name'),
                'email': form_data.get('email'),
                'mobile': form_data.get('mobile'),
                'preferred_datetime': form_data.get('preferred_datetime'),
                'timezone': form_data.get('timezone'),
                'country': form_data.get('country')
            }
            
            # Set to IDLE so next query goes through normal flow
            return {
                'next_state': ContactFormState.IDLE.value,
                'response': "All set! We've recorded your request and our team will contact you. Is there anything else I can help you with?",
                'form_data': preserved_data  # Keep ALL user data for future use
            }
        
        # Default fallback
        return {
            'next_state': ContactFormState.IDLE.value,
            'response': "Something went wrong. Let's start over. How can I help you?",
            'form_data': {}
        }


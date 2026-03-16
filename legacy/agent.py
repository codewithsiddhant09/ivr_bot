# """
# CrewAI agent for intent classification, greeting handling, and query processing.
# """
# import logging
# from typing import Dict, Any, List
# from enum import Enum

# from crewai import Agent
# from langchain_openai import ChatOpenAI

# from config import config
# from vectorstore.chromadb_client import ChromaDBClient
# from database.mongodb_client import MongoDBClient
# from utils.reranker import Reranker
# import re
# from datetime import datetime

# logger = logging.getLogger(__name__)


# class IntentType(Enum):
#     """Intent classification types."""
#     GREETING = "greeting"
#     CASUAL_CHAT = "casual_chat"  # Casual conversational responses like "I'm doing great"
#     FOLLOWUP = "followup"
#     CONTACT_REQUEST = "contact_request"
#     FEEDBACK = "feedback"  # User wants to share feedback/message with team
#     QUERY = "query"
#     GOODBYE = "goodbye"
#     UNCLEAR = "unclear"


# class ContactFormState(Enum):
#     """Contact form collection states."""
#     IDLE = "idle"
#     # Initial collection at session start
#     INITIAL_COLLECTING_NAME = "initial_collecting_name"
#     INITIAL_COLLECTING_EMAIL = "initial_collecting_email"
#     INITIAL_COLLECTING_PHONE = "initial_collecting_phone"
#     # Connect with team - only collect availability
#     ASKING_CONSENT = "asking_consent"
#     ASKING_SCHEDULE_CHANGE = "asking_schedule_change"  # Ask if user wants to keep or change existing schedule
#     COLLECTING_DATETIME = "collecting_datetime"
#     COLLECTING_TIMEZONE = "collecting_timezone"
#     # Legacy states (for backward compatibility)
#     COLLECTING_NAME = "collecting_name"
#     COLLECTING_EMAIL = "collecting_email"
#     COLLECTING_PHONE = "collecting_phone"
#     COMPLETED = "completed"


# class ChatbotAgent:
#     """CrewAI-powered agent for handling user intents and generating responses."""
    
#     def __init__(self, chromadb_client: ChromaDBClient):
#         """
#         Initialize the chatbot agent.
        
#         Args:
#             chromadb_client: ChromaDB client for document retrieval
#         """
#         self.chromadb_client = chromadb_client
        
#         # Initialize reranker if enabled
#         self.reranker = None
#         if config.enable_reranking:
#             try:
#                 self.reranker = Reranker(model_name=config.reranker_model)
#                 logger.info(f"Reranker initialized with model: {config.reranker_model}")
#             except Exception as e:
#                 logger.error(f"Failed to initialize reranker: {e}")
#                 logger.warning("Continuing without reranking")
#         else:
#             logger.info("Reranking disabled in configuration")
        
#         # Initialize MongoDB client for contact requests
#         try:
#             if config.mongodb_uri:
#                 self.mongodb_client = MongoDBClient(config.mongodb_uri, config.mongodb_database)
#                 logger.info("MongoDB client initialized for contact requests")
                
#                 # List all collections for debugging
#                 collections = self.mongodb_client.list_collections()
#                 logger.info(f"Available MongoDB collections: {collections}")
                
#                 # Get session count
#                 session_count = self.mongodb_client.get_session_count()
#                 logger.info(f"Total sessions stored: {session_count}")
#             else:
#                 self.mongodb_client = None
#                 logger.warning("MongoDB URI not configured - contact requests will not be saved")
#         except Exception as e:
#             logger.error(f"Failed to initialize MongoDB client: {e}")
#             self.mongodb_client = None
        
#         # Disable CrewAI telemetry and traces
#         import os
#         os.environ['CREWAI_TELEMETRY'] = 'false'
#         os.environ['CREWAI_DISABLE_TELEMETRY'] = 'true'
        
#         # Initialize LLM with OpenAI's store parameter for automatic conversation storage
#         # This replaces Redis caching - OpenAI stores conversations for 30 days
#         self.llm = ChatOpenAI(
#             model="gpt-4.1-nano",
#             temperature=0.3,  # Increased for more creative, human-like responses
#             openai_api_key=config.openai_api_key,
#             model_kwargs={
#                 "store": True  # Enable OpenAI conversation storage (30-day retention)
#             }
#         )
        
#         # Create the intent classification agent (for reference, not used in new implementation)
#         self.intent_agent = Agent(
#             role='Anup - Virtual Representative of TechGropse',
#             goal='As Anup, represent TechGropse and help users with all aspects of the company - services, pricing, projects, capabilities, and general inquiries',
#             backstory="""You are Anup, the official virtual representative of TechGropse, speaking on behalf of the company. 
#             You help users with everything related to TechGropse - app development services, pricing, timelines, 
#             projects, capabilities, and general company information. You always speak as 'we at TechGropse' when 
#             referring to the company (e.g., 'we at TechGropse develop', 'our services', 'we offer'). You are friendly, 
#             professional, knowledgeable, and enthusiastic about helping users with any questions about TechGropse. 
#             When greeting users, you introduce yourself as Anup from TechGropse, your virtual representative.""",
#             verbose=False,
#             allow_delegation=False,
#             llm=self.llm
#         )
    
#     def classify_intent(self, user_input: str) -> IntentType:
#         """
#         Classify the user's intent using LLM.
        
#         Args:
#             user_input: User's message
            
#         Returns:
#             Classified intent type
#         """
#         try:
#             # Use LLM to classify intent
#             prompt = f"""You are a customer service assistant. Classify the user's intent into ONE of these categories:

# 1. GREETING - user is saying hello, hi, or starting the conversation (e.g., "Hi", "Hello", "Hi, how are you?")
# 2. CASUAL_CHAT - user is making casual conversational responses like:
#    - "I'm doing great", "I'm good", "I'm fine"
#    - "How are you?" (when asked as a follow-up, not initial greeting)
#    - "me too", "same here", "that's nice"
#    - Friendly acknowledgments that don't require specific action
# 3. FOLLOWUP - user wants more details/information about the previous topic (phrases like "more info", "tell me more", "need more details", "elaborate", etc.)
# 4. CONTACT_REQUEST - user explicitly wants to be contacted by someone from the team (phrases like "connect me", "contact me", "reach out to me", "get in touch with me", "call me", "email me", "have someone contact me", "I need a callback", etc.)
# 5. FEEDBACK - user wants to share feedback, information, or a message with the team (phrases like "send this to your team", "tell your team", "convey to team", "share this with team", "let them know", "I want to share", "pass this along", etc.)
# 6. QUERY - user is asking a specific question about services, projects, capabilities, etc. This INCLUDES questions about the assistant's identity like "who are you?", "what is your name?", "tell me about yourself", etc.
# 7. GOODBYE - user is ending the conversation. This includes ANY expression of thanks, satisfaction, or ending like: "thank you", "thanks", "ok thank you", "that's all", "goodbye", "bye", "see you", "appreciate it", "perfect", "great thanks", "awesome", "all good", "done", "finished", etc.
# 8. UNCLEAR - unclear or ambiguous input

# User input: "{user_input}"

# IMPORTANT DISTINCTIONS:
# - "Hi, how are you?" = GREETING (initial contact with well-being question)
# - "How are you?" (alone, as follow-up) = CASUAL_CHAT (casual conversation)
# - "Who are you?" = QUERY (asking about the assistant's identity - needs information lookup)
# - "What is your name?" = QUERY (asking about the assistant's identity)
# - "Tell me about yourself" = QUERY (asking about the assistant)
# - "I'm doing well" = CASUAL_CHAT
# - "Tell me more" = FOLLOWUP
# - "Contact me" or "Have someone reach out to me" = CONTACT_REQUEST (they want to BE contacted)
# - "Send this to your team" or "Tell your team about this" = FEEDBACK (they want to SHARE info)
# - "Thanks" = GOODBYE

# Be VERY sensitive to goodbye hints - if there's ANY indication the user is satisfied or ending the conversation, classify as GOODBYE.
# Distinguish between CONTACT_REQUEST (user wants to be contacted) and FEEDBACK (user wants to share info with team).
# If the user is just making casual conversation or acknowledgments, classify as CASUAL_CHAT.
# ANY question about the assistant's identity (who/what/name/yourself) should be QUERY.

# Respond with ONLY the category name (GREETING, CASUAL_CHAT, FOLLOWUP, CONTACT_REQUEST, FEEDBACK, QUERY, GOODBYE, or UNCLEAR):"""

#             response = self.llm.invoke(prompt)
#             intent_text = response.content.strip().upper() if hasattr(response, 'content') else str(response).strip().upper()
            
#             # Map to IntentType
#             if 'GREETING' in intent_text:
#                 return IntentType.GREETING
#             elif 'CASUAL' in intent_text:  # Catches CASUAL_CHAT
#                 return IntentType.CASUAL_CHAT
#             elif 'FOLLOWUP' in intent_text:
#                 return IntentType.FOLLOWUP
#             elif 'CONTACT' in intent_text:  # Catches CONTACT_REQUEST
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
#             logger.error(f"Error classifying intent: {e}")
#             # Fallback to simple heuristic
#             user_input_lower = user_input.lower().strip()
            
#             # Check for contact request phrases first
#             if any(phrase in user_input_lower for phrase in [
#                 'connect me', 'contact me', 'reach out', 'get in touch',
#                 'call me', 'email me', 'have someone contact', 'someone reach out',
#                 'talk to someone', 'speak to someone', 'connect with'
#             ]):
#                 return IntentType.CONTACT_REQUEST
            
#             if any(word in user_input_lower for word in ['hi', 'hello', 'hey']):
#                 return IntentType.GREETING
#             elif any(phrase in user_input_lower for phrase in [
#                 'bye', 'goodbye', 'good bye', 'see you', 'thanks', 'thank you', 
#                 'ok thank you', 'okay thank you', 'that\'s all', 'thats all',
#                 'end', 'quit', 'exit', 'done', 'finished', 'all good',
#                 'appreciate it', 'perfect', 'great thanks', 'awesome thanks'
#             ]):
#                 return IntentType.GOODBYE
#             return IntentType.QUERY
    
#     def handle_greeting(self, user_input: str = "") -> str:
#         """
#         Generate a dynamic greeting response using LLM.
        
#         Args:
#             user_input: The user's greeting message
        
#         Returns:
#             Greeting message
#         """
#         try:
#             # Check if user asked about well-being
#             user_input_lower = user_input.lower()
#             asks_how_are_you = any(phrase in user_input_lower for phrase in [
#                 'how are you', 'how are u', 'how r you', 'how r u',
#                 'how\'s it going', 'how is it going', 'how are things',
#             ])
            
#             prompt = f"""You are Anup, a friendly representative at TechGropse.

# The user just greeted you with: "{user_input}"

# CRITICAL: Keep your greeting to ONE SHORT SENTENCE only.

# IF they asked about YOUR well-being (e.g., "Hi, how are you?", "Hello, how's it going?"):
# - Respond with: "I'm doing great, thanks for asking! How about you?"
# - Or: "Doing wonderful, thanks! How are you?"
# - Keep it to ONE sentence

# IF they just said a simple greeting (e.g., "Hi", "Hello", "Hey"):
# - Respond with: "Hi! I'm Anup from TechGropse. How can I help you?"
# - Or: "Hey! I'm Anup from TechGropse. What can I help you with?"
# - Or: "Hello! I'm Anup from TechGropse, here to help!"
# - Keep it to ONE SHORT sentence

# Examples:
# - User: "Hi, how are you?" -> "I'm doing great, thanks! How about you?"
# - User: "Hello" -> "Hi! I'm Anup from TechGropse. How can I help you?"
# - User: "Hi" -> "Hey! I'm Anup from TechGropse. What can I help you with?"

# Key points:
# - MUST be ONE SHORT sentence only
# - Be warm but concise
# - Introduce yourself as Anup from TechGropse
# - Use 'we at TechGropse', 'our', 'us' when referring to the company

# Generate a SHORT one-sentence greeting as Anup:"""

#             response = self.llm.invoke(prompt)
#             return response.content.strip() if hasattr(response, 'content') else str(response).strip()
#         except Exception as e:
#             logger.error(f"Error generating greeting: {e}")
#             return "Hi! I'm Anup from TechGropse. How can I help you?"
    
#     def handle_casual_chat(self, user_input: str) -> str:
#         """
#         Handle casual conversational responses like "I'm doing great", "me too", "how are you?", etc.
        
#         Args:
#             user_input: User's casual response
            
#         Returns:
#             Natural, friendly acknowledgment
#         """
#         try:
#             prompt = f"""You are Anup, a friendly representative at TechGropse.

# The user just said: "{user_input}"

# This is a casual conversational response. Respond naturally and warmly, varying your language to feel human:

# SPECIAL CASE - If they asked "How are you?" or similar:
# 1. Say how YOU are doing - vary your enthusiasm:
#    * "I'm doing great, thanks for asking!"
#    * "I'm wonderful, thanks!"
#    * "Doing fantastic, thanks!"
#    * "I'm having a great day, thanks!"
# 2. Ask THEM back - vary the phrasing:
#    * "How about you?"
#    * "How are you doing?"
#    * "And you?"
#    * "How's your day going?"
# 3. Keep it brief and natural - 1-2 sentences max

# GENERAL CASE - For other casual responses:
# 1. Acknowledge warmly - vary your responses:
#    * "That's awesome to hear!"
#    * "Wonderful!"
#    * "That's great!"
#    * "Glad to hear that!"
#    * "Love to hear it!"
# 2. Offer help - vary the phrasing:
#    * "What can I help you with today?"
#    * "Is there anything I can help you with?"
#    * "How can I help you?"
#    * "What brings you here today?"
# 3. Keep it brief and natural - 1-2 sentences max

# Examples:
# - User: "How are you?" -> "I'm doing great, thanks for asking! How about you?"
# - User: "How's it going?" -> "Doing fantastic, thanks! How are you doing?"
# - User: "I'm doing well" -> "That's wonderful to hear! What can I help you with today?"
# - User: "That's nice" -> "Glad you think so! Is there anything else I can help you with?"
# - User: "Good to know" -> "Great! What else can I help you with?"

# Key points:
# - If they ask about YOUR well-being, ALWAYS ask them back
# - Vary your responses to avoid sounding robotic
# - Be conversational and warm
# - Use 'we at TechGropse', 'our', 'us' when referring to the company
# - Keep it brief (1-2 sentences)

# Generate a warm, natural response as Anup:"""

#             response = self.llm.invoke(prompt)
#             return response.content.strip() if hasattr(response, 'content') else str(response).strip()
#         except Exception as e:
#             logger.error(f"Error generating casual chat response: {e}")
#             return """That's great! Is there anything I can help you with today?"""
    
#     def handle_goodbye(self) -> str:
#         """
#         Generate a goodbye response using LLM.
        
#         Returns:
#             Goodbye message
#         """
#         try:
#             prompt = """You are Anup, a friendly representative at TechGropse.

# A user is saying goodbye. Respond warmly like saying bye to a friend - thank them for chatting and 
# let them know you're always around if they need anything. Use 'we at TechGropse', 'our', 'us' when referring to the company. 
# Be friendly and genuine (1-2 sentences).

# Examples:
# - "Thanks for chatting! Feel free to reach out anytime - we at TechGropse are always here to help!"
# - "It was great talking with you! Don't hesitate to come back if you need anything else from us at TechGropse."

# Generate a warm goodbye as Anup:"""

#             response = self.llm.invoke(prompt)
#             return response.content.strip() if hasattr(response, 'content') else str(response).strip()
#         except Exception as e:
#             logger.error(f"Error generating goodbye: {e}")
#             return "Thank you for your questions! If you need any more information, feel free to reach out anytime. We at TechGropse are always here to help!"
    
#     def handle_feedback(self, user_input: str) -> str:
#         """
#         Generate a simple confirmation for user feedback or messages to be shared with the team.
        
#         Args:
#             user_input: The user's feedback or message
            
#         Returns:
#             Confirmation message
#         """
#         try:
#             prompt = f"""You are Anup, a friendly representative at TechGropse.

# The user wants to share some feedback or information with the team: "{user_input}"

# Respond with a simple, warm confirmation that:
# 1. Acknowledges you understood their message
# 2. Confirms you'll convey it to the team
# 3. Uses 'we at TechGropse', 'our', 'us' when referring to the company
# 4. Is brief and reassuring (1-2 sentences)

# Examples:
# - "Ok sure, I understood and I will convey this to my team at TechGropse!"
# - "Got it! I'll make sure to pass this along to our team."
# - "Perfect, I'll share this with the team right away!"

# Generate a brief confirmation as Anup:"""

#             response = self.llm.invoke(prompt)
#             return response.content.strip() if hasattr(response, 'content') else str(response).strip()
#         except Exception as e:
#             logger.error(f"Error generating feedback response: {e}")
#             return "Ok sure, I understood and I will convey this to my team at TechGropse!"
    
#     def is_identity_question(self, user_input: str) -> bool:
#         """
#         Check if the user is asking about the assistant's identity.
        
#         Args:
#             user_input: User's message
            
#         Returns:
#             True if it's an identity question, False otherwise
#         """
#         user_input_lower = user_input.lower().strip()
        
#         # Identity question patterns
#         identity_patterns = [
#             'who are you',
#             'what are you',
#             'what is your name',
#             "what's your name",
#             'whats your name',
#             'tell me about yourself',
#             'introduce yourself',
#             'who am i talking to',
#             'who am i speaking to',
#             'are you a bot',
#             'are you human',
#             'are you ai',
#             'are you a robot',
#             'what can you do',
#             'what do you do',
#             'your name',
#             'who is this',
#             'who is anup',
#             'are you anup',
#         ]
        
#         return any(pattern in user_input_lower for pattern in identity_patterns)
    
#     def handle_identity_question(self, user_input: str) -> str:
#         """
#         Handle identity questions directly without RAG lookup.
        
#         Args:
#             user_input: User's identity question
            
#         Returns:
#             Response about the assistant's identity
#         """
#         try:
#             prompt = f"""You are Anup, TechGropse's Virtual AI Assistant.

# The user is asking about your identity: "{user_input}"

# Respond naturally and informatively. Here are key facts about yourself:
# - Your name is Anup
# - You are TechGropse's Virtual AI Assistant
# - You help users learn about TechGropse's services, projects, and capabilities
# - You can answer questions about mobile app development, AI solutions, and company information
# - You can connect users with the TechGropse team when needed
# - You're available 24/7 to assist
# - You're powered by advanced AI technology

# Keep your response brief, friendly, and conversational (2-3 sentences max).
# Use 'we at TechGropse', 'our', 'us' when referring to the company.

# Generate a natural response as Anup:"""

#             response = self.llm.invoke(prompt)
#             return response.content.strip() if hasattr(response, 'content') else str(response).strip()
#         except Exception as e:
#             logger.error(f"Error generating identity response: {e}")
#             return "Hi! I'm Anup, TechGropse's Virtual AI Assistant. I'm here to help you learn about our services, projects, and answer any questions you might have about mobile app development and AI solutions!"
    
#     def handle_unclear(self, user_input: str) -> str:
#         """
#         Generate a dynamic clarification request for unclear input using LLM.
        
#         Args:
#             user_input: The unclear user input
            
#         Returns:
#             Clarification message
#         """
#         try:
#             prompt = f"""You are Anup, a friendly and patient representative at TechGropse.

# A user said: "{user_input}"

# This is a bit unclear or ambiguous. Respond like a helpful friend who wants to understand:
# 1. Acknowledge what they said warmly ("Hmm, I'm not quite sure what you mean by...")
# 2. Ask them to clarify in a natural way ("Could you tell me a bit more about...?")
# 3. Give them helpful examples of what you CAN help with (our services, projects, capabilities, etc.)
# 4. Use 'we at TechGropse', 'our', 'us' when referring to the company
# 5. Be encouraging and patient, not robotic
# 6. Keep it brief (2-3 sentences)

# Examples of your tone:
# - "Hmm, I'm not quite sure I follow. Could you tell me a bit more about what you're looking for? I can help with questions about our services, projects, or anything else!"
# - "I want to make sure I understand - could you rephrase that a bit? I'm here to help with anything about what we at TechGropse do!"

# Generate a warm, helpful clarification request as Anup:"""

#             response = self.llm.invoke(prompt)
#             return response.content.strip() if hasattr(response, 'content') else str(response).strip()
#         except Exception as e:
#             logger.error(f"Error generating unclear response: {e}")
#             return """I'm not quite sure what you're asking about. Could you rephrase your question? I'm here to help with anything about what we at TechGropse do!"""
    
#     def _check_context_relevance(self, query: str, context_text: str) -> bool:
#         """
#         Check if the retrieved context is actually relevant to answering the user's question.
        
#         Args:
#             query: User's question
#             context_text: Retrieved context from documents
            
#         Returns:
#             True if context can answer the question, False otherwise
#         """
#         try:
#             prompt = f"""You are evaluating whether retrieved information can answer a user's question.

# User Question: "{query}"

# Retrieved Information:
# {context_text[:1000]}  # Limit context to avoid token limits

# Task: Determine if the retrieved information contains SPECIFIC, RELEVANT content that can answer the user's question.

# Answer "YES" if:
# - The information directly addresses the user's question
# - The information contains specific details related to the question
# - The question can be answered using this information

# Answer "NO" if:
# - The information is only tangentially related or generic
# - The information doesn't contain specific details to answer the question
# - The information is just contact details or general statements
# - The question asks about something not covered in the information

# Examples:
# Q: "Who is Prateek in TechGropse?" + Context: "Contact us at sales@techgropse.com" -> NO (generic contact info, doesn't answer who Prateek is)
# Q: "What data do you collect?" + Context: "We collect email, name, phone..." -> YES (specific answer)
# Q: "What is your refund policy?" + Context: "We value privacy and security..." -> NO (doesn't answer refund policy)

# Respond with only YES or NO:"""

#             response = self.llm.invoke(prompt)
#             answer = response.content.strip().upper() if hasattr(response, 'content') else str(response).strip().upper()
            
#             is_relevant = 'YES' in answer
#             logger.debug(f"Context relevance check: {is_relevant} for query: {query[:50]}...")
#             return is_relevant
            
#         except Exception as e:
#             logger.error(f"Error checking context relevance: {e}")
#             # On error, assume context is relevant to avoid false triggers
#             return True
    
#     def retrieve_relevant_documents(self, query: str, n_results: int = 10) -> List[Dict[str, Any]]:
#         """
#         Retrieve relevant documents from ChromaDB with source diversity and optional reranking.
        
#         Args:
#             query: User query
#             n_results: Number of documents to retrieve (or return after reranking)
            
#         Returns:
#             List of relevant document chunks, diversified across sources and optionally reranked
#         """
#         try:
#             # If reranking is enabled, retrieve more candidates for better recall
#             if self.reranker and config.enable_reranking:
#                 initial_n_results = config.rerank_candidates
#                 logger.debug(f"Reranking enabled: retrieving {initial_n_results} candidates")
#             else:
#                 initial_n_results = n_results
            
#             # Retrieve initial results from ChromaDB
#             results = self.chromadb_client.search_similar_documents(query, initial_n_results)

#             # Filter results with similarity threshold
#             # Higher threshold = more lenient = more docs pass through
#             filtered_results = []
#             for result in results:
#                 # Include results with reasonable similarity (distance < 1.7)
#                 # This allows relevant context about the assistant, company info, etc.
#                 if result.get('distance', 0) < 1.7:
#                     filtered_results.append(result)
            
#             # Apply reranking if enabled and we have results
#             if self.reranker and config.enable_reranking and filtered_results:
#                 logger.debug(f"Reranking {len(filtered_results)} documents")
#                 reranked_results = self.reranker.rerank(
#                     query=query,
#                     documents=filtered_results,
#                     top_k=config.rerank_top_k
#                 )
#                 # Use reranked results for diversification
#                 final_results = self._diversify_by_source(reranked_results)
#                 logger.debug(f"After reranking: {len(final_results)} documents")
#             else:
#                 # Diversify results across different source files (no reranking)
#                 final_results = self._diversify_by_source(filtered_results)

#             logger.debug(f"Retrieved {len(final_results)} relevant documents from {len(set(r.get('metadata', {}).get('source', 'unknown') for r in final_results))} different sources")
#             return final_results

#         except Exception as e:
#             logger.error(f"Error retrieving documents: {e}")
#             return []
    
#     def _diversify_by_source(self, results: List[Dict[str, Any]], max_per_source: int = 3) -> List[Dict[str, Any]]:
#         """
#         Diversify results to include chunks from multiple source documents.
        
#         Args:
#             results: List of retrieved results
#             max_per_source: Maximum chunks to include from each source
            
#         Returns:
#             Diversified list of results
#         """
#         # Group results by source file
#         source_groups = {}
#         for result in results:
#             source = result.get('metadata', {}).get('source', 'unknown')
#             if source not in source_groups:
#                 source_groups[source] = []
#             source_groups[source].append(result)
        
#         # Take top results from each source, interleaving them
#         diversified = []
#         max_rounds = max_per_source
        
#         for round_idx in range(max_rounds):
#             for source, source_results in source_groups.items():
#                 if round_idx < len(source_results):
#                     diversified.append(source_results[round_idx])
        
#         return diversified[:10]  # Return top 10 diversified results
    
#     def generate_response_from_context(self, query: str, context_docs: List[Dict[str, Any]]) -> str:
#         """
#         Generate a response based on query and retrieved context.
        
#         Args:
#             query: User query
#             context_docs: Retrieved document contexts
            
#         Returns:
#             Generated response
#         """
#         try:
#             # Prepare context from retrieved documents with source information
#             context_text = ""
#             if context_docs:
#                 context_chunks = []
#                 for i, doc in enumerate(context_docs):
#                     chunk = doc['content'].strip()
#                     if chunk:
#                         # Include source file information
#                         source = doc.get('metadata', {}).get('source', 'Unknown')
#                         # Extract just the filename from the path
#                         import os
#                         source_filename = os.path.basename(source)
#                         context_chunks.append(f"[Source: {source_filename}]\nContext {i+1}: {chunk}")
#                 context_text = "\n\n".join(context_chunks)
            
#             if not context_text:
#                 # No context found - trigger contact form
#                 from contact_form_handler import ContactFormHandler
                
#                 if ContactFormHandler.should_trigger_contact_form(context_docs):
#                     # Return special marker to indicate contact form should be triggered
#                     return "TRIGGER_CONTACT_FORM"
#                 else:
#                     # Fallback to general guidance
#                     return """I don't have specific information about that topic in our documents. 
#                     For detailed information, please contact us directly at sales@techgropse.com. 
#                     We'll be happy to assist you with any questions."""
            
#             # Use LLM directly for better control
#             prompt = f"""You are Anup, a friendly and knowledgeable representative at TechGropse. You help with all aspects of the company - services, privacy, pricing, support, and more.

# Your Personality:
# - Warm and approachable, like talking to a helpful colleague
# - Patient and understanding when users are confused
# - Enthusiastic about helping users with anything TechGropse-related
# - Shows genuine care about user concerns
# - Occasionally uses light, professional humor to make complex topics easier
# - Mirror the user's energy level (excited -> enthusiastic, calm -> measured)

# Your Communication Style:
# - Think out loud sometimes ("Let me see...", "Okay, so...", "Alright...")
# - Use conversational bridges ("So here's the thing...", "Actually...", "You know what...", "And get this...")
# - Mix short and long sentences naturally for better rhythm
# - Use contractions (we're, it's, you'll, that's)
# - Add occasional emphasis ("really important", "absolutely", "definitely", "honestly")

# 🔴 CRITICAL - VARIED ACKNOWLEDGMENTS:
# NEVER use the same opening phrase repeatedly! Generate UNIQUE, NATURAL acknowledgments for each response.
# - Sometimes start directly with the answer (no acknowledgment needed)
# - Sometimes acknowledge the topic naturally: "So about [topic]...", "Regarding [topic]...", "When it comes to [topic]..."
# - Sometimes show understanding: "I see what you're asking about...", "You're curious about...", "You want to know about..."
# - Sometimes be casual: "Okay, so...", "Alright...", "Let me tell you about..."
# - Sometimes be thoughtful: "Hmm, let me explain...", "Here's how this works...", "This is an interesting one..."
# - Avoid repetitive phrases like "Great question!" "That's a good one!" - these should be rare exceptions, not defaults
# - Be creative and natural - imagine you're having a real conversation with a friend

# - Use rhetorical questions to engage ("Why is this important? Well...", "What does this mean for you?")
# - End responses naturally - not always with a question. Sometimes just end with the answer.

# 🔴 CRITICAL - CONCISENESS:
# - Keep responses SHORT and to the point
# - For simple questions: 2-3 sentences maximum
# - For complex questions: 3-4 sentences maximum
# - Focus on the CORE answer, reduce additional details
# - Avoid over-explaining or adding too many examples
# - Get to the point quickly, then stop

# Emotional Intelligence & Empathy:
# - If user seems confused -> Be extra patient, use analogies, break things down
# - If user seems concerned -> Acknowledge concerns first: "I can totally see why you'd want to know that..."
# - If user seems rushed -> Be concise, use bullet points
# - If user is curious -> Show appreciation: "That's such a smart question to ask..."
# - If user asks basic question -> Keep it simple, don't over-explain
# - If user asks detailed question -> Show enthusiasm for their curiosity
# - Always validate their concerns: "I totally understand why [topic] is important to you..."

# Making Technical Info Relatable:
# - Use analogies: "Think of it like..." or "It's kind of like how..."
# - Add real-world examples to explain concepts
# - Break down complex topics: "Let me break this into bite-sized pieces..."
# - Offer simple version first: "Here's the simple version, then I can go deeper if you want..."

# 🔴 CRITICAL - Well-Being Acknowledgment:
# If the user mentions their well-being in their message (e.g., "I'm doing great", "I'm good", "I'm fine", "doing well"), you MUST:
# 1. FIRST acknowledge it warmly (e.g., "Great to hear you're doing well!", "That's wonderful!", "Glad to hear that!")
# 2. THEN answer their question

# Examples:
# - User: "I'm doing great! What is your pricing?" 
#    -> "Great to hear you're doing well! So, about our pricing..."
# - User: "I'm good, thanks. Do you provide source code?"
#    -> "Wonderful! Now, regarding your question about source code..."
# - User: "Doing well. How long does development take?"
#    -> "That's great! As for development timelines..."

# User Question: {query}

# Relevant Information from Our Documents:
# {context_text}

# Important Guidelines:
# 1. ONLY use information from the "Relevant Information" above - never use general knowledge
# 2. If you have PARTIAL information, share what you know and offer to connect them: "I don't have all the specifics on that, but here's what I can tell you... Would you like me to have our team reach out with the complete details?"
# 3. If you have NO information, be honest but helpful: "Hmm, that's a great question, but I don't have the exact details on that one in front of me. Let me connect you with our team who can help!"
# 4. Always use "we at TechGropse", "our", "us" when referring to the company (you're speaking FOR the company)
# 5. Explain things like you're teaching a friend - use analogies and examples
# 6. Use natural transitions: "So basically...", "Here's the thing...", "Let me break this down...", "To put it simply...", "The cool thing is..."
# 7. If information comes from multiple documents, synthesize it naturally
# 8. Be warm and personable while staying professional
# 9. NO greetings like "Hi there!" or "Hello!" - jump straight into acknowledging their question and answering
# 10. Show you care: "I totally understand why you'd want to know that...", "That's a really important question...", "I can see why you're asking about this..."
# 11. If user mentioned their well-being, acknowledge it FIRST before answering
# 12. Vary your engagement prompts at the end:
#     - "Does that make sense, or should I explain any part differently?"
#     - "What else can I help you with?"
#     - "Feel free to ask if you want me to dive deeper into any of that!"
#     - "Is there a specific part you'd like to know more about?"
#     - Or sometimes just end naturally without a question

# Respond as Anup would - naturally, warmly, and helpfully:"""

#             # Get response from LLM directly
#             response_text = None
#             try:
#                 # Try different invocation methods
#                 if hasattr(self.llm, 'predict_messages'):
#                     response_obj = self.llm.predict_messages([{"role": "user", "content": prompt}])
#                     if isinstance(response_obj, list) and hasattr(response_obj[0], 'content'):
#                         response_text = response_obj[0].content
#                     else:
#                         response_text = str(response_obj)
#                 elif hasattr(self.llm, 'generate'):
#                     messages = [{"role": "user", "content": prompt}]
#                     gen = self.llm.generate(messages)
#                     try:
#                         response_text = gen.generations[0][0].text
#                     except Exception:
#                         response_text = str(gen)
#                 else:
#                     # Fallback to invoke
#                     response = self.llm.invoke(prompt)
#                     response_text = response.content if hasattr(response, 'content') else str(response)
#             except Exception as e:
#                 logger.debug(f"LLM call failed, trying fallback: {e}")
#                 try:
#                     response = self.llm.invoke(prompt)
#                     response_text = response.content if hasattr(response, 'content') else str(response)
#                 except Exception as e2:
#                     logger.error(f"All LLM invocation methods failed: {e2}")
#                     response_text = None
            
#             # Clean up the response
#             if response_text:
#                 response_text = response_text.strip()
                
#                 # Graduated Fallback System - 3 levels of helpfulness
#                 # Level 1: Partial information (has some context but not complete)
#                 # Level 2: Related information (tangentially related)
#                 # Level 3: No information (trigger contact form)
                
#                 response_lower = response_text.lower()
                
#                 # Detect Level 3: Complete lack of information
#                 complete_fallback_phrases = [
#                     "i don't have specific information",
#                     "that's outside what i have",
#                     "not in our current documents",
#                     "don't have that exact information",
#                     "outside what i have in our privacy",
#                     "that's not covered in our privacy"
#                 ]
                
#                 # Detect Level 1/2: Partial or related information
#                 partial_info_phrases = [
#                     "i don't have the complete details",
#                     "i don't have all the specifics",
#                     "here's what i can tell you",
#                     "what i can share is",
#                     "while i don't have the exact",
#                     "i don't have that specific detail, but"
#                 ]
                
#                 # Check for complete fallback (Level 3)
#                 is_complete_fallback = any(phrase in response_lower for phrase in complete_fallback_phrases)
                
#                 # Check for partial information (Level 1/2)
#                 has_partial_info = any(phrase in response_lower for phrase in partial_info_phrases)
                
#                 if is_complete_fallback and not has_partial_info:
#                     # Level 3: No relevant information at all - trigger contact form
#                     logger.info(f"🔔 Level 3 Fallback: No information available - triggering contact form")
#                     return "TRIGGER_CONTACT_FORM"
#                 elif has_partial_info:
#                     # Level 1/2: Has some information - let the response through
#                     # The LLM has already provided what it can and offered to connect them
#                     logger.info(f"Level 1/2 Fallback: Partial/related information provided")
#                     # Response goes through as-is
                
#                 # Remove greeting phrases that might have slipped through
#                 greeting_phrases = [
#                     "Hi there!", "Hello!", "Hey!", "Hi!", "Hey there!",
#                     "Good morning!", "Good afternoon!", "Good evening!",
#                     "Greetings!", "Hello there!"
#                 ]
                
#                 for greeting in greeting_phrases:
#                     if response_text.startswith(greeting):
#                         response_text = response_text[len(greeting):].strip()
#                         break
            
#             # Ensure we have a reasonable response
#             if not response_text or len(response_text) < 20:
#                 # This happens when LLM fails (e.g., OpenAI 500 error)
#                 logger.warning("LLM failed to generate response - using apologetic fallback")
#                 response_text = """I sincerely apologize, but I'm experiencing some technical difficulties at the moment and I'm unable to process your request properly. This is a temporary issue on our end.

# Please try asking your question again in a few moments. If the problem persists, you can always reach out to our team directly at sales@techgropse.com, and they'll be happy to assist you right away.

# I really appreciate your patience and understanding!"""
            
#             # Add engagement prompt at the end of detailed responses
#             if response_text and len(response_text) > 100:  # Only for substantial responses
#                 engagement_prompts = [
#                     "\n\nIs there anything else you'd like to know about this topic?",
#                     "\n\nWould you like more information on this, or is there anything else I can help you with?",
#                     "\n\nDo you need more details about this, or is there something else you'd like to know?",
#                     "\n\nIs there anything else about this topic you'd like me to clarify?"
#                 ]
#                 import random
#                 response_text += random.choice(engagement_prompts)
            
#             return response_text
            
#         except Exception as e:
#             logger.error(f"Error generating response: {e}")
#             return """I apologize, but I'm having trouble processing your request right now. 
#             For immediate assistance, please contact us at sales@techgropse.com."""
    
#     def _generate_followup_response(self, original_query: str, context_docs: List[Dict[str, Any]]) -> str:
#         """
#         Generate a follow-up response that provides more detailed information.
        
#         Args:
#             original_query: The original question being followed up on
#             context_docs: Retrieved document contexts
            
#         Returns:
#             Generated detailed response
#         """
#         try:
#             # Prepare context from retrieved documents with source information
#             context_text = ""
#             if context_docs:
#                 context_chunks = []
#                 for i, doc in enumerate(context_docs):
#                     chunk = doc['content'].strip()
#                     if chunk:
#                         # Include source file information
#                         source = doc.get('metadata', {}).get('source', 'Unknown')
#                         # Extract just the filename from the path
#                         import os
#                         source_filename = os.path.basename(source)
#                         context_chunks.append(f"[Source: {source_filename}]\nContext {i+1}: {chunk}")
#                 context_text = "\n\n".join(context_chunks)
            
#             if not context_text:
#                 return """I don't have additional information on that topic in our knowledge base. 
#                 For more detailed information, please contact us directly at sales@techgropse.com."""
            
#             # Use LLM to generate a more comprehensive response
#             prompt = f"""You are Anup, a friendly representative at TechGropse who loves helping people learn more.

# The user previously asked: "{original_query}"

# Now they want MORE DETAILS - they're curious and engaged!

# Relevant Information from Our Documents:
# {context_text}

# Your Response Style:
# 1. Start enthusiastically: "Sure, let me give you more details!" or "Absolutely! Here's a deeper dive..."
# 2. Use 'we at TechGropse', 'our', 'us' when referring to the company (you're speaking FOR the company)
# 3. Be thorough but conversational - like explaining to a friend
# 4. Break down complex info into digestible pieces
# 5. Use examples or analogies if helpful
# 6. Show you're happy they're interested: "Great question to dig deeper into!"
# 7. ONLY use information from the context above
# 5. Break it down clearly with examples or explanations where helpful
# 6. Be thorough but keep it conversational - like explaining to a friend
# 7. Only mention contacting support if the info really isn't there
# 8. Remember you're Anup speaking FOR TechGropse, not ABOUT TechGropse
# 9. DO NOT include greetings like "Hi there!", "Hello!" - start directly with the detailed information

# Provide a detailed, friendly response as Anup representing TechGropse (NO greetings):"""

#             # Get response from LLM
#             response_text = None
#             try:
#                 response = self.llm.invoke(prompt)
#                 response_text = response.content if hasattr(response, 'content') else str(response)
#             except Exception as e:
#                 logger.error(f"Error invoking LLM for followup: {e}")
#                 return """I'd be happy to provide more information. For specific details, please contact us at sales@techgropse.com."""
            
#             # Clean up the response
#             if response_text:
#                 response_text = response_text.strip()
                
#                 # Remove greeting phrases that might have slipped through
#                 greeting_phrases = [
#                     "Hi there!", "Hello!", "Hey!", "Hi!", "Hey there!",
#                     "Good morning!", "Good afternoon!", "Good evening!",
#                     "Greetings!", "Hello there!"
#                 ]
                
#                 for greeting in greeting_phrases:
#                     if response_text.startswith(greeting):
#                         response_text = response_text[len(greeting):].strip()
#                         break
            
#             if not response_text or len(response_text) < 20:
#                 response_text = """We'd be happy to provide more information. For specific details, 
#                 please feel free to ask a more specific question or contact us directly at sales@techgropse.com."""
            
#             # Add engagement prompt at the end of detailed follow-up responses
#             if response_text and len(response_text) > 100:  # Only for substantial responses
#                 engagement_prompts = [
#                     "\n\nDoes this answer your question completely, or would you like even more details about any specific aspect?",
#                     "\n\nIs this the level of detail you were looking for, or would you like me to elaborate on any particular point?",
#                     "\n\nDoes this cover what you wanted to know, or do you have follow-up questions about any of these points?",
#                     "\n\nI hope this gives you the detail you were looking for! Is there anything specific you'd like me to expand on further?"
#                 ]
#                 import random
#                 response_text += random.choice(engagement_prompts)
            
#             return response_text
            
#         except Exception as e:
#             logger.error(f"Error generating followup response: {e}")
#             return """We apologize, but I'm having trouble retrieving more details right now. 
#             For comprehensive information, please contact us at sales@techgropse.com."""
    
#     def process_user_input(self, user_input: str, last_user_query: str = None) -> Dict[str, Any]:
#         """
#         Process user input and generate appropriate response.
        
#         Args:
#             user_input: User's input message
#             last_user_query: Optional previous user query for follow-up handling
            
#         Returns:
#             Dictionary with intent, response, and context information
#         """
#         try:
#             # Classify intent
#             intent = self.classify_intent(user_input)
            
#             result = {
#                 'intent': intent.value,
#                 'user_input': user_input,
#                 'response': '',
#                 'context_docs': [],
#                 'needs_caching': True
#             }
            
#             # Handle based on intent
#             if intent == IntentType.GREETING:
#                 result['response'] = self.handle_greeting(user_input)
#                 result['needs_caching'] = False  # Don't cache greetings
                
#             elif intent == IntentType.CASUAL_CHAT:
#                 # Handle casual conversational responses
#                 result['response'] = self.handle_casual_chat(user_input)
#                 result['needs_caching'] = False  # Don't cache casual chat
                
#             elif intent == IntentType.GOODBYE:
#                 result['response'] = self.handle_goodbye()
#                 result['needs_caching'] = False  # Don't cache goodbyes
            
#             elif intent == IntentType.FEEDBACK:
#                 # Handle user feedback/messages to be shared with team
#                 result['response'] = self.handle_feedback(user_input)
#                 result['needs_caching'] = False  # Don't cache feedback confirmations
                
#             elif intent == IntentType.QUERY:
#                 # Check if it's an identity question - handle directly without RAG
#                 if self.is_identity_question(user_input):
#                     result['response'] = self.handle_identity_question(user_input)
#                     result['needs_caching'] = False  # Don't cache identity responses
#                 else:
#                     # Retrieve relevant documents
#                     context_docs = self.retrieve_relevant_documents(user_input)
#                     result['context_docs'] = context_docs
                    
#                     # Generate response based on context
#                     result['response'] = self.generate_response_from_context(user_input, context_docs)
                
#             elif intent == IntentType.FOLLOWUP:
#                     # For follow-ups, we need the previous substantive question (not the current "need more info")
#                     # The current user_input is already in history, so we need to skip it and get the one before
#                     if last_user_query and last_user_query.lower().strip() == user_input.lower().strip():
#                         # If last_user_query is the same as current input, we need to go back further
#                         # This shouldn't happen with proper logic, but let's handle it
#                         expanded_query = user_input
#                     elif last_user_query:
#                         # Construct a query that references the previous question and asks for more detail
#                         expanded_query = f"{last_user_query} - provide more detailed information and additional context"
#                     else:
#                         expanded_query = user_input

#                     # Get more results for follow-ups to provide comprehensive answers
#                     context_docs = self.retrieve_relevant_documents(expanded_query, n_results=6)
#                     result['context_docs'] = context_docs
                    
#                     # Generate a more detailed response with explicit instruction to expand
#                     result['response'] = self._generate_followup_response(last_user_query or user_input, context_docs)
                
#             else:  # UNCLEAR intent
#                 # Generate dynamic clarification request
#                 result['response'] = self.handle_unclear(user_input)
#                 result['needs_caching'] = False
            
#             return result
            
#         except Exception as e:
#             logger.error(f"Error processing user input: {e}")
#             return {
#                 'intent': 'error',
#                 'user_input': user_input,
#                 'response': "We're sorry, I encountered an error processing your request. Please try again or contact us for support.",
#                 'context_docs': [],
#                 'needs_caching': False
#             }


"""
CrewAI agent for intent classification, greeting handling, and query processing.
"""
import logging
from typing import Dict, Any, List
from enum import Enum

from crewai import Agent
from langchain_openai import ChatOpenAI

from config import config
from vectorstore.chromadb_client import ChromaDBClient
from database.mongodb_client import MongoDBClient
from utils.reranker import Reranker
import re
from datetime import datetime

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """Intent classification types."""
    GREETING = "greeting"
    CASUAL_CHAT = "casual_chat"  # Casual conversational responses like "I'm doing great"
    FOLLOWUP = "followup"
    CONTACT_REQUEST = "contact_request"
    FEEDBACK = "feedback"  # User wants to share feedback/message with team
    PROJECT_ENQUIRY = "project_enquiry"  # User wants to enquire about building a project/app/software
    QUERY = "query"
    GOODBYE = "goodbye"
    UNCLEAR = "unclear"


class ContactFormState(Enum):
    """Contact form collection states."""
    IDLE = "idle"
    # Initial collection at session start
    INITIAL_COLLECTING_NAME = "initial_collecting_name"
    INITIAL_COLLECTING_EMAIL = "initial_collecting_email"
    INITIAL_COLLECTING_PHONE = "initial_collecting_phone"
    # Connect with team - only collect availability
    ASKING_CONSENT = "asking_consent"
    ASKING_SCHEDULE_CHANGE = "asking_schedule_change"  # Ask if user wants to keep or change existing schedule
    COLLECTING_DATETIME = "collecting_datetime"
    COLLECTING_TIMEZONE = "collecting_timezone"
    # Legacy states (for backward compatibility)
    COLLECTING_NAME = "collecting_name"
    COLLECTING_EMAIL = "collecting_email"
    COLLECTING_PHONE = "collecting_phone"
    COMPLETED = "completed"


class ChatbotAgent:
    """CrewAI-powered agent for handling user intents and generating responses."""
    
    def __init__(self, chromadb_client: ChromaDBClient):
        """
        Initialize the chatbot agent.
        
        Args:
            chromadb_client: ChromaDB client for document retrieval
        """
        self.chromadb_client = chromadb_client
        
        # Initialize reranker if enabled
        self.reranker = None
        if config.enable_reranking:
            try:
                self.reranker = Reranker(model_name=config.reranker_model)
                logger.info(f"Reranker initialized with model: {config.reranker_model}")
            except Exception as e:
                logger.error(f"Failed to initialize reranker: {e}")
                logger.warning("Continuing without reranking")
        else:
            logger.info("Reranking disabled in configuration")
        
        # Initialize MongoDB client for contact requests
        try:
            if config.mongodb_uri:
                self.mongodb_client = MongoDBClient(config.mongodb_uri, config.mongodb_database)
                logger.info("MongoDB client initialized for contact requests")
                
                # List all collections for debugging
                collections = self.mongodb_client.list_collections()
                logger.info(f"Available MongoDB collections: {collections}")
                
                # Get session count
                session_count = self.mongodb_client.get_session_count()
                logger.info(f"Total sessions stored: {session_count}")
            else:
                self.mongodb_client = None
                logger.warning("MongoDB URI not configured - contact requests will not be saved")
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB client: {e}")
            self.mongodb_client = None
        
        # Disable CrewAI telemetry and traces
        import os
        os.environ['CREWAI_TELEMETRY'] = 'false'
        os.environ['CREWAI_DISABLE_TELEMETRY'] = 'true'
        
        # Initialize LLM with OpenAI's store parameter for automatic conversation storage
        # This replaces Redis caching - OpenAI stores conversations for 30 days
        self.llm = ChatOpenAI(
            model="gpt-4.1-nano",
            temperature=0.3,  # Increased for more creative, human-like responses
            openai_api_key=config.openai_api_key,
            model_kwargs={
                "store": True  # Enable OpenAI conversation storage (30-day retention)
            }
        )
        
        # Create the intent classification agent (for reference, not used in new implementation)
        self.intent_agent = Agent(
            role='Anup - Virtual Representative of TechGropse',
            goal='As Anup, represent TechGropse and help users with all aspects of the company - services, pricing, projects, capabilities, and general inquiries',
            backstory="""You are Anup, the official virtual representative of TechGropse, speaking on behalf of the company. 
            You help users with everything related to TechGropse - app development services, pricing, timelines, 
            projects, capabilities, and general company information. You always speak as 'we at TechGropse' when 
            referring to the company (e.g., 'we at TechGropse develop', 'our services', 'we offer'). You are friendly, 
            professional, knowledgeable, and enthusiastic about helping users with any questions about TechGropse. 
            When greeting users, you introduce yourself as Anup from TechGropse, your virtual representative.""",
            verbose=False,
            allow_delegation=False,
            llm=self.llm
        )
    
    def classify_intent(self, user_input: str) -> IntentType:
        """
        Classify the user's intent using LLM.
        
        Args:
            user_input: User's message
            
        Returns:
            Classified intent type
        """
        try:
            # Use LLM to classify intent
            prompt = f"""You are a customer service assistant. Classify the user's intent into ONE of these categories:

1. GREETING - user is saying hello, hi, or starting the conversation (e.g., "Hi", "Hello", "Hi, how are you?")
2. CASUAL_CHAT - user is making casual conversational responses like:
   - "I'm doing great", "I'm good", "I'm fine"
   - "How are you?" (when asked as a follow-up, not initial greeting)
   - "me too", "same here", "that's nice"
   - Friendly acknowledgments that don't require specific action
3. FOLLOWUP - user wants more details/information about the previous topic (phrases like "more info", "tell me more", "need more details", "elaborate", etc.)
4. CONTACT_REQUEST - user explicitly wants to be contacted by someone from the team (phrases like "connect me", "contact me", "reach out to me", "get in touch with me", "call me", "email me", "have someone contact me", "I need a callback", etc.)
5. FEEDBACK - user wants to share feedback, information, or a message with the team (phrases like "send this to your team", "tell your team", "convey to team", "share this with team", "let them know", "I want to share", "pass this along", etc.)
6. QUERY - user is asking a specific question about services, projects, capabilities, etc. This INCLUDES questions about the assistant's identity like "who are you?", "what is your name?", "tell me about yourself", etc.
7. GOODBYE - user is ending the conversation. This includes ANY expression of thanks, satisfaction, or ending like: "thank you", "thanks", "ok thank you", "that's all", "goodbye", "bye", "see you", "appreciate it", "perfect", "great thanks", "awesome", "all good", "done", "finished", etc.
8. UNCLEAR - unclear or ambiguous input

User input: "{user_input}"

IMPORTANT DISTINCTIONS:
- "Hi, how are you?" = GREETING (initial contact with well-being question)
- "How are you?" (alone, as follow-up) = CASUAL_CHAT (casual conversation)
- "Who are you?" = QUERY (asking about the assistant's identity - needs information lookup)
- "What is your name?" = QUERY (asking about the assistant's identity)
- "Tell me about yourself" = QUERY (asking about the assistant)
- "I'm doing well" = CASUAL_CHAT
- "Tell me more" = FOLLOWUP
- "Contact me" or "Have someone reach out to me" = CONTACT_REQUEST (they want to BE contacted)
- "Send this to your team" or "Tell your team about this" = FEEDBACK (they want to SHARE info)
- "Thanks" = GOODBYE

Be VERY sensitive to goodbye hints - if there's ANY indication the user is satisfied or ending the conversation, classify as GOODBYE.
Distinguish between CONTACT_REQUEST (user wants to be contacted) and FEEDBACK (user wants to share info with team).
If the user is just making casual conversation or acknowledgments, classify as CASUAL_CHAT.
ANY question about the assistant's identity (who/what/name/yourself) should be QUERY.

Respond with ONLY the category name (GREETING, CASUAL_CHAT, FOLLOWUP, CONTACT_REQUEST, FEEDBACK, QUERY, GOODBYE, or UNCLEAR):"""

            response = self.llm.invoke(prompt)
            intent_text = response.content.strip().upper() if hasattr(response, 'content') else str(response).strip().upper()
            
            # Map to IntentType
            if 'GREETING' in intent_text:
                return IntentType.GREETING
            elif 'CASUAL' in intent_text:  # Catches CASUAL_CHAT
                return IntentType.CASUAL_CHAT
            elif 'FOLLOWUP' in intent_text:
                return IntentType.FOLLOWUP
            elif 'CONTACT' in intent_text:  # Catches CONTACT_REQUEST
                return IntentType.CONTACT_REQUEST
            elif 'FEEDBACK' in intent_text:
                return IntentType.FEEDBACK
            elif 'QUERY' in intent_text:
                return IntentType.QUERY
            elif 'GOODBYE' in intent_text:
                return IntentType.GOODBYE
            else:
                return IntentType.UNCLEAR
            
        except Exception as e:
            logger.error(f"Error classifying intent: {e}")
            # Fallback to simple heuristic
            user_input_lower = user_input.lower().strip()
            
            # Check for contact request phrases first
            if any(phrase in user_input_lower for phrase in [
                'connect me', 'contact me', 'reach out', 'get in touch',
                'call me', 'email me', 'have someone contact', 'someone reach out',
                'talk to someone', 'speak to someone', 'connect with'
            ]):
                return IntentType.CONTACT_REQUEST
            
            if any(word in user_input_lower for word in ['hi', 'hello', 'hey']):
                return IntentType.GREETING
            elif any(phrase in user_input_lower for phrase in [
                'bye', 'goodbye', 'good bye', 'see you', 'thanks', 'thank you', 
                'ok thank you', 'okay thank you', 'that\'s all', 'thats all',
                'end', 'quit', 'exit', 'done', 'finished', 'all good',
                'appreciate it', 'perfect', 'great thanks', 'awesome thanks'
            ]):
                return IntentType.GOODBYE
            return IntentType.QUERY
    
    def handle_greeting(self, user_input: str = "") -> str:
        """
        Generate a dynamic greeting response using LLM.
        
        Args:
            user_input: The user's greeting message
        
        Returns:
            Greeting message
        """
        try:
            # Check if user asked about well-being
            user_input_lower = user_input.lower()
            asks_how_are_you = any(phrase in user_input_lower for phrase in [
                'how are you', 'how are u', 'how r you', 'how r u',
                'how\'s it going', 'how is it going', 'how are things',
            ])
            
            prompt = f"""You are Anup, a friendly representative at TechGropse.

The user just greeted you with: "{user_input}"

CRITICAL: Keep your greeting to ONE SHORT SENTENCE only.

IF they asked about YOUR well-being (e.g., "Hi, how are you?", "Hello, how's it going?"):
- Respond with: "I'm doing great, thanks for asking! How about you?"
- Or: "Doing wonderful, thanks! How are you?"
- Keep it to ONE sentence

IF they just said a simple greeting (e.g., "Hi", "Hello", "Hey"):
- Respond with: "Hi! I'm Anup from TechGropse. How can I help you?"
- Or: "Hey! I'm Anup from TechGropse. What can I help you with?"
- Or: "Hello! I'm Anup from TechGropse, here to help!"
- Keep it to ONE SHORT sentence

Examples:
- User: "Hi, how are you?" -> "I'm doing great, thanks! How about you?"
- User: "Hello" -> "Hi! I'm Anup from TechGropse. How can I help you?"
- User: "Hi" -> "Hey! I'm Anup from TechGropse. What can I help you with?"

Key points:
- MUST be ONE SHORT sentence only
- Be warm but concise
- Introduce yourself as Anup from TechGropse
- Use 'we at TechGropse', 'our', 'us' when referring to the company

Generate a SHORT one-sentence greeting as Anup:"""

            response = self.llm.invoke(prompt)
            return response.content.strip() if hasattr(response, 'content') else str(response).strip()
        except Exception as e:
            logger.error(f"Error generating greeting: {e}")
            return "Hi! I'm Anup from TechGropse. How can I help you?"
    
    def handle_casual_chat(self, user_input: str) -> str:
        """
        Handle casual conversational responses like "I'm doing great", "me too", "how are you?", etc.
        
        Args:
            user_input: User's casual response
            
        Returns:
            Natural, friendly acknowledgment
        """
        try:
            prompt = f"""You are Anup, a friendly representative at TechGropse.

The user just said: "{user_input}"

This is a casual conversational response. Respond naturally and warmly, varying your language to feel human:

SPECIAL CASE - If they asked "How are you?" or similar:
1. Say how YOU are doing - vary your enthusiasm:
   * "I'm doing great, thanks for asking!"
   * "I'm wonderful, thanks!"
   * "Doing fantastic, thanks!"
   * "I'm having a great day, thanks!"
2. Ask THEM back - vary the phrasing:
   * "How about you?"
   * "How are you doing?"
   * "And you?"
   * "How's your day going?"
3. Keep it brief and natural - 1-2 sentences max

GENERAL CASE - For other casual responses:
1. Acknowledge warmly - vary your responses:
   * "That's awesome to hear!"
   * "Wonderful!"
   * "That's great!"
   * "Glad to hear that!"
   * "Love to hear it!"
2. Offer help - vary the phrasing:
   * "What can I help you with today?"
   * "Is there anything I can help you with?"
   * "How can I help you?"
   * "What brings you here today?"
3. Keep it brief and natural - 1-2 sentences max

Examples:
- User: "How are you?" -> "I'm doing great, thanks for asking! How about you?"
- User: "How's it going?" -> "Doing fantastic, thanks! How are you doing?"
- User: "I'm doing well" -> "That's wonderful to hear! What can I help you with today?"
- User: "That's nice" -> "Glad you think so! Is there anything else I can help you with?"
- User: "Good to know" -> "Great! What else can I help you with?"

Key points:
- If they ask about YOUR well-being, ALWAYS ask them back
- Vary your responses to avoid sounding robotic
- Be conversational and warm
- Use 'we at TechGropse', 'our', 'us' when referring to the company
- Keep it brief (1-2 sentences)

Generate a warm, natural response as Anup:"""

            response = self.llm.invoke(prompt)
            return response.content.strip() if hasattr(response, 'content') else str(response).strip()
        except Exception as e:
            logger.error(f"Error generating casual chat response: {e}")
            return """That's great! Is there anything I can help you with today?"""
    
    def handle_goodbye(self) -> str:
        """
        Generate a goodbye response using LLM.
        
        Returns:
            Goodbye message
        """
        try:
            prompt = """You are Anup, a friendly representative at TechGropse.

A user is saying goodbye. Respond warmly like saying bye to a friend - thank them for chatting and 
let them know you're always around if they need anything. Use 'we at TechGropse', 'our', 'us' when referring to the company. 
Be friendly and genuine (1-2 sentences).

Examples:
- "Thanks for chatting! Feel free to reach out anytime - we at TechGropse are always here to help!"
- "It was great talking with you! Don't hesitate to come back if you need anything else from us at TechGropse."

Generate a warm goodbye as Anup:"""

            response = self.llm.invoke(prompt)
            return response.content.strip() if hasattr(response, 'content') else str(response).strip()
        except Exception as e:
            logger.error(f"Error generating goodbye: {e}")
            return "Thank you for your questions! If you need any more information, feel free to reach out anytime. We at TechGropse are always here to help!"
    
    def handle_feedback(self, user_input: str) -> str:
        """
        Generate a simple confirmation for user feedback or messages to be shared with the team.
        
        Args:
            user_input: The user's feedback or message
            
        Returns:
            Confirmation message
        """
        try:
            prompt = f"""You are Anup, a friendly representative at TechGropse.

The user wants to share some feedback or information with the team: "{user_input}"

Respond with a simple, warm confirmation that:
1. Acknowledges you understood their message
2. Confirms you'll convey it to the team
3. Uses 'we at TechGropse', 'our', 'us' when referring to the company
4. Is brief and reassuring (1-2 sentences)

Examples:
- "Ok sure, I understood and I will convey this to my team at TechGropse!"
- "Got it! I'll make sure to pass this along to our team."
- "Perfect, I'll share this with the team right away!"

Generate a brief confirmation as Anup:"""

            response = self.llm.invoke(prompt)
            return response.content.strip() if hasattr(response, 'content') else str(response).strip()
        except Exception as e:
            logger.error(f"Error generating feedback response: {e}")
            return "Ok sure, I understood and I will convey this to my team at TechGropse!"
    
    def is_identity_question(self, user_input: str) -> bool:
        """
        Check if the user is asking about the assistant's identity.
        
        Args:
            user_input: User's message
            
        Returns:
            True if it's an identity question, False otherwise
        """
        user_input_lower = user_input.lower().strip()
        
        # Identity question patterns
        identity_patterns = [
            'who are you',
            'what are you',
            'what is your name',
            "what's your name",
            'whats your name',
            'tell me about yourself',
            'introduce yourself',
            'who am i talking to',
            'who am i speaking to',
            'are you a bot',
            'are you human',
            'are you ai',
            'are you a robot',
            'what can you do',
            'what do you do',
            'your name',
            'who is this',
            'who is anup',
            'are you anup',
        ]
        
        return any(pattern in user_input_lower for pattern in identity_patterns)
    
    def handle_identity_question(self, user_input: str) -> str:
        """
        Handle identity questions directly without RAG lookup.
        
        Args:
            user_input: User's identity question
            
        Returns:
            Response about the assistant's identity
        """
        try:
            prompt = f"""You are Anup, TechGropse's Virtual AI Assistant.

The user is asking about your identity: "{user_input}"

Respond naturally and informatively. Here are key facts about yourself:
- Your name is Anup
- You are TechGropse's Virtual AI Assistant
- You help users learn about TechGropse's services, projects, and capabilities
- You can answer questions about mobile app development, AI solutions, and company information
- You can connect users with the TechGropse team when needed
- You're available 24/7 to assist
- You're powered by advanced AI technology

Keep your response brief, friendly, and conversational (2-3 sentences max).
Use 'we at TechGropse', 'our', 'us' when referring to the company.

Generate a natural response as Anup:"""

            response = self.llm.invoke(prompt)
            return response.content.strip() if hasattr(response, 'content') else str(response).strip()
        except Exception as e:
            logger.error(f"Error generating identity response: {e}")
            return "Hi! I'm Anup, TechGropse's Virtual AI Assistant. I'm here to help you learn about our services, projects, and answer any questions you might have about mobile app development and AI solutions!"
    
    def handle_unclear(self, user_input: str) -> str:
        """
        Generate a dynamic clarification request for unclear input using LLM.
        
        Args:
            user_input: The unclear user input
            
        Returns:
            Clarification message
        """
        try:
            prompt = f"""You are Anup, a friendly and patient representative at TechGropse.

A user said: "{user_input}"

This is a bit unclear or ambiguous. Respond like a helpful friend who wants to understand:
1. Acknowledge what they said warmly ("Hmm, I'm not quite sure what you mean by...")
2. Ask them to clarify in a natural way ("Could you tell me a bit more about...?")
3. Give them helpful examples of what you CAN help with (our services, projects, capabilities, etc.)
4. Use 'we at TechGropse', 'our', 'us' when referring to the company
5. Be encouraging and patient, not robotic
6. Keep it brief (2-3 sentences)

Examples of your tone:
- "Hmm, I'm not quite sure I follow. Could you tell me a bit more about what you're looking for? I can help with questions about our services, projects, or anything else!"
- "I want to make sure I understand - could you rephrase that a bit? I'm here to help with anything about what we at TechGropse do!"

Generate a warm, helpful clarification request as Anup:"""

            response = self.llm.invoke(prompt)
            return response.content.strip() if hasattr(response, 'content') else str(response).strip()
        except Exception as e:
            logger.error(f"Error generating unclear response: {e}")
            return """I'm not quite sure what you're asking about. Could you rephrase your question? I'm here to help with anything about what we at TechGropse do!"""
    
    def _check_context_relevance(self, query: str, context_text: str) -> bool:
        """
        Check if the retrieved context is actually relevant to answering the user's question.
        
        Args:
            query: User's question
            context_text: Retrieved context from documents
            
        Returns:
            True if context can answer the question, False otherwise
        """
        try:
            prompt = f"""You are evaluating whether retrieved information can answer a user's question.

User Question: "{query}"

Retrieved Information:
{context_text[:1000]}  # Limit context to avoid token limits

Task: Determine if the retrieved information contains SPECIFIC, RELEVANT content that can answer the user's question.

Answer "YES" if:
- The information directly addresses the user's question
- The information contains specific details related to the question
- The question can be answered using this information

Answer "NO" if:
- The information is only tangentially related or generic
- The information doesn't contain specific details to answer the question
- The information is just contact details or general statements
- The question asks about something not covered in the information

Examples:
Q: "Who is Prateek in TechGropse?" + Context: "Contact us at sales@techgropse.com" -> NO (generic contact info, doesn't answer who Prateek is)
Q: "What data do you collect?" + Context: "We collect email, name, phone..." -> YES (specific answer)
Q: "What is your refund policy?" + Context: "We value privacy and security..." -> NO (doesn't answer refund policy)

Respond with only YES or NO:"""

            response = self.llm.invoke(prompt)
            answer = response.content.strip().upper() if hasattr(response, 'content') else str(response).strip().upper()
            
            is_relevant = 'YES' in answer
            logger.debug(f"Context relevance check: {is_relevant} for query: {query[:50]}...")
            return is_relevant
            
        except Exception as e:
            logger.error(f"Error checking context relevance: {e}")
            # On error, assume context is relevant to avoid false triggers
            return True
    
    def retrieve_relevant_documents(self, query: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieve relevant documents from ChromaDB with source diversity and optional reranking.
        
        Args:
            query: User query
            n_results: Number of documents to retrieve (or return after reranking)
            
        Returns:
            List of relevant document chunks, diversified across sources and optionally reranked
        """
        try:
            # If reranking is enabled, retrieve more candidates for better recall
            if self.reranker and config.enable_reranking:
                initial_n_results = config.rerank_candidates
                logger.debug(f"Reranking enabled: retrieving {initial_n_results} candidates")
            else:
                initial_n_results = n_results
            
            # Retrieve initial results from ChromaDB
            results = self.chromadb_client.search_similar_documents(query, initial_n_results)

            # Filter results with similarity threshold
            # Higher threshold = more lenient = more docs pass through
            filtered_results = []
            for result in results:
                # Include results with reasonable similarity (distance < 1.7)
                # This allows relevant context about the assistant, company info, etc.
                if result.get('distance', 0) < 1.7:
                    filtered_results.append(result)
            
            # Apply reranking if enabled and we have results
            if self.reranker and config.enable_reranking and filtered_results:
                logger.debug(f"Reranking {len(filtered_results)} documents")
                reranked_results = self.reranker.rerank(
                    query=query,
                    documents=filtered_results,
                    top_k=config.rerank_top_k
                )
                # Use reranked results for diversification
                final_results = self._diversify_by_source(reranked_results)
                logger.debug(f"After reranking: {len(final_results)} documents")
            else:
                # Diversify results across different source files (no reranking)
                final_results = self._diversify_by_source(filtered_results)

            logger.debug(f"Retrieved {len(final_results)} relevant documents from {len(set(r.get('metadata', {}).get('source', 'unknown') for r in final_results))} different sources")
            return final_results

        except Exception as e:
            logger.error(f"Error retrieving documents: {e}")
            return []
    
    def _diversify_by_source(self, results: List[Dict[str, Any]], max_per_source: int = 3) -> List[Dict[str, Any]]:
        """
        Diversify results to include chunks from multiple source documents.
        
        Args:
            results: List of retrieved results
            max_per_source: Maximum chunks to include from each source
            
        Returns:
            Diversified list of results
        """
        # Group results by source file
        source_groups = {}
        for result in results:
            source = result.get('metadata', {}).get('source', 'unknown')
            if source not in source_groups:
                source_groups[source] = []
            source_groups[source].append(result)
        
        # Take top results from each source, interleaving them
        diversified = []
        max_rounds = max_per_source
        
        for round_idx in range(max_rounds):
            for source, source_results in source_groups.items():
                if round_idx < len(source_results):
                    diversified.append(source_results[round_idx])
        
        return diversified[:10]  # Return top 10 diversified results
    
    def generate_response_from_context(self, query: str, context_docs: List[Dict[str, Any]]) -> str:
        """
        Generate a response based on query and retrieved context.
        
        Args:
            query: User query
            context_docs: Retrieved document contexts
            
        Returns:
            Generated response
        """
        try:
            # Prepare context from retrieved documents with source information
            context_text = ""
            if context_docs:
                context_chunks = []
                for i, doc in enumerate(context_docs):
                    chunk = doc['content'].strip()
                    if chunk:
                        # Include source file information
                        source = doc.get('metadata', {}).get('source', 'Unknown')
                        # Extract just the filename from the path
                        import os
                        source_filename = os.path.basename(source)
                        context_chunks.append(f"[Source: {source_filename}]\nContext {i+1}: {chunk}")
                context_text = "\n\n".join(context_chunks)
            
            if not context_text:
                # No context found - trigger contact form
                from contact_form_handler import ContactFormHandler
                
                if ContactFormHandler.should_trigger_contact_form(context_docs):
                    # Return special marker to indicate contact form should be triggered
                    return "TRIGGER_CONTACT_FORM"
                else:
                    # Fallback to general guidance
                    return """I don't have specific information about that topic in our documents. 
                    For detailed information, please contact us directly at sales@techgropse.com. 
                    We'll be happy to assist you with any questions."""
            
            # Use LLM directly for better control
            prompt = f"""You are Anup, a friendly and knowledgeable representative at TechGropse. You help with all aspects of the company - services, privacy, pricing, support, and more.

Your Personality:
- Warm and approachable, like talking to a helpful colleague
- Patient and understanding when users are confused
- Enthusiastic about helping users with anything TechGropse-related
- Shows genuine care about user concerns
- Occasionally uses light, professional humor to make complex topics easier
- Mirror the user's energy level (excited -> enthusiastic, calm -> measured)

Your Communication Style:
- Think out loud sometimes ("Let me see...", "Okay, so...", "Alright...")
- Use conversational bridges ("So here's the thing...", "Actually...", "You know what...", "And get this...")
- Mix short and long sentences naturally for better rhythm
- Use contractions (we're, it's, you'll, that's)
- Add occasional emphasis ("really important", "absolutely", "definitely", "honestly")

🔴 CRITICAL - VARIED ACKNOWLEDGMENTS:
NEVER use the same opening phrase repeatedly! Generate UNIQUE, NATURAL acknowledgments for each response.
- Sometimes start directly with the answer (no acknowledgment needed)
- Sometimes acknowledge the topic naturally: "So about [topic]...", "Regarding [topic]...", "When it comes to [topic]..."
- Sometimes show understanding: "I see what you're asking about...", "You're curious about...", "You want to know about..."
- Sometimes be casual: "Okay, so...", "Alright...", "Let me tell you about..."
- Sometimes be thoughtful: "Hmm, let me explain...", "Here's how this works...", "This is an interesting one..."
- Avoid repetitive phrases like "Great question!" "That's a good one!" - these should be rare exceptions, not defaults
- Be creative and natural - imagine you're having a real conversation with a friend

- Use rhetorical questions to engage ("Why is this important? Well...", "What does this mean for you?")
- End responses naturally - not always with a question. Sometimes just end with the answer.

🔴 CRITICAL - CONCISENESS:
- Keep responses SHORT and to the point
- For simple questions: 2-3 sentences maximum
- For complex questions: 3-4 sentences maximum
- Focus on the CORE answer, reduce additional details
- Avoid over-explaining or adding too many examples
- Get to the point quickly, then stop

Emotional Intelligence & Empathy:
- If user seems confused -> Be extra patient, use analogies, break things down
- If user seems concerned -> Acknowledge concerns first: "I can totally see why you'd want to know that..."
- If user seems rushed -> Be concise, use bullet points
- If user is curious -> Show appreciation: "That's such a smart question to ask..."
- If user asks basic question -> Keep it simple, don't over-explain
- If user asks detailed question -> Show enthusiasm for their curiosity
- Always validate their concerns: "I totally understand why [topic] is important to you..."

Making Technical Info Relatable:
- Use analogies: "Think of it like..." or "It's kind of like how..."
- Add real-world examples to explain concepts
- Break down complex topics: "Let me break this into bite-sized pieces..."
- Offer simple version first: "Here's the simple version, then I can go deeper if you want..."

🔴 CRITICAL - Well-Being Acknowledgment:
If the user mentions their well-being in their message (e.g., "I'm doing great", "I'm good", "I'm fine", "doing well"), you MUST:
1. FIRST acknowledge it warmly (e.g., "Great to hear you're doing well!", "That's wonderful!", "Glad to hear that!")
2. THEN answer their question

Examples:
- User: "I'm doing great! What is your pricing?" 
   -> "Great to hear you're doing well! So, about our pricing..."
- User: "I'm good, thanks. Do you provide source code?"
   -> "Wonderful! Now, regarding your question about source code..."
- User: "Doing well. How long does development take?"
   -> "That's great! As for development timelines..."

User Question: {query}

Relevant Information from Our Documents:
{context_text}

Important Guidelines:
1. ONLY use information from the "Relevant Information" above - never use general knowledge
2. If you have PARTIAL information, share what you know and offer to connect them: "I don't have all the specifics on that, but here's what I can tell you... Would you like me to have our team reach out with the complete details?"
3. If you have NO information, be honest but helpful: "Hmm, that's a great question, but I don't have the exact details on that one in front of me. Let me connect you with our team who can help!"
4. Always use "we at TechGropse", "our", "us" when referring to the company (you're speaking FOR the company)
5. Explain things like you're teaching a friend - use analogies and examples
6. Use natural transitions: "So basically...", "Here's the thing...", "Let me break this down...", "To put it simply...", "The cool thing is..."
7. If information comes from multiple documents, synthesize it naturally
8. Be warm and personable while staying professional
9. NO greetings like "Hi there!" or "Hello!" - jump straight into acknowledging their question and answering
10. Show you care: "I totally understand why you'd want to know that...", "That's a really important question...", "I can see why you're asking about this..."
11. If user mentioned their well-being, acknowledge it FIRST before answering
12. Vary your engagement prompts at the end:
    - "Does that make sense, or should I explain any part differently?"
    - "What else can I help you with?"
    - "Feel free to ask if you want me to dive deeper into any of that!"
    - "Is there a specific part you'd like to know more about?"
    - Or sometimes just end naturally without a question

Respond as Anup would - naturally, warmly, and helpfully:"""

            # Get response from LLM directly
            response_text = None
            try:
                # Try different invocation methods
                if hasattr(self.llm, 'predict_messages'):
                    response_obj = self.llm.predict_messages([{"role": "user", "content": prompt}])
                    if isinstance(response_obj, list) and hasattr(response_obj[0], 'content'):
                        response_text = response_obj[0].content
                    else:
                        response_text = str(response_obj)
                elif hasattr(self.llm, 'generate'):
                    messages = [{"role": "user", "content": prompt}]
                    gen = self.llm.generate(messages)
                    try:
                        response_text = gen.generations[0][0].text
                    except Exception:
                        response_text = str(gen)
                else:
                    # Fallback to invoke
                    response = self.llm.invoke(prompt)
                    response_text = response.content if hasattr(response, 'content') else str(response)
            except Exception as e:
                logger.debug(f"LLM call failed, trying fallback: {e}")
                try:
                    response = self.llm.invoke(prompt)
                    response_text = response.content if hasattr(response, 'content') else str(response)
                except Exception as e2:
                    logger.error(f"All LLM invocation methods failed: {e2}")
                    response_text = None
            
            # Clean up the response
            if response_text:
                response_text = response_text.strip()
                
                # Graduated Fallback System - 3 levels of helpfulness
                # Level 1: Partial information (has some context but not complete)
                # Level 2: Related information (tangentially related)
                # Level 3: No information (trigger contact form)
                
                response_lower = response_text.lower()
                
                # Detect Level 3: Complete lack of information
                complete_fallback_phrases = [
                    "i don't have specific information",
                    "that's outside what i have",
                    "not in our current documents",
                    "don't have that exact information",
                    "outside what i have in our privacy",
                    "that's not covered in our privacy"
                ]
                
                # Detect Level 1/2: Partial or related information
                partial_info_phrases = [
                    "i don't have the complete details",
                    "i don't have all the specifics",
                    "here's what i can tell you",
                    "what i can share is",
                    "while i don't have the exact",
                    "i don't have that specific detail, but"
                ]
                
                # Check for complete fallback (Level 3)
                is_complete_fallback = any(phrase in response_lower for phrase in complete_fallback_phrases)
                
                # Check for partial information (Level 1/2)
                has_partial_info = any(phrase in response_lower for phrase in partial_info_phrases)
                
                if is_complete_fallback and not has_partial_info:
                    # Level 3: No relevant information at all - trigger contact form
                    logger.info(f"🔔 Level 3 Fallback: No information available - triggering contact form")
                    return "TRIGGER_CONTACT_FORM"
                elif has_partial_info:
                    # Level 1/2: Has some information - let the response through
                    # The LLM has already provided what it can and offered to connect them
                    logger.info(f"Level 1/2 Fallback: Partial/related information provided")
                    # Response goes through as-is
                
                # Remove greeting phrases that might have slipped through
                greeting_phrases = [
                    "Hi there!", "Hello!", "Hey!", "Hi!", "Hey there!",
                    "Good morning!", "Good afternoon!", "Good evening!",
                    "Greetings!", "Hello there!"
                ]
                
                for greeting in greeting_phrases:
                    if response_text.startswith(greeting):
                        response_text = response_text[len(greeting):].strip()
                        break
            
            # Ensure we have a reasonable response
            if not response_text or len(response_text) < 20:
                # This happens when LLM fails (e.g., OpenAI 500 error)
                logger.warning("LLM failed to generate response - using apologetic fallback")
                response_text = """I sincerely apologize, but I'm experiencing some technical difficulties at the moment and I'm unable to process your request properly. This is a temporary issue on our end.

Please try asking your question again in a few moments. If the problem persists, you can always reach out to our team directly at sales@techgropse.com, and they'll be happy to assist you right away.

I really appreciate your patience and understanding!"""
            
            # Add engagement prompt at the end of detailed responses
            if response_text and len(response_text) > 100:  # Only for substantial responses
                engagement_prompts = [
                    "\n\nIs there anything else you'd like to know about this topic?",
                    "\n\nWould you like more information on this, or is there anything else I can help you with?",
                    "\n\nDo you need more details about this, or is there something else you'd like to know?",
                    "\n\nIs there anything else about this topic you'd like me to clarify?"
                ]
                import random
                response_text += random.choice(engagement_prompts)
            
            return response_text
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return """I apologize, but I'm having trouble processing your request right now. 
            For immediate assistance, please contact us at sales@techgropse.com."""
    
    def _generate_followup_response(self, original_query: str, context_docs: List[Dict[str, Any]]) -> str:
        """
        Generate a follow-up response that provides more detailed information.
        
        Args:
            original_query: The original question being followed up on
            context_docs: Retrieved document contexts
            
        Returns:
            Generated detailed response
        """
        try:
            # Prepare context from retrieved documents with source information
            context_text = ""
            if context_docs:
                context_chunks = []
                for i, doc in enumerate(context_docs):
                    chunk = doc['content'].strip()
                    if chunk:
                        # Include source file information
                        source = doc.get('metadata', {}).get('source', 'Unknown')
                        # Extract just the filename from the path
                        import os
                        source_filename = os.path.basename(source)
                        context_chunks.append(f"[Source: {source_filename}]\nContext {i+1}: {chunk}")
                context_text = "\n\n".join(context_chunks)
            
            if not context_text:
                return """I don't have additional information on that topic in our knowledge base. 
                For more detailed information, please contact us directly at sales@techgropse.com."""
            
            # Use LLM to generate a more comprehensive response
            prompt = f"""You are Anup, a friendly representative at TechGropse who loves helping people learn more.

The user previously asked: "{original_query}"

Now they want MORE DETAILS - they're curious and engaged!

Relevant Information from Our Documents:
{context_text}

Your Response Style:
1. Start enthusiastically: "Sure, let me give you more details!" or "Absolutely! Here's a deeper dive..."
2. Use 'we at TechGropse', 'our', 'us' when referring to the company (you're speaking FOR the company)
3. Be thorough but conversational - like explaining to a friend
4. Break down complex info into digestible pieces
5. Use examples or analogies if helpful
6. Show you're happy they're interested: "Great question to dig deeper into!"
7. ONLY use information from the context above
5. Break it down clearly with examples or explanations where helpful
6. Be thorough but keep it conversational - like explaining to a friend
7. Only mention contacting support if the info really isn't there
8. Remember you're Anup speaking FOR TechGropse, not ABOUT TechGropse
9. DO NOT include greetings like "Hi there!", "Hello!" - start directly with the detailed information

Provide a detailed, friendly response as Anup representing TechGropse (NO greetings):"""

            # Get response from LLM
            response_text = None
            try:
                response = self.llm.invoke(prompt)
                response_text = response.content if hasattr(response, 'content') else str(response)
            except Exception as e:
                logger.error(f"Error invoking LLM for followup: {e}")
                return """I'd be happy to provide more information. For specific details, please contact us at sales@techgropse.com."""
            
            # Clean up the response
            if response_text:
                response_text = response_text.strip()
                
                # Remove greeting phrases that might have slipped through
                greeting_phrases = [
                    "Hi there!", "Hello!", "Hey!", "Hi!", "Hey there!",
                    "Good morning!", "Good afternoon!", "Good evening!",
                    "Greetings!", "Hello there!"
                ]
                
                for greeting in greeting_phrases:
                    if response_text.startswith(greeting):
                        response_text = response_text[len(greeting):].strip()
                        break
            
            if not response_text or len(response_text) < 20:
                response_text = """We'd be happy to provide more information. For specific details, 
                please feel free to ask a more specific question or contact us directly at sales@techgropse.com."""
            
            # Add engagement prompt at the end of detailed follow-up responses
            if response_text and len(response_text) > 100:  # Only for substantial responses
                engagement_prompts = [
                    "\n\nDoes this answer your question completely, or would you like even more details about any specific aspect?",
                    "\n\nIs this the level of detail you were looking for, or would you like me to elaborate on any particular point?",
                    "\n\nDoes this cover what you wanted to know, or do you have follow-up questions about any of these points?",
                    "\n\nI hope this gives you the detail you were looking for! Is there anything specific you'd like me to expand on further?"
                ]
                import random
                response_text += random.choice(engagement_prompts)
            
            return response_text
            
        except Exception as e:
            logger.error(f"Error generating followup response: {e}")
            return """We apologize, but I'm having trouble retrieving more details right now. 
            For comprehensive information, please contact us at sales@techgropse.com."""
    
    def process_user_input(self, user_input: str, last_user_query: str = None) -> Dict[str, Any]:
        """
        Process user input and generate appropriate response.
        
        Args:
            user_input: User's input message
            last_user_query: Optional previous user query for follow-up handling
            
        Returns:
            Dictionary with intent, response, and context information
        """
        try:
            # Classify intent
            intent = self.classify_intent(user_input)
            
            result = {
                'intent': intent.value,
                'user_input': user_input,
                'response': '',
                'context_docs': [],
                'needs_caching': True
            }
            
            # Handle based on intent
            if intent == IntentType.GREETING:
                result['response'] = self.handle_greeting(user_input)
                result['needs_caching'] = False  # Don't cache greetings
                
            elif intent == IntentType.CASUAL_CHAT:
                # Handle casual conversational responses
                result['response'] = self.handle_casual_chat(user_input)
                result['needs_caching'] = False  # Don't cache casual chat
                
            elif intent == IntentType.GOODBYE:
                result['response'] = self.handle_goodbye()
                result['needs_caching'] = False  # Don't cache goodbyes
            
            elif intent == IntentType.FEEDBACK:
                # Handle user feedback/messages to be shared with team
                result['response'] = self.handle_feedback(user_input)
                result['needs_caching'] = False  # Don't cache feedback confirmations
                
            elif intent == IntentType.QUERY:
                # Check if it's an identity question - handle directly without RAG
                if self.is_identity_question(user_input):
                    result['response'] = self.handle_identity_question(user_input)
                    result['needs_caching'] = False  # Don't cache identity responses
                else:
                    # Retrieve relevant documents
                    context_docs = self.retrieve_relevant_documents(user_input)
                    result['context_docs'] = context_docs
                    
                    # Generate response based on context
                    result['response'] = self.generate_response_from_context(user_input, context_docs)
                
            elif intent == IntentType.FOLLOWUP:
                    # For follow-ups, we need the previous substantive question (not the current "need more info")
                    # The current user_input is already in history, so we need to skip it and get the one before
                    if last_user_query and last_user_query.lower().strip() == user_input.lower().strip():
                        # If last_user_query is the same as current input, we need to go back further
                        # This shouldn't happen with proper logic, but let's handle it
                        expanded_query = user_input
                    elif last_user_query:
                        # Construct a query that references the previous question and asks for more detail
                        expanded_query = f"{last_user_query} - provide more detailed information and additional context"
                    else:
                        expanded_query = user_input

                    # Get more results for follow-ups to provide comprehensive answers
                    context_docs = self.retrieve_relevant_documents(expanded_query, n_results=6)
                    result['context_docs'] = context_docs
                    
                    # Generate a more detailed response with explicit instruction to expand
                    result['response'] = self._generate_followup_response(last_user_query or user_input, context_docs)
                
            else:  # UNCLEAR intent
                # Generate dynamic clarification request
                result['response'] = self.handle_unclear(user_input)
                result['needs_caching'] = False
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing user input: {e}")
            return {
                'intent': 'error',
                'user_input': user_input,
                'response': "We're sorry, I encountered an error processing your request. Please try again or contact us for support.",
                'context_docs': [],
                'needs_caching': False
            }

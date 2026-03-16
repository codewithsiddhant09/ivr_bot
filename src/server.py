#!/usr/bin/env python3
"""
Text-Only Socket.IO Server for Frontend Integration
Accepts text/voice queries and returns text responses (no audio generation).

Features:
- Real-time speech-to-text processing (Whisper)
- Parallel intent classification + RAG retrieval (AsyncChatBot)
- WebSocket for real-time communication
- Speculative text pre-processing for low-latency responses
"""

import socketio
import logging
import asyncio
import os
import sys
import time
import base64
import io
from pathlib import Path
from aiohttp import web
from openai import OpenAI

# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

# Add project root and src to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'src'))

# Use async chatbot for parallel processing
from core.chatbot_async import AsyncChatBot, get_async_chatbot
from legacy.agent import ContactFormState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Socket.IO server with CORS enabled and proper ping settings
sio = socketio.AsyncServer(
    cors_allowed_origins='*',  # Allow all origins for development
    async_mode='aiohttp',
    logger=False,
    engineio_logger=False,
    ping_timeout=60,   # 60 seconds before disconnect
    ping_interval=25   # Send ping every 25 seconds
)

app = web.Application()
sio.attach(app)

# Store client sessions
clients = {}

# Track active responses for interruption handling
active_responses = {}  # {sid: {'task': asyncio.Task, 'interrupted': bool}}


class SpeechToTextHandler:
    """Handles speech-to-text conversion using OpenAI Whisper."""
    
    def __init__(self):
        """Initialize STT handler."""
        from config import config
        self.client = OpenAI(api_key=config.openai_api_key)
    
    async def transcribe_audio(self, audio_data: bytes, audio_format: str = "webm") -> str:
        """
        Transcribe audio to text using OpenAI Whisper.
        
        Args:
            audio_data: Audio data as bytes
            audio_format: Audio format (webm, mp3, wav, etc.)
            
        Returns:
            Transcribed text
        """
        try:
            # Create a file-like object from bytes
            audio_file = io.BytesIO(audio_data)
            audio_file.name = f"audio.{audio_format}"
            
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            transcript = await loop.run_in_executor(
                None,
                lambda: self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="en"
                )
            )
            
            return transcript.text
            
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            raise






# Initialize STT handler
try:
    stt_handler = SpeechToTextHandler()
except Exception as e:
    logger.error(f"STT initialization failed: {e}")
    sys.exit(1)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_contact_form_info(session_id: str, chatbot) -> dict:
    """
    Check the contact-form state after processing a message.
    Returns a dict with 'contact_form_state' and 'current_field' if the user
    is inside the contact/scheduling flow, or None otherwise.
    """
    state = chatbot.session_manager.get_contact_form_state(session_id)

    ACTIVE_FORM_STATES = {
        'asking_consent',
        'asking_schedule_change',
        'collecting_name',
        'collecting_email',
        'collecting_phone',
        'collecting_datetime',
        'collecting_timezone',
    }

    if state not in ACTIVE_FORM_STATES:
        return None

    field_map = {
        'collecting_name': 'name',
        'collecting_email': 'email',
        'collecting_phone': 'phone',
        'collecting_datetime': 'datetime',
        'collecting_timezone': 'timezone',
    }

    return {
        'contact_form_state': state,
        'current_field': field_map.get(state),
    }


# =============================================================================
# SOCKET.IO EVENTS
# =============================================================================

@sio.event
async def connect(sid, environ, auth=None):
    """Handle client connection with parallel processing pipeline."""
    logger.info(f"🔗 Client {sid} connected")
    if auth:
        logger.info(f"📋 Connection data: {auth}")
    
    try:
        # Create async chatbot for parallel processing
        chatbot = get_async_chatbot()
        session_id, initial_message = chatbot.start_session()
        
        clients[sid] = {
            'chatbot': chatbot,
            'session_id': session_id,
            'interim_cache': {},
            'last_interim_time': 0
        }
        
        # Initialize interruption tracking for this client
        active_responses[sid] = {'task': None, 'interrupted': False}
        
        # Send connection status with session_id
        await sio.emit('status', {
            'message': 'Connected to TechGropse Server',
            'type': 'success',
            'session_id': session_id
        }, room=sid)
        
        # Send initial greeting
        await sio.emit('text_response', {
            'response': initial_message,
            'message': initial_message,
            'type': 'initial_greeting'
        }, room=sid)
        
        logger.info(f"✅ Session {session_id[:8]}... created for client {sid}")
        
    except Exception as e:
        error_message = str(e)
        logger.error(f"Error creating session for {sid}: {e}")
        
        await sio.emit('error', {
            'message': f'Failed to create session: {error_message}'
        }, room=sid)


@sio.event
async def disconnect(sid):
    """Handle client disconnection."""
    logger.info(f"🔌 Client {sid} disconnected")
    
    if sid in clients:
        client_data = clients[sid]
        chatbot = client_data['chatbot']
        session_id = client_data['session_id']
        try:
            chatbot.end_session(session_id)  # Pass session_id
        except Exception as e:
            logger.error(f"Error ending session for {sid}: {e}")
        del clients[sid]
        logger.info(f"🗑️ Session cleaned up for client {sid}")
    else:
        logger.info(f"Client {sid} already cleaned up")
    
    # Clean up interruption tracking
    if sid in active_responses:
        # Cancel any active response task
        if 'task' in active_responses[sid]:
            task = active_responses[sid]['task']
            if not task.done():
                task.cancel()
        del active_responses[sid]


@sio.event
async def new_session(sid, data):
    """
    Called by Nest when a new frontend user connects.
    Ends any existing session for this Nest socket, creates a brand-new one
    and emits the greeting.
    """
    logger.info(f"🔄 new_session requested by {sid}")

    # End any previous session cleanly
    if sid in clients:
        old_chatbot = clients[sid]['chatbot']
        old_session_id = clients[sid]['session_id']
        try:
            old_chatbot.end_session(old_session_id)
        except Exception:
            pass
        del clients[sid]

    if sid in active_responses:
        task = active_responses[sid].get('task')
        if task and not task.done():
            task.cancel()
        del active_responses[sid]

    try:
        chatbot = get_async_chatbot()
        session_id, initial_message = chatbot.start_session()

        clients[sid] = {
            'chatbot': chatbot,
            'session_id': session_id,
            'interim_cache': {},
            'last_interim_time': 0
        }
        active_responses[sid] = {'task': None, 'interrupted': False}

        # Emit the greeting as a text_response so Nest forwards it to the frontend
        await sio.emit('text_response', {
            'response': initial_message,
            'message': initial_message,
            'type': 'initial_greeting',
            'session_id': session_id
        }, room=sid)

        logger.info(f"✅ new_session created: {session_id[:8]}... for sid {sid}")

    except Exception as e:
        logger.error(f"Error in new_session for {sid}: {e}")
        await sio.emit('error', {'message': f'Failed to create session: {e}'}, room=sid)


@sio.event
async def text_only_query(sid, data):
    """Handle text-only query from client (no audio response)."""
    try:
        if sid not in clients:
            await sio.emit('error_response', {
                'message': 'Session not found'
            }, room=sid)
            return
        
        # Extract query text
        if isinstance(data, dict):
            query_text = data.get('message', '') or data.get('query', '') or data.get('text', '')
        else:
            query_text = str(data)
        
        if not query_text or not query_text.strip():
            await sio.emit('error_response', {
                'message': 'Empty query'
            }, room=sid)
            return
        
        client_data = clients[sid]
        chatbot = client_data['chatbot']
        session_id = client_data['session_id']
        
        logger.info(f"💬 Text-only query from {sid}: '{query_text}'")
        
        # Process query through async chatbot with parallel pipeline
        result = await chatbot.process_message_async(
            user_input=query_text,
            session_id=session_id
        )
        
        response = result.get('response', '')
        
        logger.info(f"✅ Text-only response for {sid}: {response[:50]}...")
        
        # Check contact form state
        form_info = get_contact_form_info(session_id, chatbot)
        is_contact = form_info is not None
        
        # Send text response
        await sio.emit('text_response', {
            'response': response,
            'message': response,
            'original_query': query_text,
            'type': 'text_only',
            'is_contact_request': is_contact,
            'contact_form_state': form_info['contact_form_state'] if form_info else 'idle',
            'current_field': form_info.get('current_field') if form_info else None,
        }, room=sid)
        
        # Emit dedicated contact_request event when inside the scheduling/contact flow
        if is_contact:
            await sio.emit('contact_request', {
                'contact_form_state': form_info['contact_form_state'],
                'current_field': form_info.get('current_field'),
                'message': response,
            }, room=sid)
            logger.info(f"📋 Emitted contact_request for {sid}: state={form_info['contact_form_state']}")
        
    except Exception as e:
        logger.error(f"Error handling text-only query for {sid}: {e}")
        await sio.emit('error_response', {
            'message': str(e)
        }, room=sid)


@sio.event
async def text_query(sid, data):
    """Handle text query from client."""
    try:
        if sid not in clients:
            await sio.emit('error', {
                'message': 'Session not found'
            }, room=sid)
            return
        
        # INTERRUPTION HANDLING: Cancel previous response if still active
        if sid in active_responses and active_responses[sid]['task']:
            logger.info(f"⚠️ Interrupting previous response for client {sid}")
            active_responses[sid]['interrupted'] = True
            
            # Cancel the previous task
            previous_task = active_responses[sid]['task']
            if previous_task and not previous_task.done():
                previous_task.cancel()
                try:
                    await previous_task
                except asyncio.CancelledError:
                    logger.info(f"✅ Previous response cancelled for {sid}")
            
            # Send interruption signal to client
            await sio.emit('response_interrupted', {
                'message': 'Previous response interrupted'
            }, room=sid)
        
        # Extract query text
        if isinstance(data, dict):
            query_text = data.get('message', '') or data.get('query', '') or data.get('text', '')
        else:
            query_text = str(data)
        
        if not query_text or not query_text.strip():
            await sio.emit('error', {
                'message': 'Empty query'
            }, room=sid)
            return
        
        client_data = clients[sid]
        chatbot = client_data['chatbot']
        session_id = client_data['session_id']  # Get session_id
        
        logger.info(f"💬 Client {sid}: '{query_text}'")
        
        # Send acknowledgment
        await sio.emit('query_received', {
            'message': query_text,
            'status': 'processing'
        }, room=sid)
        
        # Create a new task for this response
        async def process_and_respond():
            try:
                # Reset interruption flag
                active_responses[sid]['interrupted'] = False
                
                # ✨ CHECK FOR SPECULATIVE CACHE FIRST ✨
                speculative_cache = clients[sid].get('speculative_cache')
                
                logger.info(f"📦 Cache check: {'Found' if speculative_cache else 'None'}")
                
                if speculative_cache:
                    cached_text = speculative_cache['partial_text']
                    cached_result = speculative_cache['result']
                    cache_age = time.time() - speculative_cache['timestamp']
                    speculation_complete_time = speculative_cache['timestamp']
                    
                    # CRITICAL METRIC: Did speculation finish BEFORE user stopped speaking?
                    user_stop_time = time.time()
                    time_delta = user_stop_time - speculation_complete_time
                    
                    if time_delta > 0:
                        logger.info(f"✅ SPECULATION WON! Completed {time_delta:.2f}s BEFORE user stopped speaking!")
                    else:
                        logger.info(f"⏰ SPECULATION LATE! Completed {abs(time_delta):.2f}s AFTER user stopped speaking")
                    
                    logger.info(f"📦 Cache contents: interim='{cached_text}', age={cache_age:.2f}s")
                    
                    # Check if cached speculation is still relevant
                    # Use fuzzy matching: if final query contains 70%+ of cached text
                    similarity = len(set(cached_text.lower().split()) & set(query_text.lower().split())) / max(len(cached_text.split()), len(query_text.split()))
                    
                    logger.info(f"🔍 Similarity check: {similarity:.2%} (threshold: 70%, age: {cache_age:.2f}s / 5.0s)")
                    
                    if similarity > 0.7 and cache_age < 5.0:
                        logger.info(f"🎯 CACHE HIT! Using speculative result (similarity: {similarity:.2%}, age: {cache_age:.2f}s)")
                        logger.info(f"   Cached: '{cached_text}'")
                        logger.info(f"   Final:  '{query_text}'")
                        
                        result = cached_result
                        process_time = 0.001  # Nearly instant!
                        
                        # Clear cache after use
                        del clients[sid]['speculative_cache']
                    else:
                        logger.info(f"🔄 Cache miss (similarity: {similarity:.2%}, age: {cache_age:.2f}s), processing fresh...")
                        # Clear stale cache
                        if 'speculative_cache' in clients[sid]:
                            del clients[sid]['speculative_cache']
                        
                        # Process normally
                        process_start = time.time()
                        result = await chatbot.process_message_async(
                            user_input=query_text,
                            session_id=session_id
                        )
                        process_time = time.time() - process_start
                else:
                    # No cache, process normally
                    logger.info(f"🔄 No cache found, processing query with parallel pipeline for {sid}...")
                    
                    process_start = time.time()
                    
                    # Use async processing with parallel intent + RAG
                    result = await chatbot.process_message_async(
                        user_input=query_text,
                        session_id=session_id
                    )
                    
                    process_time = time.time() - process_start
                
                response = result.get('response', '')
                intent = result.get('intent', '')
                
                # Check if interrupted during processing
                if active_responses[sid]['interrupted']:
                    logger.info(f"⚠️ Response interrupted during processing for {sid}")
                    return
                
                logger.info(f"✅ [{sid[:8]}] Parallel processing: {process_time:.2f}s (Intent: {intent})")
                
                # Check contact form state — emit a separate contact_request
                # event when the user is inside the contact/scheduling flow.
                form_info = get_contact_form_info(session_id, chatbot)
                is_contact = form_info is not None
                
                # Send text response (always — Nest forwards to frontend for TTS)
                await sio.emit('text_response', {
                    'message': response,
                    'original_query': query_text,
                    'type': 'response',
                    'is_contact_request': is_contact,
                    'contact_form_state': form_info['contact_form_state'] if form_info else 'idle',
                    'current_field': form_info.get('current_field') if form_info else None,
                }, room=sid)
                
                # If the user is in an active form state, also emit a dedicated
                # contact_request event so Nest can open the form overlay.
                if is_contact:
                    await sio.emit('contact_request', {
                        'contact_form_state': form_info['contact_form_state'],
                        'current_field': form_info.get('current_field'),
                        'message': response,
                    }, room=sid)
                    logger.info(f"📋 Emitted contact_request for {sid}: state={form_info['contact_form_state']}, field={form_info.get('current_field')}")
                
                logger.info(f"📤 Sent text to client {sid}: {response[:50]}...")
                
            except asyncio.CancelledError:
                logger.info(f"⚠️ Response task cancelled for {sid}")
                raise
            except Exception as e:
                logger.error(f"Error processing query for {sid}: {e}")
                await sio.emit('error', {
                    'message': f'Processing error: {str(e)}'
                }, room=sid)
        
        # Start the task and track it
        task = asyncio.create_task(process_and_respond())
        active_responses[sid]['task'] = task
        
        try:
            await task
        except asyncio.CancelledError:
            pass  # Task was cancelled due to interruption
            
    except Exception as e:
        logger.error(f"Error handling query for {sid}: {e}")
        await sio.emit('error', {
            'message': str(e)
        }, room=sid)


@sio.event
async def voice_input(sid, data):
    """Handle voice input from client."""
    try:
        if sid not in clients:
            await sio.emit('error', {
                'message': 'Session not found'
            }, room=sid)
            return
        
        # Extract audio data
        if isinstance(data, dict):
            audio_b64 = data.get('audio', '')
            audio_format = data.get('format', 'webm')
        else:
            logger.error(f"Invalid voice input data format from {sid}")
            await sio.emit('error', {
                'message': 'Invalid audio data format'
            }, room=sid)
            return
        
        if not audio_b64:
            await sio.emit('error', {
                'message': 'Empty audio data'
            }, room=sid)
            return
        
        logger.info(f"🎤 Client {sid} sent voice input ({len(audio_b64)} bytes base64)")
        
        try:
            # Decode base64 audio
            audio_bytes = base64.b64decode(audio_b64)
            
            # Validate audio size
            if len(audio_bytes) < 1000:  # Less than 1KB
                logger.warning(f"Audio too short from {sid}: {len(audio_bytes)} bytes")
                await sio.emit('error', {
                    'message': 'Audio recording too short. Please hold the button longer.'
                }, room=sid)
                return
            
            # Send transcription status
            await sio.emit('transcription_start', {
                'message': 'Transcribing audio...'
            }, room=sid)
            
            # Transcribe audio to text
            transcribed_text = await stt_handler.transcribe_audio(audio_bytes, audio_format)
            
            logger.info(f"📝 Transcribed for {sid}: '{transcribed_text}'")
            
            # Send transcription result
            await sio.emit('transcription_complete', {
                'text': transcribed_text
            }, room=sid)
            
            # Process as text query (reuse existing logic)
            # Create a dict with the transcribed text
            text_data = {'text': transcribed_text}
            await text_query(sid, text_data)
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error processing voice input for {sid}: {e}")
            
            # Check for specific Whisper API errors
            if 'could not be decoded' in error_msg or 'format is not supported' in error_msg:
                await sio.emit('error', {
                    'message': 'Audio format error. Please try again.'
                }, room=sid)
            else:
                await sio.emit('error', {
                    'message': f'Voice processing error: {str(e)}'
                }, room=sid)
            
    except Exception as e:
        logger.error(f"Error handling voice input for {sid}: {e}")
        await sio.emit('error', {
            'message': str(e)
        }, room=sid)


# =============================================================================
# INTERIM SPEECH (for predictive processing)
# =============================================================================

@sio.event
async def interim_speech(sid, data):
    """
    Handle interim (partial) speech transcription from Web Speech API.
    SPECULATIVE EXECUTION: Runs FULL pipeline (RAG + TTS + AUDIO) in background.
    
    Strategy:
    - Process complete response while user is still speaking
    - Generate AUDIO during speculation (not just text)
    - Cache the result including audio bytes
    - If final query matches, stream cached audio instantly
    - If query changes, discard and reprocess
    
    Target: Complete audio ready BEFORE user finishes speaking
    """
    if sid not in clients:
        return
    
    try:
        partial_text = data.get('text', '') if isinstance(data, dict) else str(data)
        
        # 🚀 MORE AGGRESSIVE: Need less text for speculation (min 5 chars instead of 10)
        if not partial_text or len(partial_text) < 5:
            return
        
        # 🚀 MORE AGGRESSIVE: Rate limit reduced to 1 second (was 2 seconds)
        # This means we start speculation earlier and update more frequently
        now = time.time()
        if now - clients[sid].get('last_interim_time', 0) < 1.0:
            # Update cache with latest text but don't restart speculation
            return
        
        # Cancel previous speculation and start fresh with new text
        if 'speculation_task' in clients[sid]:
            prev_task = clients[sid]['speculation_task']
            if not prev_task.done():
                prev_task.cancel()
                logger.info(f"🔄 Cancelled previous speculation, starting fresh with: '{partial_text}'")
            return
        
        clients[sid]['last_interim_time'] = now
        
        chatbot = clients[sid]['chatbot']
        session_id = clients[sid]['session_id']
        
        logger.info(f"🔮 SPECULATION START: '{partial_text}' (while user still speaking)")
        
        # Run speculative text execution in background task
        async def speculate():
            try:
                rag_start = time.time()
                
                # Get text response (RAG + Intent + Response)
                result = await chatbot.process_interim_async(partial_text, session_id)
                
                rag_time = time.time() - rag_start
                
                if result.get('ready'):
                    response_text = result.get('response', '')
                    
                    logger.info(f"✅ Text response ready in {rag_time:.2f}s: '{response_text[:50]}...'")
                    
                    # Cache text response for instant delivery
                    cache_timestamp = time.time()
                    clients[sid]['speculative_cache'] = {
                        'partial_text': partial_text,
                        'result': result,
                        'timestamp': cache_timestamp,
                        'rag_time': rag_time
                    }
                    
                    logger.info(f"✅ SPECULATION COMPLETE: Text ready for '{partial_text}' "
                              f"(total: {rag_time:.2f}s)")
                    logger.info(f"💾 Cache saved at {cache_timestamp:.2f} (TTL: 5s)")
                    
                    # Notify client that response is pre-computed
                    await sio.emit('speculative_ready', {
                        'partial_text': partial_text,
                        'intent': result.get('intent', 'unknown'),
                        'ready': True,
                        'timings': {
                            'rag': rag_time
                        }
                    }, room=sid)
                
            except asyncio.CancelledError:
                logger.info(f"❌ Speculation cancelled for '{partial_text}'")
            except Exception as e:
                logger.error(f"Speculation error: {e}")
        
        # Start speculation task (non-blocking)
        task = asyncio.create_task(speculate())
        clients[sid]['speculation_task'] = task
        
    except Exception as e:
        logger.error(f"Interim processing error for {sid}: {e}")



# Health check endpoint
async def health(request):
    """Health check endpoint."""
    return web.Response(text='Text-Only Socket.IO Server Running')

# Serve the HTML frontend
async def serve_frontend(request):
    """Serve the HTML frontend."""
    try:
        html_path = Path(__file__).parent / 'static' / 'text_to_voice.html'
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        return web.Response(text=html_content, content_type='text/html')
    except FileNotFoundError:
        return web.Response(text='Frontend HTML file not found', status=404)

# Serve the voice-to-voice interface
async def serve_voice_interface(request):
    """Serve the voice-to-voice HTML frontend."""
    try:
        html_path = Path(__file__).parent / 'static' / 'voice_to_voice.html'
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        return web.Response(text=html_content, content_type='text/html')
    except FileNotFoundError:
        return web.Response(text='Voice interface HTML file not found', status=404)

# Add routes
app.router.add_get('/', serve_voice_interface)  # Default to voice interface
app.router.add_get('/voice', serve_voice_interface)
app.router.add_get('/text', serve_frontend)  # Text interface for testing
app.router.add_get('/health', health)


def check_environment():
    """Check if all required environment variables are set."""
    issues = []
    
    # Check OpenAI API key
    from config import config
    if not config.openai_api_key:
        issues.append("OpenAI API key is not set. Please set OPENAI_API_KEY environment variable.")
    

    
    # Check if data file exists
    if not os.path.exists(config.data_file_path):
        issues.append(f"Data file not found: {config.data_file_path}")
    
    return issues


def main(host='0.0.0.0', port=8080):
    """Start the Text-Only Socket.IO server."""
    logger.info(f"🚀 Starting Text-Only Socket.IO Server on {host}:{port}")
    logger.info("💬 Each client gets their own session")
    logger.info("� Text-only responses (no audio generation)")
    logger.info("🌐 CORS enabled for frontend integration")
    logger.info("-" * 50)
    
    web.run_app(app, host=host, port=port)


if __name__ == '__main__':
    try:
        # Check environment
        issues = check_environment()
        if issues:
            print("❌ Environment check failed:")
            for issue in issues:
                print(f"   • {issue}")
            sys.exit(1)
        
        # Start the Socket.IO server
        main(host='0.0.0.0', port=8080)
        
    except KeyboardInterrupt:
        print("\n👋 Server shutting down...")
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)
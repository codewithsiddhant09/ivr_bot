#!/usr/bin/env python3
"""
Text-to-Voice Socket.IO Server for Frontend Integration
Accepts text queries and streams audio responses to browser

Features:
- Real-time speech-to-text processing (Whisper)
- Parallel intent classification + RAG retrieval (AsyncChatBot)
- Background TTS generation with streaming (AWS Polly)
- WebSocket for real-time communication
- Target: 2-3 second total response time
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
from typing import Iterator
from openai import OpenAI

# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

# Add current directory to Python path
sys.path.append(str(Path(__file__).parent))

# Use async chatbot for parallel processing
from chatbot_async import AsyncChatBot, get_async_chatbot
from agent import ContactFormState

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





class AWSPollyTTSHandler:
    """Handles text-to-speech conversion using AWS Polly."""
    
    def __init__(self):
        """Initialize AWS Polly TTS handler."""
        from config import config
        
        # Validate AWS credentials
        if not config.aws_access_key_id or not config.aws_secret_access_key:
            raise ValueError(
                "AWS credentials are required for Polly TTS. "
                "Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables."
            )
        
        try:
            import boto3
            from contextlib import closing
            
            self.polly = boto3.client(
                'polly',
                region_name=config.aws_region,
                aws_access_key_id=config.aws_access_key_id,
                aws_secret_access_key=config.aws_secret_access_key
            )
            self.voice_id = config.polly_voice_id
            self.output_format = config.polly_output_format
            self.closing = closing
            
            # Available voices organized by gender
            self.available_voices = {
                'male': ['Stephen', 'Joey', 'Justin', 'Matthew', 'Kevin'],
                'female': ['Kendra', 'Kimberly', 'Ruth', 'Joanna', 'Salli', 'Gregory', 'Ivy', 'Danielle']
            }
            
            logger.info(f"✅ AWS Polly TTS initialized (region: {config.aws_region}, voice: {self.voice_id})")
            
        except ImportError:
            raise ImportError("boto3 is required for AWS Polly TTS. Install it with: pip install boto3")
        except Exception as e:
            logger.error(f"Failed to initialize AWS Polly client: {e}")
            raise
    
    async def text_to_speech_stream(self, text: str) -> Iterator[bytes]:
        """
        Convert text to speech using AWS Polly and return audio stream.
        
        Args:
            text: Text to convert to speech
            
        Yields:
            Audio chunks as bytes
        """
        start = time.perf_counter()
        
        try:
            logger.info(f"🔊 Generating speech with AWS Polly (voice: {self.voice_id})")
            
            # Make async request to AWS Polly
            # Use MP3 format for better browser compatibility
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.polly.synthesize_speech(
                    Text=text,
                    OutputFormat='mp3',  # MP3 format for browser compatibility
                    VoiceId=self.voice_id,
                    Engine='neural'  # Use neural engine for better quality
                )
            )
            
            end = time.perf_counter()
            logger.info(f"Time to get Polly response: {end-start}s")
            
            # Stream audio data in chunks
            with self.closing(response['AudioStream']) as stream:
                chunk_size = 1024  # 1KB chunks
                first = True
                
                while True:
                    # Read chunk from stream
                    chunk = await loop.run_in_executor(None, stream.read, chunk_size)
                    
                    if first and chunk:
                        end = time.perf_counter()
                        logger.info(f"Time to first audio chunk: {end-start}s")
                        first = False
                    
                    if not chunk:
                        break
                    
                    yield chunk
            
            logger.info(f"✅ AWS Polly TTS streaming completed")
            
        except self.polly.exceptions.TextLengthExceededException:
            logger.error("Text is too long for AWS Polly (max 3000 characters)")
            raise Exception("Text is too long for speech synthesis. Please shorten your message.")
        except self.polly.exceptions.InvalidSsmlException:
            logger.error("Invalid SSML in text")
            raise Exception("Invalid text format for speech synthesis.")
        except self.polly.exceptions.ServiceFailureException:
            logger.error("AWS Polly service failure")
            raise Exception("Text-to-speech service is temporarily unavailable. Please try again later.")
        except Exception as e:
            logger.error(f"Error in AWS Polly text_to_speech_stream: {e}")
            raise Exception(f"Text-to-speech error: {str(e)}")
    
    def set_voice(self, voice_id: str) -> bool:
        """
        Change the voice for TTS.
        
        Args:
            voice_id: AWS Polly voice ID
            
        Returns:
            True if voice was changed successfully
        """
        try:
            # Validate voice ID
            all_voices = self.available_voices['male'] + self.available_voices['female']
            if voice_id not in all_voices:
                logger.warning(f"Invalid voice ID: {voice_id}. Using default voice.")
                return False
            
            self.voice_id = voice_id
            logger.info(f"✅ Voice changed to: {voice_id}")
            return True
        except Exception as e:
            logger.error(f"Error changing voice: {e}")
            return False
    
    def get_available_voices(self) -> dict:
        """
        Get list of available voices.
        
        Returns:
            Dictionary of available voices by gender
        """
        return self.available_voices





# Initialize AWS Polly TTS handler
try:
    logger.info("🔧 Initializing AWS Polly TTS handler...")
    tts_handler = AWSPollyTTSHandler()
    logger.info("✅ AWS Polly TTS handler ready")
        
except ValueError as e:
    logger.error(f"TTS initialization failed: {e}")
    logger.error("Please ensure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are set in .env file")
    sys.exit(1)
except Exception as e:
    logger.error(f"Unexpected error during TTS initialization: {e}")
    sys.exit(1)


# Initialize STT handler
try:
    stt_handler = SpeechToTextHandler()
except Exception as e:
    logger.error(f"STT initialization failed: {e}")
    sys.exit(1)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def is_collecting_info(session_id: str) -> tuple:
    """
    Check if we're in the contact form collection flow.
    Returns (is_collecting, current_field)
    """
    from session_manager import session_manager
    
    state = session_manager.get_contact_form_state(session_id)
    
    if state in [
        ContactFormState.INITIAL_COLLECTING_NAME.value,
        'initial_collecting_name'
    ]:
        return True, 'name'
    elif state in [
        ContactFormState.INITIAL_COLLECTING_EMAIL.value,
        'initial_collecting_email'
    ]:
        return True, 'email'
    elif state in [
        ContactFormState.INITIAL_COLLECTING_PHONE.value,
        'initial_collecting_phone'
    ]:
        return True, 'phone'
    elif state in [
        ContactFormState.COLLECTING_DATETIME.value,
        'collecting_datetime'
    ]:
        return True, 'datetime'
    elif state in [
        ContactFormState.ASKING_CONSENT.value,
        'asking_consent'
    ]:
        return True, 'consent'
    
    return False, None


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
        
        # Send initial greeting asking for name
        await sio.emit('text_response', {
            'response': initial_message,
            'message': initial_message,
            'type': 'initial_greeting',
            'show_chatbox': True,
            'current_field': 'name'
        }, room=sid)
        
        logger.info(f"✅ Session {session_id[:8]}... created for client {sid}")
        
        # Generate and stream audio for initial greeting
        await stream_audio_to_client(sid, initial_message)
        
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
        
        # Send ONLY text response (no audio)
        await sio.emit('text_response', {
            'response': response,
            'message': response,
            'original_query': query_text,
            'type': 'text_only'
        }, room=sid)
        
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
                cached_audio = None  # Track if we have cached audio
                
                logger.info(f"📦 Cache check: {'Found' if speculative_cache else 'None'}")
                
                if speculative_cache:
                    cached_text = speculative_cache['partial_text']
                    cached_result = speculative_cache['result']
                    cached_audio_bytes = speculative_cache.get('audio_bytes')  # 🚀 NEW!
                    cache_age = time.time() - speculative_cache['timestamp']
                    speculation_complete_time = speculative_cache['timestamp']
                    
                    # 🚀 CRITICAL METRIC: Did speculation finish BEFORE user stopped speaking?
                    user_stop_time = time.time()  # When text_query was received
                    time_delta = user_stop_time - speculation_complete_time
                    
                    if time_delta > 0:
                        logger.info(f"✅ SPECULATION WON! Completed {time_delta:.2f}s BEFORE user stopped speaking!")
                    else:
                        logger.info(f"⏰ SPECULATION LATE! Completed {abs(time_delta):.2f}s AFTER user stopped speaking")
                    
                    logger.info(f"📦 Cache contents: interim='{cached_text}', has_audio={bool(cached_audio_bytes)}, age={cache_age:.2f}s")
                    
                    # Check if cached speculation is still relevant
                    # Use fuzzy matching: if final query contains 70%+ of cached text
                    similarity = len(set(cached_text.lower().split()) & set(query_text.lower().split())) / max(len(cached_text.split()), len(query_text.split()))
                    
                    logger.info(f"🔍 Similarity check: {similarity:.2%} (threshold: 70%, age: {cache_age:.2f}s / 5.0s)")
                    
                    if similarity > 0.7 and cache_age < 5.0:
                        logger.info(f"🎯 CACHE HIT! Using speculative result (similarity: {similarity:.2%}, age: {cache_age:.2f}s)")
                        logger.info(f"   Cached: '{cached_text}'")
                        logger.info(f"   Final:  '{query_text}'")
                        
                        if cached_audio_bytes:
                            logger.info(f"🎵 CACHED AUDIO AVAILABLE! ({len(cached_audio_bytes)} bytes) - INSTANT PLAYBACK!")
                            cached_audio = cached_audio_bytes
                        else:
                            logger.warning(f"⚠️ Cache hit but NO AUDIO! Only text was cached.")
                        
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
                timing_info = result.get('timing', {})
                
                # Check if interrupted during processing
                if active_responses[sid]['interrupted']:
                    logger.info(f"⚠️ Response interrupted during processing for {sid}")
                    return
                
                logger.info(f"✅ [{sid[:8]}] Parallel processing: {process_time:.2f}s (Intent: {intent})")
                
                # Get contact form state to determine chatbox visibility
                form_state = chatbot.session_manager.get_contact_form_state(session_id)
                
                # Determine if chatbox should be visible
                # Show chatbox when collecting initial user details or contact information
                show_chatbox = form_state in [
                    'initial_collecting_name',
                    'initial_collecting_email',
                    'initial_collecting_phone',
                    'asking_consent',
                    'collecting_name',
                    'collecting_email',
                    'collecting_phone',
                    'collecting_datetime',
                    'collecting_timezone'
                ]
                
                # Determine current field being collected
                current_field = None
                if form_state in ['collecting_name', 'initial_collecting_name']:
                    current_field = 'name'
                elif form_state in ['collecting_email', 'initial_collecting_email']:
                    current_field = 'email'
                elif form_state in ['collecting_phone', 'initial_collecting_phone']:
                    current_field = 'phone'
                elif form_state == 'collecting_datetime':
                    current_field = 'datetime'
                elif form_state == 'collecting_timezone':
                    current_field = 'timezone'
                
                # Send text response with chatbox visibility flag
                await sio.emit('text_response', {
                    'message': response,
                    'original_query': query_text,
                    'type': 'response',
                    'show_chatbox': show_chatbox,  # Flag for frontend
                    'contact_form_state': form_state,  # For debugging
                    'current_field': current_field  # Which field is being collected
                }, room=sid)
                
                logger.info(f"📤 Sent text to client {sid}: {response[:50]}...")
                
                # Check again before audio streaming
                if active_responses[sid]['interrupted']:
                    logger.info(f"⚠️ Response interrupted before audio for {sid}")
                    return
                
                # 🚀 Generate and stream audio response
                # If we have cached audio, stream it instantly!
                if cached_audio:
                    logger.info(f"🎵 Streaming CACHED audio ({len(cached_audio)} bytes) - INSTANT PLAYBACK!")
                    await stream_cached_audio_to_client(sid, cached_audio)
                else:
                    # Generate fresh audio
                    await stream_audio_to_client(sid, response)
                
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
        
        # MORE AGGRESSIVE: Need less text for speculation (min 5 chars instead of 10)
        if not partial_text or len(partial_text) < 5:
            return
        
        # MORE AGGRESSIVE: Rate limit reduced to 1 second (was 2 seconds)
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
        
        # Run full speculative execution in background task
        async def speculate():
            try:
                # 🚀 TRULY PARALLEL: Start both text and audio generation simultaneously
                rag_start = time.time()
                
                # Step 1: Start getting text response (RAG + Intent + Response)
                result = await chatbot.process_interim_async(partial_text, session_id)
                
                rag_time = time.time() - rag_start
                
                if result.get('ready'):
                    response_text = result.get('response', '')
                    
                    logger.info(f"✅ Text response ready in {rag_time:.2f}s: '{response_text[:50]}...'")
                    
                    # Step 2: 🔥 START AUDIO GENERATION IMMEDIATELY (in parallel with any remaining work)
                    audio_start = time.time()
                    logger.info(f"🎵 Starting PARALLEL audio generation...")
                    
                    # Generate audio in parallel using asyncio.gather or create_task
                    # This ensures we start audio generation immediately without waiting
                    audio_bytes = b''
                    
                    # Collect all audio chunks ASAP
                    async for audio_chunk in tts_handler.text_to_speech_stream(response_text):
                        audio_bytes += audio_chunk
                    
                    audio_time = time.time() - audio_start
                    
                    logger.info(f"🎵 Audio generated: {len(audio_bytes)} bytes in {audio_time:.2f}s")
                    
                    # Step 3: Cache BOTH text response AND audio
                    cache_timestamp = time.time()
                    clients[sid]['speculative_cache'] = {
                        'partial_text': partial_text,
                        'result': result,
                        'audio_bytes': audio_bytes,  # 🚀 Pre-generated audio
                        'timestamp': cache_timestamp,
                        'audio_generation_time': audio_time,
                        'rag_time': rag_time
                    }
                    
                    total_time = rag_time + audio_time
                    
                    logger.info(f"✅ SPECULATION COMPLETE: Text + Audio ready for '{partial_text}' "
                              f"(total: {total_time:.2f}s = RAG {rag_time:.2f}s + Audio {audio_time:.2f}s)")
                    logger.info(f"💾 Cache saved at {cache_timestamp:.2f} (TTL: 5s)")
                    
                    # Notify client that response is pre-computed (optional)
                    await sio.emit('speculative_ready', {
                        'partial_text': partial_text,
                        'intent': result.get('intent', 'unknown'),
                        'ready': True,
                        'has_audio': True,  # 🚀 Audio pre-generated
                        'timings': {
                            'rag': rag_time,
                            'audio': audio_time,
                            'total': total_time
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


@sio.event
async def change_voice(sid, data):
    """Handle voice change request from client."""
    try:
        if sid not in clients:
            await sio.emit('error', {
                'message': 'Session not found'
            }, room=sid)
            return
        
        # Extract voice ID
        if isinstance(data, dict):
            voice_id = data.get('voice_id', '') or data.get('voiceId', '')
        else:
            voice_id = str(data)
        
        if not voice_id:
            await sio.emit('error', {
                'message': 'No voice ID provided'
            }, room=sid)
            return
        
        logger.info(f"🎙️ Client {sid} requesting voice change to: {voice_id}")
        
        # Change the voice
        success = tts_handler.set_voice(voice_id)
        
        if success:
            await sio.emit('voice_changed', {
                'voice_id': voice_id,
                'message': f'Voice changed to {voice_id}'
            }, room=sid)
            logger.info(f"✅ Voice changed to {voice_id} for client {sid}")
        else:
            await sio.emit('error', {
                'message': f'Invalid voice ID: {voice_id}'
            }, room=sid)
            
    except Exception as e:
        logger.error(f"Error changing voice for {sid}: {e}")
        await sio.emit('error', {
            'message': str(e)
        }, room=sid)


@sio.event
async def get_voices(sid):
    """Send available voices to client."""
    try:
        voices = tts_handler.get_available_voices()
        await sio.emit('available_voices', {
            'voices': voices
        }, room=sid)
        logger.info(f"📋 Sent available voices to client {sid}")
    except Exception as e:
        logger.error(f"Error sending voices to {sid}: {e}")
        await sio.emit('error', {
            'message': str(e)
        }, room=sid)


async def stream_audio_to_client(sid: str, text: str):
    """
    Generate audio from text and stream it to the client.
    Supports interruption - stops streaming if client sends new query.
    
    Args:
        sid: Client session ID
        text: Text to convert to audio
    """
    try:
        logger.info(f"🔊 Generating audio for client {sid}")
        
        # Signal start of audio stream
        await sio.emit('audio_start', {
            'message': 'Starting audio stream...',
            'text_length': len(text)
        }, room=sid)
        
        # Generate and stream audio chunks
        chunk_count = 0
        async for audio_chunk in tts_handler.text_to_speech_stream(text):
            # Check for interruption before sending each chunk
            if sid in active_responses and active_responses[sid]['interrupted']:
                logger.info(f"⚠️ Audio streaming interrupted for client {sid} at chunk {chunk_count}")
                await sio.emit('audio_interrupted', {
                    'message': 'Audio playback interrupted',
                    'chunks_sent': chunk_count
                }, room=sid)
                return
            
            if audio_chunk:
                # Encode audio chunk as base64 for transmission
                audio_b64 = base64.b64encode(audio_chunk).decode('utf-8')
                
                await sio.emit('audio_chunk', {
                    'data': audio_b64,
                    'chunk_id': chunk_count,
                    'format': 'mp3'  # MP3 format
                }, room=sid)
                
                chunk_count += 1
        
        # Only send completion if not interrupted
        if sid in active_responses and not active_responses[sid]['interrupted']:
            # Signal end of audio stream
            await sio.emit('audio_end', {
                'message': 'Audio stream completed',
                'total_chunks': chunk_count
            }, room=sid)
            
            logger.info(f"🎵 Audio streaming completed for client {sid} ({chunk_count} chunks)")
        
    except asyncio.CancelledError:
        logger.info(f"⚠️ Audio streaming cancelled for client {sid}")
        await sio.emit('audio_interrupted', {
            'message': 'Audio playback cancelled'
        }, room=sid)
        raise
    except Exception as e:
        logger.error(f"Error streaming audio to client {sid}: {e}")
        await sio.emit('error', {
            'message': f'Audio streaming error: {str(e)}'
        }, room=sid)


async def stream_cached_audio_to_client(sid: str, audio_bytes: bytes):
    """
    Stream pre-generated (cached) audio to the client.
    🚀 INSTANT PLAYBACK - No TTS generation delay!
    
    Args:
        sid: Client session ID
        audio_bytes: Complete MP3 audio as bytes (already generated)
    """
    try:
        logger.info(f"⚡ Streaming CACHED audio for client {sid} ({len(audio_bytes)} bytes)")
        
        # Signal start of audio stream
        await sio.emit('audio_start', {
            'message': 'Starting audio stream (cached)...',
            'cached': True,  # Flag that this is instant cached audio
            'audio_size': len(audio_bytes)
        }, room=sid)
        
        # Stream audio in chunks (same chunk size as regular streaming for consistency)
        chunk_size = 1024  # 1KB chunks
        chunk_count = 0
        offset = 0
        
        while offset < len(audio_bytes):
            # Check for interruption before sending each chunk
            if sid in active_responses and active_responses[sid]['interrupted']:
                logger.info(f"⚠️ Cached audio streaming interrupted for client {sid} at chunk {chunk_count}")
                await sio.emit('audio_interrupted', {
                    'message': 'Audio playback interrupted',
                    'chunks_sent': chunk_count,
                    'cached': True
                }, room=sid)
                return
            
            # Extract chunk
            audio_chunk = audio_bytes[offset:offset + chunk_size]
            
            if audio_chunk:
                # Encode audio chunk as base64 for transmission
                audio_b64 = base64.b64encode(audio_chunk).decode('utf-8')
                
                await sio.emit('audio_chunk', {
                    'data': audio_b64,
                    'chunk_id': chunk_count,
                    'format': 'mp3',
                    'cached': True  # Flag that this is cached
                }, room=sid)
                
                chunk_count += 1
                offset += chunk_size
        
        # Only send completion if not interrupted
        if sid in active_responses and not active_responses[sid]['interrupted']:
            # Signal end of audio stream
            await sio.emit('audio_end', {
                'message': 'Audio stream completed (cached)',
                'total_chunks': chunk_count,
                'cached': True
            }, room=sid)
            
            logger.info(f"⚡ INSTANT cached audio streaming completed for client {sid} ({chunk_count} chunks)")
        
    except asyncio.CancelledError:
        logger.info(f"⚠️ Cached audio streaming cancelled for client {sid}")
        await sio.emit('audio_interrupted', {
            'message': 'Audio playback cancelled',
            'cached': True
        }, room=sid)
        raise
    except Exception as e:
        logger.error(f"Error streaming cached audio to client {sid}: {e}")
        await sio.emit('error', {
            'message': f'Cached audio streaming error: {str(e)}'
        }, room=sid)


# Health check endpoint
async def health(request):
    """Health check endpoint."""
    return web.Response(text='Text-to-Voice Socket.IO Server Running')

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
    """Start the Text-to-Voice Socket.IO server."""
    logger.info(f"🚀 Starting Text-to-Voice Socket.IO Server on {host}:{port}")
    logger.info("💬 Each client gets their own session")
    logger.info("🔊 Audio streams in real-time to browser")
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
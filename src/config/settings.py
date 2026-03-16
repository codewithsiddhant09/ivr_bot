"""
Configuration management for the Chatbot application.
"""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # OpenAI Configuration (required for CrewAI)
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-nano"  # Model for LLM calls
    
    # Redis Configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_decode_responses: bool = True
    redis_cache_db: int = 2  # Separate DB for cache (DB 0 = sessions, DB 2 = cache)
    
    # ChromaDB Configuration
    chromadb_persist_directory: str = "./chroma_db"
    chromadb_collection_name: str = "privacy_policy_docs"
    
    # Session Configuration
    session_timeout: int = 3600  # 1 hour in seconds
    
    # Embedding Configuration
    embedding_model: str = "all-MiniLM-L6-v2"
    
    # Chunking Configuration
    chunk_size: int = 300
    chunk_overlap: int = 100
    
    # Data Configuration
    data_file_path: str = "./data/info.txt"
    
    # Reranking Configuration
    enable_reranking: bool = True
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L6-v2"
    rerank_top_k: int = 5  # Number of documents to return after reranking
    rerank_candidates: int = 8  # Reduced from 15 to 8 for faster reranking (~0.5-0.8s instead of 1-1.5s)
    
    # MongoDB Configuration
    mongodb_uri: str = ""
    mongodb_database: str = "voicechatbot"
    
    
    # AWS Polly Configuration (TTS)
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    polly_voice_id: str = "Salli"  # Default voice
    polly_output_format: str = "mp3"

    # ElevenLabs Configuration (TTS)
    eleven_labs_api_key: str = ""
    eleven_labs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"
    eleven_labs_model_id: str = "eleven_turbo_v2"
    eleven_labs_output_format: str = "mp3_22050_32"

    # TTS engine selection: "elevenlabs" or "polly"
    # Change TTS_ENGINE (or TTS_PROVIDER) in .env to switch providers at runtime.
    tts_engine: str = "elevenlabs"
    tts_provider: str = "elevenlabs"  # alias — whichever is set wins

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }
    
    @field_validator('openai_api_key')
    @classmethod
    def validate_openai_key(cls, v):
        if not v:
            # Try to get from environment with different approaches
            v = os.getenv('OPENAI_API_KEY', '').strip('"\'')
            if not v:
                # Try reading directly from .env file
                env_file_path = Path(".env")
                if env_file_path.exists():
                    try:
                        with open(env_file_path, 'r') as f:
                            for line in f:
                                if line.startswith('OPENAI_API_KEY='):
                                    v = line.split('=', 1)[1].strip().strip('"\'')
                                    break
                    except Exception:
                        pass
        
        if not v:
            raise ValueError(
                "OpenAI API key is required. Please set OPENAI_API_KEY environment variable or in .env file"
            )
        return v.strip('"\'')


def get_config() -> Settings:
    """Get application configuration."""
    try:
        return Settings()
    except Exception as e:
        # If config creation fails, try to load environment manually
        import os
        from pathlib import Path
        
        # Try to load from .env file
        env_file = Path(".env")
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    if '=' in line and not line.startswith('#'):
                        key, value = line.strip().split('=', 1)
                        os.environ[key] = value.strip('"\'')
        
        # Try creating settings again
        return Settings()


# Global configuration instance
try:
    config = get_config()
except Exception as e:
    print(f"Warning: Config initialization failed: {e}")
    print("Please ensure your .env file contains OPENAI_API_KEY")
    # Create a minimal config for error cases
    import sys
    from types import SimpleNamespace
    config = SimpleNamespace()
    config.openai_api_key = ""
    config.data_file_path = "./data/info.txt"
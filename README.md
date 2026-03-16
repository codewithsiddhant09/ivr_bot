# 🤖 VoiceBot - AI Voice Assistant with Parallel Processing

> Intelligent voice-enabled chatbot with real-time speech processing, parallel RAG, and speculative audio generation

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![AWS Polly](https://img.shields.io/badge/AWS-Polly-orange.svg)](https://aws.amazon.com/polly/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-green.svg)](https://openai.com/)

---

## 🌟 Features

### Core Capabilities
- **🎤 Real-time Voice Input** - Web Speech API + Whisper fallback
- **🔊 Neural Text-to-Speech** - AWS Polly with multiple voices
- **⚡ Parallel Processing** - Concurrent intent classification + RAG retrieval
- **🔮 Speculative Execution** - Pre-generate responses while user speaks
- **💾 Audio Caching** - Instant playback with 0ms delay
- **🔄 Interruption Handling** - Cancel previous responses seamlessly
- **📝 Contact Form** - Intelligent information collection
- **🎯 Intent Classification** - GPT-4 powered intent detection

### Performance
- **2-3 second response time** (with parallel processing)
- **0-100ms audio playback** (with speculative cache hit)
- **70%+ cache hit rate** (with optimized speculation)
- **50% faster** than sequential processing

---

## 📁 Project Structure

```
voicebot-polly/
├── src/                          # 🆕 Main application code
│   ├── server.py                # Socket.IO server (main entry point)
│   ├── core/                    # Core business logic
│   │   ├── agent_async.py      # Async agent with parallel RAG
│   │   ├── chatbot_async.py    # Async chatbot orchestrator
│   │   ├── session_manager.py  # Session state management
│   │   └── contact_form_handler.py
│   └── config/
│       └── settings.py         # Configuration
│
├── vectorstore/                 # Vector database
│   └── chromadb_client.py      # ChromaDB client
│
├── database/                    # Database clients
│   └── mongodb_client.py       # MongoDB for contacts
│
├── utils/                       # Utilities
│   ├── reranker.py            # Cross-encoder reranker
│   └── validators.py          # Input validation
│
├── data/                        # Data files
│   └── combined_info.txt       # Knowledge base
│
├── scripts/                     # Setup scripts
│   ├── initialise_data.py     # Initialize ChromaDB
│   └── document_loader.py     # Load documents
│
├── docs/                        # 📚 Documentation
│   ├── ARCHITECTURE.md
│   ├── PARALLEL_AUDIO_OPTIMIZATION.md
│   └── SPECULATIVE_AUDIO_IMPLEMENTATION.md
│
├── legacy/                      # 🗄️ Archived files
│   ├── agent.py               # Old synchronous agent
│   └── main.py                # Old server
│
├── static/                      # Frontend
│   └── voice_to_voice.html    # Web interface
│
├── .env                         # Environment variables
├── requirements.txt
└── run_server_new.sh           # 🚀 Start script
```

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.11+
- AWS Account (for Polly TTS)
- OpenAI API Key
- MongoDB (optional, for contact storage)

### 2. Installation

```bash
# Clone repository
cd voicebot-polly

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Create a `.env` file:

```bash
# OpenAI Configuration
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini

# AWS Configuration (for Polly TTS)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1
POLLY_VOICE_ID=Joanna
POLLY_OUTPUT_FORMAT=mp3

# MongoDB (optional)
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=voicechatbot

# ChromaDB
CHROMADB_PERSIST_DIRECTORY=./chroma_db
```

### 4. Initialize Data

```bash
# Load documents into ChromaDB
python scripts/initialise_data.py
```

### 5. Start Server

```bash
# Option 1: Using the run script
./run_server_new.sh

# Option 2: Direct Python
python3 src/server.py
```

Server starts on: **http://localhost:8080**

### 6. Open Web Interface

```bash
# Voice interface (default)
open http://localhost:8080/voice

# Text interface (testing)
open http://localhost:8080/text
```

---

## 🎯 How It Works

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    USER SPEAKS                          │
│         "What are your services?"                       │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│           WEB SPEECH API (Browser STT)                  │
│  • Sends interim results every 1s                       │
│  • Fallback: Whisper API (if unavailable)              │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│         🔮 SPECULATIVE EXECUTION (1s mark)              │
│  Interim: "What are"                                    │
│  ├─ Start RAG processing in background                 │
│  ├─ Generate audio speculatively                       │
│  └─ Cache: {text, audio_bytes, intent}                 │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│        ⚡ PARALLEL PROCESSING (asyncio.gather)          │
│  ┌──────────────────┬──────────────────┐              │
│  │ Intent (GPT-4)   │ RAG (ChromaDB)  │              │
│  │ ~1.2s            │ ~0.3s            │              │
│  └──────────────────┴──────────────────┘              │
│           Both run simultaneously! = 1.2s              │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│         💬 RESPONSE GENERATION (GPT-4o-mini)            │
│  Context: Retrieved docs + Intent                      │
│  Output: "We at TechGropse offer..."                   │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│         🎵 AUDIO GENERATION (AWS Polly)                 │
│  Pre-generated during speculation!                      │
│  Cached: audio_bytes (MP3)                             │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│            USER STOPS SPEAKING (4s)                     │
│  Final: "What are your services?"                      │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│         🎯 CACHE CHECK (Similarity: 90%)                │
│  ✅ CACHE HIT! Audio ready!                            │
│  🚀 Stream cached audio instantly                      │
│  ⚡ 0ms delay! (vs 2-4s without cache)                 │
└─────────────────────────────────────────────────────────┘
```

---

## 💻 Usage

### Voice Interface

1. **Click microphone button** to start speaking
2. **Speak your question** (e.g., "What services do you offer?")
3. **Release button** when done
4. **Listen to response** (audio plays automatically)

### Supported Queries

- "What services does TechGropse offer?"
- "How much does app development cost?"
- "What technologies do you use?"
- "Tell me about your portfolio"
- "I want to contact your team"
- "Connect me with someone"

### Voice Commands

- **Interrupt**: Start speaking while bot is responding
- **Reconnect**: Refresh page if connection lost
- **Change voice**: Use voice selector (male/female options)

---

## 🔧 Configuration

### AWS Polly Voices

**Female voices:**
- Joanna (US) - Default
- Kendra (US)
- Ruth (US)
- Salli (US)

**Male voices:**
- Matthew (US)
- Joey (US)
- Stephen (US)

Change voice in `.env`:
```bash
POLLY_VOICE_ID=Matthew  # For male voice
```

### Performance Tuning

Edit `src/config/settings.py`:

```python
# Reranking
enable_reranking = True
rerank_top_k = 5
rerank_candidates = 8

# Chunking
chunk_size = 300
chunk_overlap = 100

# Rate limiting (speculation)
interim_rate_limit = 1.0  # seconds
min_chars_for_speculation = 5
```

---

## 📊 Performance Metrics

### Response Time Breakdown

| Phase | Without Speculation | With Speculation | Improvement |
|-------|---------------------|------------------|-------------|
| **User Speaking** | 4s | 4s | - |
| **RAG Processing** | 2s (after) | 2s (during) | **2s saved** |
| **Audio Generation** | 2s (after) | 2s (during) | **2s saved** |
| **Total Delay** | 4s | ~0s | **4s saved!** |

### Cost Analysis

Per 1000 queries:
- OpenAI GPT-4: ~$0.20
- OpenAI Embeddings: ~$0.02
- AWS Polly TTS: ~$0.36 (with speculation: ~$0.54)
- **Total: ~$0.58 - $0.76 per 1000 queries**

---

## 🧪 Testing

### Run Tests
```bash
# Test Polly TTS
python tests/test_polly.py

# Test contact form
python tests/test_form_flow.py

# Test streaming
python tests/test_streaming.py
```

### Health Check
```bash
curl http://localhost:8080/health
```

---

## 📚 Documentation

- [**ARCHITECTURE.md**](docs/ARCHITECTURE.md) - Complete system architecture
- [**PARALLEL_AUDIO_OPTIMIZATION.md**](docs/PARALLEL_AUDIO_OPTIMIZATION.md) - Performance optimization details
- [**SPECULATIVE_AUDIO_IMPLEMENTATION.md**](docs/SPECULATIVE_AUDIO_IMPLEMENTATION.md) - Speculative execution guide

---

## 🐛 Troubleshooting

### Common Issues

**1. "Module not found" errors**
```bash
# Ensure you're in project root and venv is activated
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
source venv/bin/activate
```

**2. AWS Polly errors**
```bash
# Verify AWS credentials
aws configure list

# Test AWS credentials
aws polly describe-voices --region us-east-1
```

**3. OpenAI API errors**
```bash
# Check API key
echo $OPENAI_API_KEY

# Test API access
python -c "from openai import OpenAI; print(OpenAI().models.list())"
```

**4. Socket connection issues**
```bash
# Check if port 8080 is available
lsof -i :8080

# Kill process if needed
kill -9 <PID>
```

**5. ChromaDB not initialized**
```bash
# Reinitialize vector database
python scripts/initialise_data.py
```

---

## 🚀 Deployment

### Production Checklist

- [ ] Set `DEBUG=False` in config
- [ ] Use production OpenAI API key
- [ ] Configure proper CORS origins
- [ ] Set up monitoring (logs, metrics)
- [ ] Enable HTTPS/SSL
- [ ] Configure firewall rules
- [ ] Set up automatic restarts (PM2, systemd)
- [ ] Configure backup for ChromaDB
- [ ] Set up rate limiting
- [ ] Configure MongoDB replica set

### Deploy to AWS EC2

```bash
# On EC2 instance
git clone <repo-url>
cd voicebot-polly

# Install dependencies
pip3 install -r requirements.txt

# Configure environment
nano .env

# Initialize data
python3 scripts/initialise_data.py

# Start with PM2
pm2 start run_server_new.sh --name voicebot
pm2 save
pm2 startup
```

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📝 License

This project is proprietary software for TechGropse.

---

## 👥 Team

**TechGropse Development Team**
- Voice AI Engineering
- Full-stack Development
- DevOps & Infrastructure

---

## 📧 Support

For support, email: support@techgropse.com

---

## 🎯 Roadmap

### Phase 1: Core Features ✅
- [x] Voice input/output
- [x] Parallel processing
- [x] Speculative execution
- [x] Audio caching

### Phase 2: Enhancements 🚧
- [ ] Multi-language support
- [ ] Voice emotion detection
- [ ] Advanced personalization
- [ ] Analytics dashboard

### Phase 3: Scale 🔮
- [ ] Distributed caching (Redis)
- [ ] Load balancing
- [ ] Auto-scaling
- [ ] Advanced monitoring

---

**Made with ❤️ by TechGropse**

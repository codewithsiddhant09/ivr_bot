#!/bin/bash

# VoiceBot Server Startup Script (Restructured)
# Runs the Socket.IO server with proper Python path

# Set the working directory to the project root
cd "$(dirname "$0")"

# Add the project root to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

echo "🚀 Starting VoiceBot Server (Restructured)"
echo "📁 Working directory: $(pwd)"
echo "🐍 Python path: $PYTHONPATH"
echo ""

# Run the server from src/
python3 src/server.py

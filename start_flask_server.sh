#!/bin/bash

# Start TANGO Flask Server
# This script starts the Flask server that integrates with React Flow

echo "🚀 Starting TANGO Flask Server..."

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "❌ ERROR: uv not found. Install from https://docs.astral.sh/uv/"
    exit 1
fi

# Change to TANGO directory
cd "$(dirname "$0")"

# Sync dependencies (installs tango-app group which includes PyQt5)
echo "📦 Syncing dependencies with uv..."
uv sync --group tango-app

echo "🔧 Starting Flask server on localhost:8000..."
echo "   This server will be accessible through Nginx at: https://tango.app.local/tango/"
echo "   Press Ctrl+C to stop the server"
echo ""

# Start the Flask server (tango-app group includes PyQt5 for GUI addons)
uv run --group tango-app python tango_flask_server.py
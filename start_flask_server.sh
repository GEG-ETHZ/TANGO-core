#!/bin/bash

# Start TANGO Flask Server
# This script starts the Flask server that integrates with React Flow

echo "🚀 Starting TANGO Flask Server..."

# Check if pixi is available
if ! command -v pixi &> /dev/null; then
    echo "❌ ERROR: Pixi not found. Please ensure pixi is installed and in PATH."
    exit 1
fi

# Change to TANGO directory
cd "$(dirname "$0")"

echo "📦 Using pixi environment (dependencies are automatically managed)"
echo "🔧 Starting Flask server on localhost:8000..."
echo "   This server will be accessible through Nginx at: https://tango.app.local/tango/"
echo "   Press Ctrl+C to stop the server"
echo ""

# Start the Flask server using pixi
pixi run python tango_flask_server.py 
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

# Check if pixi environment is installed, if not install it
if [ ! -d ".pixi" ]; then
    echo "📦 Pixi environment not found. Installing dependencies..."
    pixi install
    echo "✅ Dependencies installed!"
fi

echo "📦 Using pixi environment (dependencies are automatically managed)"
echo "🔧 Starting Flask server on localhost:8000..."
echo "   This server will be accessible through Nginx at: https://tango.app.local/tango/"
echo "   Press Ctrl+C to stop the server"
echo ""

# Start the Flask server using pixi with tango-app environment (needed for PyQt5/GUI)
pixi run -e tango-app python tango_flask_server.py 
#!/bin/bash

# Start TANGO Flask Server
# This script starts the Flask server that integrates with React Flow

echo "🚀 Starting TANGO Flask Server..."

# Activate conda environment
source /opt/conda/etc/profile.d/conda.sh
conda activate tango_env

# Install Flask dependencies if not already installed
echo "📦 Checking Flask dependencies..."
pip install -r flask_requirements.txt

# Change to TANGO directory
cd "$(dirname "$0")"

echo "🔧 Starting Flask server on localhost:8000..."
echo "   This server will be accessible through Nginx at: https://tango.app.local/tango/"
echo "   Press Ctrl+C to stop the server"
echo ""

# Start the Flask server
python tango_flask_server.py 
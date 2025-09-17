#!/usr/bin/env python3
"""
TANGO Flask Server for React Flow Integration
Runs TANGO simulations when triggered from the React app
"""

import os
import sys
import subprocess
import json
import time
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

# Add TANGO source to path
TANGO_SRC = Path(__file__).parent / "src"
sys.path.append(str(TANGO_SRC))

app = Flask(__name__)
CORS(app, origins=["https://tango.app.local"], supports_credentials=True)

# Global variable to track simulation status
simulation_status = {
    "running": False,
    "progress": 0,
    "message": "",
    "results": None,
    "error": None
}

def run_tango_simulation(config_file="/home/TANGO/examples/flexible_SF_cogeneration_e.yml", parameter_overrides=None, user_id=None):
    """
    Run TANGO simulation using the existing CLI
    """
    global simulation_status
    
    try:
        simulation_status["running"] = True
        simulation_status["progress"] = 0
        simulation_status["message"] = "Starting TANGO simulation..."
        simulation_status["error"] = None
        
        # Build the command (same as manual CLI)
        cmd = ["python", "tango_cli.py", "-f", config_file]
        
        # Add parameter overrides if provided
        if parameter_overrides:
            for key, value in parameter_overrides.items():
                cmd.extend(["--param", f"{key}={value}"])

        if user_id:
            cmd.extend(["--user-id", str(user_id)])
            print(f"👤 Running simulation for user: {user_id}")
        
        print(f"🚀 Running TANGO command: {' '.join(cmd)}")
        
        # Change to the tango directory (same as manual execution)
        tango_dir = TANGO_SRC / "tango"
        os.chdir(tango_dir)
        
        # Run the simulation (same as manual execution)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=tango_dir
        )
        
        # Update progress
        simulation_status["progress"] = 25
        simulation_status["message"] = "TANGO simulation in progress..."
        
        # Wait for completion
        stdout, stderr = process.communicate()
        
        if process.returncode == 0:
            simulation_status["progress"] = 100
            simulation_status["message"] = "TANGO simulation completed successfully!"
            simulation_status["results"] = {
                "stdout": stdout,
                "stderr": stderr,
                "return_code": process.returncode
            }
            print("✅ TANGO simulation completed successfully")
        else:
            error_details = stderr.strip() if stderr.strip() else f"Simulation failed with return code {process.returncode}"
            simulation_status["error"] = error_details
            simulation_status["message"] = "TANGO simulation failed"
            print(f"❌ TANGO simulation failed: {error_details}")
            
    except Exception as e:
        simulation_status["error"] = str(e)
        simulation_status["message"] = f"Error: {str(e)}"
        print(f"❌ Error running TANGO simulation: {e}")
    finally:
        simulation_status["running"] = False

@app.route('/status', methods=['GET'])
def get_simulation_status():
    """Get current simulation status"""
    return jsonify(simulation_status)

@app.route('/run', methods=['POST'])
def run_simulation():
    """Start a new TANGO simulation"""
    global simulation_status
    
    if simulation_status["running"]:
        return jsonify({
            "success": False,
            "message": "Simulation already running"
        }), 400
    
    try:
        data = request.get_json() or {}
        
        # Default configuration file (same as manual execution)
        config_file = data.get('config_file', '/home/TANGO/examples/flexible_SF_cogeneration_e.yml')
        
        # Parameter overrides from the request
        parameter_overrides = data.get('parameter_overrides', {})
        
        # User ID from the request
        user_id = data.get('user_id', None)
        
        print(f"🎯 Starting TANGO simulation with config: {config_file}")
        print(f"📝 Parameter overrides: {parameter_overrides}")
        print(f"👤 User ID: {user_id}")
        
        # Start simulation in background thread
        import threading
        thread = threading.Thread(
            target=run_tango_simulation,
            args=(config_file, parameter_overrides, user_id)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "success": True,
            "message": "TANGO simulation started",
            "config_file": config_file,
            "parameter_overrides": parameter_overrides
        })
        
    except Exception as e:
        print(f"❌ Error starting simulation: {e}")
        return jsonify({
            "success": False,
            "message": f"Error: {str(e)}"
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "TANGO Flask Server",
        "timestamp": time.time()
    })

if __name__ == '__main__':
    print("🚀 Starting TANGO Flask Server...")
    print("   This server will run TANGO simulations when triggered from React")
    print("   Accessible through Nginx proxy at: https://tango.app.local/tango/")
    
    # Run the Flask app on localhost (will be proxied by Nginx)
    app.run(
        host='localhost',  # Only accessible through Nginx proxy
        port=8000,         # Will be proxied to /tango/ route
        debug=False,        # Production mode
        threaded=True       # Handle multiple requests
    ) 
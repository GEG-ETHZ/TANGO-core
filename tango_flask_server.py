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
import logging
from logging.handlers import RotatingFileHandler

# Configure logging
# Default to WARNING to reduce noise, unless TANGO_DEBUG is set
log_level = logging.INFO if os.environ.get("TANGO_DEBUG") else logging.WARNING

# All runtime artifacts live under a single server_output/ directory.
# Runner internally appends "gen_files/" to save_dir, so passing _APP_DIR
# produces:  server_output/gen_files/run_<id>/  (no double-nesting)
_APP_DIR = Path(__file__).parent / "server_output"
LOG_DIR = _APP_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True, parents=True)
_APP_DIR.mkdir(exist_ok=True)  # Runner creates gen_files/ inside here

# Create formatters and handlers
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# File handler with rotation (max 5MB, 1 backup)
file_handler = RotatingFileHandler(LOG_DIR / "tango_server.log", maxBytes=5*1024*1024, backupCount=1)
file_handler.setFormatter(formatter)
file_handler.setLevel(log_level)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(log_level)

# Apply to root logger
root_logger = logging.getLogger()
root_logger.setLevel(log_level)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Specific logger for this module
logger = logging.getLogger(__name__)

# TODO: after setting up flask to use pixi, remove this because pixi properly
# adds TANGO as module in the environment
# Add TANGO source to path
TANGO_SRC = Path(__file__).parent / "src"
sys.path.append(str(TANGO_SRC))

app = Flask(__name__)
CORS(app, origins=["https://tango.app.local"], supports_credentials=True)

# Dictionary to track simulation status per user
simulation_statuses = {}


def run_tango_simulation(
    config_file="/home/TANGO/examples/flexible_SF_cogeneration_e.yml",
    parameter_overrides=None,
    user_id=None,
):
    """
    Run TANGO simulation using the existing CLI
    """
    global simulation_statuses

    try:
        # Status is already set in the /run endpoint

        # Add parameter overrides if provided
        overrides_list = []
        if parameter_overrides:
            for key, value in parameter_overrides.items():
                overrides_list.append(f"{key}={value}")

        if user_id:
            print(f"👤 Running simulation for user: {user_id}")

        print(f"🚀 Running TANGO in-process via Runner")
        
        # Import Runner here to avoid circular dependencies or early init issues
        from tango.runner import Runner

        # Update progress
        simulation_statuses[user_id]["progress"] = 25
        simulation_statuses[user_id]["message"] = "TANGO simulation in progress..."

        # Initialize Runner
        # save_dir=_APP_DIR → Runner appends gen_files/ → tango_app/gen_files/run_<id>/
        runner = Runner(
            input_file=config_file,
            save_dir=_APP_DIR,
            parameter_overrides=overrides_list,
            user_id=user_id,
            log_level=logging.getLevelName(log_level) # Pass the configured level name (WARNING or INFO)
        )
        
        # Execute
        runner.start()

        # Success handling
        simulation_statuses[user_id]["progress"] = 100
        simulation_statuses[user_id]["message"] = (
            "TANGO simulation completed successfully!"
        )
        # We don't have captured stdout/stderr strings anymore, but the logs are in the server console
        simulation_statuses[user_id]["results"] = {
            "stdout": "Check server logs for output",
            "stderr": "",
            "return_code": 0,
        }
        print(f"✅ TANGO simulation completed successfully for user {user_id}")

    except Exception as e:
        error_details = str(e)
        simulation_statuses[user_id]["error"] = error_details
        simulation_statuses[user_id]["message"] = "TANGO simulation failed"
        simulation_statuses[user_id]["running"] = False
        print(f"❌ Error running TANGO simulation for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Ensure running is always set to False when simulation ends
        if user_id in simulation_statuses:
            simulation_statuses[user_id]["running"] = False
            print(f"🔄 Simulation completed for user {user_id}, status reset")


@app.route("/status", methods=["GET"])
def get_simulation_status():
    """Get current simulation status for a specific user"""
    user_id = request.args.get("user_id")

    if not user_id:
        return jsonify(
            {"success": False, "error": "user_id parameter is required"}
        ), 400

    # Return user-specific status or default if user doesn't exist
    status = simulation_statuses.get(
        user_id,
        {
            "running": False,
            "progress": 0,
            "message": "No simulation running",
            "results": None,
            "error": None,
        },
    )

    return jsonify(status)


@app.route("/reset", methods=["POST"])
def reset_simulation():
    """Reset simulation status for a specific user"""
    global simulation_statuses

    try:
        data = request.get_json() or {}
        user_id = data.get("user_id")

        if not user_id:
            return jsonify({"success": False, "error": "user_id is required"}), 400

        if user_id in simulation_statuses:
            simulation_statuses[user_id] = {
                "running": False,
                "progress": 0,
                "message": "",
                "results": None,
                "error": None,
            }
            print(f"🔄 Reset simulation status for user {user_id}")
            return jsonify(
                {
                    "success": True,
                    "message": f"Simulation status reset for user {user_id}",
                }
            )
        else:
            return jsonify(
                {
                    "success": True,
                    "message": f"No simulation status found for user {user_id}",
                }
            )

    except Exception as e:
        print(f"❌ Error resetting simulation status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/run", methods=["POST"])
def run_simulation():
    """Start a new TANGO simulation"""
    global simulation_statuses

    try:
        data = request.get_json() or {}
        user_id = data.get("user_id")

        if not user_id:
            return jsonify({"success": False, "error": "user_id is required"}), 400

        # Check if this user already has a simulation running
        if user_id in simulation_statuses and simulation_statuses[user_id]["running"]:
            print(f"❌ User {user_id} already has a simulation running")
            return jsonify(
                {
                    "success": False,
                    "message": f"Simulation already running for user {user_id}",
                }
            ), 400

        # Check if user recently completed a simulation (prevent rapid successive requests)
        if user_id in simulation_statuses:
            last_message = simulation_statuses[user_id].get("message", "")
            if "completed successfully" in last_message or "failed" in last_message:
                # Clear the completed status to allow new simulation
                simulation_statuses[user_id]["message"] = ""
                simulation_statuses[user_id]["error"] = None
                simulation_statuses[user_id]["results"] = None

        # Initialize user status if not exists
        if user_id not in simulation_statuses:
            simulation_statuses[user_id] = {
                "running": False,
                "progress": 0,
                "message": "",
                "results": None,
                "error": None,
            }

        # Set running to True immediately to prevent race conditions
        simulation_statuses[user_id]["running"] = True
        simulation_statuses[user_id]["progress"] = 0
        simulation_statuses[user_id]["message"] = "Starting TANGO simulation..."
        simulation_statuses[user_id]["error"] = None
        simulation_statuses[user_id]["results"] = None

        print(f"✅ User {user_id} simulation status set to running")

        # Default configuration file (same as manual execution)
        config_file = data.get(
            "config_file", "/home/TANGO/examples/flexible_SF_cogeneration_e.yml"
        )

        # Parameter overrides from the request
        parameter_overrides = data.get("parameter_overrides", {})

        print(f"🎯 Starting TANGO simulation with config: {config_file}")
        print(f"📝 Parameter overrides: {parameter_overrides}")
        print(f"👤 User ID: {user_id}")

        # Start simulation in background thread
        import threading

        thread = threading.Thread(
            target=run_tango_simulation,
            args=(config_file, parameter_overrides, user_id),
        )
        thread.daemon = True
        thread.start()

        return jsonify(
            {
                "success": True,
                "message": "TANGO simulation started",
                "config_file": config_file,
                "parameter_overrides": parameter_overrides,
            }
        )

    except Exception as e:
        print(f"❌ Error starting simulation: {e}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify(
        {"status": "healthy", "service": "TANGO Flask Server", "timestamp": time.time()}
    )


if __name__ == "__main__":
    print("🚀 Starting TANGO Flask Server...")
    print("   This server will run TANGO simulations when triggered from React")
    print("   Accessible through Nginx proxy at: https://tango.app.local/tango/")

    # Run the Flask app on localhost (will be proxied by Nginx)
    app.run(
        host="localhost",  # Only accessible through Nginx proxy
        port=8000,  # Will be proxied to /tango/ route
        debug=False,  # Production mode
        threaded=True,  # Handle multiple requests
    )

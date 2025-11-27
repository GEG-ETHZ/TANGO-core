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

        # Build the command using pixi run -e tango-app (needed for PyQt5/GUI dependencies)
        cmd = [
            "pixi",
            "run",
            "-e",
            "tango-app",
            "python",
            "tango_cli.py",
            "-f",
            config_file,
        ]

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
            cwd=tango_dir,
        )

        # Update progress
        simulation_statuses[user_id]["progress"] = 25
        simulation_statuses[user_id]["message"] = "TANGO simulation in progress..."

        # Wait for completion
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            simulation_statuses[user_id]["progress"] = 100
            simulation_statuses[user_id]["message"] = (
                "TANGO simulation completed successfully!"
            )
            simulation_statuses[user_id]["results"] = {
                "stdout": stdout,
                "stderr": stderr,
                "return_code": process.returncode,
            }
            print(f"✅ TANGO simulation completed successfully for user {user_id}")
        else:
            error_details = (
                stderr.strip()
                if stderr.strip()
                else f"Simulation failed with return code {process.returncode}"
            )
            simulation_statuses[user_id]["error"] = error_details
            simulation_statuses[user_id]["message"] = "TANGO simulation failed"
            print(f"❌ TANGO simulation failed for user {user_id}: {error_details}")

    except Exception as e:
        simulation_statuses[user_id]["error"] = str(e)
        simulation_statuses[user_id]["message"] = f"Error: {str(e)}"
        simulation_statuses[user_id]["running"] = False
        print(f"❌ Error running TANGO simulation for user {user_id}: {e}")
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

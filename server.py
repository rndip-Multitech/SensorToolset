"""
RadioBridge Tools Server
This file is used to create a Flask server to serve the RadioBridge Sensor Configuration Tool.
This will serve all of the HTML pages for configuring RadioBridge sensors.
"""

"""
Importing the required libraries.
"""
from flask import Flask, send_from_directory, send_file, jsonify, request
import json
import logging
import os
import argparse

from mqtt_utils_rbt import connect_to_broker, get_sensors, send_downlink

"""
Creating the Flask app and setting the template and static directories.
"""
app = Flask(__name__, static_folder='.', static_url_path='')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
config = {
    'host': '0.0.0.0',
    'port': 5000,
    'debug': False
}


def load_config(config_file):
    """Load configuration from JSON file if it exists."""
    global config
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                file_config = json.load(f)
                config.update(file_config)
                logger.info(f"Loaded configuration from {config_file}")
        except Exception as e:
            logger.warning(f"Failed to load config file {config_file}: {e}")
    else:
        logger.info(f"Config file {config_file} not found, using defaults")


@app.route('/')
def index():
    """Serve the main index page."""
    return send_file('index.html')


@app.route('/downlinks')
def downlinks_page():
    """Serve the downlinks page."""
    return send_file('downlinks.html')


@app.route('/connect', methods=['POST'])
def connect_route():
    """
    Connect to the LoRa Network Server MQTT broker.

    Expects JSON: {"broker": "...", "port": 1883, "topic": "lora/+/up"}
    When running on the gateway, broker will usually be "localhost".
    """
    data = request.get_json() or {}
    broker = data.get('broker', 'localhost')
    port = int(data.get('port', 1883))
    topic = data.get('topic', 'lora/+/up')

    try:
        connect_to_broker(broker=broker, port=port, topic=topic)
        logger.info(f"Connected to MQTT broker {broker}:{port}, topic {topic}")
        return jsonify({"message": "Connected to MQTT broker"}), 200
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to connect to MQTT broker: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/get_sensors', methods=['GET'])
def get_sensors_route():
    """Return the list of discovered sensors from MQTT uplinks."""
    sensors = get_sensors()
    return jsonify({"sensors": sensors}), 200


@app.route('/send_downlink', methods=['POST'])
def send_downlink_route():
    """
    Send a downlink to a selected sensor via MQTT.

    Expects JSON payload matching the structure built in
    `NetworkDashboard-0.1/static/js/downlinks.js`.
    """
    data = request.get_json() or {}
    result = send_downlink(data)
    status = 200 if "message" in result else 400
    return jsonify(result), status


@app.route('/<path:path>')
def serve_static(path):
    """Serve static files from the root directory and subdirectories."""
    # Security: prevent directory traversal
    if '..' in path or path.startswith('/'):
        return "Invalid path", 403
    
    # Check if the file exists
    if os.path.isfile(path):
        # Get the directory and filename
        directory = os.path.dirname(path) if os.path.dirname(path) else '.'
        filename = os.path.basename(path)
        return send_from_directory(directory, filename)
    
    # If it's a directory, try to serve index.html from it
    if os.path.isdir(path):
        index_path = os.path.join(path, 'index.html')
        if os.path.isfile(index_path):
            return send_from_directory(path, 'index.html')
        # If no index.html, try to find an HTML file with the directory name
        html_files = [f for f in os.listdir(path) if f.endswith('.html')]
        if html_files:
            # Try to find a file matching the directory name
            dir_name = os.path.basename(path.rstrip('/'))
            for html_file in html_files:
                if html_file.startswith(dir_name) or html_file == 'index.html':
                    return send_from_directory(path, html_file)
            # If no match, serve the first HTML file
            return send_from_directory(path, html_files[0])
    
    # Default: try to serve the file anyway (for relative paths)
    try:
        directory = os.path.dirname(path) if os.path.dirname(path) else '.'
        filename = os.path.basename(path)
        return send_from_directory(directory, filename)
    except Exception as e:
        logger.warning(f"Failed to serve {path}: {e}")
        return "File not found", 404


@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors."""
    return "Page not found", 404


"""
Following used to run the Flask app.
"""
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='RadioBridge Tools Server')
    parser.add_argument('--cfgfile', type=str, help='Path to configuration file')
    parser.add_argument('--logfile', type=str, help='Path to log file')
    parser.add_argument('--host', type=str, default=config['host'], help='Host to bind to')
    parser.add_argument('--port', type=int, default=config['port'], help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Load config file if provided
    if args.cfgfile:
        load_config(args.cfgfile)
    
    # Override with command line arguments
    if args.host:
        config['host'] = args.host
    if args.port:
        config['port'] = args.port
    if args.debug:
        config['debug'] = True
    
    # Setup logging to file if specified
    if args.logfile:
        file_handler = logging.FileHandler(args.logfile)
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    logger.info(f"Starting RadioBridge Tools server on {config['host']}:{config['port']}")
    app.run(host=config['host'], port=config['port'], debug=config['debug'])

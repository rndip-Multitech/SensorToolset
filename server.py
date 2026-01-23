"""
RadioBridge Tools Server
This file is used to create a Flask server to serve the RadioBridge Sensor Configuration Tool.
This will serve all of the HTML pages for configuring RadioBridge sensors.
"""

"""
Importing the required libraries.
"""
from flask import Flask, send_from_directory, send_file, jsonify, request
from werkzeug.utils import secure_filename
import json
import logging
import os
import argparse

"""
Creating the Flask app and setting the template and static directories.
"""
app = Flask(__name__, static_folder='.', static_url_path='')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom decoder storage (served as static files)
CUSTOM_DECODER_DIR = os.path.join(
    os.path.dirname(__file__),
    "NetworkDashboard-0.1",
    "static",
    "js",
    "decoders",
    "custom",
)
os.makedirs(CUSTOM_DECODER_DIR, exist_ok=True)


def _is_safe_decoder_filename(name: str) -> bool:
    """Allow only simple .js filenames (no paths)."""
    if not name or not isinstance(name, str):
        return False
    if "/" in name or "\\" in name:
        return False
    if not name.lower().endswith(".js"):
        return False
    return True


def _decoder_file_url(filename: str) -> str:
    return f"/NetworkDashboard-0.1/static/js/decoders/custom/{filename}"

# Try to import MQTT utilities - gracefully handle if paho-mqtt isn't installed
try:
    from mqtt_utils_rbt import connect_to_broker, get_sensors, send_downlink, get_messages
    MQTT_AVAILABLE = True
    logger.info("MQTT utilities loaded successfully")
except ImportError as e:
    logger.warning(f"MQTT utilities not available: {e}. MQTT features will be disabled.")
    MQTT_AVAILABLE = False
    
    # Define stub functions so routes don't fail
    def connect_to_broker(broker, port, topic):
        return {"error": "MQTT not available. Please install paho-mqtt."}, 500
    
    def get_sensors():
        return {"sensors": []}
    
    def get_messages():
        return []
    
    def send_downlink(data, broker_ip):
        return {"error": "MQTT not available. Please install paho-mqtt."}, 500

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


@app.route('/tools_downlinks')
def tools_downlinks_page():
    """Serve the generic downlink tools page."""
    return send_file('tools_downlinks.html')


@app.route('/sensors')
def sensors_page():
    """Serve the sensor monitoring page."""
    return send_file('sensors.html')


@app.route('/RBS30X-ABM/rbs30x-abm.html')
@app.route('/RBS30x-ABM/rbs30x-abm.html')
@app.route('/rbs30x-abm.html')
def abm_page():
    """Serve the RBS30X-ABM sensor configuration page."""
    return send_file('RBS30X-ABM/rbs30x-abm.html')


@app.route('/RBS30X-ABM/<path:filename>')
@app.route('/RBS30x-ABM/<path:filename>')
def abm_static(filename):
    """Serve static files from RBS30X-ABM directory (images, CSS, JS)."""
    # Security: prevent directory traversal
    if '..' in filename or filename.startswith('/'):
        return "Invalid path", 403
    return send_from_directory('RBS30X-ABM', filename)


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


@app.route('/messages', methods=['GET'])
def get_messages_route():
    """Return the buffered MQTT messages, optionally filtered by DevEUI."""
    try:
        from mqtt_utils_rbt import get_messages
        filter_deveui = request.args.get('filter', '').strip()
        messages = get_messages()
        
        # Filter by DevEUI if provided
        if filter_deveui:
            filtered_messages = []
            for msg in messages:
                if msg.get('type') == 'json' and 'data' in msg:
                    deveui = msg['data'].get('deveui', '')
                    if filter_deveui.lower() in deveui.lower():
                        filtered_messages.append(msg)
            messages = filtered_messages
        
        return jsonify({"messages": messages}), 200
    except ImportError:
        return jsonify({"messages": [], "error": "MQTT utilities not available"}), 200
    except Exception as e:
        logger.error(f"Error fetching messages: {e}")
        return jsonify({"messages": [], "error": str(e)}), 500


@app.route('/api/decoders/list', methods=['GET'])
def list_decoders_route():
    """List uploaded custom decoder JS files."""
    files = []
    try:
        for fname in sorted(os.listdir(CUSTOM_DECODER_DIR)):
            if not _is_safe_decoder_filename(fname):
                continue
            fpath = os.path.join(CUSTOM_DECODER_DIR, fname)
            if not os.path.isfile(fpath):
                continue
            stat = os.stat(fpath)
            files.append(
                {
                    "name": fname,
                    "url": _decoder_file_url(fname),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                }
            )
        return jsonify({"files": files}), 200
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error listing decoders: {e}")
        return jsonify({"files": [], "error": str(e)}), 500


@app.route('/api/decoders/upload', methods=['POST'])
def upload_decoder_route():
    """Upload a decoder JS file (multipart form: file)."""
    try:
        if "file" not in request.files:
            return jsonify({"error": "Missing file"}), 400
        file = request.files["file"]
        if not file or not file.filename:
            return jsonify({"error": "Empty filename"}), 400

        fname = secure_filename(file.filename)
        if not _is_safe_decoder_filename(fname):
            return jsonify({"error": "Only .js files are allowed"}), 400

        dest = os.path.join(CUSTOM_DECODER_DIR, fname)
        file.save(dest)
        return jsonify({"name": fname, "url": _decoder_file_url(fname)}), 200
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error uploading decoder: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/decoders/save', methods=['POST'])
def save_decoder_route():
    """Save a decoder JS from text (JSON: {name, content})."""
    try:
        data = request.get_json() or {}
        name = secure_filename(str(data.get("name", "")).strip())
        content = str(data.get("content", ""))
        if not _is_safe_decoder_filename(name):
            return jsonify({"error": "Invalid filename (must end with .js, no paths)"}), 400
        if not content.strip():
            return jsonify({"error": "Empty content"}), 400

        dest = os.path.join(CUSTOM_DECODER_DIR, name)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(content)
            if not content.endswith("\n"):
                f.write("\n")
        return jsonify({"name": name, "url": _decoder_file_url(name)}), 200
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error saving decoder: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/decoders/delete', methods=['POST'])
def delete_decoder_route():
    """Delete a decoder JS file (JSON: {name})."""
    try:
        data = request.get_json() or {}
        name = secure_filename(str(data.get("name", "")).strip())
        if not _is_safe_decoder_filename(name):
            return jsonify({"error": "Invalid filename"}), 400
        dest = os.path.join(CUSTOM_DECODER_DIR, name)
        if not os.path.isfile(dest):
            return jsonify({"error": "File not found"}), 404
        os.remove(dest)
        return jsonify({"name": name}), 200
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error deleting decoder: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/send_downlink', methods=['POST'])
def send_downlink_route():
    """
    Send a downlink to a selected sensor via MQTT.

    Expects JSON payload matching the structure built in
    `NetworkDashboard-0.1/static/js/downlinks.js`.
    """
    data = request.get_json() or {}
    logger.info(f"Received downlink request: {json.dumps(data)}")
    
    # Extract broker from data if provided, otherwise use current connection
    broker_ip = data.pop('broker', None)
    
    try:
        result = send_downlink(data, broker_ip=broker_ip)
        status = 200 if "message" in result else 400
        logger.info(f"Downlink result: {result}, status: {status}")
        return jsonify(result), status
    except Exception as e:
        logger.error(f"Error sending downlink: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/<path:path>')
def serve_static(path):
    """Serve static files from the root directory and subdirectories."""
    # Security: prevent directory traversal
    if '..' in path or path.startswith('/'):
        return "Invalid path", 403
    
    # Normalize path for case-insensitive matching on Windows
    normalized_path = path.replace('\\', '/')
    
    # Check if the file exists (case-sensitive check first)
    if os.path.isfile(path):
        directory = os.path.dirname(path) if os.path.dirname(path) else '.'
        filename = os.path.basename(path)
        return send_from_directory(directory, filename)
    
    # Case-insensitive fallback: try to find the file with different case
    # This is useful on Windows where filesystem is case-insensitive but URLs might be case-sensitive
    if not os.path.isfile(path):
        # Try to find the file with case-insensitive matching
        path_parts = normalized_path.split('/')
        if len(path_parts) > 1:
            dir_part = '/'.join(path_parts[:-1])
            file_part = path_parts[-1]
            if os.path.isdir(dir_part):
                # List files in directory and find case-insensitive match
                try:
                    for actual_file in os.listdir(dir_part):
                        if actual_file.lower() == file_part.lower():
                            return send_from_directory(dir_part, actual_file)
                except OSError:
                    pass
    
    # If it's a directory, try to serve index.html from it
    if os.path.isdir(path):
        index_path = os.path.join(path, 'index.html')
        if os.path.isfile(index_path):
            return send_from_directory(path, 'index.html')
        # If no index.html, try to find an HTML file with the directory name
        try:
            html_files = [f for f in os.listdir(path) if f.endswith('.html')]
            if html_files:
                # Try to find a file matching the directory name
                dir_name = os.path.basename(path.rstrip('/'))
                for html_file in html_files:
                    if html_file.startswith(dir_name) or html_file == 'index.html':
                        return send_from_directory(path, html_file)
                # If no match, serve the first HTML file
                return send_from_directory(path, html_files[0])
        except OSError:
            pass
    
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
    parser = argparse.ArgumentParser(description='Sensor Toolkit Server')
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
    
    logger.info(f"Starting Sensor Toolkit server on {config['host']}:{config['port']}")
    app.run(host=config['host'], port=config['port'], debug=config['debug'])

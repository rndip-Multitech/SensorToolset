"""
RadioBridge Tools Server
This file is used to create a Flask server to serve the RadioBridge Sensor Configuration Tool.
This will serve all of the HTML pages for configuring RadioBridge sensors.
"""

"""
Importing the required libraries.
"""

from flask import Flask, send_from_directory, send_file, jsonify, request, redirect
from werkzeug.utils import secure_filename
import io
import json
import logging
import os
import argparse
import urllib.request
import urllib.error
import ssl
import base64

from app_paths import get_app_root, get_custom_decoders_dir

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_ROOT = get_app_root()

"""
Creating the Flask app and setting the template and static directories.
"""
app = Flask(__name__, static_folder=APP_ROOT, static_url_path='')

# Custom decoder storage (served as static files)
CUSTOM_DECODER_DIR = get_custom_decoders_dir()
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
    # Always serve via explicit route so custom decoders can live in a writable directory.
    return f"/decoders/custom/{filename}"

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
    return send_file(os.path.join(APP_ROOT, 'index.html'))


@app.route('/downlinks')
def downlinks_page():
    """Serve the downlinks page."""
    return send_file(os.path.join(APP_ROOT, 'downlinks.html'))


@app.route('/tools_downlinks')
def tools_downlinks_redirect():
    """Redirect legacy URL to downlinks page."""
    return redirect('/downlinks', code=302)


@app.route('/sensors')
def sensors_page():
    """Serve the sensor monitoring page."""
    return send_file(os.path.join(APP_ROOT, 'sensors.html'))


@app.route('/RBS30X-ABM/rbs30x-abm.html')
@app.route('/RBS30x-ABM/rbs30x-abm.html')
@app.route('/rbs30x-abm.html')
def abm_page():
    """Serve the RBS30X-ABM sensor configuration page."""
    return send_file(os.path.join(APP_ROOT, 'RBS30X-ABM', 'rbs30x-abm.html'))


@app.route('/RBS30X-ABM/<path:filename>')
@app.route('/RBS30x-ABM/<path:filename>')
def abm_static(filename):
    """Serve static files from RBS30X-ABM directory (images, CSS, JS)."""
    # Security: prevent directory traversal
    if '..' in filename or filename.startswith('/'):
        return "Invalid path", 403
    return send_from_directory(os.path.join(APP_ROOT, 'RBS30X-ABM'), filename)


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
    """Return the list of discovered sensors from MQTT uplinks.
    If the discovery list is empty, derive DevEUIs from the message buffer so
    downlink pages still show devices that have sent uplinks."""
    sensors = get_sensors()
    if not sensors and MQTT_AVAILABLE:
        try:
            messages = get_messages()
            seen = {s["DevEUI"] for s in sensors}
            for msg in messages:
                if msg.get("type") == "json" and isinstance(msg.get("data"), dict):
                    dev_eui = msg["data"].get("deveui")
                    if dev_eui and dev_eui not in seen:
                        seen.add(dev_eui)
                        sensors.append({"DevEUI": dev_eui, "sensor_type": "Other"})
        except Exception as e:
            logger.warning(f"Fallback sensor list from messages: {e}")
    return jsonify({"sensors": sensors}), 200


def _normalize_dev_eui(entry):
    """Extract DevEUI from a session/device object (various API shapes)."""
    if not isinstance(entry, dict):
        return None
    for key in ("deveui", "DevEUI", "dev_eui", "devEUI"):
        val = entry.get(key)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return None


@app.route('/api/network_sessions', methods=['GET'])
def network_sessions_route():
    """Fetch connected sessions/devices from the gateway's LoRa network server API.
    Uses http://localhost/api/lora/sessions (MultiTech mPower format).
    Returns { devices: [ { DevEUI: "...", last_seen: "..." } ] } for the downlinks device dropdown."""
    url = "http://localhost/api/lora/sessions"
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as e:
        logger.warning(f"Network server API error {e.code}: {url}")
        return jsonify({"devices": [], "error": f"API returned {e.code}"}), 200
    except urllib.error.URLError as e:
        logger.warning(f"Network server API unreachable: {url} - {e}")
        return jsonify({"devices": [], "error": str(e.reason) if getattr(e, "reason", None) else str(e)}), 200
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Network server API invalid JSON: {e}")
        return jsonify({"devices": [], "error": "Invalid JSON response"}), 200
    # MultiTech mPower format: { "code": 200, "result": [...], "status": "success" }
    items = []
    if isinstance(data, dict):
        items = data.get("result") or data.get("sessions") or data.get("devices") or []
    elif isinstance(data, list):
        items = data
    if not isinstance(items, list):
        items = []
    devices = []
    seen = set()
    for entry in items:
        dev_eui = _normalize_dev_eui(entry) if isinstance(entry, dict) else None
        if dev_eui and dev_eui not in seen:
            seen.add(dev_eui)
            last_seen = entry.get("last_seen", "") if isinstance(entry, dict) else ""
            devices.append({"DevEUI": dev_eui, "last_seen": last_seen})
    return jsonify({"devices": devices}), 200


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


@app.route('/decoders/custom/<path:filename>')
def serve_custom_decoder(filename):
    """Serve custom decoder JS files from the writable decoder directory."""
    if '..' in filename or filename.startswith('/'):
        return "Invalid path", 403
    if not _is_safe_decoder_filename(filename):
        return "Invalid filename", 403
    return send_from_directory(CUSTOM_DECODER_DIR, filename)


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


# --- Cloud Integrations API ---
try:
    import cloud_integrations
    CLOUD_INTEGRATIONS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Cloud integrations not available: {e}")
    CLOUD_INTEGRATIONS_AVAILABLE = False


@app.route('/cloud_integrations')
def cloud_integrations_page():
    """Serve the cloud integrations page."""
    return send_file(os.path.join(APP_ROOT, 'cloud_integrations.html'))


@app.route('/api/integrations', methods=['GET'])
def list_integrations_route():
    """List all cloud integrations."""
    if not CLOUD_INTEGRATIONS_AVAILABLE:
        return jsonify({"integrations": [], "error": "Cloud integrations not available"}), 200
    try:
        integrations = cloud_integrations.get_integrations()
        return jsonify({"integrations": integrations}), 200
    except Exception as e:
        logger.error(f"Error listing integrations: {e}")
        return jsonify({"integrations": [], "error": str(e)}), 500


@app.route('/api/integrations', methods=['POST'])
def add_integration_route():
    """Add a new cloud integration."""
    if not CLOUD_INTEGRATIONS_AVAILABLE:
        return jsonify({"error": "Cloud integrations not available"}), 500
    try:
        data = request.get_json() or {}
        integration = cloud_integrations.add_integration(data)
        return jsonify({"integration": integration}), 201
    except Exception as e:
        logger.error(f"Error adding integration: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/integrations/<integration_id>', methods=['GET'])
def get_integration_route(integration_id):
    """Get a specific integration by ID."""
    if not CLOUD_INTEGRATIONS_AVAILABLE:
        return jsonify({"error": "Cloud integrations not available"}), 500
    try:
        integration = cloud_integrations.get_integration(integration_id)
        if integration:
            return jsonify({"integration": integration}), 200
        return jsonify({"error": "Integration not found"}), 404
    except Exception as e:
        logger.error(f"Error getting integration: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/integrations/<integration_id>', methods=['PUT'])
def update_integration_route(integration_id):
    """Update an existing integration."""
    if not CLOUD_INTEGRATIONS_AVAILABLE:
        return jsonify({"error": "Cloud integrations not available"}), 500
    try:
        data = request.get_json() or {}
        integration = cloud_integrations.update_integration(integration_id, data)
        if integration:
            return jsonify({"integration": integration}), 200
        return jsonify({"error": "Integration not found"}), 404
    except Exception as e:
        logger.error(f"Error updating integration: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/integrations/<integration_id>', methods=['DELETE'])
def delete_integration_route(integration_id):
    """Delete an integration."""
    if not CLOUD_INTEGRATIONS_AVAILABLE:
        return jsonify({"error": "Cloud integrations not available"}), 500
    try:
        if cloud_integrations.delete_integration(integration_id):
            return jsonify({"success": True}), 200
        return jsonify({"error": "Integration not found"}), 404
    except Exception as e:
        logger.error(f"Error deleting integration: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/integrations/<integration_id>/toggle', methods=['POST'])
def toggle_integration_route(integration_id):
    """Enable or disable an integration."""
    if not CLOUD_INTEGRATIONS_AVAILABLE:
        return jsonify({"error": "Cloud integrations not available"}), 500
    try:
        data = request.get_json() or {}
        enabled = data.get("enabled", True)
        integration = cloud_integrations.toggle_integration(integration_id, enabled)
        if integration:
            return jsonify({"integration": integration}), 200
        return jsonify({"error": "Integration not found"}), 404
    except Exception as e:
        logger.error(f"Error toggling integration: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/integrations/<integration_id>/test', methods=['POST'])
def test_integration_route(integration_id):
    """Test an integration with a sample message."""
    if not CLOUD_INTEGRATIONS_AVAILABLE:
        return jsonify({"success": False, "message": "Cloud integrations not available"}), 500
    try:
        integration = cloud_integrations.get_integration(integration_id)
        if not integration:
            return jsonify({"success": False, "message": "Integration not found"}), 404
        result = cloud_integrations.test_integration(integration)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error testing integration: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/integrations/test', methods=['POST'])
def test_integration_unsaved_route():
    """Test an unsaved integration configuration with a sample message."""
    if not CLOUD_INTEGRATIONS_AVAILABLE:
        return jsonify({"success": False, "message": "Cloud integrations not available"}), 500
    try:
        integration = request.get_json() or {}
        result = cloud_integrations.test_integration(integration)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error testing integration: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


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

    # Always resolve under APP_ROOT (supports frozen builds)
    abs_path = os.path.join(APP_ROOT, normalized_path)
    
    # Check if the file exists (case-sensitive check first)
    if os.path.isfile(abs_path):
        directory = os.path.dirname(abs_path)
        filename = os.path.basename(abs_path)
        return send_from_directory(directory, filename)
    
    # Case-insensitive fallback: try to find the file with different case
    # This is useful on Windows where filesystem is case-insensitive but URLs might be case-sensitive
    if not os.path.isfile(abs_path):
        # Try to find the file with case-insensitive matching
        path_parts = normalized_path.split('/')
        if len(path_parts) > 1:
            dir_part = os.path.join(APP_ROOT, *path_parts[:-1])
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
    if os.path.isdir(abs_path):
        index_path = os.path.join(abs_path, 'index.html')
        if os.path.isfile(index_path):
            return send_from_directory(abs_path, 'index.html')
        # If no index.html, try to find an HTML file with the directory name
        try:
            html_files = [f for f in os.listdir(abs_path) if f.endswith('.html')]
            if html_files:
                # Try to find a file matching the directory name
                dir_name = os.path.basename(abs_path.rstrip('/'))
                for html_file in html_files:
                    if html_file.startswith(dir_name) or html_file == 'index.html':
                        return send_from_directory(abs_path, html_file)
                # If no match, serve the first HTML file
                return send_from_directory(abs_path, html_files[0])
        except OSError:
            pass
    
    # Default: try to serve the file anyway (for relative paths)
    try:
        directory = os.path.dirname(abs_path)
        filename = os.path.basename(abs_path)
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

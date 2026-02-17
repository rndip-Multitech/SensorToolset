"""
RadioBridge Tools Server
This file is used to create a Flask server to serve the RadioBridge Sensor Configuration Tool.
This will serve all of the HTML pages for configuring RadioBridge sensors.
"""

"""
Importing the required libraries.
"""

# app_paths is at repo root and adds static/py to path when imported
try:
    from flask import Flask, send_from_directory, send_file, jsonify, request, redirect, session, url_for
    from werkzeug.utils import secure_filename
    from werkzeug.middleware.proxy_fix import ProxyFix
except ImportError as e:
    import sys
    print("ERROR: Flask or its dependencies are not installed.", file=sys.stderr)
    print("Install Python dependencies by running (from the app directory):", file=sys.stderr)
    print("  ./Install postinstall", file=sys.stderr)
    print("or manually:", file=sys.stderr)
    print("  python3 -m pip install --user --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt", file=sys.stderr)
    print("Then run the app again with the same python3.", file=sys.stderr)
    sys.exit(1)
import io
import json
import logging
import os
import socket
import threading
import time
import argparse
import urllib.request
import urllib.error
from urllib.parse import quote
import ssl
import base64
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app_paths import get_app_root, get_custom_decoders_dir, get_custom_encoders_dir

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_ROOT = get_app_root()
TEMPLATES_DIR = os.path.join(APP_ROOT, "templates")
STATIC_DIR = os.path.join(APP_ROOT, "static")

"""
Creating the Flask app and setting the template and static directories.
"""
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
# Trust X-Forwarded-Proto/For when behind a reverse proxy (set TRUST_PROXY=1 when using nginx etc.)
if os.environ.get("TRUST_PROXY", "").strip() in ("1", "true", "yes"):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
# Secret key for session management (can be overridden via env)
app.secret_key = os.environ.get("SENSOR_TOOLKIT_SECRET", "sensor-toolkit-change-me")
# Allow session cookie on both HTTP and HTTPS (don't require Secure flag)
app.config["SESSION_COOKIE_SECURE"] = False
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Invalidate old browser sessions whenever the server process restarts.
APP_BOOT_ID = str(int(time.time()))

# Custom decoder and encoder storage (separate dirs so same filename does not clash)
CUSTOM_DECODER_DIR = get_custom_decoders_dir()
CUSTOM_ENCODER_DIR = get_custom_encoders_dir()
os.makedirs(CUSTOM_DECODER_DIR, exist_ok=True)
os.makedirs(CUSTOM_ENCODER_DIR, exist_ok=True)


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
    return f"/decoders/custom/{filename}"


def _encoder_file_url(filename: str) -> str:
    return f"/encoders/custom/{filename}"


@app.route('/static/<path:filename>')
def legacy_static(filename):
    """Serve static assets for legacy login page from network-dashboard-v0.0.8/static."""
    if '..' in filename or filename.startswith('/'):
        return "Invalid path", 403
    legacy_static_dir = os.path.join(APP_ROOT, "network-dashboard-v0.0.8", "static")
    return send_from_directory(legacy_static_dir, filename)


# Try to import MQTT utilities - gracefully handle if paho-mqtt isn't installed
try:
    from mqtt_utils_rbt import (
        connect_to_broker,
        get_sensors,
        send_downlink,
        get_messages,
        get_broker_config,
        read_persistent_uplink_cache,
        clear_persistent_uplink_cache,
    )
    MQTT_AVAILABLE = True
    logger.info("MQTT utilities loaded successfully")
except ImportError as e:
    logger.warning(f"MQTT utilities not available: {e}. MQTT features will be disabled.")
    MQTT_AVAILABLE = False

    # Stub functions so routes don't fail (match real module signatures)
    def connect_to_broker(broker="localhost", port=1883, topic="lora/+/up"):  # type: ignore[no-redef]
        return None

    def get_sensors():  # type: ignore[no-redef]
        return []

    def get_messages():  # type: ignore[no-redef]
        return []

    def send_downlink(data, broker_ip=None):  # type: ignore[no-redef]
        return {"error": "MQTT not available. Please install paho-mqtt."}

    def get_broker_config() -> Optional[Dict[str, Any]]:
        return None

    def read_persistent_uplink_cache(limit=0):  # type: ignore[no-redef]
        return []

    def clear_persistent_uplink_cache() -> bool:
        return False

# Configuration
config = {
    'host': '0.0.0.0',
    'port': 5000,
    'debug': False
}

def _gateway_base_url(broker):
    """Gateway HTTP base URL from broker host (no port — uses default HTTP port)."""
    if not broker or not str(broker).strip():
        return None
    host = str(broker).strip().split(":")[0]
    return "http://" + host


def authenticate_user(username: str, password: str, gateway_ip: str):
    """
    Authenticate against the gateway's HTTPS /api/login endpoint.

    Returns (ok: bool, error: Optional[str]).
    """
    username = (username or "").strip()
    password = password or ""
    gateway_ip = (gateway_ip or "").strip()
    if not username or not password or not gateway_ip:
        return False, "Missing username, password, or gateway IP"

    url = f"https://{gateway_ip}/api/login"
    payload = json.dumps({"username": username, "password": password}).encode("utf-8")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip() else {}
        except Exception:
            data = {}
        msg = data.get("error") or f"HTTP {e.code}"
        logger.warning(f"Gateway login HTTPError: {msg}")
        return False, msg
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Gateway login failed: {e}")
        return False, str(e)

    status = data.get("status")
    code = data.get("code")
    if (isinstance(status, str) and status.lower() == "success") or code == 200:
        return True, None
    return False, data.get("error") or status or "Login failed"


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


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and API.

    POST expects JSON: {"username": "...", "password": "...", "ip": "<gateway ip>"}.
    Authenticates against the gateway /api/login endpoint.
    """
    if request.method == 'POST':
        # Accept both JSON (Ajax) and form data (HTML form submit)
        if request.is_json:
            data = request.get_json(force=True, silent=True) or {}
        else:
            data = request.form
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        # Gateway IP from client input, otherwise host currently serving this app
        ip = ((data.get('ip') or request.host.split(':', 1)[0]) or '').strip()
        ok, err = authenticate_user(username, password, ip)
        if ok:
            session['username'] = username or 'user'
            session['boot_id'] = APP_BOOT_ID
            if request.is_json:
                return jsonify({'status': 'ok', 'redirect': url_for('index')}), 200
            return redirect(url_for('index'))
        err_msg = err or 'Invalid credentials'
        if request.is_json:
            return jsonify({'status': 'failed', 'error': err_msg}), 401
        return redirect(url_for('login') + '?error=' + quote(err_msg))

    # GET: if already logged in, go home; otherwise show login page
    if 'username' in session:
        return redirect(url_for('index'))

    login_path = os.path.join(TEMPLATES_DIR, "login.html")
    if os.path.isfile(login_path):
        return send_file(login_path)
    # Fallback if template missing
    return """
    <html><body>
    <h2>Sensor Toolkit Login</h2>
    <form method="post">
      <label>Username: <input type="text" name="username"></label><br>
      <label>Password: <input type="password" name="password"></label><br>
      <button type="submit">Login</button>
    </form>
    </body></html>
    """


@app.route('/logout')
def logout():
    """Clear session and return to login screen."""
    session.pop('username', None)
    return redirect(url_for('login'))


@app.before_request
def enforce_login_for_html_pages():
    """Require login for HTML pages, and invalidate stale sessions after restart."""
    # Public routes/assets.
    if request.path.startswith('/static/') or request.path in ('/login', '/logout'):
        return None

    # If session is from a previous server run, force fresh login.
    if 'username' in session and session.get('boot_id') != APP_BOOT_ID:
        session.clear()

    if request.method != 'GET':
        return None
    if 'username' in session:
        return None

    # Protect root and direct HTML navigation (including catch-all served pages).
    if request.path == '/' or request.path.endswith('.html'):
        return redirect(url_for('login'))
    return None


@app.route('/')
@app.route('/index.html')
def index():
    """Serve the main index page (requires login)."""
    if 'username' not in session:
        return redirect(url_for('login'))
    return send_file(os.path.join(TEMPLATES_DIR, "index.html"))


@app.route('/downlinks')
@app.route('/downlinks.html')
def downlinks_page():
    """Serve the downlinks page (requires login)."""
    if 'username' not in session:
        return redirect(url_for('login'))
    return send_file(os.path.join(TEMPLATES_DIR, "downlinks.html"))


@app.route('/tools_downlinks')
def tools_downlinks_redirect():
    """Redirect legacy URL to downlinks page."""
    return redirect('/downlinks', code=302)


@app.route('/sensors')
@app.route('/sensors.html')
def sensors_page():
    """Serve the sensor monitoring page (requires login)."""
    if 'username' not in session:
        return redirect(url_for('login'))
    return send_file(os.path.join(TEMPLATES_DIR, "sensors.html"))


@app.route('/RBS30X-ABM/rbs30x-abm.html')
@app.route('/RBS30x-ABM/rbs30x-abm.html')
@app.route('/rbs30x-abm.html')
def abm_page():
    """Serve the RBS30X-ABM sensor configuration page (requires login)."""
    if 'username' not in session:
        return redirect(url_for('login'))
    return send_file(os.path.join(TEMPLATES_DIR, "RBS30X-ABM", "rbs30x-abm.html"))


@app.route('/RBS30X-ABM/<path:filename>')
@app.route('/RBS30x-ABM/<path:filename>')
def abm_static(filename):
    """Serve static files from RBS30X-ABM directory (images, CSS, JS)."""
    # Security: prevent directory traversal
    if '..' in filename or filename.startswith('/'):
        return "Invalid path", 403
    return send_from_directory(os.path.join(TEMPLATES_DIR, "RBS30X-ABM"), filename)


@app.route('/connect', methods=['POST'])
def connect_route():
    """
    Connect to the LoRa Network Server MQTT broker.

    Expects JSON: {"broker": "...", "port": 1883, "topic": "lora/+/up"}
    When running on the gateway, broker will usually be "localhost".
    """
    data = request.get_json(force=True, silent=True) or {}
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
    if not isinstance(sensors, list):
        sensors = []
    if not sensors and MQTT_AVAILABLE:
        try:
            messages = get_messages()
            seen = {s.get("DevEUI", "") for s in sensors if isinstance(s, dict)}
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


@app.route('/api/uplinks/persistent-cache', methods=['GET'])
def get_persistent_uplink_cache_route():
    """Return messages from the server-side persistent uplink cache (received even when browser was closed)."""
    try:
        if not MQTT_AVAILABLE:
            return jsonify({"messages": []}), 200
        limit = request.args.get('limit', 5000, type=int)
        limit = min(max(1, limit), 10000)
        messages = read_persistent_uplink_cache(limit=limit)
        return jsonify({"messages": messages}), 200
    except Exception as e:
        logger.error(f"Error reading persistent uplink cache: {e}")
        return jsonify({"messages": [], "error": str(e)}), 500


@app.route('/api/uplinks/persistent-cache/clear', methods=['POST'])
def clear_persistent_uplink_cache_route():
    """Clear the server-side persistent uplink cache (JSONL file)."""
    try:
        if not MQTT_AVAILABLE:
            return jsonify({"success": False, "message": "MQTT utilities not available"}), 500
        ok = clear_persistent_uplink_cache()
        if ok:
            return jsonify({"success": True}), 200
        return jsonify({"success": False, "message": "Failed to clear uplink cache"}), 500
    except Exception as e:
        logger.error(f"Error clearing persistent uplink cache: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


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
        data = request.get_json(force=True, silent=True) or {}
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
        data = request.get_json(force=True, silent=True) or {}
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


# --- Custom encoders (separate directory so encoder and decoder with same name do not override) ---
@app.route('/encoders/custom/<path:filename>')
def serve_custom_encoder(filename):
    """Serve custom encoder JS files from the writable encoder directory."""
    if '..' in filename or filename.startswith('/'):
        return "Invalid path", 403
    if not _is_safe_decoder_filename(filename):
        return "Invalid filename", 403
    return send_from_directory(CUSTOM_ENCODER_DIR, filename)


@app.route('/api/encoders/list', methods=['GET'])
def list_encoders_route():
    """List uploaded custom encoder JS files."""
    try:
        files = []
        for fname in sorted(os.listdir(CUSTOM_ENCODER_DIR)):
            if not _is_safe_decoder_filename(fname):
                continue
            path = os.path.join(CUSTOM_ENCODER_DIR, fname)
            if not os.path.isfile(path):
                continue
            stat = os.stat(path)
            files.append({
                "name": fname,
                "url": _encoder_file_url(fname),
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
            })
        return jsonify({"files": files}), 200
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error listing encoders: {e}")
        return jsonify({"files": [], "error": str(e)}), 500


@app.route('/api/encoders/save', methods=['POST'])
def save_encoder_route():
    """Save an encoder JS from text (JSON: {name, content})."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        name = secure_filename(str(data.get("name", "")).strip())
        content = str(data.get("content", ""))
        if not _is_safe_decoder_filename(name):
            return jsonify({"error": "Invalid filename (must end with .js, no paths)"}), 400
        if not content.strip():
            return jsonify({"error": "Empty content"}), 400
        dest = os.path.join(CUSTOM_ENCODER_DIR, name)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(content)
            if not content.endswith("\n"):
                f.write("\n")
        return jsonify({"name": name, "url": _encoder_file_url(name)}), 200
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error saving encoder: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/encoders/delete', methods=['POST'])
def delete_encoder_route():
    """Delete an encoder JS file (JSON: {name})."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        name = secure_filename(str(data.get("name", "")).strip())
        if not _is_safe_decoder_filename(name):
            return jsonify({"error": "Invalid filename"}), 400
        dest = os.path.join(CUSTOM_ENCODER_DIR, name)
        if not os.path.isfile(dest):
            return jsonify({"error": "File not found"}), 404
        os.remove(dest)
        return jsonify({"name": name}), 200
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error deleting encoder: {e}")
        return jsonify({"error": str(e)}), 500


# --- Cloud Integrations API ---
cloud_integrations = None
try:
    import cloud_integrations as _ci
    cloud_integrations = _ci
    CLOUD_INTEGRATIONS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Cloud integrations not available: {e}")
    CLOUD_INTEGRATIONS_AVAILABLE = False


@app.route('/cloud_integrations')
def cloud_integrations_page():
    """Serve the cloud integrations page (requires login)."""
    if 'username' not in session:
        return redirect(url_for('login'))
    return send_file(os.path.join(TEMPLATES_DIR, "cloud_integrations.html"))


@app.route('/cloud_integrations.html')
def cloud_integrations_html():
    """Alias for cloud integrations page (nav links use .html)."""
    return cloud_integrations_page()


@app.route('/uplinks.html')
def uplinks_page():
    """Serve the uplinks page (requires login)."""
    if 'username' not in session:
        return redirect(url_for('login'))
    return send_file(os.path.join(TEMPLATES_DIR, "uplinks.html"))


@app.route('/decoders.html')
def decoders_page():
    """Serve the decoders page (requires login)."""
    if 'username' not in session:
        return redirect(url_for('login'))
    return send_file(os.path.join(TEMPLATES_DIR, "decoders.html"))


@app.route('/api/integrations', methods=['GET'])
def list_integrations_route():
    """List all cloud integrations."""
    if not CLOUD_INTEGRATIONS_AVAILABLE or cloud_integrations is None:
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
    if not CLOUD_INTEGRATIONS_AVAILABLE or cloud_integrations is None:
        return jsonify({"error": "Cloud integrations not available"}), 500
    assert cloud_integrations is not None
    try:
        data = request.get_json(force=True, silent=True) or {}
        integration = cloud_integrations.add_integration(data)
        return jsonify({"integration": integration}), 201
    except Exception as e:
        logger.error(f"Error adding integration: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/integrations/<integration_id>', methods=['GET'])
def get_integration_route(integration_id):
    """Get a specific integration by ID."""
    if not CLOUD_INTEGRATIONS_AVAILABLE or cloud_integrations is None:
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
    if not CLOUD_INTEGRATIONS_AVAILABLE or cloud_integrations is None:
        return jsonify({"error": "Cloud integrations not available"}), 500
    assert cloud_integrations is not None
    try:
        data = request.get_json(force=True, silent=True) or {}
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
    if not CLOUD_INTEGRATIONS_AVAILABLE or cloud_integrations is None:
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
    if not CLOUD_INTEGRATIONS_AVAILABLE or cloud_integrations is None:
        return jsonify({"error": "Cloud integrations not available"}), 500
    try:
        data = request.get_json(force=True, silent=True) or {}
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
    if not CLOUD_INTEGRATIONS_AVAILABLE or cloud_integrations is None:
        return jsonify({"success": False, "message": "Cloud integrations not available"}), 500
    assert cloud_integrations is not None
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
    if not CLOUD_INTEGRATIONS_AVAILABLE or cloud_integrations is None:
        return jsonify({"success": False, "message": "Cloud integrations not available"}), 500
    assert cloud_integrations is not None
    try:
        integration = request.get_json(force=True, silent=True) or {}
        result = cloud_integrations.test_integration(integration)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error testing integration: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/cloud/forward-message', methods=['POST'])
def forward_message_route():
    """Accept a decoded message from the uplinks page and queue it for cloud forwarding (decoder from Uplinks page)."""
    if not CLOUD_INTEGRATIONS_AVAILABLE or cloud_integrations is None:
        return jsonify({"error": "Cloud integrations not available"}), 500
    data = request.get_json(force=True, silent=True) or {}
    try:
        cloud_integrations.forward_message({
            "topic": data.get("topic", ""),
            "data": data.get("data", {}),
            "decoded": data.get("decoded"),
            "deveui": data.get("deveui"),
            "time": data.get("time") or datetime.now(timezone.utc).isoformat(),
        })
        return jsonify({"ok": True}), 200
    except Exception as e:
        logger.error(f"Error queueing forward message: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/lora/packets/queue', methods=['GET'])
def gateway_queue_get():
    """Proxy GET to gateway downlink queue API (api/lora/packets/down). Query param: broker (gateway host)."""
    broker = request.args.get("broker", "").strip()
    base = _gateway_base_url(broker)
    if not base:
        return jsonify({"error": "Broker (gateway) required. Connect first or set broker."}), 400
    # mPower downlink queue endpoint
    url = base.rstrip("/") + "/api/lora/packets/down"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body) if body.strip() else {}
        return jsonify(data)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            data = json.loads(body) if body.strip() else {}
        except Exception:
            data = {"error": str(e)}
        return jsonify(data), e.code
    except Exception as e:
        logger.warning(f"Gateway queue GET failed: {e}")
        return jsonify({"error": str(e)}), 502


@app.route('/api/lora/packets/queue/<path:subpath>', methods=['DELETE'])
def gateway_queue_delete(subpath):
    """Proxy DELETE to gateway downlink queue API (api/lora/downlink-queue/<...>). Query param: broker."""
    broker = request.args.get("broker", "").strip()
    base = _gateway_base_url(broker)
    if not base:
        return jsonify({"error": "Broker (gateway) required."}), 400
    # mPower downlink queue delete endpoint
    url = base.rstrip("/") + "/api/lora/downlink-queue/" + subpath.lstrip("/")
    try:
        req = urllib.request.Request(url, method="DELETE")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body) if body.strip() else {}
        return jsonify(data)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            data = json.loads(body) if body.strip() else {}
        except Exception:
            data = {"error": str(e)}
        return jsonify(data), e.code
    except Exception as e:
        logger.warning(f"Gateway queue DELETE failed: {e}")
        return jsonify({"error": str(e)}), 502


@app.route('/send_downlink', methods=['POST'])
def send_downlink_route():
    """
    Send a downlink to a selected sensor via MQTT.

    Expects JSON payload matching the structure built in
    `static/js/downlinks.js`.
    """
    data = request.get_json(force=True, silent=True) or {}
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


def _try_serve_from(directory: str, normalized_path: str):
    """Try to serve a file or directory index from directory + normalized_path. Returns (response, True) or (None, False)."""
    abs_path = os.path.join(directory, normalized_path)
    if os.path.isfile(abs_path):
        return send_from_directory(os.path.dirname(abs_path), os.path.basename(abs_path)), True
    if os.path.isdir(abs_path):
        index_path = os.path.join(abs_path, "index.html")
        if os.path.isfile(index_path):
            return send_from_directory(abs_path, "index.html"), True
        try:
            html_files = [f for f in os.listdir(abs_path) if f.endswith(".html")]
            if html_files:
                dir_name = os.path.basename(abs_path.rstrip("/"))
                for html_file in html_files:
                    if html_file.startswith(dir_name) or html_file == "index.html":
                        return send_from_directory(abs_path, html_file), True
                return send_from_directory(abs_path, html_files[0]), True
        except OSError:
            pass
    path_parts = normalized_path.split("/")
    if len(path_parts) > 1:
        dir_part = os.path.join(directory, *path_parts[:-1])
        file_part = path_parts[-1]
        if os.path.isdir(dir_part):
            try:
                for actual_file in os.listdir(dir_part):
                    if actual_file.lower() == file_part.lower():
                        return send_from_directory(dir_part, actual_file), True
            except OSError:
                pass
    return None, False


@app.route('/<path:path>')  # type: ignore[arg-type]
def serve_static(path: str):
    """Serve files from templates/, then static/, then root (for backward compatibility)."""
    if ".." in path or path.startswith("/"):
        return "Invalid path", 403
    normalized_path = path.replace("\\", "/")

    for base in (TEMPLATES_DIR, STATIC_DIR, APP_ROOT):
        resp, ok = _try_serve_from(base, normalized_path)
        if ok:
            return resp

    try:
        abs_path = os.path.join(APP_ROOT, normalized_path)
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
    
    def auto_connect_mqtt():
        time.sleep(1.5)
        try:
            if MQTT_AVAILABLE:
                cfg = get_broker_config()
                if cfg and cfg.get('broker'):
                    connect_to_broker(
                        broker=cfg.get('broker', 'localhost'),
                        port=int(cfg.get('port', 1883)),
                        topic=cfg.get('topic', 'lora/+/up'),
                    )
                    logger.info("Auto-connected to MQTT broker from saved config (uplinks cached when browser is closed)")
        except Exception as e:
            logger.warning("Auto-connect to MQTT failed: %s", e)

    t = threading.Thread(target=auto_connect_mqtt, daemon=True)
    t.start()

    # Write status.json with pid and AppInfo (LAN IP in AppInfo) at server start
    def write_status_json():
        urls = [f"http://127.0.0.1:{config['port']}"]
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            lan_ip = s.getsockname()[0]
            s.close()
            urls.append(f"http://{lan_ip}:{config['port']}")
        except Exception:
            pass
        status = {
            "pid": os.getpid(),
            "AppInfo": "Listening at: " + ", ".join(urls),
        }
        status_path = os.path.join(APP_ROOT, "status.json")
        try:
            with open(status_path, "w", encoding="utf-8") as f:
                json.dump(status, f, indent=2)
            logger.info("Wrote %s", status_path)
        except Exception as e:
            logger.warning("Could not write status.json: %s", e)

    write_status_json()

    logger.info(f"Starting Sensor Toolkit server on {config['host']}:{config['port']}")
    app.run(host=config['host'], port=config['port'], debug=config['debug'])

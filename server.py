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
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app_paths import get_app_root, get_custom_decoders_dir, get_custom_encoders_dir, get_data_root

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

RADIOBRIDGE_UPSTREAM_FILENAME = "radiobridge_upstream.js"
RADIOBRIDGE_META_FILENAME = "radiobridge_decoder_meta.json"


def _write_atomic(path: str, content: str) -> None:
    """Atomically write text content to a file (via temp file + replace)."""
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
        if not content.endswith("\n"):
            f.write("\n")
    os.replace(tmp_path, path)

# Device name overrides (editable); gateway names come from /api/loraNetwork/whitelist or /api/lora/devices
DEVICE_NAMES_FILE = os.path.join(get_data_root(), "device_names.json")
EMAIL_NOTIFICATION_CONFIG_FILE = os.path.join(get_data_root(), "email_notifications.json")
NOTIFICATION_RULES_FILE = os.path.join(get_data_root(), "notification_rules.json")


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
    'debug': False,
    # Local dev helper: bypass login/session checks when True.
    'auth_bypass': False,
    # RadioBridge decoder bundle URL (optional). If set, "Update Radiobridge library" will fetch from it.
    # Override via RADIOBRIDGE_DECODER_URL env var or config file key "radiobridge_decoder_url".
    # Leave empty until you have a real URL to avoid 502 errors.
    'radiobridge_decoder_url': '',
}


def _get_radiobridge_decoder_url() -> str:
    """
    Effective RadioBridge decoder URL.

    Precedence:
    1. RADIOBRIDGE_DECODER_URL environment variable (if set, non-empty)
    2. config['radiobridge_decoder_url'] from defaults or JSON config file
    """
    env_val = os.environ.get("RADIOBRIDGE_DECODER_URL", "").strip()
    if env_val:
        return env_val
    return str(config.get("radiobridge_decoder_url") or "").strip()


def _is_auth_bypassed() -> bool:
    """Return True when auth should be bypassed (for local development/testing only)."""
    env_val = os.environ.get("SENSOR_TOOLKIT_NO_AUTH", "").strip().lower()
    if env_val in ("1", "true", "yes", "on"):
        return True
    return bool(config.get("auth_bypass", False))


def _is_logged_in() -> bool:
    return _is_auth_bypassed() or ('username' in session)

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
    if _is_auth_bypassed():
        session['username'] = session.get('username') or 'dev-user'
        session['boot_id'] = APP_BOOT_ID
        if request.method == 'POST' and request.is_json:
            return jsonify({'status': 'ok', 'redirect': url_for('index'), 'bypass': True}), 200
        return redirect(url_for('index'))

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
    if _is_auth_bypassed():
        session['username'] = session.get('username') or 'dev-user'
        session['boot_id'] = APP_BOOT_ID
        return None

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
    if not _is_logged_in():
        return redirect(url_for('login'))
    return send_file(os.path.join(TEMPLATES_DIR, "index.html"))


@app.route('/downlinks')
@app.route('/downlinks.html')
def downlinks_page():
    """Serve the downlinks page (requires login)."""
    if not _is_logged_in():
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
    if not _is_logged_in():
        return redirect(url_for('login'))
    return send_file(os.path.join(TEMPLATES_DIR, "sensors.html"))


@app.route('/RBS30X-ABM/rbs30x-abm.html')
@app.route('/RBS30x-ABM/rbs30x-abm.html')
@app.route('/rbs30x-abm.html')
def abm_page():
    """Serve the RBS30X-ABM sensor configuration page (requires login)."""
    if not _is_logged_in():
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


def _normalize_deveui_key(deveui: str) -> str:
    """Normalize DevEUI for lookup: lowercase, no dashes."""
    if not deveui or not isinstance(deveui, str):
        return ""
    return deveui.strip().lower().replace("-", "")


def _extract_device_name(entry: dict) -> Optional[str]:
    """Extract display name from a gateway device/whitelist entry."""
    if not isinstance(entry, dict):
        return None
    for key in ("name", "deviceName", "Name", "label", "description", "device_name"):
        val = entry.get(key)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _fetch_gateway_device_names(broker: str) -> Dict[str, str]:
    """Fetch DevEUI -> name map from gateway (whitelist and/or lora/devices)."""
    out: Dict[str, str] = {}
    base = (broker or "localhost").strip().split("/")[0]
    if not base.startswith("http"):
        base = "http://" + base
    base = base.rstrip("/")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    # Try both whitelist and device list endpoints. On newer mPower the whitelist
    # lives under /api/loraNetwork/whitelist/devices.
    for path in (
        "/api/loraNetwork/whitelist/devices",
        "/api/loraNetwork/whitelist",
        "/api/lora/devices",
        "/api/lora/devices/",
    ):
        url = base + path
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                data = json.loads(body) if body.strip() else {}
        except Exception:
            continue
        items = []
        if isinstance(data, dict):
            items = data.get("result") or data.get("devices") or data.get("whitelist") or data.get("list") or []
        elif isinstance(data, list):
            items = data
        if not isinstance(items, list):
            continue
        for entry in items:
            if not isinstance(entry, dict):
                continue
            eui = _normalize_dev_eui(entry)
            name = _extract_device_name(entry)
            if eui and name:
                key = _normalize_deveui_key(eui)
                if key and key not in out:
                    out[key] = name
    return out


def _load_device_name_overrides() -> Dict[str, str]:
    """Load local device name overrides from JSON file."""
    if not os.path.isfile(DEVICE_NAMES_FILE):
        return {}
    try:
        with open(DEVICE_NAMES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and k and v.strip()}
    except Exception as e:
        logger.warning(f"Could not load device names overrides: {e}")
    return {}


def _save_device_name_overrides(overrides: Dict[str, str]) -> None:
    """Save local device name overrides to JSON file."""
    try:
        with open(DEVICE_NAMES_FILE, "w", encoding="utf-8") as f:
            json.dump(overrides, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save device names overrides: {e}")


def _load_email_notification_config() -> Dict[str, Any]:
    """Load SMTP/email notification config from disk."""
    defaults: Dict[str, Any] = {
        "enabled": False,
        # When False, use gateway-reported SMTP (if available) for host/port/TLS/auth.
        "use_custom_smtp": False,
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_pass": "",
        "use_tls": True,
        "from_email": "",
        "to_email": "",
    }
    if not os.path.isfile(EMAIL_NOTIFICATION_CONFIG_FILE):
        return defaults
    try:
        with open(EMAIL_NOTIFICATION_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return defaults
        out = dict(defaults)
        out.update(data)
        return out
    except Exception as e:
        logger.warning(f"Could not load email notification config: {e}")
        return defaults


def _save_email_notification_config(config_data: Dict[str, Any]) -> None:
    """Persist SMTP/email notification config to disk."""
    try:
        with open(EMAIL_NOTIFICATION_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save email notification config: {e}")


def _sanitize_email_notification_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize/validate incoming email notification config payload."""
    cfg = {
        "enabled": bool(raw.get("enabled", False)),
        "use_custom_smtp": bool(raw.get("use_custom_smtp", False)),
        "smtp_host": str(raw.get("smtp_host") or "").strip(),
        "smtp_port": int(raw.get("smtp_port") or 587),
        "smtp_user": str(raw.get("smtp_user") or "").strip(),
        "smtp_pass": str(raw.get("smtp_pass") or "").strip(),
        "use_tls": bool(raw.get("use_tls", True)),
        "from_email": str(raw.get("from_email") or "").strip(),
        "to_email": str(raw.get("to_email") or "").strip(),
    }
    if cfg["smtp_port"] < 1 or cfg["smtp_port"] > 65535:
        raise ValueError("smtp_port must be between 1 and 65535")
    return cfg


def _public_email_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    """Return safe config for UI (hides SMTP password)."""
    out = dict(config_data)
    out["smtp_pass"] = ""
    out["has_password"] = bool(config_data.get("smtp_pass"))
    return out


_GATEWAY_SMTP_CACHE: Dict[str, Any] = {"ts": 0.0, "profile": None}
_GATEWAY_SMTP_CACHE_TTL_SEC = 25.0


def _smtp_pass_is_placeholder(value: str) -> bool:
    s = str(value or "").strip()
    if not s:
        return True
    if "*" in s or s.lower() in ("hidden", "redacted", "********"):
        return True
    return False


def _unwrap_nested_config(obj: Any) -> Dict[str, Any]:
    """Unwrap common API wrappers (result/data/smtp/mail) when they hold SMTP-like keys."""
    if not isinstance(obj, dict):
        return {}
    cur: Dict[str, Any] = obj
    for _ in range(4):
        keys_lower = {str(k).lower() for k in cur.keys()}
        if any(
            k in keys_lower
            for k in (
                "smtpserver",
                "smtp_server",
                "smtp_host",
                "mailserver",
                "mail_server",
                "smtpport",
                "smtp_port",
            )
        ) or any("smtp" in k for k in keys_lower):
            return cur
        moved = False
        for wrap in ("result", "data", "smtp", "mail", "email", "config", "settings"):
            inner = cur.get(wrap)
            if isinstance(inner, dict):
                cur = inner
                moved = True
                break
        if not moved:
            break
    return cur


def _coerce_bool(val: Any, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return bool(val)
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "on", "enabled"):
        return True
    if s in ("0", "false", "no", "off", "disabled", ""):
        return False
    return default


def _normalize_gateway_smtp_dict(raw: Any) -> Optional[Dict[str, Any]]:
    """Extract a normalized SMTP profile from a gateway JSON object, or None."""
    if not isinstance(raw, dict):
        return None
    d = _unwrap_nested_config(raw)
    if not d:
        return None

    def pick_host() -> str:
        for key in (
            "smtp_host",
            "smtpHost",
            "SmtpHost",
            "mail_server",
            "mailServer",
            "smtp_server",
            "smtpServer",
            "server",
            "hostname",
            "relay",
            "smtpRelay",
            "host",
        ):
            v = d.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    def pick_port() -> int:
        for key in ("smtp_port", "smtpPort", "port", "mailPort", "SmtpPort"):
            v = d.get(key)
            if v is None:
                continue
            try:
                return int(v)
            except (TypeError, ValueError):
                continue
        return 587

    host = pick_host()
    if not host:
        return None

    port = pick_port()
    use_tls = _coerce_bool(d.get("use_tls", d.get("useTls", d.get("tls", d.get("starttls")))), True)
    ssl_mode = str(d.get("ssl_mode", d.get("sslMode", d.get("security", ""))) or "").lower()
    if port == 465:
        use_tls = True
    if ssl_mode in ("ssl", "smtps", "implicit"):
        use_tls = True

    user = str(d.get("smtp_user", d.get("smtpUser", d.get("username", d.get("user", "")))) or "").strip()
    password = str(d.get("smtp_pass", d.get("smtpPassword", d.get("password", d.get("pass", "")))) or "").strip()

    return {
        "smtp_host": host,
        "smtp_port": port,
        "use_tls": use_tls,
        "smtp_user": user,
        "smtp_pass": password,
    }


def _http_get_json(url: str, timeout_sec: float = 1.2) -> Optional[Any]:
    """GET JSON from localhost/gateway; returns parsed object or None."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        ctx = ssl.create_default_context()
        if url.startswith("https://") and ("127.0.0.1" in url or "localhost" in url):
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout_sec, context=ctx if url.startswith("https://") else None) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except Exception:
        return None


def _fetch_gateway_smtp_profile_uncached() -> Optional[Dict[str, Any]]:
    """Probe common MultiTech / gateway localhost REST paths for SMTP settings."""
    paths = [
        "/api/system/email",
        "/api/system/mail",
        "/api/system/smtp",
        "/api/email/config",
        "/api/email/smtp",
        "/api/mail/settings",
        "/api/mail/smtp",
        "/api/smtp",
        "/api/network/smtp",
        "/api/v1/system/email",
        "/api/v1/system/mail",
    ]
    bases = [
        "http://127.0.0.1",
        "http://localhost",
        "https://127.0.0.1",
        "https://localhost",
    ]
    for base in bases:
        for path in paths:
            url = base + path
            data = _http_get_json(url, timeout_sec=1.0)
            if data is None:
                continue
            profile = _normalize_gateway_smtp_dict(data)
            if profile:
                logger.info(f"Gateway SMTP profile loaded from {url}")
                return profile
    return None


def _fetch_gateway_smtp_profile() -> Optional[Dict[str, Any]]:
    now = time.monotonic()
    if (
        _GATEWAY_SMTP_CACHE["profile"] is not None
        and now - float(_GATEWAY_SMTP_CACHE["ts"]) < _GATEWAY_SMTP_CACHE_TTL_SEC
    ):
        return _GATEWAY_SMTP_CACHE["profile"]  # type: ignore[return-value]
    prof = _fetch_gateway_smtp_profile_uncached()
    _GATEWAY_SMTP_CACHE["ts"] = now
    _GATEWAY_SMTP_CACHE["profile"] = prof
    return prof


def _public_gateway_smtp_profile(gw: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not gw:
        return None
    out = {
        "smtp_host": str(gw.get("smtp_host") or ""),
        "smtp_port": int(gw.get("smtp_port") or 587),
        "use_tls": bool(gw.get("use_tls", True)),
        "smtp_user": str(gw.get("smtp_user") or ""),
        "has_password": bool(gw.get("smtp_pass")) and not _smtp_pass_is_placeholder(str(gw.get("smtp_pass") or "")),
    }
    return out


def _smtp_delivery_source_label(file_cfg: Dict[str, Any], gw: Optional[Dict[str, Any]]) -> str:
    if file_cfg.get("use_custom_smtp"):
        return "custom"
    if gw and (str(gw.get("smtp_host") or "").strip()):
        return "gateway"
    if (str(file_cfg.get("smtp_host") or "").strip()):
        return "app"
    return "none"


def _build_effective_email_config(stored: Dict[str, Any]) -> Dict[str, Any]:
    """Merge gateway SMTP (when allowed) with saved file config for sending."""
    out = dict(stored)
    if out.get("use_custom_smtp"):
        return out
    gw = _fetch_gateway_smtp_profile()
    if not gw:
        return out
    gh = (str(gw.get("smtp_host") or "")).strip()
    if not gh:
        return out
    out["smtp_host"] = gh
    out["smtp_port"] = int(gw.get("smtp_port") or out.get("smtp_port") or 587)
    if "use_tls" in gw:
        out["use_tls"] = bool(gw.get("use_tls"))
    gu = (str(gw.get("smtp_user") or "")).strip()
    if gu:
        out["smtp_user"] = gu
    gp = (str(gw.get("smtp_pass") or "")).strip()
    if gp and not _smtp_pass_is_placeholder(gp):
        out["smtp_pass"] = gp
    elif gu and (str(stored.get("smtp_pass") or "")).strip():
        out["smtp_pass"] = str(stored.get("smtp_pass") or "")
    return out


def _send_email_notification(subject: str, body: str, config_data: Dict[str, Any]) -> None:
    """Send email via SMTP using configured connection details."""
    cfg = _build_effective_email_config(config_data)
    smtp_host = str(cfg.get("smtp_host") or "").strip()
    smtp_port = int(cfg.get("smtp_port") or 587)
    smtp_user = str(cfg.get("smtp_user") or "").strip()
    smtp_pass = str(cfg.get("smtp_pass") or "").strip()
    use_tls = bool(cfg.get("use_tls", True))
    from_email = str(cfg.get("from_email") or "").strip()
    to_email = str(cfg.get("to_email") or "").strip()

    missing = []
    if not smtp_host:
        missing.append("smtp_host")
    if not from_email:
        missing.append("from_email")
    if not to_email:
        missing.append("to_email")
    if missing:
        raise ValueError("Missing required email notification fields: " + ", ".join(missing))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(body)

    ctx = ssl.create_default_context()
    if smtp_port == 465 and use_tls:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15, context=ctx) as server:
            if smtp_user:
                if not smtp_pass:
                    raise ValueError("smtp_pass is required when smtp_user is set")
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return

    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
        if use_tls:
            server.starttls(context=ctx)
        if smtp_user:
            if not smtp_pass:
                raise ValueError("smtp_pass is required when smtp_user is set")
            server.login(smtp_user, smtp_pass)
        server.send_message(msg)


def _default_notification_rules() -> Dict[str, Any]:
    return {
        "quiet_hours": {
            "enabled": False,
            "start": "22:00",
            "end": "06:00",
            "timezone_offset_min": 0,
        },
        "escalation": {
            "enabled": False,
            "email": "",
        },
        "rules": [],
    }


def _load_notification_rules() -> Dict[str, Any]:
    if not os.path.isfile(NOTIFICATION_RULES_FILE):
        return _default_notification_rules()
    try:
        with open(NOTIFICATION_RULES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default_notification_rules()
        out = _default_notification_rules()
        out.update({k: v for k, v in data.items() if k in out})
        if not isinstance(out.get("rules"), list):
            out["rules"] = []
        return out
    except Exception as e:
        logger.warning(f"Could not load notification rules config: {e}")
        return _default_notification_rules()


def _save_notification_rules(config_data: Dict[str, Any]) -> None:
    try:
        with open(NOTIFICATION_RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save notification rules config: {e}")


@app.route('/api/device-names', methods=['GET'])
def get_device_names_route():
    """Return DevEUI -> display name map (gateway + local overrides; overrides take precedence)."""
    broker = (request.args.get("broker") or "localhost").strip()
    names: Dict[str, str] = {}
    try:
        gateway = _fetch_gateway_device_names(broker)
        names.update(gateway)
    except Exception as e:
        logger.debug(f"Gateway device names unavailable: {e}")
    overrides = _load_device_name_overrides()
    for k, v in overrides.items():
        if k and v:
            names[k] = v
    return jsonify({"names": names}), 200


@app.route('/api/device-names', methods=['POST'])
def set_device_name_route():
    """Set or clear a local display name override for a DevEUI. Body: { deveui, name }."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        deveui = (data.get("deveui") or "").strip()
        name = (data.get("name") or "").strip()
        if not deveui:
            return jsonify({"error": "deveui required"}), 400
        key = _normalize_deveui_key(deveui)
        if not key:
            return jsonify({"error": "invalid deveui"}), 400
        overrides = _load_device_name_overrides()
        if name:
            overrides[key] = name
        else:
            overrides.pop(key, None)
        _save_device_name_overrides(overrides)
        return jsonify({"deveui": deveui, "name": name or None}), 200
    except Exception as e:
        logger.error(f"Set device name: {e}")
        return jsonify({"error": str(e)}), 500


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
    name_from_gateway = _extract_device_name
    for entry in items:
        dev_eui = _normalize_dev_eui(entry) if isinstance(entry, dict) else None
        if dev_eui and dev_eui not in seen:
            seen.add(dev_eui)
            last_seen = entry.get("last_seen", "") if isinstance(entry, dict) else ""
            name = name_from_gateway(entry) if isinstance(entry, dict) else None
            devices.append({"DevEUI": dev_eui, "last_seen": last_seen, "name": name})
    # Merge with device-names API (gateway whitelist/devices + local overrides)
    try:
        names_map = _fetch_gateway_device_names("localhost")
        names_map.update(_load_device_name_overrides())
        for d in devices:
            key = _normalize_deveui_key(d.get("DevEUI") or "")
            if key and names_map.get(key):
                d["name"] = names_map[key]
    except Exception:
        pass
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


def _invalidate_gateway_smtp_cache() -> None:
    _GATEWAY_SMTP_CACHE["ts"] = 0.0
    _GATEWAY_SMTP_CACHE["profile"] = None


@app.route('/api/notifications/email-config', methods=['GET'])
def get_email_notification_config_route():
    """Return email notification config (with password redacted) and gateway SMTP discovery."""
    file_cfg = _load_email_notification_config()
    gw = _fetch_gateway_smtp_profile()
    eff = _build_effective_email_config(file_cfg)
    pub = _public_email_config(eff)
    pub["use_custom_smtp"] = bool(file_cfg.get("use_custom_smtp"))
    return jsonify(
        {
            "config": pub,
            "gateway_detected": bool(gw and str(gw.get("smtp_host") or "").strip()),
            "gateway_profile": _public_gateway_smtp_profile(gw),
            "smtp_source": _smtp_delivery_source_label(file_cfg, gw),
        }
    ), 200


@app.route('/api/notifications/email-config', methods=['POST'])
def set_email_notification_config_route():
    """Save email notification config."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        existing = _load_email_notification_config()
        merged = dict(existing)
        merged.update(data)
        # Preserve existing password when UI sends empty value.
        incoming_pass = data.get("smtp_pass")
        if incoming_pass is None or str(incoming_pass).strip() == "":
            merged["smtp_pass"] = existing.get("smtp_pass", "")
        cfg = _sanitize_email_notification_config(merged)
        _save_email_notification_config(cfg)
        _invalidate_gateway_smtp_cache()
        gw = _fetch_gateway_smtp_profile()
        eff = _build_effective_email_config(cfg)
        pub = _public_email_config(eff)
        pub["use_custom_smtp"] = bool(cfg.get("use_custom_smtp"))
        return jsonify(
            {
                "success": True,
                "config": pub,
                "gateway_detected": bool(gw and str(gw.get("smtp_host") or "").strip()),
                "gateway_profile": _public_gateway_smtp_profile(gw),
                "smtp_source": _smtp_delivery_source_label(cfg, gw),
            }
        ), 200
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"Set email notification config error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/notifications/email/test', methods=['POST'])
def test_email_notification_route():
    """Send a test email using saved SMTP config."""
    try:
        cfg = _load_email_notification_config()
        subject = "SensorToolset: Test email notification"
        body = (
            "This is a test notification from SensorToolset.\n\n"
            f"Timestamp (UTC): {datetime.now(timezone.utc).isoformat()}\n"
        )
        _send_email_notification(subject, body, cfg)
        return jsonify({"success": True}), 200
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"Test email notification error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/notifications/email/notify-status', methods=['POST'])
def notify_email_sensor_status_route():
    """Send an email status notification for a specific sensor event."""
    try:
        cfg = _load_email_notification_config()
        if not cfg.get("enabled"):
            return jsonify({"success": False, "error": "Email notifications are disabled"}), 400

        data = request.get_json(force=True, silent=True) or {}
        deveui = str(data.get("deveui") or "").strip()
        status = str(data.get("status") or "").strip()
        detail = str(data.get("detail") or "").strip()
        sensor_name = str(data.get("sensor_name") or "").strip()
        if not deveui or not status:
            return jsonify({"success": False, "error": "deveui and status are required"}), 400

        title_device = f"{sensor_name} ({deveui})" if sensor_name else deveui
        subject = f"SensorToolset Alert: {title_device} is {status}"
        body = (
            "Sensor status alert from SensorToolset.\n\n"
            f"Sensor: {title_device}\n"
            f"Status: {status}\n"
            f"Detail: {detail or 'n/a'}\n"
            f"Timestamp (UTC): {datetime.now(timezone.utc).isoformat()}\n"
        )
        _send_email_notification(subject, body, cfg)
        return jsonify({"success": True}), 200
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"Email status notification error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/notifications/email/send', methods=['POST'])
def send_custom_email_notification_route():
    """Send a custom email notification (used by rule engine)."""
    try:
        cfg = _load_email_notification_config()
        if not cfg.get("enabled"):
            return jsonify({"success": False, "error": "Email notifications are disabled"}), 400
        data = request.get_json(force=True, silent=True) or {}
        subject = str(data.get("subject") or "").strip()
        body = str(data.get("body") or "").strip()
        to_email = str(data.get("to_email") or "").strip()
        if not subject or not body:
            return jsonify({"success": False, "error": "subject and body are required"}), 400
        send_cfg = dict(cfg)
        if to_email:
            send_cfg["to_email"] = to_email
        _send_email_notification(subject, body, send_cfg)
        return jsonify({"success": True}), 200
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"Custom email notification error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/notifications/rules', methods=['GET'])
def get_notification_rules_route():
    """Return notification rule/quiet-hours/escalation configuration."""
    return jsonify({"config": _load_notification_rules()}), 200


@app.route('/api/notifications/rules', methods=['POST'])
def set_notification_rules_route():
    """Save notification rule/quiet-hours/escalation configuration."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"success": False, "error": "Invalid payload"}), 400
        cfg = _default_notification_rules()
        cfg.update({k: v for k, v in data.items() if k in ("quiet_hours", "escalation", "rules")})
        if not isinstance(cfg.get("quiet_hours"), dict):
            cfg["quiet_hours"] = _default_notification_rules()["quiet_hours"]
        if not isinstance(cfg.get("escalation"), dict):
            cfg["escalation"] = _default_notification_rules()["escalation"]
        if not isinstance(cfg.get("rules"), list):
            cfg["rules"] = []
        _save_notification_rules(cfg)
        return jsonify({"success": True, "config": cfg}), 200
    except Exception as e:
        logger.error(f"Set notification rules error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/uplinks/persistent-cache', methods=['GET'])
def get_persistent_uplink_cache_route():
    """Return messages from the server-side persistent uplink cache (received even when browser was closed)."""
    try:
        if not MQTT_AVAILABLE:
            return jsonify({"messages": []}), 200
        limit = request.args.get('limit', 5000, type=int)
        limit = min(max(1, limit), 10000)
        since = (request.args.get('since') or '').strip()
        messages = read_persistent_uplink_cache(limit=limit)
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                filtered = []
                for msg in messages:
                    msg_time = (
                        (msg.get("data") or {}).get("current_time")
                        if isinstance(msg.get("data"), dict)
                        else msg.get("time")
                    ) or msg.get("time")
                    if not msg_time:
                        continue
                    try:
                        msg_dt = datetime.fromisoformat(str(msg_time).replace("Z", "+00:00"))
                    except Exception:
                        continue
                    if msg_dt > since_dt:
                        filtered.append(msg)
                messages = filtered
            except Exception:
                # Ignore invalid "since" values and fall back to full response.
                pass
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


@app.route('/api/decoders/radiobridge/update', methods=['POST'])
def update_radiobridge_decoder_route():
    """Fetch the latest RadioBridge decoder bundle from a configured URL and save it under CUSTOM_DECODER_DIR.

    Uses RADIOBRIDGE_DECODER_URL env var if set, otherwise config['radiobridge_decoder_url'].
    Writes JS to RADIOBRIDGE_UPSTREAM_FILENAME and metadata to RADIOBRIDGE_META_FILENAME.
    """
    url = _get_radiobridge_decoder_url()
    if not url:
        return jsonify({"ok": False, "error": "Radiobridge decoder URL is not configured."}), 500

    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return jsonify({"ok": False, "error": "Radiobridge decoder URL must start with http:// or https://"}), 400

    logger.info("Updating RadioBridge decoder from %s", url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SensorToolkit/RadioBridgeUpdater"})
        # Use default SSL context; caller can configure system certificates as needed.
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = getattr(resp, "status", None)
            if status is not None and status != 200:
                return jsonify({"ok": False, "error": f"Upstream returned HTTP {status}"}), 502
            raw_bytes = resp.read()
            if not raw_bytes:
                return jsonify({"ok": False, "error": "Received empty decoder bundle"}), 502
            try:
                content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                # Fallback with replacement characters
                content = raw_bytes.decode("utf-8", errors="replace")
            if not content.strip():
                return jsonify({"ok": False, "error": "Received decoder bundle with no text content"}), 502

            js_path = os.path.join(CUSTOM_DECODER_DIR, RADIOBRIDGE_UPSTREAM_FILENAME)
            meta_path = os.path.join(CUSTOM_DECODER_DIR, RADIOBRIDGE_META_FILENAME)

            # Best-effort basic validation: ensure it at least looks like JS
            if "function" not in content and "=>" not in content and "RBRadioBridgeCore" not in content:
                logger.warning("Radiobridge bundle fetched from %s does not look like JS; aborting update.", url)
                return jsonify({"ok": False, "error": "Decoder bundle does not look like JavaScript"}), 502

            # Atomic write of JS and metadata
            _write_atomic(js_path, content)

            meta = {
                "source_url": url,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "bytes": len(raw_bytes),
                "encoding": "utf-8",
                "etag": getattr(resp, "headers", {}).get("ETag") if hasattr(resp, "headers") else None,
                "last_modified": getattr(resp, "headers", {}).get("Last-Modified") if hasattr(resp, "headers") else None,
            }
            _write_atomic(meta_path, json.dumps(meta, indent=2))

            logger.info(
                "Updated RadioBridge decoder bundle at %s (%d bytes)",
                js_path,
                len(raw_bytes),
            )
            return jsonify({"ok": True, "meta": meta}), 200
    except urllib.error.HTTPError as e:
        logger.error("Failed to update RadioBridge decoder (HTTPError): %s", e)
        return jsonify({"ok": False, "error": f"HTTP error from upstream: {e.code}"}), 502
    except urllib.error.URLError as e:
        logger.error("Failed to update RadioBridge decoder (URLError): %s", e)
        reason = getattr(e, "reason", None)
        return jsonify({"ok": False, "error": str(reason or e)}), 502
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to update RadioBridge decoder: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


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


@app.route('/api/decoders/radiobridge/metadata', methods=['GET'])
def get_radiobridge_decoder_metadata_route():
    """Return metadata about the currently installed RadioBridge decoder bundle (if any)."""
    meta_path = os.path.join(CUSTOM_DECODER_DIR, RADIOBRIDGE_META_FILENAME)
    if not os.path.isfile(meta_path):
        return jsonify({"ok": False, "meta": None}), 200
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return jsonify({"ok": True, "meta": meta}), 200
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not read RadioBridge decoder metadata: %s", e)
        return jsonify({"ok": False, "meta": None, "error": str(e)}), 200


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
    if not _is_logged_in():
        return redirect(url_for('login'))
    return send_file(os.path.join(TEMPLATES_DIR, "cloud_integrations.html"))


@app.route('/cloud_integrations.html')
def cloud_integrations_html():
    """Alias for cloud integrations page (nav links use .html)."""
    return cloud_integrations_page()


@app.route('/notifications')
@app.route('/notifications.html')
def notifications_page():
    """Serve the notifications page (requires login)."""
    if not _is_logged_in():
        return redirect(url_for('login'))
    return send_file(os.path.join(TEMPLATES_DIR, "notifications.html"))


@app.route('/notifications/delivery')
@app.route('/notifications/delivery.html')
def notifications_delivery_page():
    """Email transport (gateway vs custom SMTP) configuration."""
    if not _is_logged_in():
        return redirect(url_for('login'))
    return send_file(os.path.join(TEMPLATES_DIR, "notifications_delivery.html"))


@app.route('/notifications/edit')
@app.route('/notifications/edit.html')
def notifications_edit_page():
    """Add or edit a single notification rule."""
    if not _is_logged_in():
        return redirect(url_for('login'))
    return send_file(os.path.join(TEMPLATES_DIR, "notifications_edit.html"))


@app.route('/uplinks.html')
def uplinks_page():
    """Serve the uplinks page (requires login)."""
    if not _is_logged_in():
        return redirect(url_for('login'))
    return send_file(os.path.join(TEMPLATES_DIR, "uplinks.html"))


@app.route('/decoders.html')
def decoders_page():
    """Serve the decoders page (requires login)."""
    if not _is_logged_in():
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

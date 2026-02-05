"""
Cloud Integrations Module

Forwards decoded/raw uplink data to external cloud services via:
- MQTT (publish to external broker)
- HTTP Webhook (POST JSON)
- UDP (send datagram)
- TCP (persistent connection)

Configuration is stored in config/cloud_integrations.json
"""

import json
import logging
import os
import queue
import socket
import ssl
import tempfile
import threading
import time
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)

from app_paths import get_config_dir

# Configuration file path (writable)
CONFIG_DIR = get_config_dir()
CONFIG_FILE = os.path.join(CONFIG_DIR, "cloud_integrations.json")

# Thread-safe queue for async forwarding
_forward_queue: queue.Queue = queue.Queue(maxsize=10000)
_worker_thread: Optional[threading.Thread] = None
_worker_running = False

# Active connections (for TCP/MQTT)
_connections: Dict[str, Any] = {}
_connections_lock = threading.Lock()

# Temp files for MQTT TLS certs (PEM content written to disk for paho-mqtt); cleaned on disconnect
_mqtt_cert_temp_files: Dict[str, List[str]] = {}

# MQTT client (optional import)
try:
    import paho.mqtt.client as mqtt
    PAHO_AVAILABLE = True
except ImportError:
    PAHO_AVAILABLE = False
    mqtt = None


def _ensure_config_dir():
    """Ensure config directory exists."""
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_config() -> Dict[str, Any]:
    """Load integrations configuration from JSON file."""
    _ensure_config_dir()
    if not os.path.exists(CONFIG_FILE):
        return {"integrations": []}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"integrations": []}
            if "integrations" not in data:
                data["integrations"] = []
            return data
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load cloud integrations config: {e}")
        return {"integrations": []}


def save_config(config: Dict[str, Any]) -> bool:
    """Save integrations configuration to JSON file."""
    _ensure_config_dir()
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return True
    except IOError as e:
        logger.error(f"Failed to save cloud integrations config: {e}")
        return False


def get_integrations() -> List[Dict[str, Any]]:
    """Get list of all configured integrations."""
    return load_config().get("integrations", [])


def get_integration(integration_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific integration by ID."""
    for integ in get_integrations():
        if integ.get("id") == integration_id:
            return integ
    return None


def add_integration(integration: Dict[str, Any]) -> Dict[str, Any]:
    """Add a new integration. Returns the integration with assigned ID."""
    config = load_config()
    integration = dict(integration)
    integration["id"] = str(uuid.uuid4())
    integration.setdefault("enabled", True)
    integration.setdefault("name", "Unnamed Integration")
    integration.setdefault("type", "webhook")
    integration.setdefault("config", {})
    integration.setdefault("filters", {})
    integration.setdefault("payload", {"format": "both", "include_metadata": True})
    integration["created_at"] = datetime.now(timezone.utc).isoformat()
    integration["updated_at"] = integration["created_at"]
    config["integrations"].append(integration)
    save_config(config)
    return integration


def update_integration(integration_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update an existing integration. Returns updated integration or None."""
    config = load_config()
    for i, integ in enumerate(config["integrations"]):
        if integ.get("id") == integration_id:
            # Merge updates
            for key, value in updates.items():
                if key != "id":  # Don't allow changing ID
                    integ[key] = value
            integ["updated_at"] = datetime.now(timezone.utc).isoformat()
            config["integrations"][i] = integ
            save_config(config)
            # Reconnect if needed
            _reconnect_integration(integration_id)
            return integ
    return None


def delete_integration(integration_id: str) -> bool:
    """Delete an integration by ID."""
    config = load_config()
    original_len = len(config["integrations"])
    config["integrations"] = [i for i in config["integrations"] if i.get("id") != integration_id]
    if len(config["integrations"]) < original_len:
        save_config(config)
        _disconnect_integration(integration_id)
        return True
    return False


def toggle_integration(integration_id: str, enabled: bool) -> Optional[Dict[str, Any]]:
    """Enable or disable an integration."""
    return update_integration(integration_id, {"enabled": enabled})


# --- Forwarding Logic ---

def _matches_filters(message: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    """Check if a message matches the integration's filters."""
    if not filters:
        return True
    
    # DevEUI filter
    deveui_filter = filters.get("deveui", [])
    if deveui_filter:
        msg_deveui = message.get("deveui", "")
        if not msg_deveui:
            # Try to get from data
            data = message.get("data", {})
            if isinstance(data, dict):
                msg_deveui = data.get("deveui", "")
        if msg_deveui and msg_deveui.lower().replace("-", "") not in [d.lower().replace("-", "") for d in deveui_filter]:
            return False
    
    # Event type filter
    event_filter = filters.get("event_types", [])
    if event_filter:
        msg_event = message.get("event_type", message.get("eventType", ""))
        if msg_event and msg_event.lower() not in [e.lower() for e in event_filter]:
            return False
    
    return True


def _build_payload(message: Dict[str, Any], payload_config: Dict[str, Any]) -> Dict[str, Any]:
    """Build the payload to send based on configuration."""
    fmt = payload_config.get("format", "both")
    include_meta = payload_config.get("include_metadata", True)
    
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    # Extract DevEUI
    deveui = message.get("deveui", "")
    if not deveui:
        data = message.get("data", {})
        if isinstance(data, dict):
            deveui = data.get("deveui", "")
    result["deveui"] = deveui
    
    if fmt in ("raw", "both"):
        # Include raw data
        data = message.get("data", {})
        if isinstance(data, dict):
            result["raw"] = {
                "payload_base64": data.get("data", ""),
                "port": data.get("port"),
                "topic": message.get("topic", ""),
            }
        else:
            result["raw"] = {"data": data}
    
    if fmt in ("decoded", "both"):
        # Include decoded data
        decoded = message.get("decoded", message.get("data_decoded", {}))
        result["decoded"] = decoded
    
    if include_meta:
        data = message.get("data", {})
        if isinstance(data, dict):
            result["metadata"] = {
                "rssi": data.get("rssi"),
                "snr": data.get("snr"),
                "freq": data.get("freq"),
                "dr": data.get("dr"),
                "time": data.get("time", message.get("time")),
            }
    
    return result


def _forward_webhook(integration: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    """Forward payload to HTTP webhook."""
    cfg = integration.get("config", {})
    url = cfg.get("url", "")
    if not url:
        logger.warning(f"Webhook integration {integration.get('id')} has no URL")
        return False
    
    method = cfg.get("method", "POST").upper()
    headers = {"Content-Type": "application/json"}
    
    # Add custom headers
    custom_headers = cfg.get("headers", {})
    if isinstance(custom_headers, dict):
        headers.update(custom_headers)
    
    # Add auth header if configured
    auth_type = cfg.get("auth_type", "none")
    if auth_type == "bearer":
        token = cfg.get("auth_token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    elif auth_type == "basic":
        import base64
        username = cfg.get("auth_username", "")
        password = cfg.get("auth_password", "")
        if username:
            creds = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {creds}"
    elif auth_type == "api_key":
        key_name = cfg.get("api_key_name", "X-API-Key")
        key_value = cfg.get("api_key_value", "")
        if key_value:
            headers[key_name] = key_value
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        
        # SSL context (allow self-signed for internal services)
        ctx = ssl.create_default_context()
        if cfg.get("skip_ssl_verify", False):
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        
        timeout = cfg.get("timeout", 10)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            status = resp.getcode()
            if 200 <= status < 300:
                return True
            else:
                logger.warning(f"Webhook {integration.get('name')} returned {status}")
                return False
    except Exception as e:
        logger.warning(f"Webhook {integration.get('name')} failed: {e}")
        return False


def _write_pem_temp_file(integration_id: str, pem_content: str, prefix: str) -> Optional[str]:
    """Write PEM content to a temp file; track it for cleanup. Returns path or None."""
    if not pem_content or not pem_content.strip():
        return None
    try:
        fd, path = tempfile.mkstemp(suffix=".pem", prefix=f"rbt_mqtt_{prefix}_")
        try:
            os.write(fd, pem_content.strip().encode("utf-8"))
        finally:
            os.close(fd)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        _mqtt_cert_temp_files.setdefault(integration_id, []).append(path)
        return path
    except Exception as e:
        logger.warning(f"Failed to write MQTT cert temp file {prefix}: {e}")
        return None


def _forward_mqtt(integration: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    """Forward payload to external MQTT broker."""
    if not PAHO_AVAILABLE:
        logger.warning("paho-mqtt not available for cloud MQTT integration")
        return False
    
    cfg = integration.get("config", {})
    broker = cfg.get("broker", "")
    port = cfg.get("port", 1883)
    topic = cfg.get("topic", "sensor/uplinks")
    
    if not broker:
        logger.warning(f"MQTT integration {integration.get('id')} has no broker")
        return False
    
    integration_id = integration.get("id")
    
    with _connections_lock:
        client = _connections.get(f"mqtt_{integration_id}")
        
        if client is None or not client.is_connected():
            # Create new connection
            try:
                client = mqtt.Client(client_id=f"rbt_cloud_{integration_id[:8]}")
                
                # Auth
                username = cfg.get("username", "")
                password = cfg.get("password", "")
                if username:
                    client.username_pw_set(username, password)
                
                # TLS with optional certificates (CA, client cert, client key)
                if cfg.get("use_tls", False):
                    ca_pem = (cfg.get("mqtt_ca_cert_pem") or "").strip()
                    client_cert_pem = (cfg.get("mqtt_client_cert_pem") or "").strip()
                    client_key_pem = (cfg.get("mqtt_client_key_pem") or "").strip()
                    ca_path = _write_pem_temp_file(integration_id, ca_pem, "ca") if ca_pem else None
                    cert_path = _write_pem_temp_file(integration_id, client_cert_pem, "cert") if client_cert_pem else None
                    key_path = _write_pem_temp_file(integration_id, client_key_pem, "key") if client_key_pem else None
                    if cert_path and not key_path:
                        logger.warning("MQTT: client certificate set without key; ignoring client cert")
                        cert_path = key_path = None
                    elif key_path and not cert_path:
                        logger.warning("MQTT: client key set without certificate; ignoring client key")
                        cert_path = key_path = None
                    if ca_path or cert_path:
                        client.tls_set(
                            ca_certs=ca_path,
                            certfile=cert_path,
                            keyfile=key_path,
                            cert_reqs=ssl.CERT_NONE if cfg.get("skip_ssl_verify", False) else ssl.CERT_REQUIRED,
                        )
                    else:
                        client.tls_set()
                    if cfg.get("skip_ssl_verify", False):
                        client.tls_insecure_set(True)
                
                client.connect(broker, port, keepalive=60)
                client.loop_start()
                _connections[f"mqtt_{integration_id}"] = client
                
                # Wait briefly for connection
                time.sleep(0.2)
            except Exception as e:
                logger.warning(f"MQTT integration {integration.get('name')} connect failed: {e}")
                # Clean up temp cert files on connect failure
                for p in _mqtt_cert_temp_files.pop(integration_id, []):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
                return False
    
    try:
        # Replace {deveui} placeholder in topic
        deveui = payload.get("deveui", "unknown")
        actual_topic = topic.replace("{deveui}", deveui.replace("-", ""))
        
        result = client.publish(actual_topic, json.dumps(payload), qos=cfg.get("qos", 1))
        return result.rc == 0
    except Exception as e:
        logger.warning(f"MQTT integration {integration.get('name')} publish failed: {e}")
        return False


def _forward_udp(integration: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    """Forward payload via UDP."""
    cfg = integration.get("config", {})
    host = cfg.get("host", "")
    port = cfg.get("port", 0)
    
    if not host or not port:
        logger.warning(f"UDP integration {integration.get('id')} has no host/port")
        return False
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        data = json.dumps(payload).encode("utf-8")
        sock.sendto(data, (host, int(port)))
        sock.close()
        return True
    except Exception as e:
        logger.warning(f"UDP integration {integration.get('name')} failed: {e}")
        return False


def _forward_tcp(integration: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    """Forward payload via TCP (persistent connection)."""
    cfg = integration.get("config", {})
    host = cfg.get("host", "")
    port = cfg.get("port", 0)
    
    if not host or not port:
        logger.warning(f"TCP integration {integration.get('id')} has no host/port")
        return False
    
    integration_id = integration.get("id")
    delimiter = cfg.get("delimiter", "\n")
    
    with _connections_lock:
        sock = _connections.get(f"tcp_{integration_id}")
        
        if sock is None:
            # Create new connection
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(cfg.get("timeout", 10))
                
                # TLS
                if cfg.get("use_tls", False):
                    ctx = ssl.create_default_context()
                    if cfg.get("skip_ssl_verify", False):
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                    sock = ctx.wrap_socket(sock, server_hostname=host)
                
                sock.connect((host, int(port)))
                _connections[f"tcp_{integration_id}"] = sock
            except Exception as e:
                logger.warning(f"TCP integration {integration.get('name')} connect failed: {e}")
                _connections.pop(f"tcp_{integration_id}", None)
                return False
    
    try:
        data = json.dumps(payload) + delimiter
        sock.sendall(data.encode("utf-8"))
        return True
    except Exception as e:
        logger.warning(f"TCP integration {integration.get('name')} send failed: {e}")
        # Close broken connection
        with _connections_lock:
            _connections.pop(f"tcp_{integration_id}", None)
        try:
            sock.close()
        except:
            pass
        return False


def _disconnect_integration(integration_id: str):
    """Disconnect any active connections for an integration."""
    with _connections_lock:
        # MQTT
        mqtt_key = f"mqtt_{integration_id}"
        if mqtt_key in _connections:
            try:
                _connections[mqtt_key].loop_stop()
                _connections[mqtt_key].disconnect()
            except Exception:
                pass
            del _connections[mqtt_key]
        # Remove temp cert files for this MQTT integration
        for path in _mqtt_cert_temp_files.pop(integration_id, []):
            try:
                os.unlink(path)
            except OSError:
                pass

        # TCP
        tcp_key = f"tcp_{integration_id}"
        if tcp_key in _connections:
            try:
                _connections[tcp_key].close()
            except:
                pass
            del _connections[tcp_key]


def _reconnect_integration(integration_id: str):
    """Reconnect an integration (disconnect then let next message reconnect)."""
    _disconnect_integration(integration_id)


def _process_forward(item: Dict[str, Any]):
    """Process a single forward item from the queue."""
    integration = item.get("integration")
    message = item.get("message")
    
    if not integration or not message:
        return
    
    if not integration.get("enabled", True):
        return
    
    # Check filters
    if not _matches_filters(message, integration.get("filters", {})):
        return
    
    # Build payload
    payload = _build_payload(message, integration.get("payload", {}))
    
    # Forward based on type
    integ_type = integration.get("type", "webhook")
    
    if integ_type == "webhook":
        _forward_webhook(integration, payload)
    elif integ_type == "mqtt":
        _forward_mqtt(integration, payload)
    elif integ_type == "udp":
        _forward_udp(integration, payload)
    elif integ_type == "tcp":
        _forward_tcp(integration, payload)
    else:
        logger.warning(f"Unknown integration type: {integ_type}")


def _worker_loop():
    """Background worker that processes the forward queue."""
    global _worker_running
    while _worker_running:
        try:
            item = _forward_queue.get(timeout=1.0)
            _process_forward(item)
            _forward_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Cloud integration worker error: {e}")


def start_worker():
    """Start the background forwarding worker thread."""
    global _worker_thread, _worker_running
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _worker_running = True
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True)
    _worker_thread.start()
    logger.info("Cloud integrations worker started")


def stop_worker():
    """Stop the background forwarding worker thread."""
    global _worker_running
    _worker_running = False
    if _worker_thread:
        _worker_thread.join(timeout=2.0)
    
    # Close all connections
    with _connections_lock:
        for key in list(_connections.keys()):
            try:
                conn = _connections[key]
                if hasattr(conn, "loop_stop"):
                    conn.loop_stop()
                    conn.disconnect()
                elif hasattr(conn, "close"):
                    conn.close()
            except:
                pass
        _connections.clear()
    logger.info("Cloud integrations worker stopped")


def forward_message(message: Dict[str, Any]):
    """
    Queue a message for forwarding to all enabled integrations.
    Called from mqtt_utils_rbt.py when an uplink is received.
    """
    integrations = get_integrations()
    for integ in integrations:
        if integ.get("enabled", True):
            try:
                _forward_queue.put_nowait({
                    "integration": integ,
                    "message": message,
                })
            except queue.Full:
                logger.warning("Cloud integration queue full, dropping message")


def test_integration(integration: Dict[str, Any]) -> Dict[str, Any]:
    """
    Test an integration with a sample message.
    Returns {"success": bool, "message": str}
    """
    # Create test payload
    test_message = {
        "topic": "test/message",
        "deveui": "00-00-00-00-00-00-00-00",
        "time": datetime.now(timezone.utc).isoformat(),
        "data": {
            "deveui": "00-00-00-00-00-00-00-00",
            "data": "AgFkAAo=",  # Sample base64
            "port": 1,
            "rssi": -85,
            "snr": 7.5,
        },
        "decoded": {
            "event": "test",
            "message": "Test message from Sensor Toolkit cloud integration",
        },
    }
    
    payload = _build_payload(test_message, integration.get("payload", {"format": "both", "include_metadata": True}))
    
    integ_type = integration.get("type", "webhook")
    
    try:
        if integ_type == "webhook":
            success = _forward_webhook(integration, payload)
        elif integ_type == "mqtt":
            success = _forward_mqtt(integration, payload)
        elif integ_type == "udp":
            success = _forward_udp(integration, payload)
        elif integ_type == "tcp":
            success = _forward_tcp(integration, payload)
        else:
            return {"success": False, "message": f"Unknown integration type: {integ_type}"}
        
        if success:
            return {"success": True, "message": "Test message sent successfully"}
        else:
            return {"success": False, "message": "Failed to send test message (check logs)"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# Auto-start worker when module is imported
start_worker()

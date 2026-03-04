# RadioBridge Tools - Linux Gateway Application

This application is designed to run as a custom application on MultiTech Linux-based gateways (mPower framework).

## Application Structure

The application follows the mPower custom application framework structure:

```
RadioBridgeTools/
├── Install              # Installation script for dependencies
├── Start                # Start/stop script for app lifecycle
├── manifest.json        # Application metadata
├── server.py            # Flask server to serve static HTML files
├── requirements.txt     # Python dependencies
├── config/              # Configuration directory
│   ├── example.cfg.json # Example configuration file
│   └── radioBridgeTools.cfg.json # Default configuration
├── provisioning/        # Dependency packages
│   ├── p_manifest.json  # Package manifest
├── README.md            # Provisioning documentation
└── [HTML/CSS/JS files]  # Application static files
```

## Installation



**Standard (gateway has internet):**

1. Package the application directory into a tar.gz file
2. Upload to the gateway via the mPower web interface
3. The app-manager will automatically:
   - Run `Install install` to install system dependencies
   - Run `Install postinstall` to install Python dependencies
   - Run `Start start` to start the application

*Application  takes several minutes to install.
Open an input firewall filter to allow access to tcp port from your config(default:5000)

## Configuration

The application can be configured via the `config/radioBridgeTools.cfg.json` file:

```json
{
    "host": "0.0.0.0",
    "port": 5000,
    "debug": false,
    "radiobridge_decoder_url": "https://webfiles.multitech.com/BACnet/MultiTech/RadioBridgeDecoder/radio_bridge_packet_decoder.js"
}
```

- `host`: The host address to bind the server to (default: "0.0.0.0")
- `port`: The port number to run the server on (default: 5000)
- `debug`: Enable debug mode for Flask (default: false)
- `radiobridge_decoder_url`: Optional URL for the upstream RadioBridge decoder bundle. This is used by the **Sensor Library** page when you click **Update RadioBridge Decoder**. It can also be overridden at runtime with the `RADIOBRIDGE_DECODER_URL` environment variable.

## Application Lifecycle

The `Start` script handles the application lifecycle:

- `start`: Starts the Flask server
- `stop`: Stops the Flask server
- `restart`: Restarts the Flask server
- `reload`: Reloads configuration (currently just a placeholder)

## Dependencies

### System Dependencies (IPK packages)
- python3-xmlrpc
- python3-pip
- python3-misc
- python3-multiprocessing
- python3-mmap

### Python Dependencies (current iteration does require internet access to install)
- flask~=3.0.3
- werkzeug~=3.0.3
- jinja2~=3.1.4

## Accessing the Application

Once installed and started, the application will be accessible at:
- `http://<gateway-ip>:5000`

## Web UI overview

The web UI is organized into several main pages:

- **Home** – Landing page with tiles linking to each major workflow (Uplinks, Send Downlinks, Sensor Monitor, Sensor Library, Cloud Integrations, RadioBridge Config).
- **Uplinks** – Connects to the gateway's MQTT broker and shows a live/cached table of uplink messages. A compact **MQTT** bar lets you set broker/port/topic; a condensed **Filters & Cache** bar lets you filter by DevEUI, event type, time range, and view mode (decoded/raw/both), and manage the local cache (import, CSV/JSON export, clear).
- **Send Downlinks** – Uses the same MQTT connection to send downlinks to a selected device. Supports:
  - **Build from encoder**: choose a codec/command, fill in parameters, and let the encoder build the payload.
  - **Raw hex / base64**: send a manual payload on a chosen port.
- **Sensor Monitor** – Live/near‑real‑time visualization of sensor state and history (including door/window and movement), with charts and per‑sensor snapshots.
- **Sensor Library** – Central place to manage decoders/encoders:
  - **Upload decoders / encoders**: upload `.js` files, or paste code and save.
  - **Test JavaScript code**: small editor with syntax highlighting to run decoder/encoder JavaScript in the browser before saving it.
  - **Installed decoders / encoders**: table of installed files with actions.
  - **Update RadioBridge Decoder**: fetches and installs the latest RadioBridge core decoder bundle from `radiobridge_decoder_url`, while keeping local application‑specific integrations.
- **RadioBridge Config** – UI for building RadioBridge‑specific configuration downlinks using the app's encoder logic.
- **Cloud Integrations** – Configure forwarding of decoded uplinks to external systems (HTTP/MQTT/UDP/TCP), with filters and test tools.

## Manual Testing

To test the application manually on the gateway:

```bash
# Set environment variables
export APP_DIR=$(pwd)
export CONFIG_DIR=$(pwd)/config

# Start the application
sudo ./Start start

# Stop the application
sudo ./Start stop

# Restart the application
sudo ./Start restart
```

## Logging

Application logs can be found in:
- `/var/log/messages` - System logs
- `debug_log.txt` - Application debug log (if enabled)

## Notes

- The application uses Flask to serve static HTML/CSS/JS files
- All sensor configuration pages are served from the root directory
- The server automatically handles routing for nested directories
- The application is designed to run as a background service managed by app-manager



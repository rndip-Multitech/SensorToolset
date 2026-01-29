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
│   └── README.md        # Provisioning documentation
└── [HTML/CSS/JS files]  # Application static files
```

## Installation

**Offline (no internet on gateway):** See [OFFLINE_INSTALL.md](OFFLINE_INSTALL.md) for building a self-contained binary on a Linux build machine and deploying it to the gateway without Python/pip, or for installing from source using offline pip (wheels).

**Standard (gateway has internet):**

1. Package the application directory into a tar.gz file
2. Upload to the gateway via the mPower web interface
3. The app-manager will automatically:
   - Run `Install install` to install system dependencies
   - Run `Install postinstall` to install Python dependencies
   - Run `Start start` to start the application

## Configuration

The application can be configured via the `config/radioBridgeTools.cfg.json` file:

```json
{
    "host": "0.0.0.0",
    "port": 5000,
    "debug": false
}
```

- `host`: The host address to bind the server to (default: "0.0.0.0")
- `port`: The port number to run the server on (default: 5000)
- `debug`: Enable debug mode for Flask (default: false)

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

### Python Dependencies
- flask~=3.0.3
- werkzeug~=3.0.3
- jinja2~=3.1.4

## Accessing the Application

Once installed and started, the application will be accessible at:
- `http://<gateway-ip>:5000`

The application serves the RadioBridge Sensor Configuration Tool, allowing users to:
- Configure general sensor settings
- Configure advanced sensor settings
- Generate hexcodes for various RadioBridge sensor types

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



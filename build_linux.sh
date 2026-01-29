#!/bin/bash
# Offline distribution build for Linux (e.g. LoRaWAN gateway).
# Produces a self-contained folder in ./dist/RadioBridgeTools/ (no pip on target).
#
# Build on a Linux machine with Python and PyInstaller installed:
#   pip install -r requirements.txt -r requirements-build.txt
#   ./build_linux.sh
#
# Then copy dist/RadioBridgeTools/ to the gateway and run:
#   ./RadioBridgeTools --host 0.0.0.0 --port 5000
# Or use Start script: point APP_DIR to the unpacked folder and run ./Start start.

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

python3 -m PyInstaller --noconfirm --clean \
  --name RadioBridgeTools \
  --onedir \
  --paths "NetworkDashboard-0.1/static/py" \
  --add-data "NetworkDashboard-0.1:NetworkDashboard-0.1" \
  --add-data "AdvancedConfig:AdvancedConfig" \
  --add-data "GeneralConfig:GeneralConfig" \
  --add-data "RBS301-CON:RBS301-CON" \
  --add-data "RBS301-DWS:RBS301-DWS" \
  --add-data "RBS301-PB:RBS301-PB" \
  --add-data "RBS301-TILT:RBS301-TILT" \
  --add-data "RBS306-420MA:RBS306-420MA" \
  --add-data "RBS306-ATH:RBS306-ATH" \
  --add-data "RBS306-ULS:RBS306-ULS" \
  --add-data "RBS30X-ABM:RBS30X-ABM" \
  --add-data "RBS30x-TEMP:RBS30x-TEMP" \
  --add-data "RBS30x-WAT:RBS30x-WAT" \
  --add-data "MultiTech_Logo.png:." \
  --add-data "styles.css:." \
  --add-data "*.html:." \
  --add-data "manifest.json:." \
  server.py

echo ""
echo "Build complete:"
echo "  dist/RadioBridgeTools/RadioBridgeTools"
echo ""
echo "Deploy to gateway (e.g. copy dist/RadioBridgeTools/ to device), then:"
echo "  ./RadioBridgeTools --host 0.0.0.0 --port 5000"
echo "Or with Start script: APP_DIR=/path/to/RadioBridgeTools ./Start start"


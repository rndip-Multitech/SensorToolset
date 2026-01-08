#!/bin/bash
# Diagnostic script to troubleshoot server issues

echo "=== RadioBridge Tools Server Troubleshooting ==="
echo ""

# 1. Check if server process is running
echo "1. Checking if server process is running..."
if [ -f "/var/run/RadioBridgeTools.pid" ]; then
    PID=$(cat /var/run/RadioBridgeTools.pid)
    echo "   PID file exists: /var/run/RadioBridgeTools.pid (PID: $PID)"
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "   âœ“ Process is running (PID: $PID)"
        ps -p "$PID" -o pid,cmd
    else
        echo "   âœ— Process is NOT running (stale PID file)"
    fi
else
    echo "   âœ— PID file not found"
fi

# Check for python3 server processes
ps aux | grep -E "[p]ython3.*server\.py" || echo "   âœ— No python3 server.py process found"
echo ""

# 2. Check if port 5000 is listening
echo "2. Checking if port 5000 is listening..."
if command -v netstat >/dev/null 2>&1; then
    netstat -tlnp | grep :5000 && echo "   âœ“ Port 5000 is listening" || echo "   âœ— Port 5000 is NOT listening"
elif command -v ss >/dev/null 2>&1; then
    ss -tlnp | grep :5000 && echo "   âœ“ Port 5000 is listening" || echo "   âœ— Port 5000 is NOT listening"
else
    echo "   (netstat/ss not available)"
fi
echo ""

# 3. Find app directory
echo "3. Finding app directory..."
APP_DIR=""
for dir in "/var/persistent/RadioBridge Tools" "/var/config/app/RadioBridge Tools" "/media/card/RadioBridge Tools"; do
    if [ -d "$dir" ]; then
        APP_DIR="$dir"
        echo "   Found: $APP_DIR"
        break
    fi
done

if [ -z "$APP_DIR" ]; then
    echo "   âœ— App directory not found"
else
    echo "   App directory: $APP_DIR"
    ls -la "$APP_DIR/server.py" 2>/dev/null && echo "   âœ“ server.py exists" || echo "   âœ— server.py not found"
    ls -la "$APP_DIR/Start" 2>/dev/null && echo "   âœ“ Start script exists" || echo "   âœ— Start script not found"
    ls -la "$APP_DIR/config/radioBridgeTools.cfg.json" 2>/dev/null && echo "   âœ“ Config file exists" || echo "   âœ— Config file not found"
fi
echo ""

# 4. Check Flask installation
echo "4. Checking Flask installation..."
python3 -c "import flask; print('   âœ“ Flask version:', flask.__version__)" 2>/dev/null || echo "   âœ— Flask not installed"
python3 -c "import werkzeug" 2>/dev/null && echo "   âœ“ Werkzeug installed" || echo "   âœ— Werkzeug not installed"
python3 -c "import jinja2" 2>/dev/null && echo "   âœ“ Jinja2 installed" || echo "   âœ— Jinja2 not installed"
echo ""

# 5. Check recent logs
echo "5. Checking recent logs..."
if [ -f "/var/log/messages" ]; then
    echo "   Recent Install/RadioBridgeTools/Start log entries:"
    tail -30 /var/log/messages | grep -i "radiobridge\|install\|start" | tail -10
fi

if [ -n "$APP_DIR" ] && [ -f "$APP_DIR/debug_log.txt" ]; then
    echo ""
    echo "   Debug log (last 20 lines):"
    tail -20 "$APP_DIR/debug_log.txt"
fi
echo ""

# 6. Try to manually start the server (test)
echo "6. Testing server startup..."
if [ -n "$APP_DIR" ]; then
    echo "   Testing if server can start..."
    cd "$APP_DIR"
    export APP_DIR="$APP_DIR"
    export CONFIG_DIR="$APP_DIR/config"
    
    # Test if we can import and run the server
    timeout 2 python3 -c "
import sys
sys.path.insert(0, '$APP_DIR')
try:
    from server import app
    print('   âœ“ Server module can be imported')
    print('   âœ“ Flask app object created')
except Exception as e:
    print('   âœ— Error importing/running server:', str(e))
" 2>&1
else
    echo "   âœ— Cannot test - app directory not found"
fi
echo ""

# 7. Check firewall rules
echo "7. Checking firewall rules..."
if command -v iptables >/dev/null 2>&1; then
    echo "   Checking iptables rules for port 5000:"
    iptables -L -n | grep 5000 || echo "   (No specific rules for port 5000 found)"
else
    echo "   (iptables not available)"
fi
echo ""

echo "=== Troubleshooting Complete ==="


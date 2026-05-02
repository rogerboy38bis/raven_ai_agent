#!/bin/bash
# Start All Services Script
# Starts Flask web app and ngrok tunnel for weight capture station

# Usage: ./start_all.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "AMB Weight Capture Station"
echo "========================================"
echo ""

# Check for Python virtual environment
if [ ! -d "../raven-env" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv ../raven-env
fi

# Activate virtual environment
echo "Activating virtual environment..."
source ../raven-env/bin/activate

# Install/update requirements
echo "Installing dependencies..."
pip install --quiet flask>=3.0 pyserial>=3.5 requests>=2.32

# Check if ngrok is installed
if ! command -v ngrok &> /dev/null; then
    echo "WARNING: ngrok not found in PATH"
    echo "Install from: https://ngrok.com/download"
fi

# Check for ngrok config
NGROK_CONFIG_DIR="$HOME/.config/ngrok"
NGROK_CONFIG="$NGROK_CONFIG_DIR/ngrok.yml"

if [ ! -f "$NGROK_CONFIG" ]; then
    echo "WARNING: ngrok config not found at $NGROK_CONFIG"
    echo "Create it with:"
    echo "  mkdir -p $NGROK_CONFIG_DIR"
    echo "  cat > $NGROK_CONFIG << 'EOF'"
    echo "version: \"3\""
    echo "agent:"
    echo "    authtoken: <your_token>"
    echo "tunnels:"
    echo "  bot-iot-web:"
    echo "    proto: http"
    echo "    addr: 5000"
    echo "    domain: bot1.sysmayal.ngrok.io"
    echo "EOF"
fi

echo ""
echo "Starting Flask web server on port 5000..."
python3 web_app.py &
FLASK_PID=$!

echo "Starting ngrok tunnel..."
ngrok start bot-iot-web &
NGROK_PID=$!

echo ""
echo "========================================"
echo "Services Started"
echo "========================================"
echo "Flask PID: $FLASK_PID"
echo "ngrok PID: $NGROK_PID"
echo ""
echo "Weight station running at: https://bot1.sysmayal.ngrok.io"
echo ""
echo "Logs:"
echo "  Flask: /tmp/weight_capture.log"
echo "  ngrok: http://localhost:4040"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for any process to exit
wait

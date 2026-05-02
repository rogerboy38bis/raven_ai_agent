#!/bin/bash
# RPi Scale Weight Capture Setup Script
# Run: bash setup_scale.sh
#
# This script sets up the weight capture client for Raspberry Pi
# with proper Python venv support for Debian-based systems (including RPi OS)

set -e

echo "=== RPi Scale Weight Capture Setup ==="
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "WARNING: Running as root is not recommended."
    echo "Press Ctrl+C to cancel, or Enter to continue..."
    read
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[1/6] Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-full python3-venv python3-pip

echo ""
echo "[2/6] Creating Python virtual environment..."

# Remove old venv if it exists and is broken
if [ -d "raven-env" ]; then
    if [ ! -f "raven-env/bin/python3" ]; then
        echo "  Removing broken virtual environment..."
        rm -rf raven-env
    fi
fi

# Create virtual environment
python3 -m venv raven-env

echo "  Virtual environment created at: $(pwd)/raven-env"

echo ""
echo "[3/6] Activating virtual environment and installing dependencies..."
source raven-env/bin/activate

# Upgrade pip first (important for Debian)
pip install --upgrade pip

# Install dependencies
pip install -r rpi_client/requirements.txt

echo ""
echo "[4/6] Creating environment configuration file..."
cat > .env << 'ENVEOF'
# Scale Weight Capture Configuration
# Edit these values for your environment

# ERPNext Connection
ERPNEXT_URL="https://v2.sysmayal.cloud"
ERPNEXT_API_KEY="your_api_key_here"
ERPNEXT_API_SECRET="your_api_secret_here"

# Device Settings
DEVICE_ID="SCALE-L01"

# Scale Backend: sensor_skill (RECOMMENDED), keyboard, simulator, serial
SCALE_BACKEND="sensor_skill"

# Sensor Skill ID (when using sensor_skill backend):
# - scale_plant: Plant Production Scale (500kg, /dev/ttyUSB0, ModbusRTU)
# - scale_lab: Laboratory Precision Scale (30kg, /dev/ttyUSB1, SerialCommand)
SENSOR_SKILL_ID="scale_plant"

# Raven Notifications (optional)
RAVEN_URL=""
RAVEN_CHANNEL="iot-lab"

# Flask Web UI
FLASK_HOST="0.0.0.0"
FLASK_PORT="5000"
ENVEOF

echo "  Configuration file created: .env"
echo "  IMPORTANT: Edit .env with your API keys!"

echo ""
echo "[5/6] Verifying installation..."
python3 -c "import flask; print('  Flask OK')"
python3 -c "import requests; print('  Requests OK')"
python3 -c "from sensor_skill_client import SensorSkillClient; print('  Sensor Skill Client OK')"

echo ""
echo "[6/6] Testing scale reader..."
echo "  Running scale reader test (simulator mode)..."
SCALE_BACKEND=simulator python3 -c "
from scale_reader import ScaleReader
reader = ScaleReader(backend='simulator')
weight = reader.read_weight()
print(f'  Test successful: {weight} kg')
"

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "To activate the environment:"
echo "  source raven-env/bin/activate"
echo ""
echo "To run the terminal client:"
echo "  source raven-env/bin/activate"
echo "  python3 rpi_client/weight_capture_client.py"
echo ""
echo "To run the web UI:"
echo "  source raven-env/bin/activate"
echo "  python3 rpi_client/web_app.py"
echo ""
echo "IMPORTANT: Edit .env file with your API credentials before running!"
echo ""

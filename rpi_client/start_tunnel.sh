#!/bin/bash
# ngrok Tunnel Startup Script
# Starts ngrok tunnel to expose Flask web app on port 5000

# Usage: ./start_tunnel.sh

echo "Starting ngrok tunnel for weight capture web UI..."
echo "Target: https://bot1.sysmayal.ngrok.io -> localhost:5000"

ngrok http --url=bot1.sysmayal.ngrok.io 5000 &
NGROK_PID=$!

echo "Tunnel started (PID: $NGROK_PID)"
echo "Access URL: https://bot1.sysmayal.ngrok.io"
echo ""
echo "To stop: kill $NGROK_PID"

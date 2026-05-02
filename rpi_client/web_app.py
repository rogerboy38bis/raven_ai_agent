#!/usr/bin/env python3
"""Flask Web Application for Mobile Weight Capture.

Mobile-responsive web UI for capturing barrel weights from phone browsers.
Exposed via ngrok at https://bot1.sysmayal.ngrok.io

Features:
- Mobile-friendly interface (large touch targets for gloves)
- Barrel serial input with camera scan stub
- Weight input with scale read stub
- Real-time status display
- Submission history
- Offline buffering with retry

Usage:
    python3 web_app.py

Environment variables:
    FLASK_HOST: Host to bind (default: 0.0.0.0)
    FLASK_PORT: Port to bind (default: 5000)
    ERPNEXT_URL: ERPNext server URL
    ERPNEXT_API_KEY: API key
    ERPNEXT_API_SECRET: API secret
    DEVICE_ID: Scale device ID (default: SCALE-L01)
"""
import os
import json
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify

import requests

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Initialize Flask app
app = Flask(__name__, template_folder='templates')
app.config['JSON_SORT_KEYS'] = False

# Configuration
CONFIG = {
    'erpnext_url': os.getenv('ERPNEXT_URL', 'http://sysmayal.ngrok.io'),
    'api_key': os.getenv('ERPNEXT_API_KEY', ''),
    'api_secret': os.getenv('ERPNEXT_API_SECRET', ''),
    'device_id': os.getenv('DEVICE_ID', 'SCALE-L01'),
}

# Database path
DB_PATH = Path(__file__).parent / 'weight_buffer.db'


def init_db():
    """Initialize the SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS weight_buffer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barrel_serial TEXT NOT NULL,
            gross_weight REAL NOT NULL,
            device_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            retry_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS submission_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barrel_serial TEXT NOT NULL,
            gross_weight REAL NOT NULL,
            device_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            status TEXT DEFAULT 'success'
        )
    ''')
    conn.commit()
    conn.close()


def get_auth_headers() -> Dict:
    """Get authentication headers for API requests."""
    return {
        'Authorization': f"token {CONFIG['api_key']}:{CONFIG['api_secret']}",
        'Content-Type': 'application/json'
    }


def get_pending_count() -> int:
    """Get count of pending submissions."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute('SELECT COUNT(*) FROM weight_buffer')
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_last_submission() -> Optional[Dict]:
    """Get the last successful submission."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        'SELECT * FROM submission_history ORDER BY id DESC LIMIT 1'
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_history(limit: int = 10) -> List[Dict]:
    """Get submission history."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        'SELECT * FROM submission_history ORDER BY id DESC LIMIT ?',
        (limit,)
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def validate_barrel_serial(serial: str) -> bool:
    """Validate barrel serial exists in ERPNext.

    Args:
        serial: Barrel serial to validate.

    Returns:
        True if valid or validation skipped.
    """
    if not CONFIG['api_key'] or not CONFIG['api_secret']:
        return True

    url = f"{CONFIG['erpnext_url']}/api/method/raven_ai_agent.raven_ai_agent.api.validate_barrel_serial"
    try:
        resp = requests.get(
            url,
            params={'serial': serial},
            headers=get_auth_headers(),
            timeout=10
        )
        if resp.status_code == 200:
            result = resp.json()
            return result.get('message', {}).get('valid', False)
    except requests.exceptions.RequestException as e:
        logger.warning(f"Validation request failed: {e}")
    return True


def submit_to_erpnext(barrel_serial: str, gross_weight: float, batch_name: str = "", tara_weight: float = 0.0, mode: str = "keyboard") -> Dict:
    """Submit weight to ERPNext API.

    Args:
        barrel_serial: Barrel serial number.
        gross_weight: Weight in kg.

    Returns:
        Result dictionary with status.
    """
    timestamp = datetime.now().isoformat()
    from datetime import datetime, timezone
    net_weight = gross_weight - tara_weight
    payload = {
        'device_id': CONFIG['device_id'],
        'mode': mode,
        'batch_name': batch_name,
        'barrel_serial': barrel_serial,
        'gross_weight': float(gross_weight),
        'tara_weight': float(tara_weight),
        'net_weight': float(net_weight),
        'unit': 'kg',
        'tolerance_profile': 'PLANT',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'operator_id': CONFIG.get('operator_id', 'iot-bot@amb-wellness.com'),
    }

    if not CONFIG['api_key'] or not CONFIG['api_secret']:
        logger.warning("API credentials not configured")
        buffer_submission(barrel_serial, gross_weight)
        return {'status': 'error', 'message': 'API credentials not configured'}

    url = f"{CONFIG['erpnext_url']}/api/method/amb_w_spc.api.sensor_skill.receive_weight_event"
    try:
        resp = requests.post(
            url,
            json=payload,
            headers=get_auth_headers(),
            timeout=10
        )

        if resp.status_code == 200:
            result = resp.json()
            if result.get('message') or result.get('status') == 'success':
                save_submission(barrel_serial, gross_weight, 'success')
                return {
                    'status': 'success',
                    'barrel_serial': barrel_serial,
                    'weight': gross_weight,
                    'timestamp': timestamp
                }

        logger.error(f"API error: {resp.status_code} - {resp.text}")
        buffer_submission(barrel_serial, gross_weight)
        return {'status': 'error', 'message': 'API error'}

    except requests.exceptions.RequestException as e:
        logger.error(f"Submission failed: {e}")
        buffer_submission(barrel_serial, gross_weight)
        return {'status': 'error', 'message': str(e)}


def buffer_submission(barrel_serial: str, gross_weight: float):
    """Buffer submission for later retry."""
    timestamp = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO weight_buffer (barrel_serial, gross_weight, device_id, timestamp) '
        'VALUES (?, ?, ?, ?)',
        (barrel_serial, gross_weight, CONFIG['device_id'], timestamp)
    )
    conn.commit()
    conn.close()


def save_submission(barrel_serial: str, gross_weight: float, status: str):
    """Save successful submission to history."""
    timestamp = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO submission_history (barrel_serial, gross_weight, device_id, timestamp, status) '
        'VALUES (?, ?, ?, ?, ?)',
        (barrel_serial, gross_weight, CONFIG['device_id'], timestamp, status)
    )
    conn.commit()
    conn.close()


def get_pending() -> List[Dict]:
    """Get all pending submissions."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute('SELECT * FROM weight_buffer ORDER BY created_at ASC')
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def retry_pending() -> Dict:
    """Retry all pending submissions."""
    pending = get_pending()
    results = {'success': 0, 'failed': 0}

    for item in pending:
        result = submit_to_erpnext(item['barrel_serial'], item['gross_weight'], batch_name=item.get('batch_name', ''))
        if result['status'] == 'success':
            conn = sqlite3.connect(DB_PATH)
            conn.execute('DELETE FROM weight_buffer WHERE id = ?', (item['id'],))
            conn.commit()
            conn.close()
            results['success'] += 1
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                'UPDATE weight_buffer SET retry_count = retry_count + 1 WHERE id = ?',
                (item['id'],)
            )
            conn.commit()
            conn.close()
            results['failed'] += 1

    return results


# Initialize database on startup
init_db()


# Routes
@app.route('/')
def index():
    """Main weight capture page (mobile-friendly)."""
    return render_template('index.html')


@app.route('/api/submit-weight', methods=['POST'])
def api_submit_weight():
    """Submit barrel serial + weight to ERPNext.

    Request JSON:
        {
            "barrel_serial": "JAR0001261-1-C1-001",
            "gross_weight": 25.50
        }

    Returns:
        JSON with status and submission details.
    """
    data = request.get_json()

    if not data:
        return jsonify({'status': 'error', 'message': 'No data provided'}), 400

    barrel_serial = data.get('barrel_serial', '').strip().upper()
    gross_weight = data.get('gross_weight')
    batch_name = data.get("batch_name", "").strip()

    if not barrel_serial:
        return jsonify({'status': 'error', 'message': 'Barrel serial required'}), 400

    if gross_weight is None:
        return jsonify({'status': 'error', 'message': 'Weight required'}), 400

    try:
        gross_weight = float(gross_weight)
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': 'Invalid weight format'}), 400

    # Validate barrel serial
    if not validate_barrel_serial(barrel_serial):
        return jsonify({
            'status': 'error',
            'message': f'Barrel {barrel_serial} not found'
        }), 404

    # Validate weight range
    if gross_weight < 0.5 or gross_weight > 500:
        return jsonify({
            'status': 'error',
            'message': f'Weight {gross_weight} out of range (0.5-500 kg)'
        }), 400

    # Submit to ERPNext
    result = submit_to_erpnext(barrel_serial, gross_weight, batch_name=batch_name)

    if result['status'] == 'success':
        return jsonify(result), 200
    else:
        return jsonify(result), 200  # Return 200 even if buffered


@app.route('/api/barrels/<serial>', methods=['GET'])
def api_validate_barrel(serial: str):
    """Validate barrel serial against ERPNext.

    Args:
        serial: Barrel serial to validate.

    Returns:
        JSON with validation result.
    """
    serial = serial.strip().upper()

    if not validate_barrel_serial(serial):
        return jsonify({
            'status': 'error',
            'message': f'Barrel {serial} not found'
        }), 404

    return jsonify({
        'status': 'success',
        'barrel_serial': serial,
        'valid': True
    })


@app.route('/api/status', methods=['GET'])
def api_status():
    """Get device status.

    Returns:
        JSON with device status information.
    """
    last = get_last_submission()
    pending = get_pending_count()

    return jsonify({
        'device_id': CONFIG['device_id'],
        'connected': True,
        'last_submission': last,
        'pending_count': pending,
        'erpnext_url': CONFIG['erpnext_url']
    })


@app.route('/api/pending', methods=['GET'])
def api_pending():
    """List pending offline submissions.

    Returns:
        JSON array of pending submissions.
    """
    pending = get_pending()
    return jsonify({
        'status': 'success',
        'count': len(pending),
        'items': pending
    })


@app.route('/api/retry-pending', methods=['POST'])
def api_retry_pending():
    """Retry all pending submissions.

    Returns:
        JSON with retry results.
    """
    results = retry_pending()
    return jsonify({
        'status': 'success',
        'results': results
    })


@app.route('/api/history', methods=['GET'])
def api_history():
    """Get submission history.

    Returns:
        JSON array of recent submissions.
    """
    limit = request.args.get('limit', 10, type=int)
    history = get_history(limit=limit)
    return jsonify({
        'status': 'success',
        'count': len(history),
        'items': history
    })


def main():
    """Main entry point."""
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', '5000'))

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    logger.info(f"Starting Flask server on {host}:{port}")
    logger.info(f"ERPNext URL: {CONFIG['erpnext_url']}")
    logger.info(f"Device ID: {CONFIG['device_id']}")

    app.run(host=host, port=port, debug=False)


if __name__ == '__main__':
    main()

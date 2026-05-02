#!/usr/bin/env python3
"""Weight Capture Client for AMB Manufacturing Workflow.

Terminal-based workflow for capturing barrel weights and submitting to ERPNext.

Features:
- Barrel serial scanning/entry
- Weight reading from keyboard or scale simulator
- Submission to ERPNext API
- Offline buffering for failed submissions
- Raven notification on success

Usage:
    python3 weight_capture_client.py

Environment variables:
    ERPNEXT_URL: ERPNext server URL (default: http://sysmayal.ngrok.io)
    ERPNEXT_API_KEY: API key for authentication
    ERPNEXT_API_SECRET: API secret for authentication
    RAVEN_URL: Raven server URL
    RAVEN_CHANNEL: Raven channel for notifications (default: iot-lab)
    DEVICE_ID: Scale device ID (default: SCALE-L01)
    SCALE_BACKEND: Backend type (keyboard, simulator, serial)
"""
import os
import sys
import json
import sqlite3
import logging
import requests
from datetime import datetime
from typing import Optional, List, Dict
from pathlib import Path

# Import local modules
from scale_reader import ScaleReader, ValidationError as ScaleValidationError, ScaleReaderError
from barcode_handler import BarcodeHandler, ValidationError as BarcodeValidationError

logger = logging.getLogger(__name__)

# Configuration
CONFIG = {
    'erpnext_url': os.getenv('ERPNEXT_URL', 'http://sysmayal.ngrok.io'),
    'api_key': os.getenv('ERPNEXT_API_KEY', ''),
    'api_secret': os.getenv('ERPNEXT_API_SECRET', ''),
    'raven_url': os.getenv('RAVEN_URL', ''),
    'raven_channel': os.getenv('RAVEN_CHANNEL', 'iot-lab'),
    'device_id': os.getenv('DEVICE_ID', 'SCALE-L01'),
    'scale_backend': os.getenv('SCALE_BACKEND', 'keyboard'),
    'barcode_backend': os.getenv('BARCODE_BACKEND', 'keyboard'),
}

# Database for offline buffering
DB_PATH = Path.home() / 'raven-bot' / 'weight_buffer.db'


class WeightBuffer:
    """SQLite-based offline buffer for failed submissions."""

    def __init__(self, db_path: Path = None):
        """Initialize the weight buffer.

        Args:
            db_path: Path to SQLite database.
        """
        self.db_path = db_path or DB_PATH
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
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
        conn.commit()
        conn.close()

    def add(self, barrel_serial: str, gross_weight: float,
            device_id: str, timestamp: str = None):
        """Add a submission to the buffer.

        Args:
            barrel_serial: Barrel serial number.
            gross_weight: Weight in kg.
            device_id: Device identifier.
            timestamp: ISO timestamp.
        """
        timestamp = timestamp or datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            'INSERT INTO weight_buffer (barrel_serial, gross_weight, device_id, timestamp) '
            'VALUES (?, ?, ?, ?)',
            (barrel_serial, gross_weight, device_id, timestamp)
        )
        conn.commit()
        conn.close()
        logger.info(f"Buffered: {barrel_serial} = {gross_weight} kg")

    def get_pending(self) -> List[Dict]:
        """Get all pending submissions.

        Returns:
            List of pending submission dictionaries.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            'SELECT * FROM weight_buffer ORDER BY created_at ASC'
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def count(self) -> int:
        """Count pending submissions.

        Returns:
            Number of pending submissions.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute('SELECT COUNT(*) FROM weight_buffer')
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def remove(self, row_id: int):
        """Remove a submission from the buffer.

        Args:
            row_id: Database row ID.
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute('DELETE FROM weight_buffer WHERE id = ?', (row_id,))
        conn.commit()
        conn.close()

    def increment_retry(self, row_id: int):
        """Increment retry count for a submission.

        Args:
            row_id: Database row ID.
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            'UPDATE weight_buffer SET retry_count = retry_count + 1 WHERE id = ?',
            (row_id,)
        )
        conn.commit()
        conn.close()


class WeightCaptureClient:
    """Main weight capture client with terminal UI."""

    def __init__(self):
        """Initialize the weight capture client."""
        self.buffer = WeightBuffer()
        self.scale_reader = ScaleReader(backend=CONFIG['scale_backend'])
        self.barcode_handler = BarcodeHandler(backend=CONFIG['barcode_backend'])
        self.current_serial: Optional[str] = None
        self.current_weight: Optional[float] = None
        self.submission_history: List[Dict] = []
        self.last_submission: Optional[Dict] = None

    def _get_auth_headers(self) -> Dict:
        """Get authentication headers for API requests.

        Returns:
            Dictionary with Authorization header.
        """
        return {
            'Authorization': f"token {CONFIG['api_key']}:{CONFIG['api_secret']}",
            'Content-Type': 'application/json'
        }

    def validate_barrel_serial_api(self, serial: str) -> bool:
        """Validate barrel serial exists in ERPNext.

        Args:
            serial: Barrel serial to validate.

        Returns:
            True if valid, False otherwise.
        """
        if not CONFIG['api_key'] or not CONFIG['api_secret']:
            logger.warning("API credentials not configured, skipping validation")
            return True

        url = f"{CONFIG['erpnext_url']}/api/method/raven_ai_agent.raven_ai_agent.api.validate_barrel_serial"
        try:
            resp = requests.get(
                url,
                params={'serial': serial},
                headers=self._get_auth_headers(),
                timeout=10
            )
            if resp.status_code == 200:
                result = resp.json()
                return result.get('message', {}).get('valid', False)
        except requests.exceptions.RequestException as e:
            logger.warning(f"Barrel validation request failed: {e}")
        return True  # Allow on network error

    def submit_weight(self, barrel_serial: str, gross_weight: float) -> bool:
        """Submit weight to ERPNext API.

        Args:
            barrel_serial: Barrel serial number.
            gross_weight: Weight in kg.

        Returns:
            True if successful, False otherwise.
        """
        timestamp = datetime.now().isoformat()
        payload = {
            'barrel_serial': barrel_serial,
            'gross_weight': gross_weight,
            'device_id': CONFIG['device_id'],
            'tara_weight': None
        }

        if not CONFIG['api_key'] or not CONFIG['api_secret']:
            logger.warning("API credentials not configured")
            self.buffer.add(barrel_serial, gross_weight, CONFIG['device_id'], timestamp)
            return False

        url = f"{CONFIG['erpnext_url']}/api/method/amb_w_tds.api.batch_api.receive_weight"
        try:
            resp = requests.post(
                url,
                json=payload,
                headers=self._get_auth_headers(),
                timeout=10
            )

            if resp.status_code == 200:
                result = resp.json()
                if result.get('message') or result.get('status') == 'success':
                    self.last_submission = {
                        'barrel_serial': barrel_serial,
                        'gross_weight': gross_weight,
                        'timestamp': timestamp,
                        'status': 'success'
                    }
                    self.submission_history.append(self.last_submission)
                    self._send_raven_notification(barrel_serial, gross_weight)
                    logger.info(f"Submitted: {barrel_serial} = {gross_weight} kg")
                    return True

            logger.error(f"API error: {resp.status_code} - {resp.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Submission failed: {e}")

        # Buffer for retry
        self.buffer.add(barrel_serial, gross_weight, CONFIG['device_id'], timestamp)
        return False

    def _send_raven_notification(self, serial: str, weight: float):
        """Send Raven notification on successful submission.

        Args:
            serial: Barrel serial.
            weight: Weight in kg.
        """
        if not CONFIG['raven_url']:
            logger.debug("Raven URL not configured, skipping notification")
            return

        message = f"Weight captured: {serial} = {weight} kg"

        try:
            resp = requests.post(
                f"{CONFIG['raven_url']}/api/send_message",
                json={
                    'channel': CONFIG['raven_channel'],
                    'text': message
                },
                timeout=5
            )
            if resp.status_code == 200:
                logger.info(f"Raven notification sent: {message}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Raven notification failed: {e}")

    def retry_pending(self) -> Dict[str, int]:
        """Retry all pending submissions.

        Returns:
            Dictionary with success/failure counts.
        """
        pending = self.buffer.get_pending()
        results = {'success': 0, 'failed': 0}

        for item in pending:
            if self.submit_weight(item['barrel_serial'], item['gross_weight']):
                self.buffer.remove(item['id'])
                results['success'] += 1
            else:
                self.buffer.increment_retry(item['id'])
                results['failed'] += 1

        return results

    def scan_barrel(self) -> Optional[str]:
        """Scan or enter barrel serial.

        Returns:
            Valid barrel serial, or None if cancelled.
        """
        print("\n" + "=" * 40)
        print("SCAN/ENTER BARREL SERIAL")
        print("=" * 40)
        return self.barcode_handler.scan_barrel_serial()

    def read_weight(self) -> Optional[float]:
        """Read weight from scale.

        Returns:
            Weight in kg, or None if cancelled/failed.
        """
        print("\n" + "=" * 40)
        print("READ/ENTER WEIGHT")
        print("=" * 40)
        print(f"Backend: {CONFIG['scale_backend']}")
        print("Press Ctrl+C to cancel")
        print()

        try:
            weight = self.scale_reader.read_weight()
            print(f"\nWeight: {weight} kg")
            return weight
        except ScaleReaderError as e:
            print(f"\nError: {e}")
            return None

    def show_pending(self):
        """Display pending submissions."""
        pending = self.buffer.get_pending()

        print("\n" + "=" * 40)
        print(f"PENDING SUBMISSIONS ({len(pending)} items)")
        print("=" * 40)

        if not pending:
            print("No pending submissions")
            return

        for item in pending:
            print(f"  {item['barrel_serial']}: {item['gross_weight']} kg "
                  f"(retries: {item['retry_count']})")

    def show_history(self):
        """Display submission history."""
        print("\n" + "=" * 40)
        print(f"SUBMISSION HISTORY (last 10)")
        print("=" * 40)

        history = self.submission_history[-10:] if self.submission_history else []

        if not history:
            print("No submissions yet")
            return

        for item in reversed(history):
            status_icon = "OK" if item['status'] == 'success' else "FAIL"
            print(f"  [{status_icon}] {item['barrel_serial']}: {item['gross_weight']} kg")

    def show_settings(self):
        """Display current settings."""
        print("\n" + "=" * 40)
        print("SETTINGS")
        print("=" * 40)
        print(f"ERPNext URL: {CONFIG['erpnext_url']}")
        print(f"Device ID: {CONFIG['device_id']}")
        print(f"Scale Backend: {CONFIG['scale_backend']}")
        print(f"Barcode Backend: {CONFIG['barcode_backend']}")
        print(f"Raven Channel: {CONFIG['raven_channel']}")
        print(f"API Key: {'*' * 8 if CONFIG['api_key'] else 'NOT SET'}")
        print(f"Buffer DB: {self.buffer.db_path}")
        print(f"Pending: {self.buffer.count()}")

    def run(self):
        """Run the main terminal menu loop."""
        while True:
            print("\n" + "=" * 50)
            print("=== AMB Weight Capture Station ===")
            print("=" * 50)
            print("[1] Scan/Enter barrel serial")
            print("[2] Read/Enter weight")
            print("[3] Submit to ERPNext")
            print("[4] View pending submissions")
            print("[5] Retry pending")
            print("[6] View history")
            print("[7] Settings")
            print("[0] Exit")
            print("-" * 50)

            if self.last_submission:
                print(f"Last: {self.last_submission['barrel_serial']} = "
                      f"{self.last_submission['gross_weight']} kg")

            pending = self.buffer.count()
            if pending > 0:
                print(f"Pending: {pending}")

            print()

            choice = input("Select option: ").strip()

            try:
                if choice == '1':
                    serial = self.scan_barrel()
                    if serial:
                        self.current_serial = serial
                        print(f"\nBarrel set: {serial}")

                elif choice == '2':
                    weight = self.read_weight()
                    if weight is not None:
                        self.current_weight = weight

                elif choice == '3':
                    if not self.current_serial:
                        print("\nError: No barrel serial entered")
                    elif self.current_weight is None:
                        print("\nError: No weight entered")
                    else:
                        success = self.submit_weight(
                            self.current_serial,
                            self.current_weight
                        )
                        if success:
                            print(f"\nSUCCESS: {self.current_serial} = {self.current_weight} kg")
                            self.current_serial = None
                            self.current_weight = None
                        else:
                            print(f"\nBUFFERED: Will retry later")

                elif choice == '4':
                    self.show_pending()

                elif choice == '5':
                    results = self.retry_pending()
                    print(f"\nRetry complete: {results['success']} succeeded, "
                          f"{results['failed']} failed")

                elif choice == '6':
                    self.show_history()

                elif choice == '7':
                    self.show_settings()

                elif choice == '0':
                    print("\nExiting...")
                    break

                else:
                    print("\nInvalid option")

            except KeyboardInterrupt:
                print("\n\nCancelled")
                continue


def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('/tmp/weight_capture.log')
        ]
    )

    print("=" * 50)
    print("AMB Weight Capture Station")
    print("=" * 50)
    print(f"Scale Backend: {CONFIG['scale_backend']}")
    print(f"ERPNext: {CONFIG['erpnext_url']}")
    print(f"Device: {CONFIG['device_id']}")
    print()

    client = WeightCaptureClient()
    client.run()


if __name__ == '__main__':
    main()

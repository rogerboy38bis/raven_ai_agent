#!/usr/bin/env python3
"""Sensor Skill Client - Fetch scale configuration from amb_w_spc.

This module fetches scale configuration from the Sensor Skill DocType
in amb_w_spc (PH13.2.0) and provides configuration for the scale reader.

Environment variables:
    ERPNEXT_URL: ERPNext server URL (default: http://sysmayal.ngrok.io)
    ERPNEXT_API_KEY: API key for authentication
    ERPNEXT_API_SECRET: API secret for authentication
    SENSOR_SKILL_ID: Sensor Skill ID to use (default: SCALE_BACKEND env or 'scale_plant')
        - 'scale_plant': Plant Production Scale (500kg, /dev/ttyUSB0, ModbusRTU)
        - 'scale_lab': Laboratory Precision Scale (30kg, /dev/ttyUSB1, SerialCommand)
    SENSOR_SKILL_CACHE_TTL: Cache TTL in seconds (default: 300 = 5 minutes)

Usage:
    from sensor_skill_client import SensorSkillClient

    client = SensorSkillClient()
    config = client.get_config()  # Returns dict with port, baud_rate, python_config, etc.
    print(f"Scale config: {config}")
"""
import os
import json
import logging
import time
import requests
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Flag indicating sensor_skill_client is available
# This is used by scale_reader.py to check if Sensor Skill integration is available
SENSOR_SKILL_AVAILABLE = True


class SensorSkillError(Exception):
    """Base exception for Sensor Skill client errors."""
    pass


class SensorSkillNotFoundError(SensorSkillError):
    """Raised when Sensor Skill record is not found."""
    pass


class SensorSkillClient:
    """Client for fetching Sensor Skill configuration from amb_w_spc.

    This client fetches scale configuration from the Sensor Skill DocType
    and caches the result to reduce API calls.
    """

    def __init__(self, skill_id: str = None, cache_ttl: int = None):
        """Initialize Sensor Skill client.

        Args:
            skill_id: Sensor Skill ID to fetch (e.g., 'scale_plant', 'scale_lab').
                     Defaults to SENSOR_SKILL_ID env var or 'scale_plant'.
            cache_ttl: Cache TTL in seconds. Defaults to SENSOR_SKILL_CACHE_TTL or 300.
        """
        self.erpnext_url = os.getenv('ERPNEXT_URL', 'http://sysmayal.ngrok.io')
        self.api_key = os.getenv('ERPNEXT_API_KEY', '')
        self.api_secret = os.getenv('ERPNEXT_API_SECRET', '')
        self.skill_id = skill_id or os.getenv('SENSOR_SKILL_ID', 'scale_plant')
        self.cache_ttl = cache_ttl or int(os.getenv('SENSOR_SKILL_CACHE_TTL', '300'))

        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for API requests."""
        return {
            'Authorization': f"token {self.api_key}:{self.api_secret}",
            'Content-Type': 'application/json'
        }

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if self._cache is None or self._cache_time is None:
            return False
        elapsed = (datetime.now() - self._cache_time).total_seconds()
        return elapsed < self.cache_ttl

    def fetch_config(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch Sensor Skill configuration from amb_w_spc.

        Args:
            force_refresh: Force fetch even if cache is valid.

        Returns:
            Dictionary with Sensor Skill configuration:
            - skill_id: str
            - skill_name: str
            - sensor_type: str
            - version: str
            - min_value: float
            - max_value: float
            - unit_of_measure: str
            - port: str
            - baud_rate: int
            - python_config: dict (parsed from JSON)
            - wiring_instructions: str
            - calibration_procedure: str
            - enabled: bool

        Raises:
            SensorSkillNotFoundError: If Sensor Skill record not found.
            SensorSkillError: If API request fails.
        """
        if not force_refresh and self._is_cache_valid():
            logger.debug(f"Using cached config for {self.skill_id}")
            return self._cache.copy()

        if not self.api_key or not self.api_secret:
            logger.warning("API credentials not configured, using defaults")
            return self._get_default_config()

        url = f"{self.erpnext_url}/api/method/amb_w_spc.api.sensor_skill.get_sensor_skill_config"
        try:
            resp = requests.get(
                url,
                params={'skill_id': self.skill_id},
                headers=self._get_auth_headers(),
                timeout=10
            )

            if resp.status_code == 200:
                result = resp.json()
                data = result.get('message', {})

                if not data:
                    raise SensorSkillNotFoundError(
                        f"Sensor Skill '{self.skill_id}' not found"
                    )

                # Parse python_config JSON if string
                if isinstance(data.get('python_config'), str):
                    try:
                        data['python_config'] = json.loads(data['python_config'])
                    except json.JSONDecodeError:
                        data['python_config'] = {}

                # Cache the result
                self._cache = data
                self._cache_time = datetime.now()

                logger.info(f"Fetched config for {self.skill_id}: "
                           f"port={data.get('port')}, baud={data.get('baud_rate')}")
                return data.copy()

            elif resp.status_code == 404:
                raise SensorSkillNotFoundError(
                    f"Sensor Skill '{self.skill_id}' not found"
                )

            else:
                raise SensorSkillError(
                    f"API error: {resp.status_code} - {resp.text}"
                )

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch Sensor Skill: {e}")
            # Return cached if available, otherwise defaults
            if self._cache:
                logger.warning("Using cached config due to network error")
                return self._cache.copy()
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration when API is unavailable."""
        logger.warning(f"Using default config for {self.skill_id}")

        defaults = {
            'scale_plant': {
                'skill_id': 'scale_plant',
                'skill_name': 'Plant Production Scale',
                'sensor_type': 'Scale',
                'version': '1.0.0',
                'min_value': 0,
                'max_value': 500,
                'unit_of_measure': 'kg',
                'port': '/dev/ttyUSB0',
                'baud_rate': 9600,
                'python_config': {'driver': 'ModbusRTU', 'slave_id': 1, 'scale_factor': 0.01},
                'wiring_instructions': 'RS485 to USB converter',
                'calibration_procedure': 'Place known weight and calibrate',
                'enabled': True,
            },
            'scale_lab': {
                'skill_id': 'scale_lab',
                'skill_name': 'Laboratory Precision Scale',
                'sensor_type': 'Scale',
                'version': '1.0.0',
                'min_value': 0,
                'max_value': 30,
                'unit_of_measure': 'kg',
                'port': '/dev/ttyUSB1',
                'baud_rate': 115200,
                'python_config': {'driver': 'SerialCommand', 'command': 'W', 'response_format': 'DECIMAL'},
                'wiring_instructions': 'USB-Serial to precision balance',
                'calibration_procedure': 'Warm up, zero, place certified weight',
                'enabled': True,
            },
        }

        config = defaults.get(self.skill_id, defaults['scale_plant']).copy()
        self._cache = config
        self._cache_time = datetime.now()
        return config

    def get_config(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Get Sensor Skill configuration (public method).

        Args:
            force_refresh: Force refresh from API.

        Returns:
            Sensor Skill configuration dictionary.
        """
        return self.fetch_config(force_refresh=force_refresh)

    def get_port(self) -> str:
        """Get serial port from config."""
        return self.fetch_config().get('port', '/dev/ttyUSB0')

    def get_baud_rate(self) -> int:
        """Get baud rate from config."""
        return self.fetch_config().get('baud_rate', 9600)

    def get_python_config(self) -> Dict[str, Any]:
        """Get python_config dict from config."""
        return self.fetch_config().get('python_config', {})

    def get_max_value(self) -> float:
        """Get max value from config."""
        return self.fetch_config().get('max_value', 500)

    def get_min_value(self) -> float:
        """Get min value from config."""
        return self.fetch_config().get('min_value', 0)

    def is_enabled(self) -> bool:
        """Check if Sensor Skill is enabled."""
        return self.fetch_config().get('enabled', True)

    def invalidate_cache(self):
        """Invalidate the cache, forcing a refresh on next call."""
        self._cache = None
        self._cache_time = None
        logger.debug("Cache invalidated")

    def __repr__(self) -> str:
        return f"SensorSkillClient(skill_id={self.skill_id!r}, cached={self._is_cache_valid()})"


def main():
    """Command-line interface for testing the Sensor Skill client."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    parser = argparse.ArgumentParser(description='Sensor Skill Client Test')
    parser.add_argument(
        '--skill-id', '-s',
        default=os.getenv('SENSOR_SKILL_ID', 'scale_plant'),
        help='Sensor Skill ID to fetch'
    )
    parser.add_argument(
        '--refresh', '-r',
        action='store_true',
        help='Force refresh from API'
    )
    parser.add_argument(
        '--info', '-i',
        action='store_true',
        help='Show detailed config info'
    )

    args = parser.parse_args()

    print(f"=== Sensor Skill Client Test ===")
    print(f"Skill ID: {args.skill_id}")
    print(f"ERPNext URL: {os.getenv('ERPNEXT_URL', 'http://sysmayal.ngrok.io')}")
    print()

    try:
        client = SensorSkillClient(skill_id=args.skill_id)
        config = client.get_config(force_refresh=args.refresh)

        print(f"Config loaded: {args.skill_id}")
        print(f"  Skill Name: {config.get('skill_name')}")
        print(f"  Port: {config.get('port')}")
        print(f"  Baud Rate: {config.get('baud_rate')}")
        print(f"  Max Value: {config.get('max_value')} {config.get('unit_of_measure')}")
        print(f"  Enabled: {config.get('enabled')}")

        if args.info:
            print(f"\n  Python Config: {json.dumps(config.get('python_config', {}), indent=4)}")
            print(f"\n  Wiring: {config.get('wiring_instructions')}")
            print(f"\n  Calibration: {config.get('calibration_procedure')}")

    except SensorSkillError as e:
        print(f"ERROR: {e}")


if __name__ == '__main__':
    main()

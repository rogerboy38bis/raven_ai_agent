#!/usr/bin/env python3
"""Scale Reader Module with pluggable backends.

This module provides a unified interface for reading weight from different scale backends:
- KeyboardBackend: Operator types weight directly
- SerialBackend: Reads from serial port (STUB)
- SimulatorBackend: Generates random weights for testing

Usage:
    from scale_reader import ScaleReader, KeyboardBackend, SimulatorBackend

    reader = ScaleReader(backend='simulator')
    weight = reader.read_weight()
"""
import os
import sys
import time
import random
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class ScaleReaderError(Exception):
    """Base exception for scale reader errors."""
    pass


class ValidationError(ScaleReaderError):
    """Raised when weight validation fails."""
    pass


class ConnectionError(ScaleReaderError):
    """Raised when scale connection fails."""
    pass


class ScaleBackend(ABC):
    """Abstract base class for scale backends."""

    @abstractmethod
    def read_raw(self) -> Optional[float]:
        """Read raw weight value from the backend.

        Returns:
            Weight in kg, or None if reading failed.
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the backend is connected and ready.

        Returns:
            True if connected, False otherwise.
        """
        pass

    def close(self):
        """Close the backend connection. Override if needed."""
        pass


class KeyboardBackend(ScaleBackend):
    """Keyboard/Terminal input backend.

    Reads weight from stdin where operator types the weight value.
    """

    def __init__(self, prompt: str = "Enter weight (kg): "):
        """Initialize keyboard backend.

        Args:
            prompt: Prompt string shown to operator.
        """
        self.prompt = prompt
        self._connected = True

    def read_raw(self) -> Optional[float]:
        """Read weight from stdin.

        Returns:
            Weight in kg as float, or None on error.
        """
        try:
            user_input = input(self.prompt).strip()
            if not user_input:
                return None
            return float(user_input)
        except ValueError:
            logger.error(f"Invalid weight format: {user_input}")
            return None
        except EOFError:
            return None

    def is_connected(self) -> bool:
        """Always returns True for keyboard backend."""
        return self._connected


class SerialBackend(ScaleBackend):
    """Serial port backend for reading from industrial scales.

    STUB: Basic structure for future implementation with Arduino Nano
    or industrial scale connected via /dev/ttyUSB0.
    """

    def __init__(self, port: str = None, baud: int = 9600,
                 timeout: float = 5.0):
        """Initialize serial backend.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0'). Defaults to env SCALE_PORT.
            baud: Baud rate. Defaults to 9600.
            timeout: Read timeout in seconds.
        """
        self.port = port or os.getenv('SCALE_PORT', '/dev/ttyUSB0')
        self.baud = baud
        self.timeout = timeout
        self._serial = None
        self._connected = False

    def connect(self) -> bool:
        """Establish serial connection.

        TODO: Implement actual serial connection using pyserial.
              For now, this is a STUB that always fails.

        Returns:
            True if connected, False otherwise.
        """
        # TODO: Implement serial connection
        # Example:
        # import serial
        # try:
        #     self._serial = serial.Serial(
        #         port=self.port,
        #         baudrate=self.baud,
        #         timeout=self.timeout
        #     )
        #     self._connected = True
        #     return True
        # except serial.SerialException as e:
        #     logger.error(f"Serial connection failed: {e}")
        #     return False
        logger.warning("SerialBackend.connect() - STUB: Not implemented")
        self._connected = False
        return False

    def read_raw(self) -> Optional[float]:
        """Read weight from serial port.

        TODO: Implement actual serial reading.
              Expected format may vary by scale manufacturer.

        Returns:
            Weight in kg, or None if reading failed.
        """
        # TODO: Implement serial reading
        # Example:
        # if not self._connected:
        #     self.connect()
        # if self._serial and self._serial.in_waiting:
        #     line = self._serial.readline().decode('utf-8').strip()
        #     # Parse weight from line based on scale protocol
        #     return float(parse_weight(line))
        logger.warning("SerialBackend.read_raw() - STUB: Not implemented")
        return None

    def is_connected(self) -> bool:
        """Check if serial port is connected."""
        return self._connected

    def close(self):
        """Close serial connection."""
        if self._serial:
            self._serial.close()
            self._serial = None
            self._connected = False


class SimulatorBackend(ScaleBackend):
    """Simulator backend for testing without hardware.

    Generates random weights in the range 20-30 kg.
    """

    def __init__(self, min_weight: float = 20.0, max_weight: float = 30.0):
        """Initialize simulator backend.

        Args:
            min_weight: Minimum weight in kg.
            max_weight: Maximum weight in kg.
        """
        self.min_weight = min_weight
        self.max_weight = max_weight
        self._connected = True

    def read_raw(self) -> Optional[float]:
        """Generate random weight.

        Returns:
            Random weight between min_weight and max_weight.
        """
        weight = random.uniform(self.min_weight, self.max_weight)
        return round(weight, 2)

    def is_connected(self) -> bool:
        """Always returns True for simulator."""
        return self._connected


class ScaleReader:
    """Main scale reader with stable reading detection and validation.

    Reads weight from a backend and validates:
    - Stability: 3 consecutive readings within 0.1 kg tolerance
    - Range: Between SCALE_MIN_WEIGHT and SCALE_MAX_WEIGHT
    """

    def __init__(self, backend: str = None):
        """Initialize scale reader with specified backend.

        Args:
            backend: Backend type ('keyboard', 'serial', 'simulator').
                    Defaults to SCALE_BACKEND env var or 'keyboard'.
        """
        self.backend_name = backend or os.getenv('SCALE_BACKEND', 'keyboard')
        self.min_weight = float(os.getenv('SCALE_MIN_WEIGHT', '0.5'))
        self.max_weight = float(os.getenv('SCALE_MAX_WEIGHT', '500'))
        self.stability_tolerance = 0.1
        self.stability_readings = 3

        self._backend = self._create_backend()

    def _create_backend(self) -> ScaleBackend:
        """Create the appropriate backend instance.

        Returns:
            ScaleBackend instance.
        """
        if self.backend_name == 'simulator':
            return SimulatorBackend()
        elif self.backend_name == 'serial':
            port = os.getenv('SCALE_PORT', '/dev/ttyUSB0')
            baud = int(os.getenv('SCALE_BAUD', '9600'))
            return SerialBackend(port=port, baud=baud)
        else:
            return KeyboardBackend()

    def _validate_weight(self, weight: float) -> bool:
        """Validate weight is within acceptable range.

        Args:
            weight: Weight in kg.

        Returns:
            True if valid, False otherwise.
        """
        if weight < self.min_weight:
            logger.error(f"Weight {weight} below minimum {self.min_weight} kg")
            return False
        if weight > self.max_weight:
            logger.error(f"Weight {weight} above maximum {self.max_weight} kg")
            return False
        return True

    def _is_stable(self, readings: list) -> bool:
        """Check if readings are stable within tolerance.

        Args:
            readings: List of weight readings.

        Returns:
            True if all readings within tolerance of first reading.
        """
        if len(readings) < self.stability_readings:
            return False

        first = readings[0]
        return all(abs(r - first) <= self.stability_tolerance for r in readings)

    def read_weight(self) -> float:
        """Read and validate stable weight.

        Waits for 3 consecutive stable readings before returning.
        Automatically validates weight range.

        Returns:
            Stable weight in kg.

        Raises:
            ValidationError: If weight is out of range.
            ScaleReaderError: If unable to get stable reading.
        """
        readings = []
        max_attempts = 20

        logger.info(f"Reading weight from {self.backend_name} backend...")

        for attempt in range(max_attempts):
            raw = self._backend.read_raw()

            if raw is None:
                logger.warning(f"Attempt {attempt + 1}: No reading received")
                time.sleep(0.5)
                continue

            if not self._validate_weight(raw):
                logger.warning(f"Attempt {attempt + 1}: Invalid weight {raw} kg")
                continue

            readings.append(raw)
            logger.debug(f"Attempt {attempt + 1}: Reading {raw} kg (buffer: {readings})")

            if self._is_stable(readings):
                final_weight = round(readings[-1], 2)
                logger.info(f"Stable weight confirmed: {final_weight} kg")
                return final_weight

        raise ScaleReaderError(
            f"Could not get stable reading after {max_attempts} attempts. "
            f"Last readings: {readings[-3:] if readings else []}"
        )

    def is_connected(self) -> bool:
        """Check if the backend is connected.

        Returns:
            True if connected, False otherwise.
        """
        return self._backend.is_connected()

    def close(self):
        """Close the backend connection."""
        self._backend.close()


def main():
    """Command-line interface for testing the scale reader."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    parser = argparse.ArgumentParser(description='Scale Reader Test')
    parser.add_argument(
        '--backend', '-b',
        choices=['keyboard', 'serial', 'simulator'],
        default=os.getenv('SCALE_BACKEND', 'simulator'),
        help='Scale backend to use'
    )
    parser.add_argument(
        '--count', '-c',
        type=int,
        default=1,
        help='Number of readings to take'
    )

    args = parser.parse_args()

    print(f"=== Scale Reader Test ===")
    print(f"Backend: {args.backend}")
    print(f"Min/Max: {os.getenv('SCALE_MIN_WEIGHT', '0.5')} - "
          f"{os.getenv('SCALE_MAX_WEIGHT', '500')} kg")
    print()

    reader = ScaleReader(backend=args.backend)

    for i in range(args.count):
        print(f"\n--- Reading {i + 1} ---")
        try:
            weight = reader.read_weight()
            print(f"SUCCESS: {weight} kg")
        except ScaleReaderError as e:
            print(f"ERROR: {e}")

    reader.close()


if __name__ == '__main__':
    main()

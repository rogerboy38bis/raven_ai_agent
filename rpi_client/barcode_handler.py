#!/usr/bin/env python3
"""Barcode Handler Module for barrel serial number scanning.

This module provides barcode scanning capabilities for the AMB manufacturing workflow:
- KeyboardBarcodeBackend: Operator types barrel serial manually
- CameraBarcodeBackend: STUB for phone/RPi camera barcode scanning

Supported formats:
- Stage 1: Code 39 with barrel serial only (e.g., 'JAR0001261-1-C1-001')
- Stage 2: Code 39 with serial|weight (STUB)

Usage:
    from barcode_handler import BarcodeHandler, KeyboardBarcodeBackend

    handler = BarcodeHandler(backend='keyboard')
    serial = handler.scan_barrel_serial()
"""
import os
import re
import logging
from abc import ABC, abstractmethod
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class BarcodeError(Exception):
    """Base exception for barcode handler errors."""
    pass


class ValidationError(BarcodeError):
    """Raised when barcode validation fails."""
    pass


class BarcodeBackend(ABC):
    """Abstract base class for barcode backends."""

    @abstractmethod
    def scan(self) -> Optional[str]:
        """Scan and return raw barcode data.

        Returns:
            Raw barcode string, or None if scan failed.
        """
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """Check if the backend is ready for scanning.

        Returns:
            True if ready, False otherwise.
        """
        pass


class KeyboardBarcodeBackend(BarcodeBackend):
    """Keyboard/Terminal input backend.

    Operator types barrel serial number directly.
    """

    def __init__(self, prompt: str = "Enter barrel serial: "):
        """Initialize keyboard barcode backend.

        Args:
            prompt: Prompt string shown to operator.
        """
        self.prompt = prompt
        self._ready = True

    def scan(self) -> Optional[str]:
        """Read barcode from stdin.

        Returns:
            Barcode string, or None on error.
        """
        try:
            barcode = input(self.prompt).strip().upper()
            if barcode:
                return barcode
            return None
        except EOFError:
            return None
        except KeyboardInterrupt:
            return None

    def is_ready(self) -> bool:
        """Always returns True for keyboard backend."""
        return self._ready


class CameraBarcodeBackend(BarcodeBackend):
    """Camera-based barcode scanning backend.

    STUB: Placeholder for RPi camera or phone camera scanning.
    """

    def __init__(self, camera_index: int = 0):
        """Initialize camera barcode backend.

        Args:
            camera_index: Camera device index (0 = first camera).

        TODO: Implement camera barcode scanning using:
              - picamera2 for RPi camera
              - OpenCV for barcode detection
              - pyzbar or zbar for Code 39 decoding
        """
        self.camera_index = camera_index
        self._ready = False

    def scan(self) -> Optional[str]:
        """Scan barcode from camera.

        TODO: Implement actual camera scanning.

        Example implementation:
        ```
        import cv2
        from pyzbar.pyzbar import decode

        cap = cv2.VideoCapture(self.camera_index)
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            decoded = decode(frame)
            if decoded:
                barcode = decoded[0].data.decode('utf-8')
                cap.release()
                return barcode
        cap.release()
        return None
        ```

        Returns:
            Barcode string, or None if not implemented.
        """
        logger.warning("CameraBarcodeBackend.scan() - STUB: Not implemented")
        return None

    def is_ready(self) -> bool:
        """Check if camera is available.

        Returns:
            False (STUB - not implemented).
        """
        return self._ready


class BarcodeHandler:
    """Barcode handler with Code 39 validation.

    Supports two stages:
    - Stage 1: Decode barrel serial only
    - Stage 2: Decode serial|weight format (STUB)
    """

    # Barrel serial pattern: JAR0001261-1-C1-001
    BARREL_SERIAL_PATTERN = re.compile(r'^[A-Z]{3}[0-9]+-[0-9]+-C[0-9]+-[0-9]+$')

    def __init__(self, backend: str = None):
        """Initialize barcode handler with specified backend.

        Args:
            backend: Backend type ('keyboard', 'camera'). Defaults to 'keyboard'.
        """
        self.backend_name = backend or os.getenv('BARCODE_BACKEND', 'keyboard')
        self._backend = self._create_backend()

    def _create_backend(self) -> BarcodeBackend:
        """Create the appropriate backend instance.

        Returns:
            BarcodeBackend instance.
        """
        if self.backend_name == 'camera':
            camera_index = int(os.getenv('CAMERA_INDEX', '0'))
            return CameraBarcodeBackend(camera_index=camera_index)
        else:
            return KeyboardBarcodeBackend()

    def validate_barrel_serial(self, serial: str) -> bool:
        """Validate barrel serial format.

        Valid format: JAR0001261-1-C1-001
        Pattern: [A-Z]{3}[0-9]+-[0-9]+-C[0-9]+-[0-9]+

        Args:
            serial: Barrel serial string.

        Returns:
            True if valid format, False otherwise.
        """
        if not serial:
            return False
        return bool(self.BARREL_SERIAL_PATTERN.match(serial))

    def parse_barrel_serial(self, barcode: str) -> Optional[str]:
        """Parse and validate barrel serial from barcode.

        Stage 1: Handles barcode with barrel serial only.

        Args:
            barcode: Raw barcode string.

        Returns:
            Validated barrel serial, or None if invalid.
        """
        barcode = barcode.strip().upper()

        if self.validate_barrel_serial(barcode):
            return barcode

        logger.error(f"Invalid barrel serial format: {barcode}")
        return None

    def parse_serial_with_weight(self, barcode: str) -> Tuple[Optional[str], Optional[float]]:
        """Parse barcode containing serial and weight.

        Stage 2 STUB: Handles barcode format 'JAR0001261-1-C1-001|25.50'

        TODO: Implement this method for Stage 2.

        Args:
            barcode: Raw barcode string with '|' separator.

        Returns:
            Tuple of (barrel_serial, weight) or (None, None) if invalid.

        Example:
            >>> handler.parse_serial_with_weight('JAR0001261-1-C1-001|25.50')
            ('JAR0001261-1-C1-001', 25.50)
        """
        # TODO: Implement Stage 2 parsing
        # Split on '|' character
        # Parse serial using validate_barrel_serial
        # Parse weight as float
        logger.warning("parse_serial_with_weight() - STUB: Not implemented")
        return None, None

    def scan_barrel_serial(self) -> Optional[str]:
        """Scan and validate barrel serial.

        Reads from backend and validates format until successful or user cancels.

        Returns:
            Valid barrel serial, or None if cancelled.
        """
        logger.info("Scanning barrel serial...")

        while True:
            barcode = self._backend.scan()

            if barcode is None:
                logger.info("Scan cancelled")
                return None

            serial = self.parse_barrel_serial(barcode)

            if serial:
                logger.info(f"Valid barrel serial: {serial}")
                return serial

            print(f"Invalid format: {barcode}")
            print(f"Expected format: JAR0001261-1-C1-001")
            print("Try again or press Ctrl+C to cancel")

    def is_ready(self) -> bool:
        """Check if the backend is ready.

        Returns:
            True if ready, False otherwise.
        """
        return self._backend.is_ready()


def main():
    """Command-line interface for testing the barcode handler."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    parser = argparse.ArgumentParser(description='Barcode Handler Test')
    parser.add_argument(
        '--backend', '-b',
        choices=['keyboard', 'camera'],
        default=os.getenv('BARCODE_BACKEND', 'keyboard'),
        help='Barcode backend to use'
    )
    parser.add_argument(
        '--validate',
        help='Validate a specific serial without scanning'
    )

    args = parser.parse_args()

    print("=== Barcode Handler Test ===")
    print(f"Backend: {args.backend}")
    print(f"Pattern: JAR0001261-1-C1-001")
    print()

    handler = BarcodeHandler(backend=args.backend)

    if args.validate:
        serial = args.validate.upper()
        print(f"Validating: {serial}")
        is_valid = handler.validate_barrel_serial(serial)
        print(f"Result: {'VALID' if is_valid else 'INVALID'}")
        return

    print("Test serial: JAR0001261-1-C1-001")
    print("Press Enter to scan or Ctrl+C to exit")
    print()

    serial = handler.scan_barrel_serial()

    if serial:
        print(f"\nSUCCESS: {serial}")
    else:
        print("\nNo valid serial scanned")


if __name__ == '__main__':
    main()

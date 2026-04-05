#!/usr/bin/env python3
"""
Serial Port Sniffer - Intelligent Device Detection
==================================================
Detects serial devices and their data format:
- Scale weight data (ModbusRTU, plain text)
- Temperature sensors (DS18B20, DHT, etc.)
- Generic serial devices

Features:
- Hardware presence detection (DTR/RTS signals)
- Active polling/probing for devices
- Multi-baud rate scanning
- Temperature sensor detection
- Auto-config suggestions

Run: python3 port_sniffer.py [--port /dev/ttyUSB3] [--verbose]
"""
import sys
import os
import time
import re
import json
import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

# Check pyserial
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("ERROR: pyserial not installed")
    print("Install with: pip install pyserial")
    sys.exit(1)


@dataclass
class PortInfo:
    """Information about a serial port."""
    device: str
    description: str = ""
    hwid: str = ""
    location: str = ""

    # Hardware status
    connected: bool = False
    signals: Dict[str, bool] = field(default_factory=dict)

    # Data detection
    has_data: bool = False
    bytes_available: int = 0
    data_samples: List[str] = field(default_factory=list)
    format_type: Optional[str] = None

    # Device detection
    device_type: Optional[str] = None
    suggested_driver: Optional[str] = None
    suggested_config: Dict[str, Any] = field(default_factory=dict)

    # Polling results
    polled: bool = False
    polled_at_baud: int = 0

    # Error if any
    error: Optional[str] = None


class IntelligentPortSniffer:
    """Intelligently sniffs serial ports for devices and data."""

    # Common baud rates to try
    BAUD_RATES = [9600, 19200, 38400, 57600, 115200, 2400, 4800]

    # Commands to try polling with
    POLL_COMMANDS = {
        'scale': [b'W\r', b'w\r', b'RD\r', b'?\r', b'P\r', b'S\r'],
        'temp': [b'\xff\xfe\x01\x00', b'\x01\x04\x00\x00\x00\x01\x31\xca', b'RD\r'],
        'modbus': [b'\x01\x03\x00\x00\x00\x01\x84\x0a', b'\x01\x04\x00\x00\x00\x01\xB0\x0C'],
        'generic': [b'\r', b'\n', b'?', b'ID\r', b'V\r', b'*IDN?\r'],
    }

    # Temperature sensor patterns
    TEMP_PATTERNS = [
        (r'(\d+\.\d+)\s*[°°C]', 'celsius'),
        (r'(\d+\.\d+)\s*[°°F]', 'fahrenheit'),
        (r'Temp[:\s]+(\d+\.\d+)', 'celsius'),
        (r't=(\d+)', 'raw_celsius'),
        (r'T=(\d+\.\d+)', 'celsius'),
        (r'.*?(\d{2}:\d{2}:\d{2}).*?', 'time'),
        (r'Sensor\s*(\d+)', 'sensor_id'),
    ]

    # Weight patterns
    WEIGHT_PATTERNS = [
        (r'(\d+\.?\d*)\s*(?:kg|KG|Kg)', 'kg'),
        (r'(\d+\.?\d*)\s*(?:g|g\b)', 'grams'),
        (r'S\s*W[:\s]+(\d+\.?\d*)', 'stable_weight'),
        (r'W[:\s]+(\d+\.?\d*)', 'weight'),
        (r's(\d+)', 'scale_value'),
        (r'[+-]?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)', 'number'),
    ]

    def __init__(self, ports=None, timeout=2.0, verbose=False, probe=True):
        self.timeout = timeout
        self.verbose = verbose
        self.probe = probe
        self.ports = ports or self._list_all_ports()
        self.results: Dict[str, PortInfo] = {}

    def _list_all_ports(self) -> List[str]:
        """List all available serial ports with info."""
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append(port.device)
        return sorted(ports)

    def _get_port_info(self, port_name: str) -> PortInfo:
        """Get detailed info about a port."""
        info = PortInfo(device=port_name)

        try:
            port_details = None
            for p in serial.tools.list_ports.comports():
                if p.device == port_name:
                    port_details = p
                    break

            if port_details:
                info.description = port_details.description or "Unknown"
                info.hwid = port_details.hwid or "Unknown"
                info.location = port_details.location or "Unknown"

        except Exception as e:
            pass

        return info

    def _detect_device_type(self, samples: List[str]) -> Optional[str]:
        """Detect what type of device is connected."""
        text = ' '.join(samples).lower()

        # Temperature indicators
        if any(kw in text for kw in ['temp', 't=', 'humidity', 'hum', 'celsius', 'fahrenheit']):
            return 'temperature_sensor'

        # Scale/weight indicators
        if any(kw in text for kw in ['kg', 'weight', 'scale', 'balance', 'gram', 'g\r', 'kg\r']):
            return 'scale'

        # Modbus response
        if len(samples) > 0 and all(len(s) <= 10 for s in samples if isinstance(s, str)):
            # Short responses could be modbus binary
            return 'modbus_device'

        # Generic serial device
        return 'unknown'

    def _parse_data_format(self, data: bytes) -> tuple:
        """Parse data and determine format."""
        # Try ModbusRTU
        if self._is_modbus_rtu(data):
            weight = self._parse_modbus_weight(data)
            return 'modbus_rtu', f"Weight: {weight:.3f} kg" if weight else "Modbus data"

        # Try plain text
        try:
            text = data.decode('utf-8', errors='ignore').strip()
            if text:
                # Check for temperature
                for pattern, unit in self.TEMP_PATTERNS:
                    match = re.search(pattern, text)
                    if match:
                        return 'temperature', f"{match.group(0)[:50]}"

                # Check for weight
                for pattern, unit in self.WEIGHT_PATTERNS:
                    match = re.search(pattern, text)
                    if match:
                        return 'weight', f"{match.group(1)} {unit}"

                return 'plain_text', text[:60]
        except:
            pass

        # Binary data
        return 'binary', data.hex()[:40]

    def _is_modbus_rtu(self, data: bytes) -> bool:
        """Check if data is ModbusRTU."""
        if len(data) < 5:
            return False
        # Check function code
        if data[1] in [0x03, 0x04, 0x06, 0x10]:
            return True
        return False

    def _parse_modbus_weight(self, data: bytes) -> Optional[float]:
        """Extract weight from Modbus response."""
        try:
            if len(data) >= 6 and data[1] in [0x03, 0x04]:
                raw = (data[3] << 8) | data[4]
                return raw * 0.01
        except:
            pass
        return None

    def _check_hardware_signals(self, ser: serial.Serial) -> Dict[str, bool]:
        """Check hardware signals on port."""
        signals = {}
        try:
            signals['dtr'] = ser.dtr
            signals['rts'] = ser.rts
            signals['cts'] = ser.cts
            signals['dsr'] = ser.dsr
            signals['ri'] = ser.ri
            signals['cd'] = ser.cd
        except:
            pass
        return signals

    def _poll_port(self, ser: serial.Serial, device_hints: List[str] = None) -> List[str]:
        """Poll a port with various commands to get response."""
        samples = []
        hints = device_hints or ['generic', 'scale', 'temp', 'modbus']

        for hint in hints:
            commands = self.POLL_COMMANDS.get(hint, self.POLL_COMMANDS['generic'])
            for cmd in commands:
                try:
                    # Clear buffer
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()

                    # Send command
                    ser.write(cmd)
                    ser.flush()

                    # Wait for response
                    time.sleep(0.3)

                    if ser.in_waiting:
                        data = ser.read(ser.in_waiting)
                        if data:
                            fmt, parsed = self._parse_data_format(data)
                            samples.append(parsed)
                            return samples
                except Exception as e:
                    pass

        return samples

    def _probe_port_at_baud(self, port_name: str, baudrate: int) -> tuple:
        """Probe a port at specific baud rate."""
        info = PortInfo(device=port_name)
        info.polled = True
        info.polled_at_baud = baudrate

        try:
            ser = serial.Serial(
                port=port_name,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                write_timeout=1.0
            )

            info.connected = True
            info.signals = self._check_hardware_signals(ser)

            # Check if data already in buffer
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                fmt, parsed = self._parse_data_format(data)
                info.has_data = True
                info.format_type = fmt
                info.data_samples.append(parsed)
                return info, f"DATA: {parsed[:40]}"

            # Poll the device
            if self.probe:
                samples = self._poll_port(ser)
                if samples:
                    info.has_data = True
                    info.format_type = info._detect_device_type(samples) if hasattr(info, '_detect_device_type') else 'unknown'
                    info.data_samples.extend(samples)
                    return info, f"RESPONDED: {samples[0][:40]}"

            ser.close()

        except serial.SerialException as e:
            info.error = str(e)

        return info, None

    def _probe_port(self, port_name: str) -> PortInfo:
        """Probe a port at multiple baud rates."""
        best_info = self._get_port_info(port_name)
        best_info.connected = True

        # Check hardware signals first (no need to open port)
        try:
            ser = serial.Serial(port_name, baudrate=9600, timeout=0.1)
            best_info.signals = self._check_hardware_signals(ser)
            ser.close()
        except:
            pass

        has_hw = best_info.signals.get('dtr') or best_info.signals.get('rts')
        hw_status = "HW" if has_hw else ""

        print(f"  {port_name:<15} [9600]  {hw_status:>3}  ", end="", flush=True)

        # Try each baud rate
        for baudrate in self.BAUD_RATES:
            info, response = self._probe_port_at_baud(port_name, baudrate)

            if info.has_data:
                best_info = info
                print(f"{baudrate} baud -> {response}")
                break
            elif info.error:
                print(f"\n    └─ Error at {baudrate}: {info.error}")
        else:
            # No response at any baud rate
            if has_hw:
                print(f"No response (has hardware)")
            else:
                print(f"Empty port")

        return best_info

    def sniff(self) -> Dict[str, PortInfo]:
        """Scan all ports and detect devices."""
        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║           SERIAL PORT SNIFFER - Active Probing Mode          ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print()
        print(f"  Timeout: {self.timeout}s | Probing: {'Yes' if self.probe else 'No'}")
        print(f"  Baud rates: {self.BAUD_RATES}")
        print(f"  Ports found: {len(self.ports)}")
        print()
        print("─" * 65)
        print("  Port           Baud  HW  Status")
        print("─" * 65)

        for port in self.ports:
            info = self._probe_port(port)
            self.results[port] = info

        print("─" * 65)

        # Analyze results
        self._analyze_devices()

        return self.results

    def _analyze_devices(self):
        """Analyze detected devices and set types."""
        for port, info in self.results.items():
            if not info.data_samples:
                continue

            text_samples = ' '.join(str(s) for s in info.data_samples).lower()

            # Detect device type
            if any(kw in text_samples for kw in ['temp', 't=', 'celsius', 'fahrenheit']):
                info.device_type = 'temperature_sensor'
                info.suggested_driver = 'TemperatureSensor'
                info.suggested_config = {'poll_interval': 60, 'unit': 'celsius'}
            elif any(kw in text_samples for kw in ['kg', 'weight', 'g\r', 'gram', 'balance']):
                info.device_type = 'scale'
                if info.format_type == 'modbus_rtu':
                    info.suggested_driver = 'ModbusRTU'
                    info.suggested_config = {'slave_id': 1, 'scale_factor': 0.01}
                else:
                    info.suggested_driver = 'SerialCommand'
                    info.suggested_config = {'command': 'W', 'response_format': 'DECIMAL'}
            else:
                info.device_type = 'unknown_serial'
                info.suggested_driver = 'GenericSerial'
                info.suggested_config = {}

    def print_summary(self):
        """Print intelligent summary."""
        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║                     ANALYSIS SUMMARY                       ║")
        print("╚══════════════════════════════════════════════════════════════╝")

        # Categorize
        responding = [p for p, i in self.results.items() if i.has_data]
        hw_no_data = [p for p, i in self.results.items() if not i.has_data and (i.signals.get('dtr') or i.signals.get('rts'))]
        empty = [p for p, i in self.results.items() if not i.has_data and not i.signals.get('dtr') and not i.signals.get('rts')]
        errors = [p for p, i in self.results.items() if i.error]

        # Find device types
        scales = [p for p, i in self.results.items() if i.device_type == 'scale']
        temps = [p for p, i in self.results.items() if i.device_type == 'temperature_sensor']
        unknown = [p for p, i in self.results.items() if i.device_type == 'unknown_serial']

        print()

        if responding:
            print("  ✓ DEVICES RESPONDING:")
            for port in responding:
                info = self.results[port]
                print(f"    {port}")
                print(f"      └─ Type: {info.device_type or 'Unknown'}")
                print(f"      └─ Format: {info.format_type}")
                print(f"      └─ Baud: {info.polled_at_baud}")
                print(f"      └─ Driver: {info.suggested_driver}")
                if info.data_samples:
                    sample = info.data_samples[0][:50]
                    print(f"      └─ Sample: {sample}")
                print()
        else:
            print("  ⚠️  NO DEVICES RESPONDING TO POLL")
            print()

        if hw_no_data:
            print("  📦 HARDWARE DETECTED (no data):")
            for port in hw_no_data:
                info = self.results[port]
                sigs = []
                if info.signals.get('dtr'): sigs.append('DTR')
                if info.signals.get('rts'): sigs.append('RTS')
                print(f"    • {port}: {', '.join(sigs) if sigs else 'unknown signal'}")
            print()
            print("  Possible issues:")
            print("    1. Device is sleeping, needs wake-up command")
            print("    2. Wrong serial settings (8N1 may not match)")
            print("    3. Device needs special initialization")
            print("    4. TX/RX wires might be swapped")
            print()

        if empty:
            print("  🔌 EMPTY PORTS (no hardware):")
            for port in empty:
                print(f"    • {port}")
            print()

        if errors:
            print("  ❌ ERRORS:")
            for port in errors:
                print(f"    • {port}: {self.results[port].error}")
            print()

        # Recommendations
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║                    RECOMMENDATIONS                           ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print()

        if scales:
            print(f"  🔧 Found SCALE on: {', '.join(scales)}")
            print()
            for port in scales:
                info = self.results[port]
                print(f"    doc = frappe.get_doc('Sensor Skill', 'scale_plant')")
                print(f"    doc.port = '{port}'")
                print(f"    doc.driver = '{info.suggested_driver}'")
                print(f"    doc.python_config = '{json.dumps(info.suggested_config)}'")
                print(f"    doc.baudrate = {info.polled_at_baud}")
                print(f"    doc.save(); frappe.db.commit()")
                print()
            return

        if temps:
            print(f"  🌡️  Found TEMPERATURE SENSOR on: {', '.join(temps)}")
            print()

        if unknown:
            print(f"  ❓ Unknown devices on: {', '.join(unknown)}")
            for port in unknown:
                info = self.results[port]
                if info.data_samples:
                    print(f"    {port}: {info.data_samples[0][:50]}")
            print()

        if not responding:
            print("  📝 NEXT STEPS:")
            print()
            print("    1. Check physical connections")
            print("    2. Verify device power is ON")
            print("    3. Try pressing a button on the device")
            print("    4. Check TX/RX are not reversed")
            print("    5. For testing, use: python3 rpi_client/tester.py --mode simulator")
            print()

        print("─" * 65)

    def get_best_scale_port(self) -> Optional[PortInfo]:
        """Get the best port for a scale."""
        for port, info in self.results.items():
            if info.device_type == 'scale' and info.has_data:
                return info
        for port, info in self.results.items():
            if info.has_data:
                return info
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Intelligent Serial Port Sniffer with Active Probing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 port_sniffer.py                    # Scan all ports with probing
  python3 port_sniffer.py --port /dev/ttyUSB3  # Scan specific port
  python3 port_sniffer.py --timeout 5        # Longer timeout
  python3 port_sniffer.py --no-probe         # Passive mode only (no polling)
        """
    )
    parser.add_argument('--port', '-p', help='Specific port to check')
    parser.add_argument('--timeout', '-t', type=float, default=2.0,
                       help='Timeout per port (seconds, default: 2)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')
    parser.add_argument('--no-probe', action='store_true',
                       help='Disable active probing (passive mode only)')
    args = parser.parse_args()

    ports = [args.port] if args.port else None

    sniffer = IntelligentPortSniffer(
        ports=ports,
        timeout=args.timeout,
        verbose=args.verbose,
        probe=not args.no_probe
    )
    results = sniffer.sniff()
    sniffer.print_summary()

    # Auto-generate update script if scale found
    best = sniffer.get_best_scale_port()
    if best:
        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║                 AUTO-GENERATE SCRIPT                        ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print()
        print("Run this on your ERPNext server:")
        print()
        print("```python")
        print("import frappe")
        print("import json")
        print()
        print(f"doc = frappe.get_doc('Sensor Skill', 'scale_plant')")
        print(f"doc.port = '{best.device}'")
        print(f"doc.driver = '{best.suggested_driver}'")
        print(f"doc.baudrate = {best.polled_at_baud}")
        print(f"doc.python_config = '{json.dumps(best.suggested_config)}'")
        print("doc.save()")
        print("frappe.db.commit()")
        print("print('Updated!')")
        print("```")


if __name__ == "__main__":
    main()

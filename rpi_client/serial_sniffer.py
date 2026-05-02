#!/usr/bin/env python3
"""
Serial Port Sniffer & Protocol Detector
======================================
Sniffs all serial ports to detect connected devices and their data format.

Features:
- Scans all /dev/ttyUSB* and /dev/ttyACM* ports
- Detects data format (ModbusRTU, plain text, binary)
- Identifies baud rate by analyzing data patterns
- Auto-detects scale protocol

Usage:
    python3 serial_sniffer.py [--duration 10] [--ports ttyUSB0,ttyUSB1]
"""
import sys
import os
import time
import threading
import argparse
from collections import defaultdict
from typing import List, Dict, Optional, Tuple

# Check for pyserial
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("ERROR: pyserial not installed")
    print("Install with: pip install pyserial")
    sys.exit(1)


class SerialSniffer:
    """Sniffs serial ports to detect devices and data."""

    def __init__(self, duration: int = 10, ports: List[str] = None):
        self.duration = duration
        self.ports_to_scan = ports
        self.results: Dict[str, dict] = {}
        self.running = False
        self.threads: List[threading.Thread] = []

    def get_all_ports(self) -> List[str]:
        """Get all available serial ports."""
        ports = []

        # List from /dev
        for pattern in ['/dev/ttyUSB*', '/dev/ttyACM*']:
            import glob
            ports.extend(glob.glob(pattern))

        # Filter by specific ports if provided
        if self.ports_to_scan:
            ports = [p for p in ports if os.path.basename(p) in self.ports_to_scan]

        return sorted(ports)

    def analyze_data(self, data: bytes) -> dict:
        """Analyze received data to determine format."""
        analysis = {
            'raw_hex': data.hex(),
            'raw_bytes': list(data),
            'length': len(data),
            'format': 'unknown',
            'likely_protocol': None,
            'details': {}
        }

        if len(data) == 0:
            analysis['format'] = 'empty'
            return analysis

        # Check for ModbusRTU pattern
        # Modbus format: [slave_id][function][data][crc_low][crc_high]
        if 4 <= len(data) <= 16:
            analysis['format'] = 'modbus'
            analysis['likely_protocol'] = 'ModbusRTU'
            analysis['details'] = {
                'slave_id': data[0] if len(data) > 0 else None,
                'function_code': data[1] if len(data) > 1 else None,
                'byte_count': data[2] if len(data) > 2 else None,
                'crc_present': len(data) >= 4
            }

            # Try to decode weight from Modbus
            if len(data) >= 5:
                weight_high = data[3]
                weight_low = data[4]
                weight_raw = (weight_high << 8) | weight_low
                analysis['details']['decoded_weight'] = weight_raw
                analysis['details']['weight_with_scale_factor'] = {
                    'scale_0.01': weight_raw * 0.01,
                    'scale_0.001': weight_raw * 0.001,
                    'scale_0.1': weight_raw * 0.1,
                }

        # Check for plain text (ASCII printable + common control chars)
        try:
            text = data.decode('ascii', errors='ignore')
            # Check if mostly printable
            printable_count = sum(1 for c in text if c.isprintable() or c in '\r\n\t')
            if printable_count > len(text) * 0.8 and len(text) > 0:
                analysis['format'] = 'text'
                analysis['details']['text'] = repr(text.strip())
                analysis['details']['likely_scale_output'] = True

                # Try to extract weight from text
                import re
                weights = re.findall(r'(\d+\.?\d*)\s*(kg|KG|lb|LB|g|G)?', text)
                if weights:
                    analysis['details']['extracted_weights'] = weights

                    # Try to identify protocol
                    if 'kg' in text.lower():
                        analysis['likely_protocol'] = 'PlainTextScale'
                    elif 'W' in text and len(text) < 20:
                        analysis['likely_protocol'] = 'SerialCommand (response)'
        except:
            pass

        # Check for binary data
        if analysis['format'] == 'unknown':
            analysis['format'] = 'binary'
            analysis['likely_protocol'] = 'UnknownBinary'
            # Check for specific patterns
            if len(data) >= 2:
                combined = (data[0] << 8) | data[1]
                analysis['details']['16bit_value'] = combined

        return analysis

    def sniff_port(self, port: str, timeout: float = 1.0):
        """Sniff a single port."""
        results = {
            'port': port,
            'device_id': None,
            'readings': [],
            'data_samples': [],
            'baud_rates_detected': [],
            'formats_detected': set(),
            'protocol_suggestion': None,
            'error': None
        }

        # Get device info
        try:
            info = serial.tools.list_ports.grep(port)
            for p in info:
                results['device_id'] = p[2] if len(p) > 2 else None
                break
        except:
            pass

        # Try common baud rates
        baud_rates = [9600, 19200, 38400, 57600, 115200, 4800, 2400]

        for baud in baud_rates:
            ser = None
            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=baud,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=timeout
                )

                # Read multiple times to detect data
                samples = []
                for i in range(3):
                    if ser.in_waiting:
                        data = ser.read(ser.in_waiting)
                        if data:
                            samples.append(data)
                            analysis = self.analyze_data(data)
                            results['formats_detected'].add(analysis['format'])
                            results['data_samples'].append({
                                'baud': baud,
                                'analysis': analysis
                            })
                    time.sleep(0.5)

                if samples:
                    results['baud_rates_detected'].append(baud)
                    results['readings'].extend(samples)

            except serial.SerialException as e:
                pass
            finally:
                if ser and ser.is_open:
                    ser.close()

        # Determine best protocol suggestion
        all_samples = results['data_samples']
        if not all_samples:
            results['protocol_suggestion'] = 'No data detected'
            return results

        # Get first sample's analysis
        first_analysis = all_samples[0]['analysis']

        if first_analysis['likely_protocol']:
            results['protocol_suggestion'] = first_analysis['likely_protocol']
        elif 'modbus' in first_analysis['format']:
            results['protocol_suggestion'] = 'ModbusRTU'
        else:
            results['protocol_suggestion'] = 'PlainText or Unknown'

        return results

    def run(self):
        """Run the sniffer on all ports."""
        print("=" * 70)
        print("SERIAL PORT SNIFFER & PROTOCOL DETECTOR")
        print("=" * 70)

        ports = self.get_all_ports()
        print(f"\nScanning {len(ports)} ports for {self.duration} seconds...")
        print(f"Ports: {', '.join(ports) if ports else 'None found'}")
        print()

        if not ports:
            print("No serial ports found!")
            return

        # Scan each port
        for port in ports:
            print(f"[*] Sniffing {port}...", end=" ", flush=True)

            # Run in thread to allow parallel scanning
            thread = threading.Thread(target=self._sniff_and_store, args=(port,))
            thread.start()
            self.threads.append(thread)

        # Wait for all threads
        for thread in self.threads:
            thread.join()

        # Print results
        self._print_results()

    def _sniff_and_store(self, port: str):
        """Sniff port and store results."""
        self.results[port] = self.sniff_port(port)
        print("done")

    def _print_results(self):
        """Print analysis results."""
        print("\n" + "=" * 70)
        print("RESULTS")
        print("=" * 70)

        has_data = False
        for port, results in sorted(self.results.items()):
            print(f"\n{'─' * 70}")
            print(f"📡 {port}")
            print(f"{'─' * 70}")

            if results['device_id']:
                print(f"   Device ID: {results['device_id']}")

            if not results['readings']:
                print("   Status: ❌ No data detected")
                continue

            has_data = True
            print(f"   Status: ✅ Data detected!")
            print(f"   Suggested Protocol: {results['protocol_suggestion']}")

            if results['baud_rates_detected']:
                print(f"   Detected Baud Rates: {results['baud_rates_detected']}")

            print(f"   Formats Detected: {', '.join(results['formats_detected'])}")

            # Show sample data
            print("\n   📊 Data Samples:")
            for i, sample in enumerate(results['data_samples'][:3], 1):
                analysis = sample['analysis']
                print(f"\n   Sample {i} (baud: {sample['baud']}):")
                print(f"      Format: {analysis['format']}")
                print(f"      Raw: {analysis['raw_hex']}")

                if analysis['details']:
                    print(f"      Details:")
                    for k, v in analysis['details'].items():
                        if k != 'text':
                            print(f"        {k}: {v}")
                    if 'text' in analysis['details']:
                        print(f"        text: {analysis['details']['text']}")

        if not has_data:
            print("\n⚠️  No serial data detected on any port.")
            print("\nTroubleshooting:")
            print("  1. Check USB connections")
            print("  2. Verify device is powered on")
            print("  3. Check if device is already open by another process")
            print("  4. Run as root: sudo python3 serial_sniffer.py")
        else:
            print("\n" + "=" * 70)
            print("RECOMMENDATIONS")
            print("=" * 70)

            for port, results in sorted(self.results.items()):
                if results['readings'] and results['protocol_suggestion']:
                    protocol = results['protocol_suggestion']
                    baud = results['baud_rates_detected'][0] if results['baud_rates_detected'] else 9600

                    print(f"\n{port}:")
                    print(f"  Protocol: {protocol}")
                    print(f"  Baud Rate: {baud}")

                    if 'ModbusRTU' in str(protocol):
                        print(f"  Config: python_config = {{'driver':'ModbusRTU','slave_id':1,'scale_factor':0.01}}")
                    elif 'PlainText' in str(protocol):
                        print(f"  Config: python_config = {{'driver':'SerialCommand','command':'W','response_format':'DECIMAL'}}")


def main():
    parser = argparse.ArgumentParser(description='Serial Port Sniffer & Protocol Detector')
    parser.add_argument('-d', '--duration', type=int, default=10,
                       help='Duration to sniff each port (seconds)')
    parser.add_argument('-p', '--ports', type=str, default='',
                       help='Comma-separated ports to scan (e.g., ttyUSB0,ttyUSB1)')

    args = parser.parse_args()

    ports = args.ports.split(',') if args.ports else None

    sniffer = SerialSniffer(duration=args.duration, ports=ports)
    sniffer.run()


if __name__ == '__main__':
    main()

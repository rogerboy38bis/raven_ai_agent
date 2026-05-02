#!/usr/bin/env python3
"""
Dummy Scale Simulator - ModbusRTU Slave Device
================================================
Implements proper ModbusRTU slave behavior for testing with minimalmodbus.

Usage:
    python3 dummy_scale.py /dev/ttyUSB0 9600

This script acts as a ModbusRTU SLAVE:
- Listens for incoming Modbus requests from minimalmodbus (master)
- Responds with weight data when addressed correctly

ModbusRTU Protocol:
- Master (minimalmodbus) sends: [SlaveID] [Function] [Addr Hi] [Addr Lo] [Count Hi] [Count Lo] [CRC]
- Slave (this) responds with:    [SlaveID] [Function] [ByteCount] [Data...] [CRC]
"""
import sys
import time
import random
import struct

# Check if pyserial is available
try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed")
    print("Install with: pip install pyserial")
    sys.exit(1)


class DummyModbusScale:
    """Simulates a ModbusRTU scale device (SLAVE behavior).

    This implements proper Modbus slave behavior:
    - Listens for Modbus request frames
    - Validates CRC
    - Responds with appropriate function code
    """

    FUNCTION_READ_HOLDING = 0x03
    FUNCTION_READ_INPUT = 0x04

    def __init__(self, port, baudrate=9600, slave_id=1, base_weight=25.0):
        self.port = port
        self.baudrate = baudrate
        self.slave_id = slave_id
        self.base_weight = base_weight
        self.current_weight = base_weight
        self.ser = None
        self.running = False

    def connect(self):
        """Open serial connection."""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0  # Timeout for reading
            )
            print(f"Connected to {self.port} at {self.baudrate} baud (Slave ID: {self.slave_id})")
            return True
        except serial.SerialException as e:
            print(f"Failed to open {self.port}: {e}")
            return False

    def _crc16_modbus(self, data):
        """Calculate CRC16-MODBUS (same as standard Modbus)."""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc

    def _verify_crc(self, frame):
        """Verify CRC of a Modbus frame."""
        if len(frame) < 3:
            return False
        # CRC is last 2 bytes (low byte first, high byte second)
        received_crc = frame[-2] | (frame[-1] << 8)
        data_without_crc = frame[:-2]
        calculated_crc = self._crc16_modbus(data_without_crc)
        return received_crc == calculated_crc

    def _generate_weight(self):
        """Generate a realistic weight reading with small variations."""
        # Add small random fluctuation (±0.05kg)
        variation = random.uniform(-0.05, 0.05)
        self.current_weight = self.base_weight + variation
        # Ensure weight stays in valid range
        self.current_weight = max(0.5, min(500, self.current_weight))
        return round(self.current_weight, 2)

    def _build_response(self, function, data_bytes):
        """Build a Modbus response frame with correct CRC."""
        response = bytes([self.slave_id, function, len(data_bytes)]) + data_bytes
        crc = self._crc16_modbus(response)
        response += bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        return response

    def _handle_read_holding_registers(self, addr_hi, addr_lo, count_hi, count_lo):
        """Handle Read Holding Registers (Function 0x03).

        minimalmodbus read_register(0, 0) sends:
        [SlaveID] [0x03] [AddrHi] [AddrLo] [CountHi] [CountLo] [CRC]
        """
        # Note: scale_reader.py uses read_register(0, 0) - one register starting at 0
        start_addr = (addr_hi << 8) | addr_lo
        quantity = (count_hi << 8) | count_lo

        print(f"  -> Read Holding Registers: addr={start_addr}, count={quantity}")

        # Weight value as 16-bit register (scaled by 100 = scale_factor 0.01)
        # For 25.00 kg -> register value = 2500
        weight_reg = int(self._generate_weight() * 100)

        # High byte first, low byte second
        reg_hi = (weight_reg >> 8) & 0xFF
        reg_lo = weight_reg & 0xFF

        print(f"  -> Weight: {self.current_weight:.2f} kg -> register={weight_reg} (0x{weight_reg:04X})")

        return bytes([reg_hi, reg_lo])

    def _handle_read_input_registers(self, addr_hi, addr_lo, count_hi, count_lo):
        """Handle Read Input Registers (Function 0x04)."""
        start_addr = (addr_hi << 8) | addr_lo
        quantity = (count_hi << 8) | count_lo

        print(f"  -> Read Input Registers: addr={start_addr}, count={quantity}")

        weight_reg = int(self._generate_weight() * 100)
        reg_hi = (weight_reg >> 8) & 0xFF
        reg_lo = weight_reg & 0xFF

        return bytes([reg_hi, reg_lo])

    def _process_request(self, request):
        """Process an incoming Modbus request and build response.

        Returns:
            bytes: Response frame to send, or None if no response needed
        """
        if len(request) < 5:
            print(f"  <- Short frame: {request.hex()}")
            return None

        # Parse request
        slave_id = request[0]
        function = request[1]
        addr_hi = request[2]
        addr_lo = request[3]
        count_hi = request[4]
        count_lo = request[5]

        print(f"  <- Request: slave={slave_id}, func=0x{function:02X}, addr={addr_hi:02X}{addr_lo:02X}")

        # Check if addressed to us
        if slave_id != self.slave_id:
            print(f"  <- Not addressed to us (slave {self.slave_id}), ignoring")
            return None

        # Check CRC
        if not self._verify_crc(request):
            print(f"  <- CRC error!")
            return None

        # Handle function codes
        if function == self.FUNCTION_READ_HOLDING:
            data = self._handle_read_holding_registers(addr_hi, addr_lo, count_hi, count_lo)
            return self._build_response(self.FUNCTION_READ_HOLDING, data)

        elif function == self.FUNCTION_READ_INPUT:
            data = self._handle_read_input_registers(addr_hi, addr_lo, count_hi, count_lo)
            return self._build_response(self.FUNCTION_READ_INPUT, data)

        else:
            # Exception: function not supported
            print(f"  <- Unsupported function: 0x{function:02X}")
            # Exception response: function | 0x80, exception code 1
            error_resp = bytes([self.slave_id, function | 0x80, 0x01])
            crc = self._crc16_modbus(error_resp)
            error_resp += bytes([crc & 0xFF, (crc >> 8) & 0xFF])
            return error_resp

    def run(self):
        """Run the Modbus slave loop - listen for requests and respond."""
        if not self.connect():
            return

        self.running = True
        print(f"ModbusRTU Slave running on {self.port}...")
        print("Waiting for requests from master (minimalmodbus)...")
        print("Press Ctrl+C to stop")

        try:
            while self.running:
                # Read available bytes
                if self.ser.in_waiting > 0:
                    # Read up to 20 bytes (enough for a Modbus request frame)
                    # Request format: [slave][func][addr_hi][addr_lo][count_hi][count_lo][crc_lo][crc_hi] = 8 bytes
                    request = self.ser.read(min(self.ser.in_waiting, 20))

                    if request:
                        print(f"\n[Request received: {request.hex()}]")
                        response = self._process_request(request)

                        if response:
                            print(f"[Response: {response.hex()}]")
                            self.ser.write(response)
                            print("[Response sent]")

                time.sleep(0.1)  # Small delay to prevent CPU spin

        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            self.close()

    def close(self):
        """Close serial connection."""
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Serial port closed")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 dummy_scale.py <port> [baudrate] [slave_id] [base_weight]")
        print("")
        print("Arguments:")
        print("  port       - Serial port (e.g., /dev/ttyUSB0, COM3)")
        print("  baudrate   - Baud rate (default: 9600)")
        print("  slave_id   - Modbus slave ID (default: 1)")
        print("  base_weight - Base weight in kg (default: 25.0)")
        print("")
        print("Example:")
        print("  python3 dummy_scale.py /dev/ttyUSB3 9600 1 25.5")
        print("")
        print("This implements ModbusRTU SLAVE behavior:")
        print("  - Listens for requests from minimalmodbus (master)")
        print("  - Responds with weight data when addressed")
        sys.exit(1)

    port = sys.argv[1]
    baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 9600
    slave_id = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    base_weight = float(sys.argv[4]) if len(sys.argv) > 4 else 25.0

    scale = DummyModbusScale(port, baudrate, slave_id, base_weight)
    scale.run()


if __name__ == "__main__":
    main()

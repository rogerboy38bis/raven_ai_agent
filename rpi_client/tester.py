#!/usr/bin/env python3
"""
Scale Reader Diagnostic Tester
==============================
Tests each component of the scale reading pipeline to identify where data is lost.

Run: python3 tester.py

For ModbusRTU loopback test (requires two terminal windows):
  Terminal 1: python3 dummy_scale.py /dev/ttyUSB3 9600 1 25.0
  Terminal 2: python3 tester.py --modbus-loopback /dev/ttyUSB3
"""
import sys
import os
import time
import threading

# Add rpi_client to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("SCALE READER DIAGNOSTIC TESTER")
print("=" * 60)

# Test 1: Import sensor_skill_client
print("\n[TEST 1] Importing sensor_skill_client...")
try:
    from sensor_skill_client import SensorSkillClient, SENSOR_SKILL_AVAILABLE
    print(f"  SENSOR_SKILL_AVAILABLE = {SENSOR_SKILL_AVAILABLE}")
    print("  PASS: sensor_skill_client imported")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 2: Get sensor config from API
print("\n[TEST 2] Fetching Sensor Skill config...")
try:
    client = SensorSkillClient(skill_id='scale_plant')
    config = client.get_config()
    print(f"  Port: {config.get('port')}")
    print(f"  Baud Rate: {config.get('baud_rate')}")
    print(f"  Max Value: {config.get('max_value')}")
    driver = config.get('python_config', {}).get('driver', 'N/A')
    print(f"  Driver: {driver}")
    print("  PASS: Config fetched successfully")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 3: Import scale_reader
print("\n[TEST 3] Importing scale_reader...")
try:
    from scale_reader import ScaleReader, ScaleReaderError
    print("  PASS: scale_reader imported")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 4: Test with simulator backend
print("\n[TEST 4] Testing with simulator backend...")
try:
    sim_reader = ScaleReader(backend='simulator', skill_id='scale_plant')
    print(f"  is_connected() = {sim_reader.is_connected()}")
    weight = sim_reader.read_weight()
    print(f"  Weight: {weight} kg")
    sim_reader.close()
    print("  PASS: Simulator works")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 5: Import dummy_scale
print("\n[TEST 5] Importing dummy_scale...")
try:
    from dummy_scale import DummyModbusScale
    print("  PASS: dummy_scale imported")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 6: Test ModbusRTU loopback (requires dummy_scale running)
print("\n[TEST 6] Testing ModbusRTU loopback...")
print("  NOTE: Run 'python3 dummy_scale.py <port> 9600' in another terminal first!")
print("  Or use: python3 tester.py --modbus-loopback /dev/ttyUSB3")

# Parse command line for loopback test
import argparse
parser = argparse.ArgumentParser(description='Scale Reader Diagnostic')
parser.add_argument('--modbus-loopback', metavar='PORT',
                    help='Test ModbusRTU loopback with dummy_scale on PORT')
args = parser.parse_args()

if args.modbus_loopback:
    # Test with specified port
    test_port = args.modbus_loopback
    print(f"\n  Testing with port: {test_port}")

    try:
        import serial
        # Check if port exists
        try:
            ser = serial.Serial(test_port, 9600, timeout=0.5)
            ser.close()
            print(f"  Port {test_port} is accessible")
        except serial.SerialException:
            print(f"  WARN: Port {test_port} not accessible")
            print("  Make sure dummy_scale.py is running on this port")

        reader = ScaleReader(backend='sensor_skill', skill_id='scale_plant')
        print(f"  ScaleReader created with backend={reader.backend_name}")

        # Override port from sensor skill config
        reader._backend._config['port'] = test_port
        print(f"  Port overridden to: {test_port}")

        print("  Attempting to read weight...")
        is_connected = reader.is_connected()
        print(f"  is_connected() = {is_connected}")

        if is_connected:
            weight = reader.read_weight()
            print(f"  Weight: {weight} kg")
            print("  PASS: ModbusRTU loopback successful!")
        else:
            print("  WARN: Not connected - check if dummy_scale is running")

        reader.close()

    except Exception as e:
        print(f"  FAIL: {e}")
        import traceback
        traceback.print_exc()
else:
    print("  SKIP: --modbus-loopback not specified")
    print("  To test ModbusRTU, run in two terminals:")
    print("    Terminal 1: python3 dummy_scale.py /dev/ttyUSB3 9600")
    print("    Terminal 2: python3 tester.py --modbus-loopback /dev/ttyUSB3")

# Test 7: Create ScaleReader instance
print("\n[TEST 7] Creating ScaleReader instance...")
try:
    reader = ScaleReader(backend='sensor_skill', skill_id='scale_plant')
    print(f"  backend_name: {reader.backend_name}")
    print(f"  skill_id: {reader.skill_id}")
    print("  PASS: ScaleReader created")
except Exception as e:
    print(f"  FAIL: {e}")

# Summary
print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
print("\nIf any test shows FAIL, check the error message above.")
print("\nCommon issues and fixes:")
print("  1. 'No module named minimalmodbus':")
print("     pip install minimalmodbus")
print("")
print("  2. 'API credentials not configured':")
print("     Set ERPNEXT_URL, ERPNEXT_API_KEY, ERPNEXT_API_SECRET in .env")
print("")
print("  3. 'Port /dev/ttyUSB0 not found':")
print("     Update Sensor Skill port on server: bench console")
print("     doc = frappe.get_doc('Sensor Skill', 'scale_plant')")
print("     doc.port = '/dev/ttyUSB3'")
print("     doc.save()")
print("")
print("  4. Scale not connected:")
print("     - Check USB cable")
print("     - Verify port matches Sensor Skill config")
print("     - Try different port (ttyUSB0, ttyUSB1, etc.)")
print("")
print("  5. ModbusRTU test (loopback):")
print("     Terminal 1: python3 dummy_scale.py /dev/ttyUSB3 9600 1 25.0")
print("     Terminal 2: python3 tester.py --modbus-loopback /dev/ttyUSB3")

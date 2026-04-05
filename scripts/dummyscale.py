#!/usr/bin/env python3
"""Dummy Scale Simulator for PH13.4.0 testing.
Simulates a ModbusRTU scale by serving random stable weights
via a simple TCP socket that the scale_reader can connect to,
or by creating a virtual serial port pair.

Usage:
  python3 dummyscale.py [--port 9876] [--weight 25.03] [--jitter 0.005]
"""
import argparse
import socket
import struct
import time
import random
import threading
import json
import sys

class DummyScale:
    def __init__(self, base_weight=25.03, jitter=0.005, stable_after=3):
        self.base_weight = base_weight
        self.jitter = jitter
        self.stable_after = stable_after
        self.readings = 0

    def read_weight(self):
        self.readings += 1
        noise = random.uniform(-self.jitter, self.jitter)
        w = round(self.base_weight + noise, 3)
        stable = self.readings >= self.stable_after
        return w, stable

    def reset(self):
        self.readings = 0

def run_tcp_server(host, port, scale):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(5)
    print(f"[DummyScale] TCP server listening on {host}:{port}")
    print(f"[DummyScale] Base weight: {scale.base_weight} kg, jitter: +/-{scale.jitter}")
    print(f"[DummyScale] Send 'read' to get weight, 'reset' to reset stability counter")
    while True:
        conn, addr = srv.accept()
        print(f"[DummyScale] Connection from {addr}")
        try:
            while True:
                data = conn.recv(1024).decode().strip()
                if not data:
                    break
                if data == 'read':
                    w, stable = scale.read_weight()
                    resp = json.dumps({"weight": w, "stable": stable, "unit": "kg"})
                    conn.sendall((resp + "\n").encode())
                elif data == 'reset':
                    scale.reset()
                    conn.sendall(b'{"status":"reset"}\n')
                else:
                    conn.sendall(b'{"error":"unknown command"}\n')
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            conn.close()
            print(f"[DummyScale] {addr} disconnected")

def run_stdout_mode(scale, interval=1.0):
    print(f"[DummyScale] Stdout mode - printing weights every {interval}s")
    print(f"[DummyScale] Base: {scale.base_weight} kg, jitter: +/-{scale.jitter}")
    try:
        while True:
            w, stable = scale.read_weight()
            mark = "STABLE" if stable else "..."
            print(f"  {w:.3f} kg  {mark}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[DummyScale] Stopped.")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Dummy Scale Simulator")
    p.add_argument("--port", type=int, default=9876, help="TCP port (0=stdout mode)")
    p.add_argument("--weight", type=float, default=25.03, help="Base weight in kg")
    p.add_argument("--jitter", type=float, default=0.005, help="Random jitter +/-")
    p.add_argument("--stdout", action="store_true", help="Print to stdout instead of TCP")
    args = p.parse_args()

    scale = DummyScale(base_weight=args.weight, jitter=args.jitter)
    if args.stdout:
        run_stdout_mode(scale)
    else:
        run_tcp_server("0.0.0.0", args.port, scale)

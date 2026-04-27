#!/usr/bin/env python3
"""Shared gate helpers for KTOX extensions - BLE workflow control."""
from __future__ import annotations

import time
import subprocess
from typing import Optional


def _scan_ble_devices(scan_window_seconds: int = 4) -> dict[str, dict]:
    """
    Scan for BLE devices using bluetoothctl.

    Returns dict of device_address -> {"name": str, "rssi": int, "services": [uuid, ...]}
    """
    devices = {}
    try:
        # Start BLE scan
        subprocess.run(
            ["bluetoothctl", "scan", "on"],
            capture_output=True,
            timeout=2,
        )
        time.sleep(scan_window_seconds)

        # Get devices
        result = subprocess.run(
            ["bluetoothctl", "devices"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        for line in result.stdout.split('\n'):
            parts = line.split()
            if len(parts) >= 3 and parts[0] == 'Device':
                addr = parts[1]
                name = ' '.join(parts[2:])
                devices[addr] = {"name": name, "rssi": 0, "services": []}

        # Stop scan
        subprocess.run(
            ["bluetoothctl", "scan", "off"],
            capture_output=True,
            timeout=2,
        )
    except Exception:
        pass

    return devices


def WAIT_FOR_PRESENT(
    *,
    name: str = "",
    mac: str = "",
    service_uuid: str = "",
    timeout_seconds: int = 0,
    scan_window_seconds: int = 4,
    poll_interval_seconds: int = 2,
    fail_closed: bool = True,
) -> bool:
    """
    Wait until a BLE device becomes present.

    Args:
        name: Advertised device name to match (partial match)
        mac: MAC address to match (e.g., "AA:BB:CC:DD:EE:FF")
        service_uuid: Service UUID to match
        timeout_seconds: Max wait time (0 = infinite)
        scan_window_seconds: Duration of each BLE scan window
        poll_interval_seconds: Interval between scans
        fail_closed: If True, raise on timeout; if False, return False

    Returns:
        True if device found, False if timeout and warn_only mode

    Raises:
        TimeoutError: If timeout and fail_closed=True
        RuntimeError: If BLE unavailable and fail_closed=True
    """
    start = time.monotonic()

    while True:
        try:
            devices = _scan_ble_devices(scan_window_seconds)

            for addr, info in devices.items():
                # Match by MAC
                if mac and addr.upper() != mac.upper():
                    continue
                # Match by name
                if name and name.lower() not in info["name"].lower():
                    continue
                # Match by service (stub - requires service introspection)
                if service_uuid:
                    if service_uuid not in info.get("services", []):
                        continue

                return True
        except Exception as e:
            if fail_closed:
                raise RuntimeError(f"BLE scan failed: {e}")
            return False

        if timeout_seconds > 0:
            elapsed = time.monotonic() - start
            if elapsed >= timeout_seconds:
                if fail_closed:
                    raise TimeoutError("WAIT_FOR_PRESENT timed out")
                return False

        time.sleep(poll_interval_seconds)


def WAIT_FOR_NOTPRESENT(
    *,
    name: str = "",
    mac: str = "",
    service_uuid: str = "",
    timeout_seconds: int = 0,
    scan_window_seconds: int = 4,
    poll_interval_seconds: int = 2,
    fail_closed: bool = True,
) -> bool:
    """
    Wait until a BLE device is no longer present.

    Args:
        name: Advertised device name to match (partial match)
        mac: MAC address to match
        service_uuid: Service UUID to match
        timeout_seconds: Max wait time (0 = infinite)
        scan_window_seconds: Duration of each BLE scan window
        poll_interval_seconds: Interval between scans
        fail_closed: If True, raise on timeout; if False, return False

    Returns:
        True if device disappeared, False if timeout and warn_only mode

    Raises:
        TimeoutError: If timeout and fail_closed=True
        RuntimeError: If BLE unavailable and fail_closed=True
    """
    start = time.monotonic()

    while True:
        try:
            devices = _scan_ble_devices(scan_window_seconds)
            device_found = False

            for addr, info in devices.items():
                # Match by MAC
                if mac and addr.upper() != mac.upper():
                    continue
                # Match by name
                if name and name.lower() not in info["name"].lower():
                    continue
                # Match by service (stub)
                if service_uuid:
                    if service_uuid not in info.get("services", []):
                        continue

                device_found = True
                break

            if not device_found:
                return True
        except Exception as e:
            if fail_closed:
                raise RuntimeError(f"BLE scan failed: {e}")
            return False

        if timeout_seconds > 0:
            elapsed = time.monotonic() - start
            if elapsed >= timeout_seconds:
                if fail_closed:
                    raise TimeoutError("WAIT_FOR_NOTPRESENT timed out")
                return False

        time.sleep(poll_interval_seconds)

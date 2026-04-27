#!/usr/bin/env python3
"""CLI wrapper for WAIT_FOR_NOTPRESENT."""
from __future__ import annotations

import argparse
import sys

from api import WAIT_FOR_NOTPRESENT


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait until a BLE device is no longer present.")
    parser.add_argument("--name", default="", help="Device name to match (partial, case-insensitive)")
    parser.add_argument("--mac", default="", help="MAC address to match (AA:BB:CC:DD:EE:FF)")
    parser.add_argument("--service-uuid", default="", help="Service UUID to match")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=0,
        help="Max wait time in seconds (0 = infinite)",
    )
    parser.add_argument(
        "--scan-window-seconds",
        type=int,
        default=4,
        help="Duration of each BLE scan window",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=2,
        help="Interval between scans",
    )
    parser.add_argument(
        "--failure-policy",
        choices=["fail_closed", "warn_only"],
        default="fail_closed",
        help="Behavior on timeout",
    )
    args = parser.parse_args()

    if not args.name and not args.mac and not args.service_uuid:
        print("Error: At least one of --name, --mac, or --service-uuid required", file=sys.stderr)
        return 2

    try:
        fail_closed = args.failure_policy == "fail_closed"
        result = WAIT_FOR_NOTPRESENT(
            name=args.name,
            mac=args.mac,
            service_uuid=args.service_uuid,
            timeout_seconds=args.timeout_seconds,
            scan_window_seconds=args.scan_window_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
            fail_closed=fail_closed,
        )
        if result:
            print("Device no longer present")
            return 0
        else:
            print("Device still present (warn_only mode)", file=sys.stderr)
            return 1
    except TimeoutError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

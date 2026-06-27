#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import socket
import struct
import subprocess
import sys
import time
from typing import Any


def slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or "sensor"


def chip_slug(value: str) -> str:
    if value.startswith("coretemp-"):
        return "coretemp"
    if value.startswith("acpitz-"):
        return "acpitz"
    return slug(value)


def label_slug(value: str) -> str:
    if re.fullmatch(r"Package id \d+", value, re.IGNORECASE):
        return slug(value.replace(" id ", "_"))
    return slug(value)


def collect_sensors(sensors_bin: str) -> list[dict[str, str]]:
    raw = subprocess.check_output([sensors_bin, "-j"], text=True, stderr=subprocess.STDOUT)
    payload = json.loads(raw)
    metrics: list[dict[str, str]] = []
    for chip, chip_data in payload.items():
        if not isinstance(chip_data, dict):
            continue
        chip_id = chip_slug(chip)
        for label, values in chip_data.items():
            if label == "Adapter" or not isinstance(values, dict):
                continue
            input_values = [
                value
                for key, value in values.items()
                if key.endswith("_input") and isinstance(value, int | float)
            ]
            if not input_values:
                continue
            metrics.append(
                {
                    "key": f"sensor.temp.value[{chip_id}.{label_slug(label)}]",
                    "value": f"{float(input_values[0]):.3f}",
                }
            )
    return metrics


def send_to_zabbix(server: str, port: int, host: str, metrics: list[dict[str, str]]) -> dict[str, Any]:
    now = int(time.time())
    body = {
        "request": "sender data",
        "data": [
            {"host": host, "key": metric["key"], "value": metric["value"], "clock": now}
            for metric in metrics
        ],
    }
    encoded = json.dumps(body, separators=(",", ":")).encode()
    packet = b"ZBXD\x01" + struct.pack("<Q", len(encoded)) + encoded
    with socket.create_connection((server, port), timeout=10) as sock:
        sock.sendall(packet)
        header = sock.recv(13)
        if len(header) != 13 or not header.startswith(b"ZBXD\x01"):
            raise RuntimeError("invalid response header from Zabbix server")
        length = struct.unpack("<Q", header[5:13])[0]
        response = b""
        while len(response) < length:
            chunk = sock.recv(length - len(response))
            if not chunk:
                break
            response += chunk
    return json.loads(response.decode())


def failed_count(response: dict[str, Any]) -> int | None:
    info = str(response.get("info") or "")
    match = re.search(r"failed:\s*(\d+)", info)
    return int(match.group(1)) if match else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Send lm-sensors temperatures to Zabbix trapper items.")
    parser.add_argument("--host", required=True, help="Zabbix technical host name, for example 'sys s10'.")
    parser.add_argument("--server", default="127.0.0.1", help="Zabbix server address.")
    parser.add_argument("--port", type=int, default=10051, help="Zabbix trapper port.")
    parser.add_argument("--sensors-bin", default="/usr/bin/sensors", help="Path to sensors binary.")
    parser.add_argument("--dry-run", action="store_true", help="Print collected metrics and do not send.")
    parser.add_argument("--quiet", action="store_true", help="Suppress success output.")
    args = parser.parse_args()

    try:
        metrics = collect_sensors(args.sensors_bin)
        if args.dry_run:
            print(json.dumps(metrics, indent=2, ensure_ascii=False))
            return 0
        if not metrics:
            raise RuntimeError("no sensor temperature metrics found")
        response = send_to_zabbix(args.server, args.port, args.host, metrics)
        failed = failed_count(response)
        if response.get("response") != "success" or failed not in (None, 0):
            raise RuntimeError(json.dumps(response, ensure_ascii=False))
        if not args.quiet:
            print(response.get("info") or response)
        return 0
    except Exception as exc:
        print(f"ctm-send-sensors-to-zabbix: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


PROMETHEUS_URL = os.environ.get("TAILNET_WATCH_PROMETHEUS_URL", "http://127.0.0.1:9090").rstrip("/")
RELAY_URL = os.environ.get("TAILNET_WATCH_RELAY_URL", "http://127.0.0.1:8066/alertmanager")
STATE_FILE = os.environ.get("TAILNET_WATCH_STATE_FILE", "/var/lib/ctm-monitoring/tailnet-watch.json")
BASELINE_NOTIFY = os.environ.get("TAILNET_WATCH_BASELINE_NOTIFY", "false").lower() in {"1", "true", "yes", "on"}
TIMEOUT_SEC = float(os.environ.get("TAILNET_WATCH_TIMEOUT_SEC", "8"))
QUERY = os.environ.get("TAILNET_WATCH_NODE_QUERY", "headscale_nodes_info")
PREAUTH_INFO_QUERY = os.environ.get("TAILNET_WATCH_PREAUTH_INFO_QUERY", "headscale_preauthkeys_info")
PREAUTH_CREATED_QUERY = os.environ.get("TAILNET_WATCH_PREAUTH_CREATED_QUERY", "headscale_preauthkeys_created_timestamp")
PREAUTH_EXPIRATION_QUERY = os.environ.get("TAILNET_WATCH_PREAUTH_EXPIRATION_QUERY", "headscale_preauthkeys_expiration_timestamp")

SENSITIVE_LABELS = {
    "__name__",
    "machine_key",
    "node_key",
    "disco_key",
}

SAFE_LABELS = (
    "id",
    "name",
    "given_name",
    "user",
    "user_id",
    "tailscale_ip",
    "tailscale_ipv6",
    "register_method",
    "instance",
    "job",
    "service",
    "role",
)

SAFE_PREAUTH_LABELS = (
    "id",
    "user",
    "user_id",
    "reusable",
    "ephemeral",
    "used",
    "acl_tags",
    "instance",
    "job",
    "service",
    "role",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def format_unix_timestamp(value: Any) -> str:
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return ""
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp, timezone.utc).astimezone().strftime("%Y.%m.%d %H:%M:%S")


def device_key(labels: dict[str, Any]) -> str:
    node_id = str(labels.get("id") or "").strip()
    if node_id:
        return f"id:{node_id}"
    stable = "|".join(str(labels.get(name) or "") for name in ("user", "name", "given_name", "tailscale_ip"))
    if not stable.strip("|"):
        stable = json.dumps({k: v for k, v in labels.items() if k not in SENSITIVE_LABELS}, sort_keys=True)
    return f"hash:{short_hash(stable)}"


def safe_device(labels: dict[str, Any]) -> dict[str, str]:
    device = {name: str(labels.get(name) or "") for name in SAFE_LABELS if labels.get(name)}
    device["key"] = device_key(labels)
    return device


def preauth_key(labels: dict[str, Any]) -> str:
    key_id = str(labels.get("id") or "").strip()
    user = str(labels.get("user") or "").strip()
    if key_id or user:
        return f"user:{user}|id:{key_id}"
    stable = json.dumps({k: v for k, v in labels.items() if k not in SENSITIVE_LABELS}, sort_keys=True)
    return f"hash:{short_hash(stable)}"


def safe_preauth_key(labels: dict[str, Any]) -> dict[str, str]:
    item = {name: str(labels.get(name) or "") for name in SAFE_PREAUTH_LABELS if labels.get(name)}
    item["key"] = preauth_key(labels)
    return item


def prometheus_query(query: str) -> list[dict[str, Any]]:
    url = PROMETHEUS_URL + "/api/v1/query?" + urllib.parse.urlencode({"query": query})
    with urllib.request.urlopen(url, timeout=TIMEOUT_SEC) as response:
        body = json.loads(response.read().decode("utf-8"))
    if body.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {body}")
    result = body.get("data", {}).get("result", [])
    if not isinstance(result, list):
        raise RuntimeError("Prometheus returned an unexpected result shape")
    return result


def collect_devices() -> dict[str, dict[str, str]]:
    devices: dict[str, dict[str, str]] = {}
    for item in prometheus_query(QUERY):
        metric = item.get("metric") or {}
        if not isinstance(metric, dict):
            continue
        device = safe_device(metric)
        devices[device["key"]] = device
    return devices


def collect_metric_values(query: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in prometheus_query(query):
        metric = item.get("metric") or {}
        value = item.get("value") or []
        if not isinstance(metric, dict) or len(value) < 2:
            continue
        values[preauth_key(metric)] = str(value[1])
    return values


def collect_preauth_keys() -> dict[str, dict[str, str]]:
    created = collect_metric_values(PREAUTH_CREATED_QUERY)
    expires = collect_metric_values(PREAUTH_EXPIRATION_QUERY)
    keys: dict[str, dict[str, str]] = {}
    for item in prometheus_query(PREAUTH_INFO_QUERY):
        metric = item.get("metric") or {}
        if not isinstance(metric, dict):
            continue
        key = safe_preauth_key(metric)
        stable_key = key["key"]
        if stable_key in created:
            key["created_at"] = format_unix_timestamp(created[stable_key])
        if stable_key in expires:
            key["expires_at"] = format_unix_timestamp(expires[stable_key])
        keys[stable_key] = key
    return keys


def load_state(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {"version": 1, "devices": {}, "preauth_keys": {}, "initialized": False}
    with open(path, "r", encoding="utf-8") as handle:
        state = json.load(handle)
    if not isinstance(state, dict):
        raise RuntimeError(f"invalid state file: {path}")
    state.setdefault("version", 1)
    state.setdefault("devices", {})
    state.setdefault("preauth_keys", {})
    state.setdefault("initialized", False)
    return state


def save_state(path: str, state: dict[str, Any]) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, mode=0o750, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tailnet-watch-", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def device_name(device: dict[str, str]) -> str:
    return device.get("name") or device.get("given_name") or device.get("id") or "unknown"


def alert_for_device(device: dict[str, str], starts_at: str, *, test: bool = False) -> dict[str, Any]:
    name = device_name(device)
    labels = {
        "alertname": "TailnetNewDeviceDetected",
        "severity": "info",
        "area": "tailscale",
        "category": "inventory",
        "device": name,
        "name": name,
        "user": device.get("user", ""),
        "tailscale_ip": device.get("tailscale_ip", ""),
        "tailscale_ipv6": device.get("tailscale_ipv6", ""),
        "register_method": device.get("register_method", ""),
        "id": device.get("id", ""),
        "given_name": device.get("given_name", ""),
        "source": "headscale_nodes_info",
    }
    labels = {key: value for key, value in labels.items() if value}
    suffix = "test" if test else short_hash(device.get("key", name))
    return {
        "status": "firing",
        "startsAt": starts_at,
        "fingerprint": f"ctm-tailnet-new-device-{suffix}",
        "labels": labels,
        "annotations": {
            "summary": f"Tailnet new device detected: {name}",
            "description": "A new Tailscale/Headscale device appeared in the tailnet device inventory.",
        },
    }


def alert_for_preauth_key(item: dict[str, str], starts_at: str, *, test: bool = False) -> dict[str, Any]:
    key_id = item.get("id") or "unknown"
    user = item.get("user") or "-"
    name = f"Headscale Key #{key_id}"
    labels = {
        "alertname": "HeadscalePreauthKeyCreated",
        "severity": "info",
        "area": "tailscale",
        "category": "auth",
        "device": name,
        "name": name,
        "user": user,
        "id": key_id,
        "reusable": item.get("reusable", ""),
        "ephemeral": item.get("ephemeral", ""),
        "used": item.get("used", ""),
        "acl_tags": item.get("acl_tags", ""),
        "created_at": item.get("created_at", ""),
        "expires_at": item.get("expires_at", ""),
        "source": "headscale_preauthkeys_info",
    }
    labels = {key: value for key, value in labels.items() if value}
    suffix = "test-key" if test else short_hash(item.get("key", name))
    return {
        "status": "firing",
        "startsAt": starts_at,
        "fingerprint": f"ctm-headscale-preauth-key-created-{suffix}",
        "labels": labels,
        "annotations": {
            "summary": f"Headscale preauth key created: #{key_id}",
            "description": f"A new Headscale preauth key for user {user} appeared in the Headscale metrics inventory.",
        },
    }


def alertmanager_payload(
    devices: list[dict[str, str]] | None = None,
    preauth_keys: list[dict[str, str]] | None = None,
    *,
    test: bool = False,
) -> dict[str, Any]:
    starts_at = now_iso()
    devices = devices or []
    preauth_keys = preauth_keys or []
    alerts = [
        *[alert_for_device(device, starts_at, test=test) for device in devices],
        *[alert_for_preauth_key(item, starts_at, test=test) for item in preauth_keys],
    ]
    return {
        "receiver": "dingtalk",
        "status": "firing",
        "commonLabels": {
            "severity": "info",
            "area": "tailscale",
            "category": "inventory" if devices and not preauth_keys else "auth" if preauth_keys and not devices else "change",
        },
        "alerts": alerts,
    }


def post_relay(payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        RELAY_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"relay returned HTTP {exc.code}: {body}") from exc
    if not 200 <= status < 300:
        raise RuntimeError(f"relay returned HTTP {status}: {body}")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return
    if parsed.get("ok") is False:
        raise RuntimeError(f"relay rejected payload: {body}")


def test_device() -> dict[str, str]:
    return {
        "key": "test:tailnet-watch",
        "id": "TEST",
        "name": "tailnet-watch-test",
        "given_name": "tailnet-watch-test",
        "user": "ctm",
        "tailscale_ip": "100.64.0.250",
        "register_method": "TEST",
    }


def test_preauth_key() -> dict[str, str]:
    return {
        "key": "test:headscale-preauth-key",
        "id": "TEST",
        "user": "ctm",
        "reusable": "false",
        "ephemeral": "false",
        "used": "false",
        "acl_tags": "tag:monitor",
        "created_at": datetime.now().astimezone().strftime("%Y.%m.%d %H:%M:%S"),
        "expires_at": datetime.fromtimestamp(time.time() + 86400, timezone.utc).astimezone().strftime("%Y.%m.%d %H:%M:%S"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Notify when new Headscale/Tailscale devices appear.")
    parser.add_argument("--dry-run", action="store_true", help="Print the payload/state decision without posting or writing state.")
    parser.add_argument("--test", action="store_true", help="Send a synthetic test notification through the relay.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.test:
        payload = alertmanager_payload([test_device()], [test_preauth_key()], test=True)
        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        post_relay(payload)
        print("sent tailnet watch test notification")
        return

    devices = collect_devices()
    preauth_keys = collect_preauth_keys()
    state = load_state(STATE_FILE)
    previous = state.get("devices") or {}
    previous_keys = state.get("preauth_keys") or {}
    if not devices and previous:
        raise RuntimeError("Prometheus returned zero tailnet devices; keeping the previous state")
    if not preauth_keys and previous_keys:
        raise RuntimeError("Prometheus returned zero Headscale preauth keys; keeping the previous state")

    initialized = bool(state.get("initialized"))
    new_devices = [device for key, device in sorted(devices.items()) if key not in previous]
    new_keys = [item for key, item in sorted(preauth_keys.items()) if key not in previous_keys]

    if not initialized:
        state.update(
            {
                "initialized": True,
                "initialized_at": now_iso(),
                "last_checked_at": now_iso(),
                "devices": devices,
                "preauth_keys": preauth_keys,
            }
        )
        if BASELINE_NOTIFY and (devices or preauth_keys):
            payload = alertmanager_payload(list(devices.values()), list(preauth_keys.values()))
            if args.dry_run:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                post_relay(payload)
        if not args.dry_run:
            save_state(STATE_FILE, state)
        print(f"initialized tailnet baseline with {len(devices)} devices and {len(preauth_keys)} preauth keys")
        return

    if new_devices or new_keys:
        payload = alertmanager_payload(new_devices, new_keys)
        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            post_relay(payload)

    state.update({"last_checked_at": now_iso(), "devices": devices, "preauth_keys": preauth_keys})
    if not args.dry_run:
        save_state(STATE_FILE, state)
    print(
        f"checked {len(devices)} tailnet devices and {len(preauth_keys)} preauth keys; "
        f"new_devices={len(new_devices)} new_keys={len(new_keys)}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ctm-tailnet-watch: {exc}", file=sys.stderr)
        raise SystemExit(1)

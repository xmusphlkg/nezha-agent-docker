#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback.
    ZoneInfo = None


LISTEN_HOST = os.environ.get("DINGTALK_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("DINGTALK_LISTEN_PORT", "8066"))
WEBHOOK = os.environ.get("DINGTALK_WEBHOOK", "")
SECRET = os.environ.get("DINGTALK_SECRET", "")
KEYWORD = os.environ.get("DINGTALK_KEYWORD", "CTM")
MAX_ALERTS = int(os.environ.get("DINGTALK_MAX_ALERTS", "5"))
DISPLAY_TIMEZONE = os.environ.get("DINGTALK_TIMEZONE", "Asia/Shanghai")
AT_MOBILES = [
    item.strip()
    for item in os.environ.get("DINGTALK_AT_MOBILES", "").split(",")
    if item.strip()
]
AT_ALL = os.environ.get("DINGTALK_AT_ALL", "false").lower() in {"1", "true", "yes", "on"}
TIMEOUT_SEC = float(os.environ.get("DINGTALK_TIMEOUT_SEC", "8"))


def signed_webhook() -> str:
    if not SECRET:
        return WEBHOOK
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{SECRET}".encode("utf-8")
    digest = hmac.new(SECRET.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(digest))
    separator = "&" if "?" in WEBHOOK else "?"
    return f"{WEBHOOK}{separator}timestamp={timestamp}&sign={sign}"


def post_dingtalk(payload: dict[str, Any]) -> tuple[int, str]:
    if not WEBHOOK:
        raise RuntimeError("DINGTALK_WEBHOOK is not configured")
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        signed_webhook(),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body


def dingtalk_ok(status: int, body: str) -> bool:
    if not 200 <= status < 300:
        return False
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return True
    return parsed.get("errcode", 0) == 0


def field(labels: dict[str, Any], *names: str) -> str:
    for name in names:
        value = labels.get(name)
        if value:
            return str(value)
    return "-"


def line_value(value: Any, limit: int = 240) -> str:
    text = "-" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def title_for(alert: dict[str, Any]) -> str:
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    return line_value(
        annotations.get("summary")
        or labels.get("alertname")
        or annotations.get("description")
        or "Prometheus alert",
        120,
    )


def status_word(status: str) -> str:
    normalized = status.upper()
    if normalized == "FIRING":
        return "PROBLEM"
    if normalized == "RESOLVED":
        return "RESOLVED"
    return normalized


def action_word(status: str) -> str:
    return "恢复" if status.upper() == "RESOLVED" else "发生"


def reason_for(alert: dict[str, Any]) -> str:
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    alertname = str(labels.get("alertname") or "")
    event = str(labels.get("event") or "")
    mapping = {
        "WazuhSSHRootLogin": "SSH root 登录",
        "WazuhSSHActiveRootSession": "SSH root 会话仍在线",
        "WazuhSSHInvalidUserAttempts": "SSH 无效用户尝试",
        "WazuhSSHFailureBurst": "SSH 登录失败爆发",
        "WazuhKeyFileModified": "关键文件修改",
        "WazuhKeyFileDeleted": "关键文件删除",
        "WazuhKeyFileAdded": "关键文件新增",
        "WazuhFIMQueueFull": "关键文件监控队列异常",
        "WazuhCriticalAlertsDetected": "Wazuh 严重安全告警",
        "WazuhHighAlertsDetected": "Wazuh 高危安全告警",
        "WazuhAPIUnavailable": "Wazuh API 不可用",
        "WazuhIndexerUnavailable": "Wazuh Indexer 不可用",
        "WazuhCriticalProcessDown": "Wazuh 关键进程异常",
        "TailnetNewDeviceDetected": "Tailnet 新设备加入",
        "HeadscalePreauthKeyCreated": "Headscale 新增预授权 Key",
        "HeadscaleRoutesAwaitingApproval": "Tailnet 路由待批准",
        "HeadscaleExporterDown": "Headscale 指标不可用",
        "HeadscaleDatabaseUnhealthy": "Headscale 数据库异常",
    }
    if alertname in mapping:
        return mapping[alertname]
    if event in {"modified", "deleted", "added"}:
        return f"关键文件{ {'modified': '修改', 'deleted': '删除', 'added': '新增'}[event] }"
    return line_value(annotations.get("summary") or alertname or "安全告警", 80)


def device_for(alert: dict[str, Any]) -> str:
    labels = alert.get("labels") or {}
    return field(labels, "agent_name", "device", "name", "node", "host", "instance", "job")


def address_for(alert: dict[str, Any]) -> str:
    labels = alert.get("labels") or {}
    address = field(labels, "agent_ip", "tailscale_ip", "host_ip", "ip", "address")
    if address != "-":
        return address
    if labels.get("agent_name"):
        return "-"
    instance = str(labels.get("instance") or "")
    if instance:
        return instance.rsplit(":", 1)[0]
    return "-"


def monitor_item_for(alert: dict[str, Any]) -> str:
    labels = alert.get("labels") or {}
    alertname = str(labels.get("alertname") or "")
    mapping = {
        "WazuhSSHRootLogin": "wazuh.ssh.root_login",
        "WazuhSSHActiveRootSession": "wazuh.ssh.root_session",
        "WazuhSSHInvalidUserAttempts": "wazuh.ssh.invalid_user",
        "WazuhSSHFailureBurst": "wazuh.ssh.failure_burst",
        "WazuhKeyFileModified": "wazuh.fim.file.modified",
        "WazuhKeyFileDeleted": "wazuh.fim.file.deleted",
        "WazuhKeyFileAdded": "wazuh.fim.file.added",
        "WazuhFIMQueueFull": "wazuh.fim.queue",
        "WazuhCriticalAlertsDetected": "wazuh.alerts.critical",
        "WazuhHighAlertsDetected": "wazuh.alerts.high",
        "WazuhAPIUnavailable": "wazuh.api.up",
        "WazuhIndexerUnavailable": "wazuh.indexer.up",
        "WazuhCriticalProcessDown": "wazuh.process.up",
        "TailnetNewDeviceDetected": "tailscale.device.new",
        "HeadscalePreauthKeyCreated": "headscale.authkey.created",
        "HeadscaleRoutesAwaitingApproval": "headscale.routes.pending",
        "HeadscaleExporterDown": "headscale.exporter.up",
        "HeadscaleDatabaseUnhealthy": "headscale.database.up",
    }
    return mapping.get(alertname, alertname or "-")


def event_label(value: str) -> str:
    return {
        "modified": "修改",
        "deleted": "删除",
        "added": "新增",
        "root_login": "root 登录",
        "invalid_user": "无效用户",
        "failed": "登录失败",
        "success": "登录成功",
    }.get(value, value)


def key_info_items(alert: dict[str, Any]) -> list[tuple[str, str]]:
    labels = alert.get("labels") or {}
    alertname = str(labels.get("alertname") or "")
    category = str(labels.get("category") or "")
    items: list[tuple[str, str]] = []
    if category == "ssh" or alertname.startswith("WazuhSSH"):
        items = [
            ("用户", field(labels, "user")),
            ("来源", field(labels, "srcip")),
            ("事件", event_label(field(labels, "outcome"))),
            ("规则", field(labels, "rule_id")),
            ("Level", field(labels, "level")),
        ]
    elif category == "fim" or alertname.startswith("WazuhKeyFile") or alertname == "WazuhFIMQueueFull":
        items = [
            ("文件", field(labels, "path")),
            ("动作", event_label(field(labels, "event"))),
            ("用户", field(labels, "user")),
            ("规则", field(labels, "rule_id")),
            ("Level", field(labels, "level")),
        ]
    elif alertname == "HeadscalePreauthKeyCreated":
        items = [
            ("Key ID", field(labels, "id")),
            ("用户", field(labels, "user")),
            ("可复用", field(labels, "reusable")),
            ("临时 Key", field(labels, "ephemeral")),
            ("已使用", field(labels, "used")),
            ("ACL Tags", field(labels, "acl_tags")),
            ("创建时间", field(labels, "created_at")),
            ("过期时间", field(labels, "expires_at")),
            ("来源", field(labels, "source", "job")),
        ]
    elif category in {"inventory", "routing", "auth"} or str(labels.get("area") or "") in {"tailscale", "headscale"}:
        items = [
            ("设备", field(labels, "device", "name")),
            ("用户", field(labels, "user")),
            ("Tailnet IP", field(labels, "tailscale_ip")),
            ("IPv6", field(labels, "tailscale_ipv6")),
            ("注册方式", field(labels, "register_method")),
            ("ID", field(labels, "id")),
            ("来源", field(labels, "source", "job")),
        ]
    else:
        items = [
            ("类别", field(labels, "category", "area")),
            ("实例", field(labels, "instance")),
            ("规则", field(labels, "rule_id")),
            ("Level", field(labels, "level")),
        ]
    return [(name, line_value(value, 180)) for name, value in items if value != "-"]


def compact_key_info(alert: dict[str, Any]) -> str:
    parts = [f"{name}:{value}" for name, value in key_info_items(alert)]
    return "；".join(parts) if parts else "-"


def current_state_for(alert: dict[str, Any]) -> str:
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    status = status_word(str(alert.get("status") or "unknown"))
    value = (
        labels.get("value")
        or annotations.get("value")
        or annotations.get("current")
        or annotations.get("summary")
        or reason_for(alert)
    )
    return f"{status}: {line_value(value, 160)}"


def event_id_for(alert: dict[str, Any]) -> str:
    labels = alert.get("labels") or {}
    return line_value(
        alert.get("fingerprint")
        or labels.get("event_id")
        or labels.get("id")
        or labels.get("rule_id")
        or "-",
        80,
    )


def display_time(value: Any) -> str:
    if not value or str(value).startswith("0001-01-01"):
        return "-"
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return line_value(text, 80)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if ZoneInfo is not None:
        try:
            target_tz = ZoneInfo(DISPLAY_TIMEZONE)
        except Exception:
            target_tz = timezone(timedelta(hours=8))
    else:
        target_tz = timezone(timedelta(hours=8))
    return parsed.astimezone(target_tz).strftime("%Y.%m.%d %H:%M:%S")


def alert_headline(alert: dict[str, Any]) -> str:
    status = status_word(str(alert.get("status") or "unknown"))
    device = device_for(alert)
    reason = reason_for(alert)
    action = action_word(str(alert.get("status") or "unknown"))
    suffix = "恢复" if status == "RESOLVED" else "告警"
    return f"{KEYWORD}安全告警{status},服务器:{device}{action}: {reason} {suffix}！"


def alert_lines(alert: dict[str, Any], index: int | None = None) -> list[str]:
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    status = str(alert.get("status") or "unknown").upper()
    prefix = f"{index}. " if index is not None else ""
    key_items = key_info_items(alert)
    lines = []
    if index is not None:
        lines.extend([f"#### {prefix}{alert_headline(alert)}", ""])
    lines.extend(
        [
            "---",
            "",
            "**基本信息**",
            "",
            f"告警主机: {device_for(alert)}",
            "",
            f"主机地址: {address_for(alert)}",
            "",
            f"告警等级: {field(labels, 'severity')}",
            "",
            f"监控项目: {monitor_item_for(alert)}",
            "",
            "---",
            "",
            "**问题详情**",
            "",
        ]
    )
    if key_items:
        for name, value in key_items:
            lines.extend([f"- {name}: {value}", ""])
    else:
        lines.extend(["-", ""])
    lines.extend(
        [
            "---",
            "",
            "**事件信息**",
            "",
            f"当前状态: {current_state_for(alert)}",
            "",
            f"告警信息: {line_value(annotations.get('description') or annotations.get('summary') or reason_for(alert))}",
            "",
            f"告警时间: {display_time(alert.get('startsAt'))}",
            "",
            f"事件ID: {event_id_for(alert)}",
        ]
    )
    ends_at = alert.get("endsAt")
    if status == "RESOLVED" and ends_at and not str(ends_at).startswith("0001-01-01"):
        lines.extend(["", f"恢复时间: {display_time(ends_at)}"])
    return lines


def markdown_from_alertmanager(body: dict[str, Any]) -> tuple[str, str]:
    status = str(body.get("status") or "unknown").upper()
    alerts = body.get("alerts") or []
    count = len(alerts)
    if count == 1:
        title = alert_headline(alerts[0])
    else:
        title = f"{KEYWORD}安全告警{status_word(status)},共{count}条"
    lines = [f"### {title}", ""]
    for index, alert in enumerate(alerts[:MAX_ALERTS], 1):
        if index > 1:
            lines.extend(["---", ""])
        lines.extend(alert_lines(alert, index if count > 1 else None))
        lines.append("")
    if count > MAX_ALERTS:
        lines.append(f"_仅显示前 {MAX_ALERTS} 条，共 {count} 条。_")
    return title, "\n".join(lines).strip()


def dingtalk_payload(body: dict[str, Any]) -> dict[str, Any]:
    title, text = markdown_from_alertmanager(body)
    return {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text},
        "at": {"atMobiles": AT_MOBILES, "isAtAll": AT_ALL},
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ctm-dingtalk-relay/1.0"

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self.send_json(200, {"ok": True})
            return
        self.send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path not in {"/", "/alertmanager"}:
            self.send_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
            status, response_body = post_dingtalk(dingtalk_payload(body))
        except Exception as exc:
            self.log_message("relay error: %s", exc)
            self.send_json(500, {"ok": False, "error": str(exc)})
            return
        ok = dingtalk_ok(status, response_body)
        self.send_json(200 if ok else 502, {"ok": ok, "dingtalk_status": status, "body": response_body})

    def send_json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))


def main() -> None:
    if not WEBHOOK:
        print("DINGTALK_WEBHOOK is required", file=sys.stderr)
        raise SystemExit(2)
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    print(f"ctm-dingtalk-relay listening on {LISTEN_HOST}:{LISTEN_PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

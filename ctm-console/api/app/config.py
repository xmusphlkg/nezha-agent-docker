import json
from functools import lru_cache
from typing import Literal

import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "CTM Console"
    environment: Literal["dev", "prod", "test"] = "prod"
    public_base_url: str = "http://192.168.3.222:3000"

    mysql_host: str = "192.168.3.222"
    mysql_port: int = 3306
    mysql_user: str = "ctm_console"
    mysql_password: str | None = None
    mysql_database: str = "ctm_console"
    mysql_table: str = "ctm_console_cache"
    mysql_connect_timeout_sec: int = 10

    zabbix_url: str = "http://host.docker.internal:8080/api_jsonrpc.php"
    zabbix_token: str | None = None
    zabbix_user: str | None = None
    zabbix_password: str | None = None
    zabbix_timeout_sec: float = 10.0
    zabbix_concurrency: int = 4

    prometheus_url: str = "http://host.docker.internal:9090"
    prometheus_timeout_sec: float = 10.0
    prometheus_concurrency: int = 4

    grafana_base_url: str = "http://192.168.30.91:30037"
    grafana_org_id: int | None = 1
    grafana_default_from: str | None = "now-6h"
    grafana_default_to: str | None = "now"
    grafana_timezone: str | None = "browser"
    grafana_refresh: str | None = "30s"

    ctm_wazuh_enabled: bool = False
    ctm_wazuh_modules: str = "agents,alerts,ssh,fim"
    ctm_wazuh_window: str = "24h"
    ctm_wazuh_top_limit: int = 8
    ctm_wazuh_recent_limit: int = 12

    ctm_admin_username: str = "admin"
    ctm_admin_password: str | None = None
    ctm_session_secret: str | None = None
    ctm_session_ttl_hours: int = 12

    nav_scan_cidrs: str = "192.168.3.0/24"
    nav_scan_ports: str = (
        "80,443,3000,3001,5000,5001,5173,5601,8000,8006,8080,8081,"
        "8088,8090,8443,8888,9000,9001,9090,9091,9093,9200,9443"
    )
    nav_scan_timeout_sec: float = 1.2
    nav_scan_connect_timeout_sec: float = 0.45
    nav_scan_concurrency: int = 256

    pve_servers_json: str | None = None
    pve_host: str | None = None
    pve_port: int = 8006
    pve_name: str = "PVE"
    pve_token_id: str | None = None
    pve_token_secret: str | None = None
    pve_verify_ssl: bool = False
    pve_timeout_sec: float = 10.0
    pve_concurrency: int = 4

    snapshot_interval_sec: int = 30
    alerts_interval_sec: int = 60
    series_cache_ttl_sec: int = 300

    @field_validator("zabbix_url", "prometheus_url", "grafana_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("grafana_default_from", "grafana_default_to", "grafana_timezone", "grafana_refresh")
    @classmethod
    def strip_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("mysql_table", "mysql_database")
    @classmethod
    def validate_mysql_identifier(cls, value: str) -> str:
        if not re.match(r"^[A-Za-z0-9_]+$", value):
            raise ValueError("MySQL identifiers may only contain letters, numbers, and underscores")
        return value

    def pve_servers(self) -> list[dict[str, object]]:
        if self.pve_servers_json:
            raw = json.loads(self.pve_servers_json)
            if not isinstance(raw, list):
                raise ValueError("PVE_SERVERS_JSON must be a JSON array")
            return [server for server in raw if isinstance(server, dict)]
        if self.pve_host and self.pve_token_id and self.pve_token_secret:
            return [
                {
                    "name": self.pve_name,
                    "host": self.pve_host,
                    "port": self.pve_port,
                    "token_id": self.pve_token_id,
                    "token_secret": self.pve_token_secret,
                    "verify_ssl": self.pve_verify_ssl,
                }
            ]
        return []

    def wazuh_modules(self) -> set[str]:
        allowed = {"agents", "alerts", "ssh", "fim"}
        modules = {
            item.strip().lower()
            for item in self.ctm_wazuh_modules.split(",")
            if item.strip()
        }
        if not modules or "all" in modules:
            return allowed
        return modules & allowed

    def nav_scan_cidr_list(self) -> list[str]:
        return [cidr.strip() for cidr in self.nav_scan_cidrs.split(",") if cidr.strip()]

    def nav_scan_port_list(self) -> list[int]:
        ports: list[int] = []
        for item in self.nav_scan_ports.split(","):
            item = item.strip()
            if not item:
                continue
            port = int(item)
            if 1 <= port <= 65535:
                ports.append(port)
        return sorted(set(ports))


@lru_cache
def get_settings() -> Settings:
    return Settings()

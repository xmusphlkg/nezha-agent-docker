from __future__ import annotations

from urllib.parse import urlencode

from ..config import Settings
from ..models import GrafanaDashboardLink, GrafanaIntegration


DASHBOARDS = [
    ("main", "Grafana 总览", "全局运行态势与跨系统入口", "ctm-ops-overview", "ctm-main"),
    ("hosts", "设备健康", "Zabbix 主机、硬件、当前问题", "ctm-zabbix-operations", None),
    ("resources", "资源容量", "CPU、内存、磁盘、网络趋势", "ctm-zabbix-resources", None),
    ("server-trends", "单机趋势", "按机器 drilldown 到 1h/6h/24h 趋势", "ctm-server-trends", "ctm-e69cba-e599a8-e8afa6-e68385"),
    ("tailnet", "远程网络", "Headscale/Tailnet 节点、路由、密钥", "ctm-tailnet-headscale", None),
    ("services", "服务可达", "Blackbox 与 Prometheus targets", "ctm-service-blackbox", None),
    ("lan", "局域网资产", "WatchYourLAN 在线设备与未知资产", "ctm-lan-assets", None),
    ("alerts", "告警安全", "Zabbix、Prometheus 与安全事件汇总", "ctm-alerts-security", None),
    ("wazuh", "Wazuh 安全", "Agent、规则、SSH、FIM 综合分析", "ctm-wazuh-security", None),
    ("wazuh-ssh", "SSH 登录", "SSH 来源、用户、规则与最近事件", "ctm-wazuh-ssh", None),
    ("wazuh-fim", "关键文件", "关键路径变更、规则与主机聚合", "ctm-wazuh-fim", None),
    ("unified", "全量排障", "跨 Zabbix、Prometheus、Wazuh 的排障视图", "ctm-unified-infra", None),
]


def build_grafana_integration(settings: Settings) -> GrafanaIntegration:
    return GrafanaIntegration(
        baseUrl=settings.grafana_base_url,
        dashboards=[
            GrafanaDashboardLink(
                id=dashboard_id,
                title=title,
                description=description,
                url=grafana_dashboard_url(settings.grafana_base_url, uid, default_grafana_params(settings), slug),
            )
            for dashboard_id, title, description, uid, slug in DASHBOARDS
        ],
    )


def default_grafana_params(settings: Settings) -> dict[str, str]:
    params: dict[str, str] = {}
    if settings.grafana_org_id is not None:
        params["orgId"] = str(settings.grafana_org_id)
    if settings.grafana_default_from:
        params["from"] = settings.grafana_default_from
    if settings.grafana_default_to:
        params["to"] = settings.grafana_default_to
    if settings.grafana_timezone:
        params["timezone"] = settings.grafana_timezone
    if settings.grafana_refresh:
        params["refresh"] = settings.grafana_refresh
    return params


def grafana_dashboard_url(
    base_url: str,
    uid: str,
    params: dict[str, str] | None = None,
    slug: str | None = None,
) -> str:
    path = f"{base_url.rstrip('/')}/d/{uid}"
    if slug:
        path = f"{path}/{slug}"
    if not params:
        return path
    return f"{path}?{urlencode(params)}"

from urllib.parse import parse_qs, urlparse

from app.config import Settings
from app.services.grafana_links import build_grafana_integration


def test_grafana_links_use_configured_runtime_and_drilldown_defaults():
    settings = Settings(
        grafana_base_url="http://192.168.30.91:30037/",
        grafana_org_id=1,
        grafana_default_from="now-6h",
        grafana_default_to="now",
        grafana_timezone="browser",
        grafana_refresh="30s",
    )

    integration = build_grafana_integration(settings)
    server_trends = next(dashboard for dashboard in integration.dashboards if dashboard.id == "server-trends")
    parsed = urlparse(server_trends.url)

    assert integration.baseUrl == "http://192.168.30.91:30037"
    assert parsed.scheme == "http"
    assert parsed.netloc == "192.168.30.91:30037"
    assert parsed.path == "/d/ctm-server-trends/ctm-e69cba-e599a8-e8afa6-e68385"
    assert parse_qs(parsed.query) == {
        "orgId": ["1"],
        "from": ["now-6h"],
        "to": ["now"],
        "timezone": ["browser"],
        "refresh": ["30s"],
    }

from app.services.prometheus_mapper import build_lan_summary, build_services, build_tailnet


def sample(metric, value):
    return {"metric": metric, "value": [123, str(value)]}


def test_tailnet_summary_counts_nodes_routes_and_keys():
    tailnet = build_tailnet(
        online=[
            sample({"id": "1", "name": "s3", "user": "lab"}, 1),
            sample({"id": "2", "name": "phone", "user": "lab"}, 0),
        ],
        info=[],
        last_seen=[sample({"id": "1"}, 100), sample({"id": "2"}, 100)],
        routes_available=[sample({"id": "1"}, 2)],
        routes_approved=[sample({"id": "1"}, 1)],
        api_up=[sample({}, 1)],
        db_ok=[sample({}, 1)],
        keys=[sample({"user": "lab", "reusable": "true"}, 3600)],
    )

    assert tailnet.totalNodes == 2
    assert tailnet.onlineNodes == 1
    assert tailnet.offlineNodes == 1
    assert tailnet.routeDelta == 1
    assert tailnet.expiringKeys == 1
    assert tailnet.health == "warning"


def test_services_summary_parses_probe_failures_and_targets():
    services = build_services(
        probes=[
            sample({"job": "blackbox-core-http", "instance": "http://a", "target": "http://a"}, 1),
            sample({"job": "blackbox-zabbix-file-sd", "instance": "10.0.0.2", "zbx_name": "s3"}, 0),
        ],
        durations=[sample({"job": "blackbox-core-http", "instance": "http://a"}, 0.12)],
        targets=[
            {"scrapeUrl": "http://a/metrics", "health": "up", "labels": {"job": "a"}},
            {"scrapeUrl": "http://b/metrics", "health": "down", "labels": {"job": "b"}, "lastError": "timeout"},
        ],
    )

    assert services.probeTotal == 2
    assert services.probeFailed == 1
    assert services.targetDown == 1
    assert services.health == "warning"


def test_lan_summary_filters_blank_assets_and_counts_unknown_online():
    lan = build_lan_summary(
        [
            sample(
                {
                    "ip": "192.168.3.10",
                    "mac": "AA:BB:CC:DD:EE:01",
                    "name": "printer",
                    "iface": "ens18",
                    "known": "1",
                },
                1,
            ),
            sample(
                {
                    "ip": "192.168.3.20",
                    "mac": "AA:BB:CC:DD:EE:02",
                    "name": "unknown",
                    "iface": "ens18",
                    "known": "0",
                },
                1,
            ),
            sample({"ip": "", "mac": "", "name": "stale", "known": "0"}, 0),
        ]
    )

    assert lan.totalDevices == 2
    assert lan.onlineDevices == 2
    assert lan.knownDevices == 1
    assert lan.unknownOnline == 1
    assert lan.interfaces == ["ens18"]
    assert lan.devices[0].ip == "192.168.3.20"
    assert lan.health == "warning"

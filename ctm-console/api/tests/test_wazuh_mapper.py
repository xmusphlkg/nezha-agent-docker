from app.services.prometheus_mapper import build_wazuh_summary


def sample(metric, value):
    return {"metric": metric, "value": [123, str(value)]}


def test_wazuh_summary_builds_selected_security_views():
    summary = build_wazuh_summary(
        enabled=True,
        modules={"agents", "alerts", "ssh", "fim"},
        window="24h",
        metrics={
            "api_up": [sample({}, 1)],
            "indexer_up": [sample({}, 1)],
            "agents_status": [
                sample({"status": "active"}, 2),
                sample({"status": "disconnected"}, 1),
            ],
            "manager_critical_down": [sample({}, 0)],
            "agent_status": [
                sample({"agent_id": "001", "name": "s1", "status": "active", "ip": "10.0.0.1"}, 1),
                sample({"agent_id": "002", "name": "s2", "status": "disconnected"}, 1),
                sample({"agent_id": "000", "name": "wazuh", "status": "active"}, 1),
            ],
            "agent_keepalive": [sample({"agent_id": "001", "name": "s1", "ip": "10.0.0.1"}, 100)],
            "rootcheck_outstanding": [
                sample({"agent_id": "001", "name": "s1", "finding_status": "outstanding"}, 3)
            ],
            "syscheck_findings": [sample({"agent_id": "001", "name": "s1"}, 4)],
            "alert_counts": [
                sample({"severity": "high"}, 7),
                sample({"severity": "medium"}, 3),
            ],
            "alert_top_rules": [
                sample({"rule_id": "5710", "description": "invalid user", "severity": "high"}, 7)
            ],
            "ssh_counts": [
                sample({"outcome": "all"}, 20),
                sample({"outcome": "failed"}, 5),
                sample({"outcome": "invalid_user"}, 2),
            ],
            "ssh_top_sources": [sample({"srcip": "203.0.113.10"}, 6)],
            "ssh_recent": [
                sample(
                    {
                        "rank": "1",
                        "timestamp": "2026-06-23T00:00:00Z",
                        "agent_name": "s1",
                        "srcip": "203.0.113.10",
                        "outcome": "failed",
                    },
                    1,
                )
            ],
            "fim_counts": [
                sample({"event": "modified"}, 2),
                sample({"event": "added"}, 1),
            ],
            "fim_top_paths": [sample({"path": "/etc/passwd"}, 2)],
            "fim_recent": [
                sample(
                    {
                        "rank": "1",
                        "timestamp": "2026-06-23T00:00:00Z",
                        "agent_name": "s1",
                        "event": "modified",
                        "path": "/etc/passwd",
                    },
                    1,
                )
            ],
        },
    )

    assert summary.enabled is True
    assert summary.agentTotal == 3
    assert [agent.id for agent in summary.agents] == ["002", "001"]
    assert summary.inactiveAgents == 1
    assert summary.rootcheckOutstanding == 3
    assert summary.alerts.severityCounts["high"] == 7
    assert summary.ssh.failed == 5
    assert summary.ssh.recent[0].srcip == "203.0.113.10"
    assert summary.fim.keyEvents == 3
    assert summary.fim.topPaths[0].label == "/etc/passwd"
    assert summary.health == "warning"


def test_wazuh_agents_only_does_not_require_indexer():
    summary = build_wazuh_summary(
        enabled=True,
        modules={"agents"},
        window="24h",
        metrics={
            "api_up": [sample({}, 1)],
            "agents_status": [sample({"status": "active"}, 2)],
            "manager_critical_down": [sample({}, 0)],
        },
    )

    assert summary.indexerUp is None
    assert summary.health == "ok"

from app.clients.pve import PVEServerConfig
from app.services.pve_mapper import build_pve_summary


def test_build_pve_summary_normalizes_vm_and_ct_resources():
    server = PVEServerConfig(
        name="lab",
        host="pve.local",
        token_id="user@pam!monitor",
        token_secret="secret",
    )

    summary = build_pve_summary(
        configured=True,
        collected=[
            {
                "server": server,
                "version": {"version": "8.2.0"},
                "latencyMs": 12,
                "nodes": [
                    {
                        "node": "pve1",
                        "status": "online",
                        "cpu": 0.25,
                        "mem": 4,
                        "maxmem": 8,
                        "disk": 10,
                        "maxdisk": 20,
                    }
                ],
                "resources": [
                    {
                        "type": "qemu",
                        "vmid": 100,
                        "node": "pve1",
                        "name": "vm-a",
                        "status": "running",
                        "cpu": 0.5,
                        "maxcpu": 4,
                        "mem": 2,
                        "maxmem": 8,
                    },
                    {
                        "type": "lxc",
                        "vmid": 101,
                        "node": "pve1",
                        "name": "ct-a",
                        "status": "stopped",
                        "cpu": 0,
                        "maxcpu": 2,
                    },
                ],
            }
        ],
        errors=[],
    )

    assert summary.configured is True
    assert summary.health == "ok"
    assert summary.totalGuests == 2
    assert summary.runningGuests == 1
    assert summary.qemuGuests == 1
    assert summary.lxcGuests == 1
    assert summary.cpuPct == 25
    assert summary.memPct == 50
    assert summary.diskPct == 50
    assert summary.guests[0].cpuPct == 50

from app.models import Problem
from app.services.normalizer import host_ids_for_machine, normalize_machines, summarize_items


def test_sys_phy_hosts_merge_into_one_machine():
    hosts = [
        {"hostid": "1", "host": "sys_s3", "name": "sys_s3", "groups": []},
        {"hostid": "2", "host": "phy_s3", "name": "phy_s3", "groups": []},
    ]
    items = [
        {"hostid": "1", "name": "CPU utilization", "key_": "system.cpu.util", "lastvalue": "42", "lastclock": "100"},
        {"hostid": "1", "name": "Number of CPUs", "key_": "system.cpu.num", "lastvalue": "16", "lastclock": "100"},
        {"hostid": "1", "name": "Operating system", "key_": "system.sw.os", "lastvalue": "Linux version 6.8.12-4-pve #1 SMP PREEMPT_DYNAMIC PMX", "lastclock": "100"},
        {"hostid": "1", "name": "CPU model", "key_": "system.hw.cpu", "lastvalue": "Intel(R) Xeon(R) Gold 6138 CPU @ 2.00GHz", "lastclock": "100"},
        {"hostid": "1", "name": "Memory utilization", "key_": "vm.memory.size[pused]", "lastvalue": "55", "lastclock": "100"},
        {"hostid": "1", "name": "Available memory", "key_": "vm.memory.size[available]", "lastvalue": str(45 * 1024), "lastclock": "100"},
        {"hostid": "1", "name": "Total memory", "key_": "vm.memory.size[total]", "lastvalue": str(100 * 1024), "lastclock": "100"},
        {"hostid": "1", "name": "FS [/]: Space: Used", "key_": "vfs.fs.size[/,used]", "lastvalue": str(70 * 1024), "lastclock": "100"},
        {"hostid": "1", "name": "FS [/]: Space: Total", "key_": "vfs.fs.size[/,total]", "lastvalue": str(100 * 1024), "lastclock": "100"},
        {"hostid": "1", "name": "System uptime", "key_": "system.uptime", "lastvalue": "172800", "lastclock": "100"},
        {"hostid": "2", "name": "CPU temperature", "key_": "sensor.temp", "lastvalue": "61", "lastclock": "100"},
    ]

    machines, devices = normalize_machines(hosts, items, [])

    assert devices == []
    assert len(machines) == 1
    assert machines[0].id == "s3"
    assert machines[0].mode == "paired"
    assert machines[0].sysHost == "sys_s3"
    assert machines[0].phyHost == "phy_s3"
    assert machines[0].osName == "Proxmox VE / Linux 6.8.12-4-pve"
    assert machines[0].cpuModel == "Intel Xeon(R) Gold 6138 @ 2.00GHz"
    assert machines[0].cpuCores == 16
    assert machines[0].cpuPct == 42
    assert machines[0].memPct == 55
    assert machines[0].memBytes == 55 * 1024
    assert machines[0].maxMemBytes == 100 * 1024
    assert machines[0].diskPct == 70
    assert machines[0].diskBytes == 70 * 1024
    assert machines[0].maxDiskBytes == 100 * 1024
    assert machines[0].uptimeSec == 172800
    assert machines[0].maxTempC == 61


def test_unpaired_host_stays_standalone():
    hosts = [{"hostid": "1", "host": "NAS", "name": "NAS", "groups": []}]
    items = [{"hostid": "1", "name": "Zabbix agent ping", "key_": "agent.ping", "lastvalue": "1"}]

    machines, _ = normalize_machines(hosts, items, [])

    assert machines[0].id == "nas"
    assert machines[0].mode == "standalone"
    assert machines[0].sysHost == "NAS"
    assert machines[0].agentUp is True


def test_zabbix_74_hostgroups_and_snmp_availability_are_supported():
    hosts = [
        {"hostid": "1", "host": "s1", "name": "Server01", "hostgroups": [{"name": "Hardware"}]},
        {"hostid": "2", "host": "e1", "name": "核心交换机", "hostgroups": [{"name": "exchange"}]},
    ]
    items = [
        {
            "hostid": "1",
            "name": "SNMP agent availability",
            "key_": "zabbix[host,snmp,available]",
            "lastvalue": "1",
        },
        {"hostid": "2", "name": "ICMP ping", "key_": "icmpping", "lastvalue": "1"},
    ]

    machines, devices = normalize_machines(hosts, items, [])

    assert machines[0].id == "s1"
    assert machines[0].sysHost == "Server01"
    assert machines[0].agentUp is True
    assert len(devices) == 1
    assert devices[0].host == "核心交换机"


def test_disabled_hosts_are_ignored():
    hosts = [
        {"hostid": "1", "host": "old", "name": "old", "status": "1", "groups": []},
        {"hostid": "2", "host": "new", "name": "new", "status": "0", "groups": []},
    ]
    items = [
        {"hostid": "1", "name": "CPU utilization", "key_": "system.cpu.util", "lastvalue": "99"},
        {"hostid": "2", "name": "CPU utilization", "key_": "system.cpu.util", "lastvalue": "10"},
    ]

    machines, _ = normalize_machines(hosts, items, [])

    assert [machine.id for machine in machines] == ["new"]
    assert machines[0].cpuPct == 10


def test_space_prefix_and_chinese_ids_are_preserved():
    hosts = [
        {"hostid": "1", "host": "sys s10", "name": "监控", "groups": []},
        {"hostid": "2", "host": "s1", "name": "phy_路由", "groups": []},
    ]

    machines, _ = normalize_machines(hosts, [], [])

    assert {machine.id for machine in machines} == {"s10", "路由"}


def test_display_name_prefix_wins_over_opaque_host_id():
    hosts = [
        {"hostid": "1", "host": "sys s9", "name": "sys_GPU", "groups": []},
        {"hostid": "2", "host": "s9", "name": "phy_GPU", "groups": []},
    ]

    machines, devices = normalize_machines(hosts, [], [])

    assert devices == []
    assert len(machines) == 1
    assert machines[0].id == "gpu"
    assert machines[0].mode == "paired"
    assert machines[0].sysHost == "sys_GPU"
    assert machines[0].phyHost == "phy_GPU"


def test_host_ids_for_machine_includes_standalone_hosts():
    hosts = [
        {"hostid": "1", "host": "cloud_nanchang", "name": "南昌云服务器", "groups": []},
        {"hostid": "2", "host": "sys_s6", "name": "sys_s6", "groups": []},
        {"hostid": "3", "host": "phy_s6", "name": "phy_s6", "groups": []},
    ]

    assert host_ids_for_machine(hosts, "cloud_nanchang") == {"standalone:1": "1"}
    assert host_ids_for_machine(hosts, "s6") == {"sys": "2", "phy": "3"}


def test_exchange_group_becomes_network_device():
    hosts = [{"hostid": "1", "host": "core-sw", "name": "core-sw", "groups": [{"name": "exchange"}]}]
    items = [{"hostid": "1", "name": "Interface eth0 bits received", "key_": "net.if.in[eth0]", "lastvalue": "1000"}]

    machines, devices = normalize_machines(hosts, items, [])

    assert machines == []
    assert len(devices) == 1
    assert devices[0].host == "core-sw"
    assert devices[0].netBps == 1000


def test_chinese_switch_name_becomes_network_device():
    hosts = [{"hostid": "1", "host": "e1", "name": "核心交换机", "groups": []}]

    machines, devices = normalize_machines(hosts, [], [])

    assert machines == []
    assert devices[0].host == "核心交换机"


def test_pdu_and_ups_hosts_become_infrastructure_devices():
    hosts = [
        {"hostid": "1", "host": "P1", "name": "PDU_UPS_1", "groups": []},
        {"hostid": "2", "host": "UPS", "name": "UPS", "groups": []},
    ]
    items = [
        {"hostid": "1", "name": "Input voltage", "key_": "sensor.voltage", "lastvalue": "220"},
        {"hostid": "2", "name": "Temperature", "key_": "sensor.temp", "lastvalue": "25"},
    ]

    machines, devices = normalize_machines(hosts, items, [])

    assert machines == []
    assert [device.host for device in devices] == ["PDU_UPS_1", "UPS"]


def test_item_classification_for_resource_metrics():
    metrics = summarize_items(
        [
            {"name": "CPU idle time", "key_": "system.cpu.util[,idle]", "lastvalue": "88"},
            {"name": "Available memory in %", "key_": "vm.memory.size[pavailable]", "lastvalue": "30"},
            {"name": "Disk usage", "key_": "vfs.fs.size[/,pused]", "lastvalue": "77"},
            {"name": "FS [/]: Space: Used, in %", "key_": "vfs.fs.dependent.size[/,pused]", "lastvalue": "66"},
            {"name": "FS [/]: Space: Free, in %", "key_": "vfs.fs.dependent.size[/,pfree]", "lastvalue": "34"},
            {"name": "Fan speed", "key_": "fan.rpm", "lastvalue": "3200"},
        ]
    )

    assert metrics.cpu == [12]
    assert metrics.mem == [70]
    assert metrics.disk == [77, 66]
    assert metrics.fan == [3200]


def test_memory_usage_is_derived_from_available_and_total_bytes():
    metrics = summarize_items(
        [
            {"name": "Available memory", "key_": "vm.memory.available[snmp]", "lastvalue": str(3 * 1024)},
            {"name": "Total memory", "key_": "vm.memory.total[memTotalReal.0]", "lastvalue": str(12 * 1024)},
        ]
    )

    assert metrics.mem == [75]
    assert metrics.mem_bytes == 9 * 1024
    assert metrics.max_mem_bytes == 12 * 1024


def test_direct_memory_percentage_wins_over_byte_derivation():
    metrics = summarize_items(
        [
            {"name": "Memory utilization", "key_": "vm.memory.util[snmp]", "lastvalue": "33"},
            {"name": "Available memory", "key_": "vm.memory.available[snmp]", "lastvalue": str(3 * 1024)},
            {"name": "Total memory", "key_": "vm.memory.total[memTotalReal.0]", "lastvalue": str(12 * 1024)},
        ]
    )

    assert metrics.mem == [33]


def test_os_is_derived_from_snmp_system_description():
    ikuai = summarize_items(
        [
            {
                "name": "System description",
                "key_": "system.descr[sysDescr.0]",
                "lastvalue": "Linux iKuai 5.10.194 #0 SMP Mon Dec 13 10:43:05 2021 x86_64",
            }
        ]
    )
    truenas = summarize_items(
        [
            {
                "name": "System description",
                "key_": "system.descr[sysDescr.0]",
                "lastvalue": (
                    "TrueNAS-25.10.4. Hardware: x86_64 Intel(R) Xeon(R) Gold 6138 "
                    "CPU @ 2.00GHz. Software: Linux 6.12.91-production+truenas"
                ),
            }
        ]
    )

    assert ikuai.os_names == ["iKuai 5.10.194"]
    assert truenas.os_names == ["TrueNAS 25.10.4 / Linux 6.12.91-production+truenas"]


def test_ubuntu_and_pve_versions_are_derived_from_kernel_strings():
    ubuntu = summarize_items(
        [
            {
                "name": "Operating system",
                "key_": "system.sw.os",
                "lastvalue": (
                    "Linux version 6.8.0-124-generic (buildd@host) "
                    "(gcc (Ubuntu 12.3.0-1ubuntu1~22.04.3) 12.3.0) "
                    "#124~22.04.1-Ubuntu SMP PREEMPT_DYNAMIC"
                ),
            }
        ]
    )
    pve = summarize_items(
        [
            {
                "name": "Operating system",
                "key_": "system.sw.os",
                "lastvalue": (
                    "Linux version 6.8.12-4-pve (build@proxmox) "
                    "#1 SMP PREEMPT_DYNAMIC PMX 6.8.12-4"
                ),
            }
        ]
    )

    assert ubuntu.os_names == ["Ubuntu 22.04.3 / Linux 6.8.0-124-generic"]
    assert pve.os_names == ["Proxmox VE / Linux 6.8.12-4-pve"]


def test_pve_product_version_is_read_from_custom_version_item():
    metrics = summarize_items(
        [
            {
                "name": "PVE version",
                "key_": "pve.version",
                "lastvalue": "pve-manager/8.3.5/9f411e79 (running kernel: 6.8.12-4-pve)",
            }
        ]
    )

    assert metrics.os_names == ["Proxmox VE 8.3.5 / Linux 6.8.12-4-pve"]


def test_disk_usage_is_derived_from_used_and_total_bytes():
    metrics = summarize_items(
        [
            {"name": "FS [/data]: Space: Used", "key_": "vfs.fs.size[/data,used]", "lastvalue": "80"},
            {"name": "FS [/data]: Space: Total", "key_": "vfs.fs.size[/data,total]", "lastvalue": "100"},
        ]
    )

    assert metrics.disk == [80]
    assert metrics.disk_bytes == 80
    assert metrics.max_disk_bytes == 100


def test_disk_usage_is_parsed_from_filesystem_json_payload():
    metrics = summarize_items(
        [
            {
                "name": "FS [/]: Get data",
                "key_": "vfs.fs.dependent[/,data]",
                "lastvalue": '{"fsname":"/","bytes":{"used":30,"free":70,"total":100,"pused":30,"pfree":70}}',
            },
            {
                "name": "Get filesystems",
                "key_": "vfs.fs.get",
                "lastvalue": '[{"fsname":"/srv","bytes":{"used":45,"free":55,"total":100}}]',
            },
        ]
    )

    assert metrics.disk == [30, 45]


def test_disk_io_utilization_is_not_storage_capacity():
    metrics = summarize_items(
        [
            {"name": "sda: Disk utilization", "key_": "vfs.dev.util[diskIOLA1.1]", "lastvalue": "99", "units": "%"},
            {"name": "FS [/]: Inodes: Free, in %", "key_": "vfs.fs.dependent.inode[/,pfree]", "lastvalue": "1", "units": "%"},
        ]
    )

    assert metrics.disk == []


def test_non_cpu_model_items_are_not_cpu_model():
    metrics = summarize_items(
        [
            {"name": "Solid State Disk 0 Model name", "key_": "dell.server.hw.physicaldisk.model[1]", "lastvalue": "SSDSC2KB960G7R"},
            {"name": "System Model name", "key_": "system.hw.model", "lastvalue": "PowerEdge R750"},
        ]
    )

    assert metrics.cpu_models == []


def test_problem_health_is_critical_for_high_severity():
    hosts = [{"hostid": "1", "host": "sys_s4", "name": "sys_s4", "groups": []}]
    problems = [
        Problem(
            source="zabbix",
            severity="high",
            host="sys_s4",
            name="Disk full",
            ageSec=60,
            eventId="e1",
        )
    ]

    machines, _ = normalize_machines(hosts, [], problems)

    assert machines[0].health == "critical"

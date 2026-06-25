from app.services.collector import select_series_items, series_metric_name, series_metric_value


def test_series_selection_keeps_memory_and_disk_when_many_cpu_items_exist():
    items = [
        {
            "itemid": str(index),
            "name": f"CPU utilization core {index}",
            "key_": f"system.cpu.util[{index}]",
            "lastvalue": "1",
        }
        for index in range(30)
    ]
    items.extend(
        [
            {
                "itemid": "mem",
                "name": "Memory utilization",
                "key_": "vm.memory.utilization",
                "lastvalue": "42",
            },
            {
                "itemid": "disk",
                "name": "FS [/]: Space: Used, in %",
                "key_": "vfs.fs.dependent.size[/,pused]",
                "lastvalue": "61",
            },
        ]
    )

    selected_metrics = [series_metric_name(item) for item in select_series_items(items)]

    assert "memPct" in selected_metrics
    assert "diskPct" in selected_metrics
    assert selected_metrics.count("cpuPct") == 8


def test_series_metric_value_converts_available_memory_and_idle_cpu():
    assert (
        series_metric_value(
            {"name": "Available memory in %", "key_": "vm.memory.size[pavailable]"},
            "18.5",
            "memPct",
        )
        == 81.5
    )
    assert (
        series_metric_value(
            {"name": "CPU idle time", "key_": "system.cpu.util[,idle]"},
            "92",
            "cpuPct",
        )
        == 8
    )


def test_series_metric_value_converts_free_disk_percent():
    assert series_metric_name({"name": "FS [/]: Space: Free, in %", "key_": "vfs.fs.size[/,pfree]", "lastvalue": "34"}) == "diskPct"
    assert series_metric_value({"name": "FS [/]: Space: Free, in %", "key_": "vfs.fs.size[/,pfree]"}, "34", "diskPct") == 66

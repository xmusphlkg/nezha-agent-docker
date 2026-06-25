import orjson

from app.models import Problem


def test_problem_cache_payload_is_json_serializable():
    problem = Problem(
        source="zabbix",
        severity="warning",
        host="sys_s3",
        name="Disk pressure",
        ageSec=30,
        eventId="1",
    )

    payload = {"problems": [problem.model_dump(mode="json")]}

    assert orjson.loads(orjson.dumps(payload))["problems"][0]["host"] == "sys_s3"

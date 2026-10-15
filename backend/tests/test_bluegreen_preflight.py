"""Synthetic-only evidence tests; no Lightsail access or shell commands."""
from dataclasses import replace

import pytest

from tools.bluegreen_preflight import Evidence, assess, parse_meminfo, parse_listeners


@pytest.fixture
def evidence():
    return Evidence(
        cpu_count=2, available_mem_mib=1400, free_disk_mib=20000,
        api_active=True, nginx_active=True, nginx_valid=True, unit_loopback=True,
        listeners=frozenset({("127.0.0.1", 8000), ("0.0.0.0", 443)}),
    )


def test_parsers():
    assert parse_meminfo("MemAvailable: 1048576 kB\n") == 1024
    with pytest.raises(ValueError, match="MEMINFO_UNAVAILABLE"):
        parse_meminfo("MemTotal: 2097152 kB\n")
    assert parse_listeners("LISTEN 0 2048 127.0.0.1:8000 0.0.0.0:*\n") == frozenset({
        ("127.0.0.1", 8000),
    })


def test_good_resources_do_not_authorize_cutover(evidence):
    result = assess(evidence)
    assert result["resource_checks_passed"] is True
    assert result["production_modified"] is False
    assert result["cutover_authorized"] is False
    assert "DATABASE_RECOVERY_UNVERIFIED" in result["manual_review_required"]


@pytest.mark.parametrize("changed,code", [
    ({"cpu_count": 1}, "CPU_BELOW_MINIMUM"),
    ({"available_mem_mib": 200}, "MEMORY_BELOW_THRESHOLD"),
    ({"free_disk_mib": 100}, "DISK_BELOW_THRESHOLD"),
    ({"api_active": False}, "PRIMARY_SERVICE_UNVERIFIED"),
    ({"unit_loopback": False}, "PRIMARY_SERVICE_UNVERIFIED"),
    ({"nginx_active": False}, "NGINX_UNVERIFIED"),
    ({"nginx_valid": False}, "NGINX_UNVERIFIED"),
    ({"listeners": frozenset()}, "PRIMARY_PORT_UNVERIFIED"),
    ({"listeners": frozenset({("127.0.0.1", 8000), ("127.0.0.1", 8001)})},
     "STANDBY_PORT_OCCUPIED"),
    ({"listeners": frozenset({("127.0.0.1", 8000), ("0.0.0.0", 8000)})},
     "PRIMARY_NON_LOOPBACK_BINDING"),
])
def test_fail_closed_on_resource_risks(evidence, changed, code):
    result = assess(replace(evidence, **changed))
    assert result["resource_checks_passed"] is False
    assert code in result["resource_blockers"]
    assert result["cutover_authorized"] is False

"""Read-only blue/green resource preflight; never changes production."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Evidence:
    cpu_count: int
    available_mem_mib: int
    free_disk_mib: int
    api_active: bool
    nginx_active: bool
    nginx_valid: bool
    unit_loopback: bool
    listeners: frozenset[tuple[str, int]]


def parse_meminfo(raw: str) -> int:
    match = re.search(r"^MemAvailable:\s+(\d+)\s+kB$", raw, re.MULTILINE)
    if not match:
        raise ValueError("MEMINFO_UNAVAILABLE")
    return int(match.group(1)) // 1024


def parse_listeners(raw: str) -> frozenset[tuple[str, int]]:
    result = set()
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0] != "LISTEN":
            continue
        found = re.fullmatch(r"(\[[^\]]+\]|[^:]+):(\d+)", fields[3])
        if found:
            result.add((found.group(1), int(found.group(2))))
    return frozenset(result)


def _probe(*args: str) -> tuple[bool, str]:
    try:
        p = subprocess.run(args, capture_output=True, text=True,
                           timeout=8, check=False)
        return p.returncode == 0, p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False, ""


def collect() -> Evidence:
    available = parse_meminfo(Path("/proc/meminfo").read_text(encoding="ascii"))
    disk = shutil.disk_usage("/opt/diaglob/app")
    active, _ = _probe("systemctl", "is-active", "--quiet", "diaglob-api.service")
    nginx, _ = _probe("systemctl", "is-active", "--quiet", "nginx.service")
    valid, _ = _probe("sudo", "-n", "nginx", "-t")
    unit_ok, unit = _probe("systemctl", "show", "--value", "-p", "ExecStart",
                           "diaglob-api.service")
    sockets_ok, sockets = _probe("ss", "-ltnH")
    if not sockets_ok:
        raise ValueError("LISTENERS_UNAVAILABLE")
    return Evidence(
        cpu_count=os.cpu_count() or 0,
        available_mem_mib=available,
        free_disk_mib=disk.free // 1048576,
        api_active=active,
        nginx_active=nginx,
        nginx_valid=valid,
        unit_loopback=unit_ok and all(v in unit for v in (
            "uvicorn", "127.0.0.1", "8000")),
        listeners=parse_listeners(sockets),
    )


def assess(e: Evidence) -> dict:
    blockers = []
    if e.cpu_count < 2:
        blockers.append("CPU_BELOW_MINIMUM")
    if e.available_mem_mib < 768:
        blockers.append("MEMORY_BELOW_THRESHOLD")
    if e.free_disk_mib < 1024:
        blockers.append("DISK_BELOW_THRESHOLD")
    if not e.api_active or not e.unit_loopback:
        blockers.append("PRIMARY_SERVICE_UNVERIFIED")
    if not e.nginx_active or not e.nginx_valid:
        blockers.append("NGINX_UNVERIFIED")
    if ("127.0.0.1", 8000) not in e.listeners:
        blockers.append("PRIMARY_PORT_UNVERIFIED")
    if any(port == 8001 for _, port in e.listeners):
        blockers.append("STANDBY_PORT_OCCUPIED")
    if any(port == 8000 and host != "127.0.0.1" for host, port in e.listeners):
        blockers.append("PRIMARY_NON_LOOPBACK_BINDING")
    return {
        "mode": "read_only_bluegreen_preflight",
        "available_mem_mib": e.available_mem_mib,
        "free_disk_mib": e.free_disk_mib,
        "cpu_count": e.cpu_count,
        "resource_checks_passed": not blockers,
        "resource_blockers": blockers,
        "manual_review_required": [
            "INSTANCE_SNAPSHOT_UNVERIFIED",
            "DATABASE_RECOVERY_UNVERIFIED",
            "NGINX_SWITCH_UNREVIEWED",
            "ROLLBACK_AND_DRAIN_UNTESTED",
        ],
        "cutover_authorized": False,
        "production_modified": False,
    }


def main() -> int:
    try:
        result = assess(collect())
    except (OSError, ValueError):
        result = {
            "mode": "read_only_bluegreen_preflight",
            "resource_checks_passed": False,
            "resource_blockers": ["EVIDENCE_COLLECTION_FAILED"],
            "cutover_authorized": False,
            "production_modified": False,
        }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["resource_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

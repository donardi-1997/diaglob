#!/usr/bin/env python3
"""Sync Shopify App Pricing configuration into the production env file.

Usage (as root, from the deploy workflow):

    python sync_shopify_billing_env.py /etc/diaglob/diaglob.env /tmp/payload.json

The payload is a JSON object produced from GitHub Actions secrets/variables.
Empty values are ignored, so an unset secret never wipes an existing value.
Every value is validated before anything is written; on any error the env
file is left untouched. Only key names and CHANGED/UNCHANGED are printed —
never values.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

_TOKEN = re.compile(r"^[A-Za-z0-9_\-]{20,255}$")
_APP_HANDLE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?$")
_PLANS = {"starter", "growth", "pro"}
_INTERVALS = {"EVERY_30_DAYS", "ANNUAL"}
_USD = re.compile(r"^(?:0|[1-9][0-9]{0,6})(?:\.[0-9]{1,2})?$")
_GATES = ("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", "SHOPIFY_BILLING_SCHEDULER_ENABLED")


class SyncError(ValueError):
    pass


def _validate_handles(raw: str) -> str:
    try:
        catalog = json.loads(raw)
    except ValueError:
        raise SyncError("SHOPIFY_APP_PRICING_HANDLES_JSON") from None
    if not isinstance(catalog, dict) or not catalog:
        raise SyncError("SHOPIFY_APP_PRICING_HANDLES_JSON")
    for handle, entry in catalog.items():
        if not _APP_HANDLE.fullmatch(handle) or not isinstance(entry, dict):
            raise SyncError("SHOPIFY_APP_PRICING_HANDLES_JSON")
        if entry.get("plan") not in _PLANS:
            raise SyncError("SHOPIFY_APP_PRICING_HANDLES_JSON")
        prices = entry.get("prices")
        if prices is not None:
            if (
                not isinstance(prices, dict) or not prices
                or not set(prices) <= _INTERVALS
                or not all(isinstance(v, str) and _USD.fullmatch(v) for v in prices.values())
            ):
                raise SyncError("SHOPIFY_APP_PRICING_HANDLES_JSON")
        elif entry.get("interval") not in _INTERVALS or not (
            isinstance(entry.get("amount_usd"), str) and _USD.fullmatch(entry["amount_usd"])
        ):
            raise SyncError("SHOPIFY_APP_PRICING_HANDLES_JSON")
    return json.dumps(catalog, separators=(",", ":"), sort_keys=True)


def validate_payload(payload: dict) -> dict[str, str]:
    """Return env assignments (already formatted for the env file)."""
    if not isinstance(payload, dict):
        raise SyncError("PAYLOAD")
    out: dict[str, str] = {}

    def value(key: str) -> str:
        raw = payload.get(key) or ""
        if not isinstance(raw, str):
            raise SyncError(key)
        return raw.strip()

    org = value("SHOPIFY_PARTNER_ORG_ID")
    if org:
        if not org.isascii() or not org.isdecimal():
            raise SyncError("SHOPIFY_PARTNER_ORG_ID")
        out["SHOPIFY_PARTNER_ORG_ID"] = org
    gid = value("SHOPIFY_PARTNER_APP_GID")
    if gid:
        if not re.fullmatch(r"gid://shopify/App/[0-9]+", gid):
            raise SyncError("SHOPIFY_PARTNER_APP_GID")
        out["SHOPIFY_PARTNER_APP_GID"] = gid
    token = value("SHOPIFY_PARTNER_ACCESS_TOKEN")
    if token:
        if not _TOKEN.fullmatch(token):
            raise SyncError("SHOPIFY_PARTNER_ACCESS_TOKEN")
        out["SHOPIFY_PARTNER_ACCESS_TOKEN"] = token
    handles = value("SHOPIFY_APP_PRICING_HANDLES_JSON")
    if handles:
        # Single quotes keep JSON intact for both `bash .` and systemd
        # EnvironmentFile; validated JSON never contains a single quote.
        out["SHOPIFY_APP_PRICING_HANDLES_JSON"] = "'" + _validate_handles(handles) + "'"
    store_handle = value("SHOPIFY_APP_STORE_HANDLE")
    if store_handle:
        if not _APP_HANDLE.fullmatch(store_handle):
            raise SyncError("SHOPIFY_APP_STORE_HANDLE")
        out["SHOPIFY_APP_STORE_HANDLE"] = store_handle
    for gate in _GATES:
        flag = value(gate).lower()
        if flag:
            if flag not in {"true", "false"}:
                raise SyncError(gate)
            out[gate] = flag
    return out


def apply(env_text: str, assignments: dict[str, str]) -> tuple[str, dict[str, str]]:
    lines = env_text.splitlines()
    status: dict[str, str] = {}
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        name, sep, current = line.partition("=")
        key = name.strip()
        if sep and not line.lstrip().startswith("#") and key in assignments:
            if key in seen:
                status[key] = "CHANGED"
                continue  # drop duplicates so the last value cannot win
            seen.add(key)
            status[key] = "UNCHANGED" if current == assignments[key] else "CHANGED"
            result.append(f"{key}={assignments[key]}")
        else:
            result.append(line)
    for key, val in assignments.items():
        if key not in seen:
            result.append(f"{key}={val}")
            status[key] = "CHANGED"
    return "\n".join(result) + "\n", status


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("USAGE: sync_shopify_billing_env.py <env_file> <payload.json>", file=sys.stderr)
        return 2
    env_path, payload_path = Path(argv[1]), Path(argv[2])
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        assignments = validate_payload(payload)
    except (OSError, ValueError) as exc:
        key = str(exc) if isinstance(exc, SyncError) else "PAYLOAD"
        print(f"SHOPIFY_BILLING_SYNC_INVALID: {key}", file=sys.stderr)
        return 1
    finally:
        try:
            payload_path.unlink()
        except OSError:
            pass
    if not assignments:
        print("SHOPIFY_BILLING_SYNC_SKIPPED")
        return 0

    original = env_path.read_text(encoding="utf-8")
    updated, status = apply(original, assignments)
    for key in sorted(status):
        print(f"SHOPIFY_BILLING_SYNC {status[key]}: {key}")
    if updated == original:
        return 0
    st = env_path.stat()
    fd, tmp = tempfile.mkstemp(dir=str(env_path.parent), prefix=".diaglob-env-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(updated)
        os.chmod(tmp, st.st_mode & 0o777)
        if hasattr(os, "chown"):
            try:
                os.chown(tmp, st.st_uid, st.st_gid)
            except PermissionError:
                pass
        os.replace(tmp, env_path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

"""Runtime context passed to supplier provider instances."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class SupplierRuntimeContext:
    """Tenant-safe runtime data required by a supplier provider.

    Database sessions and ORM entities deliberately stay outside provider
    clients. Services resolve/decrypt connection credentials, then construct a
    provider with this immutable context.
    """

    organization_id: int
    store_id: int
    credentials: Mapping[str, str] = field(default_factory=dict)

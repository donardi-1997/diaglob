"""In-memory ONE-TIME synthetic Shopify privacy delivery simulation.

No API route or production integration. This is not merchant authentication,
safe storage, legal approval, or real customer-data delivery. The fixture flag
is a test contract, not cryptographic proof of synthetic provenance.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .shopify_privacy_synthetic_export import EncryptedSyntheticExport

_REQUEST_ID = re.compile(r"^[0-9a-f]{64}$")
_RECIPIENT_ID = re.compile(r"^[A-Za-z0-9:_-]{1,128}$")
_MAX_TTL_SECONDS = 900
_MIN_TTL_SECONDS = 60
_MAX_CIPHERTEXT_BYTES = 1_000_000
_MAX_OUTSTANDING = 16


class SyntheticPrivacyDeliveryError(ValueError):
    """Non-sensitive rejection code, including for unknown delivery tokens."""


@dataclass(frozen=True)
class SyntheticDeliveryTicket:
    token: str = field(repr=False)
    expires_in_seconds: int
    synthetic_only: bool = True
    merchant_delivery_allowed: bool = False


@dataclass(frozen=True)
class SyntheticDeliveryReceipt:
    ciphertext: bytes = field(repr=False)
    sha256: str
    synthetic_only: bool = True
    merchant_delivery_allowed: bool = False
    fulfillment_complete: bool = False


@dataclass(frozen=True)
class _Entry:
    binding: tuple[str, int, int, str]
    ciphertext: bytes = field(repr=False)
    sha256: str
    expires_at: float


def _binding(
    request_id: str, organization_id: int, store_id: int, recipient_binding: str,
) -> tuple[str, int, int, str]:
    if (
        not isinstance(request_id, str)
        or _REQUEST_ID.fullmatch(request_id) is None
        or type(organization_id) is not int
        or organization_id <= 0
        or type(store_id) is not int
        or store_id <= 0
        or not isinstance(recipient_binding, str)
        or _RECIPIENT_ID.fullmatch(recipient_binding) is None
    ):
        raise SyntheticPrivacyDeliveryError("INVALID_SYNTHETIC_DELIVERY_BINDING")
    return (request_id, organization_id, store_id, recipient_binding)


class SyntheticPrivacyDeliveryVault:
    """Bounded, volatile ciphertext vault for isolated tests only.

    The caller supplies an opaque recipient binding from test fixtures; the
    vault does NOT authenticate a merchant. The token is returned to the Python
    test caller once and never placed in an API response, URL, log, or database.
    No persistent storage: restart discards all entries, by design.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def _purge_locked(self, now: float) -> int:
        stale = [
            digest for digest, entry in self._entries.items()
            if now >= entry.expires_at
        ]
        for digest in stale:
            del self._entries[digest]
        return len(stale)

    def purge_expired(self) -> int:
        """Remove expired fixture artifacts; report a non-sensitive count."""
        with self._lock:
            return self._purge_locked(self._clock())

    def issue(
        self, *, artifact: EncryptedSyntheticExport, request_id: str,
        organization_id: int, store_id: int, recipient_binding: str,
        ttl_seconds: int = 300, fixture_authorized: bool = False,
    ) -> SyntheticDeliveryTicket:
        """Issue test-only one-time access to ciphertext, not plaintext."""
        if fixture_authorized is not True:
            raise SyntheticPrivacyDeliveryError("LIVE_DELIVERY_DISABLED")
        binding = _binding(request_id, organization_id, store_id, recipient_binding)
        if type(ttl_seconds) is not int or not (
            _MIN_TTL_SECONDS <= ttl_seconds <= _MAX_TTL_SECONDS
        ):
            raise SyntheticPrivacyDeliveryError("INVALID_SYNTHETIC_DELIVERY_TTL")
        if (
            type(artifact) is not EncryptedSyntheticExport
            or artifact.synthetic_only is not True
            or artifact.delivery_authorized is not False
            or artifact.fulfillment_complete is not False
            or not isinstance(artifact.ciphertext, bytes)
            or not (1 <= len(artifact.ciphertext) <= _MAX_CIPHERTEXT_BYTES)
            or not isinstance(artifact.sha256, str)
            or not hmac.compare_digest(
                hashlib.sha256(artifact.ciphertext).hexdigest(), artifact.sha256
            )
        ):
            raise SyntheticPrivacyDeliveryError("INVALID_SYNTHETIC_DELIVERY_ARTIFACT")
        with self._lock:
            now = self._clock()
            self._purge_locked(now)
            if len(self._entries) >= _MAX_OUTSTANDING:
                raise SyntheticPrivacyDeliveryError("SYNTHETIC_DELIVERY_CAPACITY_REACHED")
            token = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode("ascii")).hexdigest()
            self._entries[digest] = _Entry(
                binding=binding,
                ciphertext=artifact.ciphertext,
                sha256=artifact.sha256,
                expires_at=now + ttl_seconds,
            )
        return SyntheticDeliveryTicket(
            token=token, expires_in_seconds=ttl_seconds,
        )

    def redeem(
        self, *, token: str, request_id: str, organization_id: int,
        store_id: int, recipient_binding: str, fixture_authorized: bool = False,
    ) -> SyntheticDeliveryReceipt:
        """Consume a fixture once; invalid scope never consumes a valid token."""
        if fixture_authorized is not True:
            raise SyntheticPrivacyDeliveryError("LIVE_DELIVERY_DISABLED")
        binding = _binding(request_id, organization_id, store_id, recipient_binding)
        if not isinstance(token, str) or not (32 <= len(token) <= 128):
            raise SyntheticPrivacyDeliveryError("SYNTHETIC_DELIVERY_UNAVAILABLE")
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._lock:
            self._purge_locked(self._clock())
            entry = self._entries.get(digest)
            if entry is None or entry.binding != binding:
                raise SyntheticPrivacyDeliveryError("SYNTHETIC_DELIVERY_UNAVAILABLE")
            del self._entries[digest]
        return SyntheticDeliveryReceipt(
            ciphertext=entry.ciphertext, sha256=entry.sha256,
        )

    def revoke(
        self, *, token: str, request_id: str, organization_id: int,
        store_id: int, recipient_binding: str, fixture_authorized: bool = False,
    ) -> bool:
        """Revoke a fixture with the same binding; no other tenant can revoke."""
        if fixture_authorized is not True:
            raise SyntheticPrivacyDeliveryError("LIVE_DELIVERY_DISABLED")
        binding = _binding(request_id, organization_id, store_id, recipient_binding)
        if not isinstance(token, str) or not (32 <= len(token) <= 128):
            return False
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._lock:
            self._purge_locked(self._clock())
            entry = self._entries.get(digest)
            if entry is None or entry.binding != binding:
                return False
            del self._entries[digest]
        return True

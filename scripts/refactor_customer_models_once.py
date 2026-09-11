"""One-off source-to-source refactor for the Customer model domain.

This helper is intentionally temporary. It moves the existing Customer and
CustomerStoreProfile SQLAlchemy definitions out of app.models without changing
the definitions themselves, then leaves app.models as a compatibility re-export.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "backend" / "app" / "models.py"
CUSTOMERS = ROOT / "backend" / "app" / "model_domains" / "customers.py"

CUSTOMER_MARKER = """# ============================================================\n# CUSTOMER\n# ============================================================\n"""
AGENT_MARKER = """# ============================================================\n# AGENT\n# ============================================================\n"""


def main() -> None:
    source = MODELS.read_text(encoding="utf-8")

    if "from .model_domains.customers import Customer, CustomerStoreProfile" in source:
        raise SystemExit("Customer model extraction has already been applied")

    try:
        start = source.index(CUSTOMER_MARKER)
        end = source.index(AGENT_MARKER, start)
    except ValueError as exc:
        raise SystemExit("Expected Customer/Agent section markers were not found") from exc

    section = source[start:end].rstrip() + "\n"
    if "class Customer(Base):" not in section:
        raise SystemExit("Customer definition not found inside extraction section")
    if "class CustomerStoreProfile(Base):" not in section:
        raise SystemExit("CustomerStoreProfile definition not found inside extraction section")

    module = '''"""Customer persistence models.\n\nPhysically extracted from the legacy ``app.models`` module. The table names,\ncolumns, constraints, relationships, defaults, and shared SQLAlchemy metadata\nare intentionally unchanged.\n"""\n\nfrom datetime import datetime\n\nfrom sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint\nfrom sqlalchemy.orm import Mapped, mapped_column, relationship\n\nfrom ..db import Base\n\n'''
    # Keep the original model bodies byte-for-byte apart from their section comments.
    module += section
    module += '\n__all__ = ["Customer", "CustomerStoreProfile"]\n'

    replacement = '''# ============================================================\n# CUSTOMER DOMAIN (compatibility re-export)\n# ============================================================\n\n# Customer models are physically defined in app.model_domains.customers.\n# This import preserves the historical app.models import surface.\nfrom .model_domains.customers import Customer, CustomerStoreProfile\n\n\n'''

    updated = source[:start] + replacement + source[end:]

    if "class Customer(Base):" in updated or "class CustomerStoreProfile(Base):" in updated:
        raise SystemExit("Customer definitions unexpectedly remain in app.models")

    CUSTOMERS.write_text(module, encoding="utf-8")
    MODELS.write_text(updated, encoding="utf-8")

    print(f"Extracted Customer models: {len(source)} -> {len(updated)} bytes")


if __name__ == "__main__":
    main()

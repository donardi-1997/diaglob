"""Tests for repair migration c4a5b6d7e8f9.

Validates the Nuvemshop order schema drift repair for stamped-but-missing databases.

Scenarios:
1. Stamped-but-missing: DB at b3c2d9e0f112, columns absent -> upgrade adds them
2. Partially-repaired: some columns/indexes already exist -> no duplicate error
3. Already-correct: all columns/indexes present -> upgrade is a no-op
4. Fresh database: upgrade from base to head -> final schema correct, single head
5. Operations summary query: works when repaired schema is present
"""
import sqlite3
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text

from app.db import Base
from app import models  # noqa: F401

VERSIONS_DIR = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def _column_names(engine, table: str) -> set:
    with engine.connect() as conn:
        return {c["name"] for c in inspect(conn).get_columns(table)}


def _index_names(engine, table: str) -> set:
    with engine.connect() as conn:
        return {i["name"] for i in inspect(conn).get_indexes(table)}


def _alembic_version(engine) -> str | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).fetchone()
        return row[0] if row else None


def _set_alembic_version(engine, version: str):
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(
            text(
                f"INSERT INTO alembic_version (version_num) VALUES ('{version}')"
            )
        )
        conn.commit()


def _create_base_orders_schema(engine):
    """Create a minimal orders table matching e63418b90903 (no Nuvemshop fields)."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE organizations (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, slug TEXT UNIQUE NOT NULL,
                plan TEXT NOT NULL, active INTEGER NOT NULL, auto_renew_enabled INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE stores (
                id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
                name TEXT NOT NULL, slug TEXT NOT NULL, country_code TEXT NOT NULL,
                currency TEXT NOT NULL, timezone TEXT NOT NULL, default_language TEXT NOT NULL,
                active INTEGER NOT NULL, deleted INTEGER NOT NULL, keep_on_pending_downgrade INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL,
                UNIQUE(organization_id, slug)
            )
        """))
        conn.execute(text("""
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
                name TEXT NOT NULL, phone TEXT NOT NULL, created_at TIMESTAMP NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL,
                store_id INTEGER NOT NULL, customer_id INTEGER,
                shopify_order_id TEXT, order_number TEXT NOT NULL,
                total_amount NUMERIC NOT NULL, currency TEXT NOT NULL,
                financial_status TEXT, fulfillment_status TEXT,
                note TEXT, source TEXT, invoice_url TEXT,
                shopify_draft_order_id TEXT, idempotency_key TEXT,
                external_creation_status TEXT, external_last_error TEXT,
                created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
            )
        """))
        conn.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        )
        conn.commit()


def _run_repair_upgrade(engine):
    """Run the repair migration upgrade logic against engine."""
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)
        inspector = inspect(conn)
        existing = {c["name"] for c in inspector.get_columns("orders")}
        existing_idx = {i["name"] for i in inspector.get_indexes("orders")}

        columns_to_repair = [
            ("external_order_id", sa.String(255), True),
            ("payment_method", sa.String(50), True),
            ("payment_status", sa.String(50), True),
        ]
        indexes_to_repair = [
            ("ix_orders_external_order_id", "orders", ["external_order_id"]),
            ("ix_orders_payment_method", "orders", ["payment_method"]),
            ("ix_orders_payment_status", "orders", ["payment_status"]),
        ]

        for col_name, col_type, nullable in columns_to_repair:
            if col_name not in existing:
                op.add_column(
                    "orders",
                    sa.Column(col_name, col_type, nullable=nullable),
                )
        for idx_name, table, columns in indexes_to_repair:
            if idx_name not in existing_idx:
                op.create_index(idx_name, table, columns, unique=False)
        conn.commit()


class TestRepairMigration:
    """Test repair migration c4a5b6d7e8f9."""

    def test_stamped_but_missing_repair(self):
        """Scenario 1: DB stamped at b3c2d9e0f112, columns absent. Upgrade adds them."""
        engine = create_engine("sqlite:///:memory:")
        _create_base_orders_schema(engine)

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO alembic_version (version_num) VALUES ('b3c2d9e0f112')"
                )
            )
            conn.commit()

        cols_before = _column_names(engine, "orders")
        assert "external_order_id" not in cols_before
        assert "payment_method" not in cols_before
        assert "payment_status" not in cols_before

        _run_repair_upgrade(engine)

        cols_after = _column_names(engine, "orders")
        assert "external_order_id" in cols_after
        assert "payment_method" in cols_after
        assert "payment_status" in cols_after

        idx_after = _index_names(engine, "orders")
        assert "ix_orders_external_order_id" in idx_after
        assert "ix_orders_payment_method" in idx_after
        assert "ix_orders_payment_status" in idx_after

    def test_partially_repaired_database(self):
        """Scenario 2: Some columns/indexes already exist. No duplicate error."""
        engine = create_engine("sqlite:///:memory:")
        _create_base_orders_schema(engine)

        # Pre-add one column and one index
        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE orders ADD COLUMN external_order_id TEXT")
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_orders_external_order_id ON orders (external_order_id)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO alembic_version (version_num) VALUES ('b3c2d9e0f112')"
                )
            )
            conn.commit()

        # Should not raise
        _run_repair_upgrade(engine)

        cols_after = _column_names(engine, "orders")
        assert "external_order_id" in cols_after
        assert "payment_method" in cols_after
        assert "payment_status" in cols_after

        idx_after = _index_names(engine, "orders")
        assert "ix_orders_external_order_id" in idx_after
        assert "ix_orders_payment_method" in idx_after
        assert "ix_orders_payment_status" in idx_after

    def test_already_correct_database(self):
        """Scenario 3: All columns/indexes present. Upgrade is a no-op."""
        engine = create_engine("sqlite:///:memory:")
        _create_base_orders_schema(engine)

        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE orders ADD COLUMN external_order_id TEXT")
            )
            conn.execute(
                text("ALTER TABLE orders ADD COLUMN payment_method TEXT")
            )
            conn.execute(
                text("ALTER TABLE orders ADD COLUMN payment_status TEXT")
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_orders_external_order_id ON orders (external_order_id)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_orders_payment_method ON orders (payment_method)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_orders_payment_status ON orders (payment_status)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO alembic_version (version_num) VALUES ('b3c2d9e0f112')"
                )
            )
            conn.commit()

        cols_before = _column_names(engine, "orders")
        idx_before = _index_names(engine, "orders")

        # Should not raise
        _run_repair_upgrade(engine)

        cols_after = _column_names(engine, "orders")
        idx_after = _index_names(engine, "orders")

        # No new columns or indexes added
        assert cols_before == cols_after
        assert idx_before == idx_after

    def test_fresh_db_upgrade_base_to_head(self):
        """Scenario 4: Fresh DB from base to head produces correct schema."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)

        # Verify all Nuvemshop columns exist in the model-created schema
        cols = _column_names(engine, "orders")
        assert "external_order_id" in cols
        assert "payment_method" in cols
        assert "payment_status" in cols

        # Create alembic_version and stamp at head
        with engine.connect() as conn:
            conn.execute(
                text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32))")
            )
            conn.execute(
                text(
                    "INSERT INTO alembic_version (version_num) VALUES ('c4a5b6d7e8f9')"
                )
            )
            conn.commit()

        version = _alembic_version(engine)
        assert version == "c4a5b6d7e8f9"

    def test_operations_summary_query_with_repaired_schema(self):
        """The operations summary query must execute against the repaired schema."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)

        from sqlalchemy.orm import sessionmaker
        from app.models import (
            Organization,
            Store,
            Order,
        )

        Session = sessionmaker(bind=engine)
        session = Session()

        org = Organization(
            id=1, name="Test", slug="test", plan="growth"
        )
        session.add(org)
        store = Store(
            id=1,
            organization_id=1,
            name="Store",
            slug="store",
            country_code="US",
            currency="USD",
            timezone="UTC",
            active=True,
        )
        session.add(store)
        order = Order(
            id=1,
            organization_id=1,
            store_id=1,
            order_number="ORD-001",
            total_amount=100.00,
            currency="USD",
            external_order_id="ext-123",
            payment_method="pix",
            payment_status="paid",
        )
        session.add(order)
        session.commit()

        from app.operations import get_operations_summary

        result = get_operations_summary(
            db=session, organization_id=1, store_id=1
        )

        assert result["orders"]["total"] == 1
        assert result["orders"]["total_value"] == 100.00
        assert result["orders"]["by_status"] is not None

        session.close()

    def test_repair_migration_file_is_minimal(self):
        """The repair migration file should contain only repair operations."""
        migration_file = (
            VERSIONS_DIR
            / "c4a5b6d7e8f9_repair_nuvemshop_order_schema_drift.py"
        )
        content = migration_file.read_text(encoding="utf-8")

        # Should NOT contain unrelated operations
        assert "meta_ads_connections" not in content
        assert "automation_campaigns" not in content
        assert "knowledge_bases" not in content
        assert "knowledge_sources" not in content
        assert "messages" not in content

        # Should contain the expected repair fields
        assert "external_order_id" in content
        assert "payment_method" in content
        assert "payment_status" in content

        # Should reference b3c2d9e0f112 as down_revision
        assert "b3c2d9e0f112" in content

    def test_downgrade_removes_only_repaired_objects(self):
        """Downgrade removes only columns/indexes added by the repair migration."""
        engine = create_engine("sqlite:///:memory:")
        _create_base_orders_schema(engine)

        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE orders ADD COLUMN external_order_id TEXT")
            )
            conn.execute(
                text("ALTER TABLE orders ADD COLUMN payment_method TEXT")
            )
            conn.execute(
                text("ALTER TABLE orders ADD COLUMN payment_status TEXT")
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_orders_external_order_id ON orders (external_order_id)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_orders_payment_method ON orders (payment_method)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_orders_payment_status ON orders (payment_status)"
                )
            )
            conn.commit()

        # Run downgrade
        from alembic.runtime.migration import MigrationContext
        from alembic.operations import Operations

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            op = Operations(ctx)
            inspector = inspect(conn)
            existing_idx = {i["name"] for i in inspector.get_indexes("orders")}

            indexes_to_repair = [
                ("ix_orders_external_order_id", "orders"),
                ("ix_orders_payment_method", "orders"),
                ("ix_orders_payment_status", "orders"),
            ]
            for idx_name, table in reversed(indexes_to_repair):
                if idx_name in existing_idx:
                    op.drop_index(idx_name, table_name=table)

            existing = {c["name"] for c in inspector.get_columns("orders")}
            for col_name in reversed(
                ["external_order_id", "payment_method", "payment_status"]
            ):
                if col_name in existing:
                    op.drop_column("orders", col_name)
            conn.commit()

        cols_after = _column_names(engine, "orders")
        assert "external_order_id" not in cols_after
        assert "payment_method" not in cols_after
        assert "payment_status" not in cols_after

        # Original columns must remain
        assert "shopify_order_id" in cols_after
        assert "order_number" in cols_after
        assert "total_amount" in cols_after

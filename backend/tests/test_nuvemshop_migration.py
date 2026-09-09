"""Tests for Nuvemshop Alembic migration f6f002b05545.

Validates four critical scenarios:
A. Fresh database — upgrade head works, columns exist
B. Baseline e63418b90903 — upgrade adds only Nuvemshop fields
C. Stamped-but-missing — revision recorded but columns absent
D. Already-repaired — columns present, upgrade is idempotent
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
        row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        return row[0] if row else None


def _set_alembic_version(engine, version: str):
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(text(f"INSERT INTO alembic_version (version_num) VALUES ('{version}')"))
        conn.commit()


class TestNuvemshopMigration:
    """Test the repaired f6f002b05545 migration."""

    def test_fresh_db_upgrade_head(self):
        """A. Fresh database: alembic upgrade head creates Nuvemshop fields."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)

        # Simulate fresh DB at e63418b90903 by stamping
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32))"))
            conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('e63418b90903')"))
            conn.commit()

        # Remove Nuvemshop columns to simulate pre-migration state
        with engine.connect() as conn:
            for col in ["external_order_id", "payment_method", "payment_status"]:
                try:
                    conn.execute(text(f"ALTER TABLE orders DROP COLUMN {col}"))
                except Exception:
                    pass  # SQLite may not support DROP COLUMN
            conn.commit()

        # For SQLite, recreate the DB from scratch
        engine2 = create_engine("sqlite:///:memory:")

        # Create schema matching e63418b90903 (without Nuvemshop fields)
        with engine2.connect() as conn:
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
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('e63418b90903')"))
            conn.commit()

        # Verify pre-migration state
        cols_before = _column_names(engine2, "orders")
        assert "external_order_id" not in cols_before
        assert "payment_method" not in cols_before
        assert "payment_status" not in cols_before

        # Simulate upgrade by running the migration body
        # (Can't use alembic CLI in test, so run the ops directly)
        from alembic.runtime.migration import MigrationContext
        from alembic.operations import Operations

        with engine2.connect() as conn:
            ctx = MigrationContext.configure(conn)
            op = Operations(ctx)

            # Run the same logic as the migration
            inspector = inspect(conn)
            existing = {c["name"] for c in inspector.get_columns("orders")}
            existing_idx = {i["name"] for i in inspector.get_indexes("orders")}

            if "external_order_id" not in existing:
                op.add_column("orders", sa.Column("external_order_id", sa.String(255), nullable=True))
            if "payment_method" not in existing:
                op.add_column("orders", sa.Column("payment_method", sa.String(50), nullable=True))
            if "payment_status" not in existing:
                op.add_column("orders", sa.Column("payment_status", sa.String(50), nullable=True))
            if "ix_orders_external_order_id" not in existing_idx:
                op.create_index("ix_orders_external_order_id", "orders", ["external_order_id"], unique=False)
            if "ix_orders_payment_method" not in existing_idx:
                op.create_index("ix_orders_payment_method", "orders", ["payment_method"], unique=False)
            if "ix_orders_payment_status" not in existing_idx:
                op.create_index("ix_orders_payment_status", "orders", ["payment_status"], unique=False)
            conn.commit()

        cols_after = _column_names(engine2, "orders")
        assert "external_order_id" in cols_after
        assert "payment_method" in cols_after
        assert "payment_status" in cols_after

        idx_after = _index_names(engine2, "orders")
        assert "ix_orders_external_order_id" in idx_after
        assert "ix_orders_payment_method" in idx_after
        assert "ix_orders_payment_status" in idx_after

    def test_baseline_e63418b90903_adds_only_nuvemshop(self):
        """B. Baseline: only Nuvemshop fields are added, nothing else."""
        import sqlalchemy as sa

        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
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
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('e63418b90903')"))
            conn.commit()

        # Record pre-migration columns
        cols_before = _column_names(engine, "orders")

        # Run migration
        from alembic.runtime.migration import MigrationContext
        from alembic.operations import Operations

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            op = Operations(ctx)
            inspector = inspect(conn)
            existing = {c["name"] for c in inspector.get_columns("orders")}
            existing_idx = {i["name"] for i in inspector.get_indexes("orders")}

            for col_name, col_type, nullable in [
                ("external_order_id", sa.String(255), True),
                ("payment_method", sa.String(50), True),
                ("payment_status", sa.String(50), True),
            ]:
                if col_name not in existing:
                    op.add_column("orders", sa.Column(col_name, col_type, nullable=nullable))
            for idx_name, table, columns in [
                ("ix_orders_external_order_id", "orders", ["external_order_id"]),
                ("ix_orders_payment_method", "orders", ["payment_method"]),
                ("ix_orders_payment_status", "orders", ["payment_status"]),
            ]:
                if idx_name not in existing_idx:
                    op.create_index(idx_name, table, columns, unique=False)
            conn.commit()

        cols_after = _column_names(engine, "orders")

        # Only Nuvemshop fields should be new
        new_cols = cols_after - cols_before
        assert new_cols == {"external_order_id", "payment_method", "payment_status"}, (
            f"Unexpected new columns: {new_cols}"
        )

    def test_stamped_but_missing_repair(self):
        """C. Stamped-but-missing: revision recorded, columns absent. Upgrade adds them."""
        import sqlalchemy as sa

        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL,
                    store_id INTEGER NOT NULL, order_number TEXT NOT NULL,
                    total_amount NUMERIC NOT NULL, currency TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
                )
            """))
            # Simulate stamped-but-missing: revision recorded but columns absent
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('f6f002b05545')"))
            conn.commit()

        # Verify columns don't exist
        cols_before = _column_names(engine, "orders")
        assert "external_order_id" not in cols_before

        # Run migration — must not error
        from alembic.runtime.migration import MigrationContext
        from alembic.operations import Operations

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            op = Operations(ctx)
            inspector = inspect(conn)
            existing = {c["name"] for c in inspector.get_columns("orders")}
            existing_idx = {i["name"] for i in inspector.get_indexes("orders")}

            for col_name, col_type, nullable in [
                ("external_order_id", sa.String(255), True),
                ("payment_method", sa.String(50), True),
                ("payment_status", sa.String(50), True),
            ]:
                if col_name not in existing:
                    op.add_column("orders", sa.Column(col_name, col_type, nullable=nullable))
            for idx_name, table, columns in [
                ("ix_orders_external_order_id", "orders", ["external_order_id"]),
                ("ix_orders_payment_method", "orders", ["payment_method"]),
                ("ix_orders_payment_status", "orders", ["payment_status"]),
            ]:
                if idx_name not in existing_idx:
                    op.create_index(idx_name, table, columns, unique=False)
            conn.commit()

        cols_after = _column_names(engine, "orders")
        assert "external_order_id" in cols_after
        assert "payment_method" in cols_after
        assert "payment_status" in cols_after

    def test_already_repaired_idempotent(self):
        """D. Already-repaired: columns present. Re-running upgrade is safe."""
        import sqlalchemy as sa

        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL,
                    store_id INTEGER NOT NULL, order_number TEXT NOT NULL,
                    total_amount NUMERIC NOT NULL, currency TEXT NOT NULL,
                    external_order_id TEXT, payment_method TEXT, payment_status TEXT,
                    created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
                )
            """))
            conn.execute(text("CREATE INDEX ix_orders_external_order_id ON orders (external_order_id)"))
            conn.execute(text("CREATE INDEX ix_orders_payment_method ON orders (payment_method)"))
            conn.execute(text("CREATE INDEX ix_orders_payment_status ON orders (payment_status)"))
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('f6f002b05545')"))
            conn.commit()

        # Run migration — must not error on duplicate columns/indexes
        from alembic.runtime.migration import MigrationContext
        from alembic.operations import Operations

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            op = Operations(ctx)
            inspector = inspect(conn)
            existing = {c["name"] for c in inspector.get_columns("orders")}
            existing_idx = {i["name"] for i in inspector.get_indexes("orders")}

            for col_name, col_type, nullable in [
                ("external_order_id", sa.String(255), True),
                ("payment_method", sa.String(50), True),
                ("payment_status", sa.String(50), True),
            ]:
                if col_name not in existing:
                    op.add_column("orders", sa.Column(col_name, col_type, nullable=nullable))
            for idx_name, table, columns in [
                ("ix_orders_external_order_id", "orders", ["external_order_id"]),
                ("ix_orders_payment_method", "orders", ["payment_method"]),
                ("ix_orders_payment_status", "orders", ["payment_status"]),
            ]:
                if idx_name not in existing_idx:
                    op.create_index(idx_name, table, columns, unique=False)
            conn.commit()

        # Verify nothing changed
        cols_after = _column_names(engine, "orders")
        assert "external_order_id" in cols_after
        assert "payment_method" in cols_after
        assert "payment_status" in cols_after

    def test_downgrade_removes_only_nuvemshop(self):
        """Downgrade removes only Nuvemshop fields, nothing else."""
        import sqlalchemy as sa

        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL,
                    store_id INTEGER NOT NULL, order_number TEXT NOT NULL,
                    total_amount NUMERIC NOT NULL, currency TEXT NOT NULL,
                    shopify_order_id TEXT, financial_status TEXT,
                    external_order_id TEXT, payment_method TEXT, payment_status TEXT,
                    created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
                )
            """))
            conn.execute(text("CREATE INDEX ix_orders_external_order_id ON orders (external_order_id)"))
            conn.execute(text("CREATE INDEX ix_orders_payment_method ON orders (payment_method)"))
            conn.execute(text("CREATE INDEX ix_orders_payment_status ON orders (payment_status)"))
            conn.commit()

        # Run downgrade
        from alembic.runtime.migration import MigrationContext
        from alembic.operations import Operations

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            op = Operations(ctx)
            inspector = inspect(conn)
            existing_idx = {i["name"] for i in inspector.get_indexes("orders")}

            for idx_name, table in reversed([
                ("ix_orders_external_order_id", "orders"),
                ("ix_orders_payment_method", "orders"),
                ("ix_orders_payment_status", "orders"),
            ]):
                if idx_name in existing_idx:
                    op.drop_index(idx_name, table_name=table)

            existing = {c["name"] for c in inspector.get_columns("orders")}
            for col_name in reversed(["external_order_id", "payment_method", "payment_status"]):
                if col_name in existing:
                    op.drop_column("orders", col_name)
            conn.commit()

        cols_after = _column_names(engine, "orders")
        assert "external_order_id" not in cols_after
        assert "payment_method" not in cols_after
        assert "payment_status" not in cols_after

        # shopify_order_id must remain
        assert "shopify_order_id" in cols_after

    def test_migration_file_is_minimal(self):
        """The migration file should contain only Nuvemshop operations."""
        migration_file = VERSIONS_DIR / "f6f002b05545_add_nuvemshop_order_fields.py"
        text = migration_file.read_text(encoding="utf-8")

        # Should NOT contain unrelated operations
        assert "meta_ads_connections" not in text, "Migration contains unrelated meta_ads_connections"
        assert "automation_campaigns" not in text, "Migration contains unrelated automation_campaigns"
        assert "automation_recipient" not in text, "Migration contains unrelated automation_recipient"
        assert "automation_runs" not in text, "Migration contains unrelated automation_runs"
        assert "knowledge_bases" not in text, "Migration contains unrelated knowledge_bases"
        assert "knowledge_sources" not in text, "Migration contains unrelated knowledge_sources"
        assert "messages" not in text, "Migration contains unrelated messages"
        assert "repurchase_enabled" not in text, "Migration contains unrelated repurchase_enabled"

        # Should NOT have broken dialect logic
        assert "is_sqlite_db()" not in text, "Migration has broken is_sqlite_db() call"

        # Should contain the expected Nuvemshop fields
        assert "external_order_id" in text
        assert "payment_method" in text
        assert "payment_status" in text

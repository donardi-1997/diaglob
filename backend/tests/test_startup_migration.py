"""Tests for application startup and migration safety.

Ensures:
1. Application startup does NOT call Base.metadata.create_all
2. Alembic config loads correctly
3. Alembic target_metadata contains all tables
4. Baseline revision exists and is no-op
"""
import ast
from pathlib import Path

import pytest


class TestStartupSafety:
    """Verify application startup does not mutate schema."""

    def test_main_import_does_not_call_create_all(self):
        """Importing app.main must not trigger Base.metadata.create_all."""
        source = Path(__file__).resolve().parent.parent / "app" / "main.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check for Base.metadata.create_all(...)
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "create_all"
                    and isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == "metadata"
                ):
                    pytest.fail(
                        "app.main still calls Base.metadata.create_all — "
                        "schema creation must be managed by Alembic"
                    )

    def test_lifespan_defined(self):
        """app.main must use modern FastAPI lifespan."""
        source = Path(__file__).resolve().parent.parent / "app" / "main.py"
        text = source.read_text(encoding="utf-8")

        assert "lifespan" in text
        assert "@asynccontextmanager" in text
        assert "on_event" not in text


class TestAlembicConfiguration:
    """Verify Alembic is properly configured."""

    def test_alembic_ini_exists(self):
        ini = Path(__file__).resolve().parent.parent / "alembic.ini"
        assert ini.exists(), "alembic.ini not found"

    def test_alembic_env_exists(self):
        env = Path(__file__).resolve().parent.parent / "alembic" / "env.py"
        assert env.exists(), "alembic/env.py not found"

    def test_versions_dir_exists(self):
        versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
        assert versions.exists(), "alembic/versions/ not found"

    def test_baseline_revision_exists(self):
        versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
        baseline = list(versions.glob("*initial_schema*"))
        assert len(baseline) >= 1, "Initial schema migration not found"

    def test_target_metadata_contains_tables(self):
        """Alembic target_metadata must see all application tables."""
        from app.db import Base
        from app import models  # noqa: F401

        tables = set(Base.metadata.tables.keys())
        assert "organizations" in tables
        assert "stores" in tables
        assert "users" in tables
        assert "conversations" in tables
        assert "messages" in tables
        assert "orders" in tables
        assert "products" in tables
        assert len(tables) >= 30, f"Expected 30+ tables, got {len(tables)}"

    def test_initial_schema_creates_tables(self):
        """Initial schema migration must contain create_table operations."""
        versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
        schema_files = list(versions.glob("*initial_schema*"))
        assert len(schema_files) >= 1, "Initial schema migration not found"

        text = schema_files[0].read_text(encoding="utf-8")
        assert "create_table" in text, "Initial schema must create tables"
        assert "organizations" in text, "Initial schema must create organizations table"


class TestCreateAllRemoved:
    """Verify create_all is not in application runtime paths."""

    def _has_create_all_call(self, filepath: Path) -> bool:
        """Check if a Python file contains an actual Base.metadata.create_all() call."""
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "create_all"
                    and isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == "metadata"
                ):
                    return True
        return False

    def test_no_create_all_in_main(self):
        source = Path(__file__).resolve().parent.parent / "app" / "main.py"
        assert not self._has_create_all_call(source), (
            "Base.metadata.create_all found in main.py"
        )

    def test_create_all_only_in_tests_and_seed(self):
        """create_all should only appear in test fixtures and seed.py."""
        app_dir = Path(__file__).resolve().parent.parent / "app"
        for py_file in app_dir.rglob("*.py"):
            if py_file.name == "__pycache__":
                continue
            if self._has_create_all_call(py_file):
                pytest.fail(
                    f"create_all found in application code: {py_file}"
                )

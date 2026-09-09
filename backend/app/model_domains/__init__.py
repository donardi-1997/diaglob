"""Domain-oriented import surfaces for SQLAlchemy models.

This package is an incremental migration boundary around the legacy
``app.models`` monolith. Consumers should prefer the narrow domain modules
below; physical model definitions can then be moved safely in later steps
without changing every caller at once.
"""

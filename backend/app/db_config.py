"""Database configuration sourced from the central runtime settings."""

from .settings import get_settings


DATABASE_URL = get_settings().database_url

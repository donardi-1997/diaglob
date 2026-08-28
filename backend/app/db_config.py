import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "diaglob.db"


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{DB_PATH.as_posix()}",
)

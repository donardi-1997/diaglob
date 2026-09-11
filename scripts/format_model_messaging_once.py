"""One-off formatting fix for the extracted Messaging domain."""
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "backend/app/model_domains/messaging.py"
text = path.read_text()
old = "from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint\n"
new = '''from sqlalchemy import (\n    DateTime,\n    ForeignKey,\n    Integer,\n    JSON,\n    String,\n    Text,\n    UniqueConstraint,\n)\n'''
if old not in text:
    raise SystemExit("messaging sqlalchemy import not found")
path.write_text(text.replace(old, new, 1))

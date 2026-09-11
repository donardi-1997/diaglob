"""One-off rewrite of app.models after physically extracting Knowledge models."""
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "backend/app/models.py"
text = PATH.read_text()

# These SQLAlchemy symbols were only needed by the Knowledge block / association table.
text = text.replace("    BigInteger,\n", "", 1)
text = text.replace("    Column,\n", "", 1)
text = text.replace("    Table,\n", "", 1)

# Add the Knowledge compatibility import immediately after the tenancy import block.
tenancy_end = ''')\n\n\n# ============================================================\n# ASSOCIATION TABLES\n# ============================================================\n'''
knowledge_import = ''')\nfrom .model_domains.knowledge import (  # noqa: F401\n    KnowledgeBase,\n    KnowledgeSource,\n    agent_knowledge_bases,\n)\n\n\n# ============================================================\n# ASSOCIATION TABLES\n# ============================================================\n'''
if tenancy_end not in text:
    raise SystemExit("tenancy import boundary not found")
text = text.replace(tenancy_end, knowledge_import, 1)

association_marker = '''# ============================================================\n# ASSOCIATION TABLES\n# ============================================================\n'''
tenancy_marker = '''# ============================================================\n# TENANCY DOMAIN (compatibility re-export)\n# ============================================================\n'''
association_start = text.index(association_marker)
tenancy_start = text.index(tenancy_marker, association_start)
text = (
    text[:association_start]
    + '''# ============================================================\n# ASSOCIATION TABLES\n# ============================================================\n\n# Tenant/store association tables live in app.model_domains.tenancy.\n# Agent/Knowledge association table lives in app.model_domains.knowledge.\n\n'''
    + text[tenancy_start:]
)

knowledge_base_marker = '''# ============================================================\n# KNOWLEDGE BASE\n# ============================================================\n'''
conversation_marker = '''# ============================================================\n# CONVERSATION\n# ============================================================\n'''
knowledge_start = text.index(knowledge_base_marker)
conversation_start = text.index(conversation_marker, knowledge_start)
text = (
    text[:knowledge_start]
    + '''# ============================================================\n# KNOWLEDGE DOMAIN (compatibility re-export)\n# ============================================================\n\n# KnowledgeBase, KnowledgeSource, and agent_knowledge_bases are physically\n# defined in app.model_domains.knowledge and imported near the top of this file.\n\n\n'''
    + text[conversation_start:]
)

PATH.write_text(text)

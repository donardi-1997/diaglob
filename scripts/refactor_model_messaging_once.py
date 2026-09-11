"""One-off rewrite of app.models after physically extracting Messaging models."""
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "backend/app/models.py"
text = PATH.read_text()

knowledge_import_end = '''from .model_domains.knowledge import (  # noqa: F401\n    KnowledgeBase,\n    KnowledgeSource,\n    agent_knowledge_bases,\n)\n'''
messaging_import = knowledge_import_end + '''from .model_domains.messaging import (  # noqa: F401\n    Conversation,\n    Message,\n    WhatsAppConnection,\n    WhatsAppMessageTemplate,\n)\n'''
if knowledge_import_end not in text:
    raise SystemExit("knowledge import block not found")
text = text.replace(knowledge_import_end, messaging_import, 1)

conversation_marker = '''# ============================================================\n# CONVERSATION\n# ============================================================\n'''
tenancy_user_marker = '''# ============================================================\n# TENANCY USER / MEMBERSHIP DOMAIN (compatibility re-export)\n# ============================================================\n'''
conversation_start = text.index(conversation_marker)
tenancy_user_start = text.index(tenancy_user_marker, conversation_start)
text = (
    text[:conversation_start]
    + '''# ============================================================\n# MESSAGING DOMAIN (compatibility re-export)\n# ============================================================\n\n# Conversation and Message are physically defined in app.model_domains.messaging\n# and imported near the top of this file.\n\n\n'''
    + text[tenancy_user_start:]
)

whatsapp_marker = '''# ============================================================\n# WHATSAPP CONNECTION\n# ============================================================\n'''
oauth_marker = '''# OAuth state models are physically defined in app.model_domains.oauth.\n'''
whatsapp_start = text.index(whatsapp_marker)
oauth_start = text.index(oauth_marker, whatsapp_start)
text = (
    text[:whatsapp_start]
    + '''# WhatsApp connection/template persistence models are physically defined in\n# app.model_domains.messaging and imported near the top of this file.\n\n\n'''
    + text[oauth_start:]
)

PATH.write_text(text)

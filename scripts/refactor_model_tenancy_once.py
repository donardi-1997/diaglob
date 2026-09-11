"""One-off rewrite of app.models after physically extracting tenancy models."""
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "backend/app/models.py"
text = PATH.read_text()

base_import = "from .db import Base\n"
tenancy_import = '''from .db import Base\nfrom .model_domains.tenancy import (  # noqa: F401\n    MembershipStore,\n    Organization,\n    OrganizationInvitation,\n    OrganizationMembership,\n    Store,\n    User,\n    agent_stores,\n    knowledge_base_stores,\n    organization_invitation_stores,\n)\n'''
if base_import not in text:
    raise SystemExit("Base import not found")
text = text.replace(base_import, tenancy_import, 1)

association_marker = '''# ============================================================\n# ASSOCIATION TABLES\n# ============================================================\n'''
organization_marker = '''# ============================================================\n# ORGANIZATION\n# ============================================================\n'''
association_start = text.index(association_marker)
organization_start = text.index(organization_marker, association_start)
agent_kb_start = text.index("agent_knowledge_bases = Table(", association_start, organization_start)
agent_kb_block = text[agent_kb_start:organization_start].rstrip() + "\n\n"
text = (
    text[:association_start]
    + association_marker
    + "\n# Tenant/store association tables are defined in app.model_domains.tenancy.\n"
    + agent_kb_block
    + text[organization_start:]
)

organization_start = text.index(organization_marker)
customer_marker = '''# ============================================================\n# CUSTOMER DOMAIN (compatibility re-export)\n# ============================================================\n'''
customer_start = text.index(customer_marker, organization_start)
text = (
    text[:organization_start]
    + '''# ============================================================\n# TENANCY DOMAIN (compatibility re-export)\n# ============================================================\n\n# Tenancy models are physically defined in app.model_domains.tenancy.\n# Imports near the top preserve the historical app.models import surface.\n\n\n'''
    + text[customer_start:]
)

user_marker = '''# ============================================================\n# USER\n# ============================================================\n'''
commerce_marker = "# Commerce integration models are physically defined in app.model_domains.commerce_integrations."
user_start = text.index(user_marker)
commerce_start = text.index(commerce_marker, user_start)
text = (
    text[:user_start]
    + '''# ============================================================\n# TENANCY USER / MEMBERSHIP DOMAIN (compatibility re-export)\n# ============================================================\n\n# User, invitation, membership, and membership-store models are physically\n# defined in app.model_domains.tenancy and imported near the top of this file.\n\n'''
    + text[commerce_start:]
)

PATH.write_text(text)

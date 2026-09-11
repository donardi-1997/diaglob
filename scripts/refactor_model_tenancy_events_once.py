"""One-off move of Store lifecycle listeners into the tenancy domain."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tenancy_path = ROOT / "backend/app/model_domains/tenancy.py"
models_path = ROOT / "backend/app/models.py"

tenancy = tenancy_path.read_text()
models = models_path.read_text()

old_import = "from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, UniqueConstraint\n"
new_import = '''from sqlalchemy import (\n    Boolean,\n    Column,\n    DateTime,\n    ForeignKey,\n    Integer,\n    String,\n    Table,\n    UniqueConstraint,\n    event,\n    inspect as sa_inspect,\n)\n'''
if old_import not in tenancy:
    raise SystemExit("tenancy sqlalchemy import not found")
tenancy = tenancy.replace(old_import, new_import, 1)

user_marker = '''# ============================================================\n# USER\n# ============================================================\n'''
listener_block = '''# ============================================================\n# STORE ACTIVITY TRACKING\n# ============================================================\n\n@event.listens_for(Store, "before_insert")\ndef _diaglob_store_active_since_insert(\n    mapper,\n    connection,\n    target,\n):\n    if target.active:\n        if target.active_since is None:\n            target.active_since = datetime.utcnow()\n    else:\n        target.active_since = None\n\n\n@event.listens_for(Store, "before_update")\ndef _diaglob_store_active_since_update(\n    mapper,\n    connection,\n    target,\n):\n    state = sa_inspect(target)\n    history = state.attrs.active.history\n\n    if not history.has_changes():\n        return\n\n    if target.active:\n        target.active_since = datetime.utcnow()\n    else:\n        target.active_since = None\n\n\n'''
if listener_block not in tenancy:
    if user_marker not in tenancy:
        raise SystemExit("tenancy user marker not found")
    tenancy = tenancy.replace(user_marker, listener_block + user_marker, 1)

tenancy_path.write_text(tenancy)

models = models.replace("from sqlalchemy import event\n", "", 1)
models = models.replace("from sqlalchemy import inspect as sa_inspect\n", "", 1)

activity_marker = '''# ============================================================\n# STORE ACTIVITY TRACKING\n# ============================================================\n'''
automations_marker = '''# ============================================================\n# AUTOMATIONS\n# ============================================================\n'''
activity_start = models.index(activity_marker)
automations_start = models.index(automations_marker, activity_start)
models = (
    models[:activity_start]
    + '''# Store activity listeners are physically defined with Store in\n# app.model_domains.tenancy.\n\n\n'''
    + models[automations_start:]
)
models_path.write_text(models)

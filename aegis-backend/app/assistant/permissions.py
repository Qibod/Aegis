"""
app/assistant/permissions.py
──────────────────────────────
Role-based permission checks for assistant tool calls.
"""
from fastapi import HTTPException
from app.models import User


def require_read(user: User) -> None:
    """All roles can read."""
    pass


def require_propose_change(user: User, entity_type: str) -> None:
    """Admin can propose any change. Auditor can only propose third-party changes."""
    if user.role in ("org_admin", "head_of_audit"):
        return
    if user.role == "auditor" and entity_type == "org_third_parties":
        return
    raise HTTPException(403, f"Role '{user.role}' cannot propose changes to {entity_type}")


def require_apply_change(user: User, entity_type: str) -> None:
    """Same rules as propose."""
    require_propose_change(user, entity_type)


def require_resolve_flagged(user: User) -> None:
    if user.role not in ("org_admin", "head_of_audit"):
        raise HTTPException(403, "Only admins can resolve flagged fields")


def require_approve_proposal(user: User) -> None:
    if user.role not in ("org_admin", "head_of_audit"):
        raise HTTPException(403, "Only admins can approve re-seed proposals")

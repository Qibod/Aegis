"""
app/validation/status_machine.py
──────────────────────────────────
Valid field_status values and transition helpers.
"""
from typing import Literal

FieldStatus = Literal[
    "seeded",
    "unknown",
    "user_edited",
    "verified",
    "disputed",
    "verified_after_dispute",
    "flagged_for_review",
    "unverifiable",
]

# Statuses that show a green tick in the UI
VERIFIED_STATUSES: set[str] = {"verified", "verified_after_dispute"}

# Statuses that trigger the resolution modal
DISPUTED_STATUSES: set[str] = {"flagged_for_review"}


def status_after_validator_a(verified: bool, verification_status: str) -> str:
    """Map Validator A result to a field_status."""
    if verification_status == "verified":
        return "verified"
    if verification_status == "disputed":
        return "disputed"
    return "unverifiable"


def status_after_validator_b(b_status: str) -> str:
    """Map Validator B result to a final field_status."""
    mapping = {
        "verified_after_dispute": "verified_after_dispute",
        "flagged_for_review":     "flagged_for_review",
        "verified_qa_pass":       "verified",
        "verified_qa_fail":       "disputed",
    }
    return mapping.get(b_status, "disputed")

"""app/assistant/tools — Claude tool definitions for the GRC Assistant."""

from app.assistant.tools.read_field import TOOL_DEF as read_field_def, handle as read_field
from app.assistant.tools.propose_change import TOOL_DEF as propose_change_def, handle as propose_change
from app.assistant.tools.apply_change import TOOL_DEF as apply_change_def, handle as apply_change
from app.assistant.tools.preview_propagation import TOOL_DEF as preview_propagation_def, handle as preview_propagation
from app.assistant.tools.request_revalidation import TOOL_DEF as request_revalidation_def, handle as request_revalidation
from app.assistant.tools.list_unverified import TOOL_DEF as list_unverified_def, handle as list_unverified
from app.assistant.tools.search_history import TOOL_DEF as search_history_def, handle as search_history

ALL_TOOL_DEFS = [
    read_field_def,
    propose_change_def,
    apply_change_def,
    preview_propagation_def,
    request_revalidation_def,
    list_unverified_def,
    search_history_def,
]

TOOL_HANDLERS = {
    "get_profile_field":       read_field,
    "propose_profile_change":  propose_change,
    "apply_proposed_change":   apply_change,
    "preview_propagation":     preview_propagation,
    "request_revalidation":    request_revalidation,
    "list_unverified_fields":  list_unverified,
    "search_change_history":   search_history,
}

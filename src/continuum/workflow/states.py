"""
Episode reasons (why flagged) and status lifecycle (detected -> contacted -> promised -> returned/unreachable/opted_out).
"""

from __future__ import annotations
from enum import Enum
from typing import Dict, Set


class EpisodeReason(str, Enum):
    """Why the patient was flagged for outreach."""
    FOLLOWUP_OVERDUE = "FOLLOWUP_OVERDUE"
    REFILL_GAP = "REFILL_GAP"
    COMBINED = "COMBINED"


class EpisodeStatus(str, Enum):
    """Workflow state of the care continuum episode."""
    DETECTED = "detected"
    CONTACTED = "contacted"
    PROMISED = "promised"
    RETURNED = "returned"
    UNREACHABLE = "unreachable"
    OPTED_OUT = "opted_out"


# Valid FSM transitions
VALID_TRANSITIONS: Dict[str, Set[str]] = {
    EpisodeStatus.DETECTED.value: {
        EpisodeStatus.CONTACTED.value,
        EpisodeStatus.PROMISED.value,
        EpisodeStatus.RETURNED.value,
        EpisodeStatus.UNREACHABLE.value,
        EpisodeStatus.OPTED_OUT.value
    },
    EpisodeStatus.CONTACTED.value: {
        EpisodeStatus.PROMISED.value,
        EpisodeStatus.RETURNED.value,
        EpisodeStatus.UNREACHABLE.value,
        EpisodeStatus.OPTED_OUT.value,
        EpisodeStatus.CONTACTED.value  # repeated contact attempt
    },
    EpisodeStatus.PROMISED.value: {
        EpisodeStatus.RETURNED.value,
        EpisodeStatus.CONTACTED.value,
        EpisodeStatus.UNREACHABLE.value,
        EpisodeStatus.OPTED_OUT.value
    },
    EpisodeStatus.UNREACHABLE.value: {
        EpisodeStatus.CONTACTED.value,
        EpisodeStatus.RETURNED.value,
        EpisodeStatus.OPTED_OUT.value
    },
    EpisodeStatus.RETURNED.value: {
        EpisodeStatus.DETECTED.value   # re-flagged on subsequent overdue cycle
    },
    EpisodeStatus.OPTED_OUT.value: {
        EpisodeStatus.DETECTED.value   # re-subscribed
    }
}


def is_valid_transition(current_status: str, next_status: str) -> bool:
    if current_status == next_status:
        return True
    allowed = VALID_TRANSITIONS.get(current_status, set())
    return next_status in allowed

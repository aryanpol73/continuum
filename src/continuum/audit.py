"""
Audit logging facility for Continuum.
All modifications, clinical evaluations, episode transitions, and outreach actions MUST be logged.
"""

from __future__ import annotations
import json
from datetime import datetime
from typing import Any, Dict, Optional, Union
from sqlalchemy.orm import Session
from src.continuum.models import AuditLog


def log_action(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: Union[str, int],
    user: str = "system",
    details: Optional[Dict[str, Any]] = None,
    commit: bool = True
) -> AuditLog:
    """
    Creates an immutable audit log record.
    """
    details_str = json.dumps(details, default=str) if details else None
    
    log_entry = AuditLog(
        timestamp=datetime.utcnow(),
        user_or_system=user,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details_json=details_str
    )
    
    db.add(log_entry)
    if commit:
        try:
            db.commit()
            db.refresh(log_entry)
        except Exception:
            db.rollback()
            raise

    return log_entry

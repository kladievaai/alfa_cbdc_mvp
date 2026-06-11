"""Журнал аудита."""
from sqlalchemy.orm import Session
from ..models import AuditLogEntry


def log(db: Session, *, actor: str, action: str, entity: str,
        entity_id: int | None = None, details: dict | None = None) -> AuditLogEntry:
    entry = AuditLogEntry(
        actor=actor, action=action, entity=entity,
        entity_id=entity_id, details=details or {},
    )
    db.add(entry)
    db.flush()
    return entry

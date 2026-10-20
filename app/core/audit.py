import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.modules.identity.models import AuditLog


def record_audit(
    session: Session,
    actor_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    before: object = None,
    after: object = None,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_json=_safe(before),
            after_json=_safe(after),
            created_at=utc_now(),
        )
    )


def _safe(value: object):
    if value is None:
        return None
    return json.loads(json.dumps(value, default=str))

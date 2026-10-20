from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.database import get_engine
from app.modules.identity.access import assign_role
from app.modules.identity.models import User, UserRole

PASSWORD = "password123"


def unique_email() -> str:
    return f"user-{uuid4()}@example.com"


def register(client, full_name: str = "Test User") -> tuple[str, dict, dict]:
    email = unique_email()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": full_name},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return email, {"Authorization": f"Bearer {body['access_token']}"}, body


def set_only_role(email: str, role_name: str) -> None:
    with Session(get_engine()) as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        session.execute(delete(UserRole).where(UserRole.user_id == user.id))
        session.flush()
        assign_role(session, user.id, role_name)
        session.commit()


def as_role(client, role_name: str) -> tuple[str, dict]:
    email, headers, _body = register(client)
    set_only_role(email, role_name)
    return email, headers


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def future(days: int = 2) -> str:
    return iso(datetime.now(UTC) + timedelta(days=days))


def past(days: int = 2) -> str:
    return iso(datetime.now(UTC) - timedelta(days=days))


def money(value: str) -> Decimal:
    return Decimal(value)

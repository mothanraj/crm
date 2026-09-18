from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.lead_service import validate_assignee


def test_validate_assignee_requires_active_employee():
    emp = SimpleNamespace(id=uuid4(), is_active=True, role=SimpleNamespace(name="EMPLOYEE"))
    assert validate_assignee(emp) is emp


@pytest.mark.parametrize("role", ["MANAGER", "ADMIN", None])
def test_validate_assignee_rejects_non_employees(role):
    emp = SimpleNamespace(id=uuid4(), is_active=True, role=SimpleNamespace(name=role) if role else None)
    with pytest.raises(ValueError, match="employees"):
        validate_assignee(emp)


def test_validate_assignee_rejects_inactive():
    emp = SimpleNamespace(id=uuid4(), is_active=False, role=SimpleNamespace(name="EMPLOYEE"))
    with pytest.raises(ValueError, match="inactive"):
        validate_assignee(emp)


def test_validate_assignee_rejects_missing():
    with pytest.raises(ValueError, match="not found"):
        validate_assignee(None)

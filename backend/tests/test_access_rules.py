"""Aturan kombinasi peran (Keputusan desain: peran ganda)."""
import pytest

from app.models import Role
from app.services.access_rules import RoleCombinationError, validate_role_combination


@pytest.mark.parametrize("roles", [
    {Role.PIC_KLIEN},
    {Role.INTAKE_SUPPORT, Role.FINANCE_REVIEWER},
    {Role.SERVICE_LEAD, Role.FINANCE_REVIEWER},
    {Role.SYSTEM_ADMIN, Role.SERVICE_LEAD},
])
def test_allowed_combinations(roles):
    validate_role_combination(roles)


@pytest.mark.parametrize("roles, message", [
    (set(), "minimal satu"),
    ({Role.PIC_KLIEN, Role.INTAKE_SUPPORT}, "PIC Klien"),
    ({Role.PIC_KLIEN, Role.SYSTEM_ADMIN}, "PIC Klien"),
    ({Role.SYSTEM_ADMIN, Role.FINANCE_REVIEWER}, "System Admin"),
])
def test_forbidden_combinations(roles, message):
    with pytest.raises(RoleCombinationError, match=message):
        validate_role_combination(roles)

"""Fixtures comunes.

`_owner_access_by_default`: las suites de API anteriores a la matriz de roles
(auditoría 23-nov, #10/#11) no prueban permisos y no tienen BD. Para ellas el
usuario es owner de cualquier org; las pruebas de roles (test_api_v2_roles.py,
test_orgs_access.py) inyectan su propio OrgAccess con el rol que prueban.
"""
import pytest

import src.orgs.access as access_module


class _OwnerEverywhere:
    def role_of(self, *, org_id, user_id):
        return "owner"

    def org_of(self, *, resource, resource_id):
        return None


@pytest.fixture(autouse=True)
def _owner_access_by_default(monkeypatch):
    monkeypatch.setattr(access_module, "_access_factory",
                        lambda: access_module.OrgAccess(_OwnerEverywhere()))

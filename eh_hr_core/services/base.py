# -*- coding: utf-8 -*-
"""Service base class and tiny service registry.

Services are plain Python classes - NOT odoo.models.Model.  They are
constructed with a reference to an active env (which carries the transaction)
and any dependencies they need.

This inverts the Odoo-default habit of placing business logic on the model
class.  Models in the EH HR Platform stay thin: they store data and enforce
constraints; services do the work.

Why?

    * Services compose freely (compute → policy → tz) without polluting the
      ORM with cross-cutting concerns.
    * Services can be unit-tested with mocks - no database fixture needed
      for every variant.
    * The same service serves a JSON-RPC endpoint, a cron, an import wizard,
      and a model trigger without those four call sites diverging.

Usage::

    from odoo.addons.eh_hr_core.services import locate_service
    svc = locate_service('eh.hr.attendance.compute', env=env)
    result = svc.compute_day(employee, date)
"""
from typing import Callable, Dict


_REGISTRY: Dict[str, Callable] = {}


def register_service(code: str):
    """Decorator: register a service class under a string code.

    Example::

        @register_service('eh.hr.policy.engine')
        class PolicyEngineService(HrService):
            ...
    """
    def decorator(cls):
        if code in _REGISTRY:
            raise RuntimeError(f'Service {code} already registered')
        _REGISTRY[code] = cls
        cls._service_code = code
        return cls
    return decorator


def locate_service(code: str, env):
    """Resolve a registered service code to an instance bound to ``env``."""
    if code not in _REGISTRY:
        raise KeyError(f'No service registered under code {code!r}')
    return _REGISTRY[code](env)


class HrService:
    """Base class for all platform services.

    The base class intentionally provides almost nothing - services are
    plain Python.  Conventions enforced:

        * Every service has an ``env`` attribute (Odoo env).
        * Every service exposes a ``_service_code`` class attribute (set by
          the @register_service decorator) so the registry can self-describe.
        * Constructors accept ``env`` and optional injected dependencies;
          omitted dependencies are resolved through :py:func:`locate_service`.
    """

    _service_code: str = ''

    def __init__(self, env):
        self.env = env

    def locate(self, code):
        return locate_service(code, self.env)

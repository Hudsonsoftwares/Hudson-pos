# -*- coding: utf-8 -*-
"""Service-level audit emission.

Thin wrapper over ``eh.hr.audit.log.write_event`` for use in services that
don't carry a recordset.
"""
from .base import HrService, register_service


@register_service('eh.hr.audit.service')
class AuditService(HrService):

    def emit(self, model, record_id, action, payload=None, actor=None):
        actor = actor or self.env.user
        self.env['eh.hr.audit.log'].sudo().write_event(
            model=model, record_id=record_id, action=action,
            actor=actor, payload=payload or {},
        )

# -*- coding: utf-8 -*-
"""eh.hr.platform.mixin - base for every record in the EH HR Platform.

The platform mixin gives a record:
    * a canonical ``correlation_id`` for tracing across services / audit / RPC,
    * a uniform :py:meth:`emit_platform_event` helper that publishes a typed
      event on ``bus.bus`` and writes a row to the audit log,
    * a hook that other modules may extend (``_platform_subjects``) to declare
      additional employees / users that should be considered "interested
      parties" for permission and notification purposes.

The mixin is deliberately lean: it does NOT touch state machines, approvals
or policies - those concerns belong to their respective engines.
"""
import uuid
from odoo import api, fields, models


class HrPlatformMixin(models.AbstractModel):
    _name = 'eh.hr.platform.mixin'
    _description = 'EH HR Platform - base mixin'

    correlation_id = fields.Char(
        string='Correlation ID',
        copy=False,
        index=True,
        readonly=True,
        help='Stable identifier used for tracing across services, audit log, '
             'webhooks, and outbound events. Auto-generated on create.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('correlation_id', uuid.uuid4().hex)
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Hooks (override in concrete models)
    # ------------------------------------------------------------------
    def _platform_subjects(self):
        """Return a set of res.users records considered "subjects" of self.

        Used by permission checks and notification fan-out.  Default
        implementation returns an empty recordset.
        """
        return self.env['res.users']

    def emit_platform_event(self, topic, payload=None):
        """Publish a structured platform event.

        :param topic: dotted topic name, e.g. ``"attendance.day.updated"``.
        :param payload: JSON-serialisable dict.  Augmented with
            ``record_id``, ``model`` and ``correlation_id`` before send.
        """
        self.ensure_one()
        payload = dict(payload or {})
        payload.update({
            'model': self._name,
            'record_id': self.id,
            'correlation_id': self.correlation_id,
        })
        # In-process bus - replace with queue/Kafka adapter for clustered deploys.
        self.env['bus.bus']._sendone(
            self.env.company,
            f'hr.events.{topic}',
            payload,
        )
        # Cross-emit to the audit log so the platform event is replay-able.
        company = self.company_id if 'company_id' in self._fields \
            and self.company_id else self.env.company
        self.env['eh.hr.audit.log'].sudo().write_event(
            model=self._name,
            record_id=self.id,
            action=f'event:{topic}',
            actor=self.env.user,
            payload=payload,
            company_id=company.id,
        )

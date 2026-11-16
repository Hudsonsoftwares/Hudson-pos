# -*- coding: utf-8 -*-
"""Expose a few HR-platform-wide knobs through res.config.settings.

Per-company values delegated to ``eh.hr.settings.entry``.  This view is just
sugar so HR officers don't have to touch the underlying key/value table.
"""
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hr_audit_retention_days = fields.Integer(
        string='Audit log retention (days)', default=730,
        config_parameter='eh_hr_core.audit_retention_days',
    )
    hr_pii_redact_in_exports = fields.Boolean(
        string='Redact PII in exports', default=True,
        config_parameter='eh_hr_core.pii_redact_in_exports',
    )

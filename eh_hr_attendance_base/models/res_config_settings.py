# -*- encoding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    eh_hr_consent_validity_months = fields.Integer(
        related='company_id.eh_hr_consent_validity_months',
        readonly=False,
    )
    eh_hr_consent_retention_months = fields.Integer(
        related='company_id.eh_hr_consent_retention_months',
        readonly=False,
    )
    eh_hr_audit_retention_months = fields.Integer(
        related='company_id.eh_hr_audit_retention_months',
        readonly=False,
    )
    eh_hr_consent_text_face = fields.Text(
        related='company_id.eh_hr_consent_text_face',
        readonly=False,
    )
    eh_hr_match_threshold = fields.Float(
        related='company_id.eh_hr_match_threshold',
        readonly=False,
    )
    eh_hr_kiosk_idle_seconds = fields.Integer(
        related='company_id.eh_hr_kiosk_idle_seconds',
        readonly=False,
    )

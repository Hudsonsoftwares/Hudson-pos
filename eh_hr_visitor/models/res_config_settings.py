# -*- encoding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    eh_hr_visitor_nda_text = fields.Text(
        related='company_id.eh_hr_visitor_nda_text',
        readonly=False,
    )
    eh_hr_visitor_visitor_agreement_text = fields.Text(
        related='company_id.eh_hr_visitor_visitor_agreement_text',
        readonly=False,
    )
    eh_hr_visitor_safety_declaration_text = fields.Text(
        related='company_id.eh_hr_visitor_safety_declaration_text',
        readonly=False,
    )
    eh_hr_visitor_privacy_consent_text = fields.Text(
        related='company_id.eh_hr_visitor_privacy_consent_text',
        readonly=False,
    )
    eh_hr_visitor_auto_checkout_enabled = fields.Boolean(
        related='company_id.eh_hr_visitor_auto_checkout_enabled',
        readonly=False,
    )
    eh_hr_visitor_auto_checkout_hour = fields.Integer(
        related='company_id.eh_hr_visitor_auto_checkout_hour',
        readonly=False,
    )
    eh_hr_visitor_retention_days = fields.Integer(
        related='company_id.eh_hr_visitor_retention_days',
        readonly=False,
    )
    eh_hr_visitor_photo_consent_text = fields.Text(
        related='company_id.eh_hr_visitor_photo_consent_text',
        readonly=False,
    )

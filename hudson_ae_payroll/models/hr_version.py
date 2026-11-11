# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrVersion(models.Model):
    """
    UAE Salary Configuration Extension.
    Adds UAE-specific allowances (Airfare Allowance) and aligns salary breakdown calculation
    for UAE contracts and templates.
    """
    _inherit = 'hr.version'

    airfare_allowance = fields.Monetary(
        string="Airfare Allowance",
        tracking=True,
        help="Monthly recurring airfare allowance component for UAE contracts and templates."
    )
    airfare_allowance_percent = fields.Float(
        string="Airfare %",
        compute='_compute_airfare_percent',
        digits=(16, 2),
        help="Percentage of Airfare Allowance against Total Salary (wage)."
    )

    @api.depends('wage', 'airfare_allowance')
    def _compute_airfare_percent(self):
        for rec in self:
            total = rec.wage or 0.0
            if total > 0.0:
                rec.airfare_allowance_percent = ((rec.airfare_allowance or 0.0) / total) * 100.0
            else:
                rec.airfare_allowance_percent = 0.0

    @api.depends('airfare_allowance')
    def _compute_breakdown_totals(self):
        super()._compute_breakdown_totals()
        for rec in self:
            if rec.is_uae_localization and rec.airfare_allowance:
                total_sum = rec.breakdown_total + (rec.airfare_allowance or 0.0)
                rec.breakdown_total = total_sum
                rec.breakdown_diff = total_sum - (rec.wage or 0.0)
                rec.breakdown_is_equal = abs(rec.breakdown_diff) < 0.01

    @api.model
    def _get_whitelist_fields_from_template(self):
        res = super()._get_whitelist_fields_from_template()
        if 'airfare_allowance' not in res:
            res.append('airfare_allowance')
        return res

    @api.onchange('contract_template_id')
    def _onchange_contract_template_id(self):
        super()._onchange_contract_template_id()
        if self.contract_template_id and hasattr(self.contract_template_id, 'airfare_allowance'):
            self.airfare_allowance = self.contract_template_id.airfare_allowance

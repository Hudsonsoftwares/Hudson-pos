# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    quality_alert_todo = fields.Boolean(
        string='Quality Alert Pending',
        compute='_compute_quality_alert_todo',
    )
    quality_check_todo = fields.Boolean(
        string='Quality Check Pending',
        compute='_compute_quality_check_todo',
    )

    def _compute_quality_alert_todo(self):
        for prod in self:
            if 'quality.check' in self.env:
                prod.quality_alert_todo = any(
                    check.quality_state == 'fail' for check in getattr(prod, 'quality_check_ids', [])
                )
            else:
                prod.quality_alert_todo = False

    def _compute_quality_check_todo(self):
        for prod in self:
            if 'quality.check' in self.env:
                prod.quality_check_todo = any(
                    check.quality_state == 'none' for check in getattr(prod, 'quality_check_ids', [])
                )
            else:
                prod.quality_check_todo = False

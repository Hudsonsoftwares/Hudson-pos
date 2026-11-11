# -*- coding: utf-8 -*-
from odoo import api, fields, models

class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    def _compute_rule(self, localdict):
        amount, rate, qty = super()._compute_rule(localdict)
        return amount, rate, qty

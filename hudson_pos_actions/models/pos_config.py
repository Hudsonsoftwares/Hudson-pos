# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, models, _


class PosConfig(models.Model):
    _inherit = 'pos.config'

    def _compute_selection_pay_after(self):
        """Remove Odoo Enterprise lock from 'Each Order' so customers can pay after each order at table."""
        return [("meal", _("Meal")), ("each", _("Each Order"))]

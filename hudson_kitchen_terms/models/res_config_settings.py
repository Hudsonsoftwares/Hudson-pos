# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kitchen_mode = fields.Boolean(
        string="Use restaurant/kitchen terminology",
        related='company_id.kitchen_mode',
        readonly=False,
        help="When enabled, manufacturing terminology will be displayed using restaurant/kitchen terms."
    )
    kitchen_task = fields.Boolean(
        string="Kitchen Tasks",
        compute='_compute_kitchen_task',
        inverse='_inverse_kitchen_task',
        help="When enabled, work orders / kitchen tasks and kitchen labels are available in Manufacturing."
    )

    @api.depends('group_mrp_routings')
    def _compute_kitchen_task(self):
        for record in self:
            record.kitchen_task = bool(record.group_mrp_routings)

    def _inverse_kitchen_task(self):
        for record in self:
            record.group_mrp_routings = bool(record.kitchen_task)

    def set_values(self):
        super().set_values()
        if self.kitchen_mode and self.company_id:
            self.env['kitchen.label']._ensure_company_labels(self.company_id)
        self.env['kitchen.label']._invalidate_terminology_caches()

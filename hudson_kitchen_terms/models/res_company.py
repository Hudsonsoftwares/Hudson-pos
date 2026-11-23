# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    kitchen_mode = fields.Boolean(
        string="Kitchen Mode",
        default=False,
        help="When enabled, manufacturing terminology will be displayed using restaurant/kitchen terms."
    )
    kitchen_task = fields.Boolean(
        string="Kitchen Tasks",
        compute='_compute_kitchen_task',
        inverse='_inverse_kitchen_task',
        help="When enabled, work orders / kitchen tasks and kitchen labels are available in Manufacturing."
    )

    def _compute_kitchen_task(self):
        routing_group = self.env.ref('mrp.group_mrp_routings', raise_if_not_found=False)
        group_user = self.env.ref('base.group_user', raise_if_not_found=False)
        is_enabled = bool(routing_group and group_user and routing_group in group_user.all_implied_ids)
        for record in self:
            record.kitchen_task = is_enabled

    def _inverse_kitchen_task(self):
        routing_group = self.env.ref('mrp.group_mrp_routings', raise_if_not_found=False)
        group_user = self.env.ref('base.group_user', raise_if_not_found=False)
        if routing_group and group_user:
            for record in self:
                if record.kitchen_task:
                    group_user._apply_group(routing_group)
                else:
                    group_user._remove_group(routing_group)
        self.env['kitchen.label']._invalidate_terminology_caches()

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        enabled = companies.filtered('kitchen_mode')
        if enabled:
            self.env['kitchen.label']._ensure_company_labels(enabled)
        return companies

    def write(self, vals):
        res = super().write(vals)
        if vals.get('kitchen_mode'):
            self.env['kitchen.label']._ensure_company_labels(self.filtered('kitchen_mode'))
        self.env['kitchen.label']._invalidate_terminology_caches()
        return res

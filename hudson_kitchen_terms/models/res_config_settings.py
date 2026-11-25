# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .kitchen_trace import kitchen_trace


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

    # --- diagnostics: Settings screen (Manufacturing > Configuration > Settings)
    @api.model
    def get_views(self, views, options=None):
        kitchen_trace(self.env, 'settings get_views', company=self.env.company)
        try:
            return super().get_views(views, options=options)
        except Exception:
            kitchen_trace(self.env, 'settings get_views FAILED', level='ERROR', company=self.env.company, exc=True)
            raise

    def onchange(self, values, field_names, fields_spec):
        try:
            return super().onchange(values, field_names, fields_spec)
        except Exception:
            kitchen_trace(self.env, 'settings onchange FAILED', level='ERROR', company=self.env.company,
                          field_names=field_names, exc=True)
            raise

    def execute(self):
        kitchen_trace(self.env, 'settings save', company=self.company_id,
                      new_kitchen_mode=self.kitchen_mode, new_kitchen_task=self.kitchen_task)
        try:
            return super().execute()
        except Exception:
            kitchen_trace(self.env, 'settings save FAILED', level='ERROR', company=self.company_id, exc=True)
            raise

    def set_values(self):
        super().set_values()
        if self.kitchen_mode and self.company_id:
            self.env['kitchen.label']._ensure_company_labels(self.company_id)
        self.env['kitchen.label']._invalidate_terminology_caches()

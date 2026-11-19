# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class MrpRoutingWorkcenter(models.Model):
    _inherit = 'mrp.routing.workcenter'

    quality_point_ids = fields.One2many(
        'mrp.routing.workcenter.step',
        'workorder_operation_id',
        string='Instructions / Quality Points',
        copy=True,
    )
    # Backward-compatible alias so existing views/client caches requesting step_ids never fail:
    step_ids = fields.One2many(
        'mrp.routing.workcenter.step',
        'workorder_operation_id',
        string='Operation Steps',
        copy=True,
    )
    quality_point_count = fields.Integer(
        string='Quality Points Count',
        compute='_compute_quality_point_count',
    )

    @api.depends('quality_point_ids')
    def _compute_quality_point_count(self):
        for op in self:
            op.quality_point_count = len(op.quality_point_ids)

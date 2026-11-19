# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    quality_point_ids = fields.One2many(
        'mrp.routing.workcenter.step',
        related='operation_id.quality_point_ids',
        string='Instructions / Quality Points',
        readonly=True,
    )
    step_ids = fields.One2many(
        'mrp.routing.workcenter.step',
        related='operation_id.quality_point_ids',
        string='Operation Steps',
        readonly=True,
    )

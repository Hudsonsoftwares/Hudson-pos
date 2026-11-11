# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import _, api, fields, models
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    quality_check_ids = fields.One2many('quality.check', 'workorder_id', string='Quality Checks')
    quality_check_count = fields.Integer(compute='_compute_quality_check_count')

    @api.depends('quality_check_ids.quality_state')
    def _compute_quality_check_count(self):
        for wo in self:
            wo.quality_check_count = len(wo.quality_check_ids)

    def button_start(self, raise_on_invalid_state=False):
        res = super().button_start(raise_on_invalid_state=raise_on_invalid_state)
        for wo in self:
            wo._generate_quality_checks()
        return res

    def _generate_quality_checks(self):
        self.ensure_one()
        if self.quality_check_ids:
            return self.env['quality.check']
        operation = self.operation_id
        if not operation:
            return self.env['quality.check']
        points = self.env['quality.point']._get_matching_points(
            company=self.production_id.company_id,
            products=self.product_id,
            is_manufacturing=True,
            workorder_operation=operation,
        )
        points = points.filtered(lambda p: p.workorder_operation_id == operation)
        common_vals = {
            'production_id': self.production_id.id,
            'workorder_id': self.id,
            'company_id': self.production_id.company_id.id,
        }
        return self.env['quality.check']._create_checks_from_points(
            points, common_vals, products=self.product_id)

    def button_finish(self):
        pending = self.quality_check_ids.filtered(lambda c: c.quality_state == 'none')
        if pending:
            raise UserError(_(
                'You must complete all Quality Checks for this Work Order '
                'before finishing it:\n%s'
            ) % '\n'.join('- %s' % c.name for c in pending))
        return super().button_finish()

    def action_view_quality_checks(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'Quality.action_quality_check')
        action['domain'] = [('workorder_id', '=', self.id)]
        action['context'] = {'default_workorder_id': self.id}
        return action

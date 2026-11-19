# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class MrpRoutingWorkcenterStep(models.Model):
    _name = 'mrp.routing.workcenter.step'
    _description = 'BoM Operation Instruction / Quality Step'
    _order = 'sequence, id'

    name = fields.Char(string='Reference', default=lambda self: _('New'), copy=False, readonly=True)
    title = fields.Char(string='Title', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)
    applies_to_manufacturing = fields.Boolean(string='Applies to Manufacturing', default=True)

    workorder_operation_id = fields.Many2one(
        'mrp.routing.workcenter',
        string='Work Order Operation',
        ondelete='cascade',
        required=True,
        index=True,
    )
    operation_id = fields.Many2one(
        'mrp.routing.workcenter',
        string='Operation',
        related='workorder_operation_id',
        readonly=False,
        store=True,
    )
    bom_id = fields.Many2one(
        'mrp.bom',
        string='Bill of Materials',
        related='workorder_operation_id.bom_id',
        store=True,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    test_type = fields.Selection(
        selection=[
            ('instructions', 'Instructions'),
            ('picture', 'Take a Picture'),
            ('consumed_materials', 'Register Consumed Materials'),
            ('production', 'Register Production'),
            ('byproducts', 'Register By-products'),
            ('print_product_label', 'Print Product Label'),
            ('print_lot_label', 'Print Lot/SN Label'),
            ('passfail', 'Pass - Fail'),
            ('measure', 'Measure'),
            ('spreadsheet', 'Spreadsheet'),
        ],
        string='Type',
        default='instructions',
        required=True,
    )

    instructions = fields.Html(string='Instructions')
    notes = fields.Text(string='Notes')

    # Measurement parameters
    norm = fields.Float(string='Norm')
    norm_unit = fields.Char(string='Unit', default='mm')
    tolerance_min = fields.Float(string='Tolerance Min')
    tolerance_max = fields.Float(string='Tolerance Max')
    failure_message = fields.Text(string='Message If Failure')

    # Attachments
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')

    # Bridge to Quality Control Point (quality.point)
    quality_point_id = fields.Integer(string='Linked Quality Point ID', index=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('mrp.routing.workcenter.step') or _('New')
            if vals.get('operation_id') and not vals.get('workorder_operation_id'):
                vals['workorder_operation_id'] = vals['operation_id']

        records = super().create(vals_list)

        # Synchronize with quality.point if Quality module is installed in this database
        if 'quality.point' in self.env:
            for rec in records:
                if not rec.quality_point_id:
                    rec._sync_create_quality_point()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'quality.point' in self.env:
            for rec in self:
                rec._sync_write_quality_point()
        return res

    def unlink(self):
        if 'quality.point' in self.env:
            for rec in self:
                if rec.quality_point_id:
                    qp = self.env['quality.point'].sudo().browse(rec.quality_point_id)
                    if qp.exists():
                        qp.unlink()
        return super().unlink()

    def _sync_create_quality_point(self):
        self.ensure_one()
        try:
            QP = self.env['quality.point'].sudo()
            target_type = self.test_type if self.test_type in dict(QP._fields['test_type'].selection) else 'instructions'
            vals = {
                'title': self.title,
                'sequence': self.sequence,
                'test_type': target_type,
                'instructions': self.instructions or '',
                'workorder_operation_id': self.workorder_operation_id.id,
                'applies_to_manufacturing': True,
                'company_id': self.company_id.id if self.company_id else self.env.company.id,
            }
            if hasattr(QP, 'notes') and self.notes:
                vals['notes'] = self.notes
            if hasattr(QP, 'norm'):
                vals['norm'] = self.norm
                vals['norm_unit'] = self.norm_unit
                vals['tolerance_min'] = self.tolerance_min
                vals['tolerance_max'] = self.tolerance_max
            if hasattr(QP, 'failure_message') and self.failure_message:
                vals['failure_message'] = self.failure_message
            qp = QP.create(vals)
            self.sudo().write({'quality_point_id': qp.id, 'name': qp.name})
        except Exception as e:
            _logger.warning("Could not sync quality.point for step %s: %s", self.id, e)

    def _sync_write_quality_point(self):
        self.ensure_one()
        if not self.quality_point_id:
            self._sync_create_quality_point()
            return
        try:
            qp = self.env['quality.point'].sudo().browse(self.quality_point_id)
            if not qp.exists():
                self._sync_create_quality_point()
                return
            QP = self.env['quality.point'].sudo()
            target_type = self.test_type if self.test_type in dict(QP._fields['test_type'].selection) else 'instructions'
            vals = {
                'title': self.title,
                'sequence': self.sequence,
                'test_type': target_type,
                'instructions': self.instructions or '',
                'workorder_operation_id': self.workorder_operation_id.id,
                'applies_to_manufacturing': True,
            }
            if hasattr(qp, 'notes'):
                vals['notes'] = self.notes
            if hasattr(qp, 'norm'):
                vals['norm'] = self.norm
                vals['norm_unit'] = self.norm_unit
                vals['tolerance_min'] = self.tolerance_min
                vals['tolerance_max'] = self.tolerance_max
            if hasattr(qp, 'failure_message'):
                vals['failure_message'] = self.failure_message
            qp.write(vals)
        except Exception as e:
            _logger.warning("Could not update quality.point %s for step %s: %s", self.quality_point_id, self.id, e)

    def _register_hook(self):
        super()._register_hook()
        try:
            # Check if tables exist before running query to avoid aborted transaction during first load
            self.env.cr.execute("SELECT to_regclass('mrp_routing_workcenter_step')")
            if not self.env.cr.fetchone()[0]:
                return

            if 'quality.point' in self.env:
                self.env.cr.execute("SELECT to_regclass('quality_point')")
                if not self.env.cr.fetchone()[0]:
                    return

                QP = self.env['quality.point'].sudo()
                qps = QP.search([('workorder_operation_id', '!=', False)])
                existing_qp_ids = set(self.sudo().search([('quality_point_id', '!=', False)]).mapped('quality_point_id'))
                valid_types = [
                    'instructions', 'consumed_materials', 'production', 'byproducts',
                    'picture', 'passfail', 'measure', 'spreadsheet', 'print_product_label', 'print_lot_label'
                ]
                for qp in qps:
                    if qp.id not in existing_qp_ids:
                        self.sudo().create({
                            'name': qp.name,
                            'title': qp.title or qp.name,
                            'sequence': qp.sequence,
                            'test_type': qp.test_type if qp.test_type in valid_types else 'instructions',
                            'instructions': qp.instructions or '',
                            'notes': getattr(qp, 'notes', '') or '',
                            'workorder_operation_id': qp.workorder_operation_id.id,
                            'company_id': qp.company_id.id if qp.company_id else self.env.company.id,
                            'norm': getattr(qp, 'norm', 0.0) or 0.0,
                            'norm_unit': getattr(qp, 'norm_unit', 'mm') or 'mm',
                            'tolerance_min': getattr(qp, 'tolerance_min', 0.0) or 0.0,
                            'tolerance_max': getattr(qp, 'tolerance_max', 0.0) or 0.0,
                            'failure_message': getattr(qp, 'failure_message', '') or '',
                            'quality_point_id': qp.id,
                        })
        except Exception as e:
            _logger.debug("Error in auto-sync quality.point hook: %s", e)

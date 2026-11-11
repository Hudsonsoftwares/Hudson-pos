# -*- coding: utf-8 -*-

# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError

class QualityCheckWizard(models.TransientModel):
    _name = 'quality.check.wizard'
    _description = 'Quality Check Wizard'

    # Origin references
    picking_id = fields.Many2one('stock.picking', 'Transfer')
    production_id = fields.Many2one('mrp.production', 'Manufacturing Order')
    repair_id = fields.Many2one('repair.order', 'Repair Order')

    # Current check info
    check_ids = fields.Many2many('quality.check', string='Pending Checks')
    current_check_id = fields.Many2one('quality.check', string='Current Check')
    failure_location_id = fields.Many2one('stock.location', string='Failure Location')
    failure_location_ids = fields.Many2many(related='current_check_id.point_id.failure_location_ids')
    
    # Related fields to show dynamically on the wizard view
    operation_name = fields.Char(compute='_compute_operation_name', string='Operation Name')
    name = fields.Char(related='current_check_id.point_id.name', string='Reference')
    title = fields.Char(related='current_check_id.point_id.title', string='Title')
    test_type = fields.Selection(related='current_check_id.test_type', string='Test Type')
    product_id = fields.Many2one(related='current_check_id.product_id', string='Product')
    qty_line = fields.Float(related='current_check_id.qty_line', string='Quantity Line')
    qty_to_test = fields.Float(related='current_check_id.qty_to_test', string='Quantity to Test')
    qty_tested = fields.Float(related='current_check_id.qty_tested', string='Quantity Tested', readonly=False)
    
    # Input fields for processing
    measure = fields.Float(related='current_check_id.measure', string='Measure', readonly=False)
    picture = fields.Binary(related='current_check_id.picture', string='Picture', readonly=False)
    note = fields.Html(related='current_check_id.notes', string='Note', readonly=False)
    additional_note = fields.Text(related='current_check_id.additional_note', string='Additional Note', readonly=False)

    @api.depends('picking_id', 'production_id', 'repair_id')
    def _compute_operation_name(self):
        for wiz in self:
            if wiz.picking_id and wiz.picking_id.picking_type_id:
                wiz.operation_name = wiz.picking_id.picking_type_id.name.upper()
            elif wiz.picking_id:
                wiz.operation_name = 'INVENTORY MOVE'
            elif wiz.production_id:
                wiz.operation_name = 'MANUFACTURING ORDER'
            elif wiz.repair_id:
                wiz.operation_name = 'REPAIR ORDER'
            else:
                wiz.operation_name = 'QUALITY CHECK'

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        
        # Determine the origin model and record
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')
        
        if not active_model or not active_id:
            return res
            
        record = self.env[active_model].browse(active_id)
        if not record.exists():
            return res

        # Find all pending quality checks for this record
        domain = [('quality_state', '=', 'none')]
        if active_model == 'stock.picking':
            domain.append(('picking_id', '=', record.id))
            res['picking_id'] = record.id
        elif active_model == 'mrp.production':
            domain.append(('production_id', '=', record.id))
            res['production_id'] = record.id
        elif active_model == 'repair.order':
            domain.append(('repair_id', '=', record.id))
            res['repair_id'] = record.id
            
        pending_checks = self.env['quality.check'].search(domain)
        
        if not pending_checks:
            raise UserError(_('There are no pending quality checks for this operation.'))
            
        res['check_ids'] = [(6, 0, pending_checks.ids)]
        res['current_check_id'] = pending_checks[0].id
        
        # Auto-assign the first failure location if any exist
        point = pending_checks[0].point_id
        if point.failure_location_ids:
            res['failure_location_id'] = point.failure_location_ids[0].id
            
        return res

    def _show_next(self):
        self.ensure_one()
        # Find next check
        pending_checks = self.check_ids.filtered(lambda c: c.quality_state == 'none')
        if not pending_checks:
            # We are done! Let's resume the original action
            return self._resume_origin_action()
            
        # Re-render wizard for next check
        self.current_check_id = pending_checks[0].id
        return {
            'name': _('Quality Check'),
            'type': 'ir.actions.act_window',
            'res_model': 'quality.check.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _resume_origin_action(self):
        """Simply close the wizard and return to the form view."""
        return {'type': 'ir.actions.act_window_close'}

    def action_pass(self):
        self.ensure_one()
        if self.current_check_id:
            self.current_check_id.do_pass()
        return self._show_next()

    def action_fail(self):
        self.ensure_one()
        if self.current_check_id:
            if self.current_check_id.point_id.failure_location_ids:
                # let the user choose the failure location in the
                # "Quality Check Failed" pop-up; it continues with the next check
                return self.current_check_id._get_fail_wizard_action(quality_check_wizard=self)
            self.current_check_id.do_fail(False)
        return self._show_next()

    def action_measure(self):
        self.ensure_one()
        if self.current_check_id:
            action = self.current_check_id.do_measure()
            if isinstance(action, dict):
                # measure out of tolerance: the fail pop-up continues with the next check
                action['context']['default_quality_check_wizard_id'] = self.id
                return action
        return self._show_next()

    def action_open_spreadsheet(self):
        self.ensure_one()
        if self.current_check_id:
            return self.current_check_id.action_open_spreadsheet()
        return {'type': 'ir.actions.act_window_close'}

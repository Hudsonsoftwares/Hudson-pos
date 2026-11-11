# -*- coding: utf-8 -*-

# pyrefly: ignore [missing-import]
from odoo import _, api, fields, models
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError


class RepairOrder(models.Model):
    _inherit = 'repair.order'

    quality_check_ids = fields.One2many('quality.check', 'repair_id', string='Quality Checks')
    quality_check_count = fields.Integer(compute='_compute_quality_check_count')
    quality_check_fail_count = fields.Integer(compute='_compute_quality_check_count')
    quality_check_todo = fields.Boolean(compute='_compute_quality_check_todo')
    quality_alert_ids = fields.One2many('quality.alert', 'repair_id', string='Quality Alerts')
    quality_alert_count = fields.Integer(compute='_compute_quality_alert_count')
    quality_alert_todo = fields.Boolean(
        compute='_compute_quality_alert_todo',
        help='A failed quality check has no quality alert yet.')

    @api.depends('quality_check_ids.quality_state', 'quality_check_ids.alert_ids')
    def _compute_quality_alert_todo(self):
        for repair in self:
            if not repair.id:
                repair.quality_alert_todo = False
                continue
            repair.quality_alert_todo = bool(self.env['quality.check'].search_count([
                ('repair_id', '=', repair.id), ('quality_state', '=', 'fail'), ('alert_ids', '=', False)]))

    @api.depends('quality_check_ids.quality_state')
    def _compute_quality_check_count(self):
        for repair in self:
            if not repair.id:
                repair.quality_check_count = 0
                repair.quality_check_fail_count = 0
                continue
            repair.quality_check_count = self.env['quality.check'].search_count([('repair_id', '=', repair.id)])
            repair.quality_check_fail_count = self.env['quality.check'].search_count([('repair_id', '=', repair.id), ('quality_state', '=', 'fail')])

    @api.depends('quality_check_ids.quality_state')
    def _compute_quality_check_todo(self):
        for repair in self:
            if not repair.id:
                repair.quality_check_todo = False
                continue
            repair.quality_check_todo = bool(self.env['quality.check'].search_count([('repair_id', '=', repair.id), ('quality_state', '=', 'none')]))

    @api.depends('quality_alert_ids')
    def _compute_quality_alert_count(self):
        for repair in self:
            if not repair.id:
                repair.quality_alert_count = 0
                continue
            repair.quality_alert_count = self.env['quality.alert'].search_count([('repair_id', '=', repair.id)])

    def _action_repair_confirm(self):
        res = super()._action_repair_confirm()
        self._generate_quality_checks()
        return res
        
    def action_validate(self):
        res = super().action_validate()
        self._generate_quality_checks()
        return res

    def action_repair_end(self):
        for repair in self:
            if repair.quality_check_todo:
                return repair.action_open_quality_check_wizard()
        return super().action_repair_end()

    def action_open_quality_check_wizard(self):
        self.ensure_one()
        return {
            'name': _('Quality Check'),
            'type': 'ir.actions.act_window',
            'res_model': 'quality.check.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_repair_id': self.id, 'active_model': 'repair.order', 'active_id': self.id},
        }

    def _generate_quality_checks(self):
        """Generate quality checks based on control points matching the repair's picking type."""
        for repair in self:
            if not repair.picking_type_id or repair.quality_check_ids:
                continue
                
            points = self.env['quality.point']._get_matching_points(
                company=repair.company_id,
                products=repair.product_id,
                picking_type=repair.picking_type_id,
            )
            
            common_vals = {
                'repair_id': repair.id,
                'company_id': repair.company_id.id,
            }
            self.env['quality.check']._create_checks_from_points(
                points, common_vals, products=repair.product_id)

    def action_view_quality_checks(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('Quality.action_quality_check')
        action['domain'] = [('repair_id', '=', self.id)]
        action['context'] = {'default_repair_id': self.id}
        return action

    def action_create_quality_alert(self):
        """'Quality Alert' header button: open a new alert for a failed check."""
        self.ensure_one()
        check = self.env['quality.check']._get_alert_check(self.quality_check_ids)
        if not check:
            raise UserError(_("There is no failed quality check on this repair order."))
        return check._get_create_alert_action()

    def action_view_quality_alerts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('Quality.action_quality_alert')
        action['domain'] = [('repair_id', '=', self.id)]
        action['context'] = {'default_repair_id': self.id}
        return action

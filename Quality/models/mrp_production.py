# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import _, api, fields, models
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    quality_check_ids = fields.One2many('quality.check', 'production_id', string='Quality Checks')
    quality_check_count = fields.Integer(compute='_compute_quality_check_count')
    quality_check_fail_count = fields.Integer(compute='_compute_quality_check_count')
    quality_check_todo = fields.Boolean(compute='_compute_quality_check_todo')
    quality_alert_ids = fields.One2many('quality.alert', 'production_id', string='Quality Alerts')
    quality_alert_count = fields.Integer(compute='_compute_quality_alert_count')
    quality_alert_todo = fields.Boolean(
        compute='_compute_quality_alert_todo',
        help='A failed quality check has no quality alert yet.')

    @api.depends('quality_check_ids.quality_state', 'quality_check_ids.alert_ids')
    def _compute_quality_alert_todo(self):
        for production in self:
            production.quality_alert_todo = any(
                c.quality_state == 'fail' and not c.alert_ids for c in production.quality_check_ids)

    @api.depends('quality_check_ids.quality_state')
    def _compute_quality_check_count(self):
        for production in self:
            production.quality_check_count = len(production.quality_check_ids)
            production.quality_check_fail_count = len(
                production.quality_check_ids.filtered(lambda c: c.quality_state == 'fail'))

    @api.depends('quality_check_ids.quality_state')
    def _compute_quality_check_todo(self):
        for prod in self:
            prod.quality_check_todo = any(c.quality_state == 'none' for c in prod.quality_check_ids)

    @api.depends('quality_alert_ids')
    def _compute_quality_alert_count(self):
        for production in self:
            production.quality_alert_count = len(production.quality_alert_ids)

    def action_confirm(self):
        res = super().action_confirm()
        for production in self:
            production._generate_quality_checks()
        return res

    def _generate_quality_checks(self):
        self.ensure_one()
        points = self.env['quality.point']._get_matching_points(
            company=self.company_id,
            products=self.product_id,
            is_manufacturing=True,
        )
        # Only order-level points here; work-order-level points (with a
        # workorder_operation_id set) are generated per work order instead.
        points = points.filtered(lambda p: not p.workorder_operation_id)
        common_vals = {
            'production_id': self.id,
            'company_id': self.company_id.id,
        }
        return self.env['quality.check']._create_checks_from_points(
            points, common_vals, products=self.product_id)

    def pre_button_mark_done(self):
        for prod in self:
            pending = prod.quality_check_ids.filtered(lambda c: c.quality_state == 'none')
            if pending:
                return prod.action_open_quality_check_wizard()
        return super().pre_button_mark_done()

    def action_open_quality_check_wizard(self):
        self.ensure_one()
        return {
            'name': _('Quality Check'),
            'type': 'ir.actions.act_window',
            'res_model': 'quality.check.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_production_id': self.id, 'active_model': 'mrp.production', 'active_id': self.id},
        }

    def action_view_quality_checks(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'Quality.action_quality_check')
        action['domain'] = [('production_id', '=', self.id)]
        action['context'] = {
            'default_production_id': self.id,
            'default_company_id': self.company_id.id,
        }
        return action

    def action_create_quality_alert(self):
        """'Quality Alert' header button: open a new alert for a failed check
        of the manufacturing order (including its work order checks)."""
        self.ensure_one()
        check = self.env['quality.check']._get_alert_check(self.quality_check_ids)
        if not check:
            raise UserError(_("There is no failed quality check on this manufacturing order."))
        return check._get_create_alert_action()

    def action_view_quality_alerts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'Quality.action_quality_alert')
        action['domain'] = [('production_id', '=', self.id)]
        action['context'] = {'default_production_id': self.id}
        return action

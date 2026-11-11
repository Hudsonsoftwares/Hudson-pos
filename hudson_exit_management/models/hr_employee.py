# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    resignation_ids = fields.One2many(
        'hr.resignation',
        'employee_id',
        string='Resignations'
    )
    resignation_count = fields.Integer(
        string='Resignation Count',
        compute='_compute_resignation_count'
    )

    def _compute_resignation_count(self):
        for rec in self:
            rec.resignation_count = len(rec.resignation_ids.filtered(lambda r: r.state != 'cancel'))

    def action_open_resignations(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('hudson_exit_management.action_hr_resignation')
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {'default_employee_id': self.id}
        return action

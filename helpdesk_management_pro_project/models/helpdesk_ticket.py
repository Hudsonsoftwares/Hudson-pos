# -*- coding: utf-8 -*-
from odoo import fields, models, api, _

class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.management.ticket'

    task_id = fields.Many2one('project.task', string='Project Task', copy=False, tracking=True)
    task_ids = fields.One2many('project.task', 'helpdesk_ticket_id', string='Tasks')
    task_count = fields.Integer(compute='_compute_task_count')

    @api.depends('task_ids')
    def _compute_task_count(self):
        for ticket in self:
            ticket.task_count = len(ticket.task_ids)

    def action_plan_intervention(self):
        self.ensure_one()
        return {
            'name': _('Plan Intervention'),
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_name': f'Intervention for: {self.name}',
                'default_helpdesk_ticket_id': self.id,
            }
        }

    def action_view_tasks(self):
        self.ensure_one()
        if len(self.task_ids) == 1:
            return {
                'name': _('Task'),
                'type': 'ir.actions.act_window',
                'res_model': 'project.task',
                'res_id': self.task_ids[0].id,
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'current',
            }
        return {
            'name': _('Tasks'),
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'domain': [('helpdesk_ticket_id', '=', self.id)],
            'context': {'default_helpdesk_ticket_id': self.id},
        }


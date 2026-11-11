# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class TicketConvertTask(models.TransientModel):
    _name = 'helpdesk.ticket.convert.task'
    _description = 'Convert Ticket to Task'

    ticket_id = fields.Many2one('helpdesk.management.ticket', required=True, readonly=True)
    name = fields.Char('Task Title', required=True)
    project_id = fields.Many2one('project.project', 'Project', required=True)
    user_ids = fields.Many2many('res.users', string='Assignees')

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if 'ticket_id' in fields_list and self.env.context.get('active_id'):
            ticket = self.env['helpdesk.management.ticket'].browse(self.env.context.get('active_id'))
            defaults['ticket_id'] = ticket.id
            defaults['name'] = ticket.subject
        return defaults

    def action_convert_to_task(self):
        self.ensure_one()
        if not self.ticket_id:
            raise UserError(_("No ticket specified."))

        task_vals = {
            'name': self.name,
            'project_id': self.project_id.id,
            'user_ids': [(6, 0, self.user_ids.ids)],
            'description': self.ticket_id.description,
            'partner_id': self.ticket_id.partner_id.id,
            'helpdesk_ticket_id': self.ticket_id.id,
        }
        
        task = self.env['project.task'].create(task_vals)
        self.ticket_id.write({
            'task_id': task.id,
        })
        
        self.ticket_id.message_post(body=_("Ticket converted to Task: %s", task._get_html_link()))
        
        return {
            'name': _('Task'),
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'res_id': task.id,
            'view_mode': 'form',
        }


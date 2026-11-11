# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class TicketConvertLead(models.TransientModel):
    _name = 'helpdesk.ticket.convert.lead'
    _description = 'Convert Ticket to Lead'

    ticket_id = fields.Many2one('helpdesk.management.ticket', required=True, readonly=True)
    name = fields.Char('Lead Name', required=True)
    partner_id = fields.Many2one('res.partner', 'Customer', readonly=True)
    team_id = fields.Many2one('crm.team', 'Sales Team')
    user_id = fields.Many2one('res.users', 'Salesperson')

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if 'ticket_id' in fields_list and self.env.context.get('active_id'):
            ticket = self.env['helpdesk.management.ticket'].browse(self.env.context.get('active_id'))
            defaults['ticket_id'] = ticket.id
            defaults['name'] = ticket.subject
            defaults['partner_id'] = ticket.partner_id.id
        return defaults

    def action_convert_to_lead(self):
        self.ensure_one()
        if not self.ticket_id:
            raise UserError(_("No ticket specified."))

        lead_vals = {
            'name': self.name,
            'partner_id': self.partner_id.id,
            'description': self.ticket_id.description,
            'team_id': self.team_id.id,
            'user_id': self.user_id.id,
            'helpdesk_ticket_id': self.ticket_id.id,
        }
        
        lead = self.env['crm.lead'].create(lead_vals)
        self.ticket_id.write({
            'lead_id': lead.id,
        })
        
        self.ticket_id.message_post(body=_("Ticket converted to Lead: %s", lead._get_html_link()))
        
        return {
            'name': _('Lead'),
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': lead.id,
            'view_mode': 'form',
        }


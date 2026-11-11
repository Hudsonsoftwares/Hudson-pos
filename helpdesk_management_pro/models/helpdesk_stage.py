# -*- coding: utf-8 -*-
from odoo import api, fields, models

class HelpdeskManagementStage(models.Model):
    _name = 'helpdesk.management.stage'
    _description = 'Helpdesk Stage'
    _order = 'sequence, id'

    def _default_team_ids(self):
        team_id = self.env.context.get('default_team_id')
        return [(6, 0, [team_id])] if team_id else False

    name = fields.Char(string='Stage Name', required=True, translate=True)
    description = fields.Text(string='Description', translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_close = fields.Boolean(string='Closing Stage', help="Tickets in this stage are considered closed.")
    fold = fields.Boolean(string='Folded', help="This stage is folded in the kanban view by default.")

    team_ids = fields.Many2many('helpdesk.management.team', string='Helpdesk Teams', default=_default_team_ids,
                                help="Specific teams that uses this stage. Other teams will not be able to see or use this stage.")

    template_id = fields.Many2one('mail.template', string='Email Template',
                                  domain="[('model', '=', 'helpdesk.management.ticket')]",
                                  help="If set, an email will be sent to the customer when the ticket reaches this step.")

    ticket_count = fields.Integer(string='Tickets', compute='_compute_ticket_count')

    def _compute_ticket_count(self):
        counts = dict(self.env['helpdesk.management.ticket']._read_group(
            [('stage_id', 'in', self.ids)], ['stage_id'], ['__count']))
        for stage in self:
            stage.ticket_count = counts.get(stage, 0)

    def action_open_tickets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'helpdesk.management.ticket',
            'view_mode': 'list,kanban,form',
            'domain': [('stage_id', '=', self.id)],
            'context': {'default_stage_id': self.id},
        }

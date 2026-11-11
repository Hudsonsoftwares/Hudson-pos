# -*- coding: utf-8 -*-
from odoo import fields, models, _

class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.management.ticket'

    lead_id = fields.Many2one('crm.lead', string='CRM Lead', copy=False, tracking=True)

    def action_view_lead(self):
        self.ensure_one()
        if not self.lead_id:
            return
        return {
            'name': _('Lead'),
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': self.lead_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }


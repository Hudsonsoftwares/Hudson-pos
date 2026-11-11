# -*- coding: utf-8 -*-
from odoo import fields, models

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    helpdesk_ticket_id = fields.Many2one('helpdesk.management.ticket', string='Helpdesk Ticket', tracking=True)


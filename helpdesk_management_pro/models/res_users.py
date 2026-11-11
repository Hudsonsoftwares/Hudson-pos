# -*- coding: utf-8 -*-
# pyrefly: ignore[missing-import]
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Daily targets of the "My Performance" dashboard, set by each user (0 = no target set)
    helpdesk_target_closed = fields.Integer(string='Helpdesk Target Tickets to Close', default=0)
    helpdesk_target_success = fields.Float(string='Helpdesk Target SLA Success Rate', default=0.0)
    helpdesk_target_rating = fields.Float(string='Helpdesk Target Customer Rating', default=0.0)

# -*- encoding: utf-8 -*-
from odoo import api, fields, models

class EhHrMeetingRoom(models.Model):
    _name = 'eh.hr.meeting.room'
    _description = 'Meeting Room'

    name = fields.Char(string='Room Name', required=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
    )
    active = fields.Boolean(default=True)

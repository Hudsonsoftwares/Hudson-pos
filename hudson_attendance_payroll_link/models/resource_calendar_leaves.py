# -*- coding: utf-8 -*-
from odoo import api, fields, models

class ResourceCalendarLeaves(models.Model):
    _inherit = 'resource.calendar.leaves'

    is_mandatory = fields.Boolean(
        string='Mandatory Holiday',
        default=True,
        help="When checked, this public holiday is treated as a mandatory statutory holiday for attendance and payroll scheduled hours."
    )

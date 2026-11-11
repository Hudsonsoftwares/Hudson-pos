# -*- coding: utf-8 -*-
from odoo import fields, models


class ResourceCalendar(models.Model):
    _inherit = 'resource.calendar'

    tz = fields.Selection(
        related='company_id.tz',
        string="Timezone",
        readonly=True,
    )

# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    planning_employee_unavailabilities = fields.Selection(
        [
            ('switch', 'Request a replacement'),
            ('unassign', 'Remove themselves from shifts'),
        ],
        string='Allow employees to',
        config_parameter='hudson_planning.employee_unavailabilities',
        default='switch',
        help='What employees can do on their published shifts when they are unavailable.',
    )

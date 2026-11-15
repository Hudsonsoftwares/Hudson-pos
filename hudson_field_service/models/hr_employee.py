# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Settings > Stock by Vehicle
    fs_vehicle_location_id = fields.Many2one(
        'stock.location',
        string='Vehicle Stock',
        domain="[('usage', '=', 'internal')]",
        # Private employee data (not on the public profile); read with sudo
        groups='hr.group_hr_user',
        help="Stock location of the technician's vehicle: parts used on their jobs are taken from it.",
    )

# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class FsShiftTemplate(models.Model):
    _inherit = 'fs.shift.template'

    worksheet_template_id = fields.Many2one(
        'fs.worksheet.template',
        string='Worksheet',
        ondelete='set null',
        help='Worksheet of the field service jobs planned with this template.',
    )

    @api.depends('worksheet_template_id')
    def _compute_display_name(self):
        # e.g. "8 - 12 Management [Device Installation and Maintenance]"
        super()._compute_display_name()
        for template in self.filtered('worksheet_template_id'):
            template.display_name = f'{template.display_name} [{template.worksheet_template_id.name}]'

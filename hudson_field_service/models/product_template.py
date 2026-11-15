# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    worksheet_template_id = fields.Many2one(
        'fs.worksheet.template',
        string='Worksheet',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Worksheet the technicians fill in on the field service jobs of this service. "
             "When its Sales Order is confirmed, the service becomes a field service job for the "
             "customer: planned through its shifts with Plan Services, otherwise as a job to schedule.",
    )

    @api.onchange('type')
    def _onchange_type_worksheet(self):
        if self.type != 'service':
            self.worksheet_template_id = False

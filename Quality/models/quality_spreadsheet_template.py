# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import fields, models

class QualitySpreadsheetTemplate(models.Model):
    _name = 'quality.spreadsheet.template'
    _description = 'Quality Spreadsheet Template'
    _inherit = ['spreadsheet.mixin']
    _order = 'name'

    name = fields.Char(string='Name', required=True, translate=True)
    success_cell = fields.Char(string='Success cell', default='B17', help='Spreadsheet cell containing the final test result (e.g. PASS/FAIL)')
    active = fields.Boolean(default=True)

    def action_open_spreadsheet(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'action_quality_spreadsheet',
            'params': {
                'spreadsheet_id': self.id,
            }
        }

# -*- coding: utf-8 -*-
import base64
import csv
import io
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HdsInBonusImportWizard(models.Model):
    _name = 'hds.in.bonus.import.wizard'
    _description = 'Import Bonus Lines Wizard'

    bonus_id = fields.Many2one('hds.in.bonus', string="Bonus Document", required=True, ondelete='cascade')
    file_data = fields.Binary(string="Excel / CSV File", required=True)
    file_name = fields.Char(string="File Name")
    delimiter = fields.Selection([
        (',', 'Comma (,)'),
        (';', 'Semicolon (;)'),
        ('\t', 'Tab (\\t)'),
    ], string="Delimiter", default=',')

    paste_data = fields.Text(
        string="Or Paste CSV Data",
        help="Format per line: Employee_Code,Bonus_Amount,Remarks\ne.g. EMP001,15000,Diwali Incentive"
    )

    def action_import(self):
        self.ensure_one()
        if self.bonus_id.state not in ('draft', 'submitted'):
            raise UserError(_("You can only import lines into Draft or Submitted bonus documents."))

        lines_to_create = []

        if self.paste_data:
            stream = io.StringIO(self.paste_data.strip())
            reader = csv.reader(stream, delimiter=self.delimiter or ',')
            lines_to_create.extend(self._parse_rows(reader))
        elif self.file_data:
            content = base64.b64decode(self.file_data).decode('utf-8-sig', errors='ignore')
            stream = io.StringIO(content)
            reader = csv.reader(stream, delimiter=self.delimiter or ',')
            lines_to_create.extend(self._parse_rows(reader))
        else:
            raise UserError(_("Please upload a file or paste CSV data to import."))

        if not lines_to_create:
            raise UserError(_("No valid employee bonus lines found in the input data."))

        # Clear existing lines and create imported lines
        self.bonus_id.line_ids.unlink()
        self.env['hds.in.bonus.line'].create(lines_to_create)
        return {'type': 'ir.actions.act_window_close'}

    def _parse_rows(self, reader):
        created_vals = []
        for row_idx, row in enumerate(reader, start=1):
            if not row or not any(row):
                continue
            # Skip header if first column contains non-digit words like 'Employee'
            if row_idx == 1 and ('employee' in row[0].lower() or 'code' in row[0].lower()):
                continue

            emp_ref = row[0].strip() if len(row) > 0 else ''
            amount_str = row[1].strip() if len(row) > 1 else '0'
            remarks = row[2].strip() if len(row) > 2 else ''

            if not emp_ref:
                continue

            # Search employee by registration number, identification ID, or name
            employee = self.env['hr.employee'].search([
                '|', '|',
                ('registration_number', '=', emp_ref),
                ('identification_id', '=', emp_ref),
                ('name', '=ilike', emp_ref)
            ], limit=1)

            if not employee:
                continue

            try:
                amount = float(amount_str.replace(',', ''))
            except ValueError:
                amount = 0.0

            # Find active contract
            contract = self.env['hr.version'].search([
                ('employee_id', '=', employee.id),
                ('active', '=', True)
            ], order='id desc', limit=1)

            created_vals.append({
                'bonus_id': self.bonus_id.id,
                'employee_id': employee.id,
                'contract_id': contract.id if contract else False,
                'amount': amount,
            })
        return created_vals

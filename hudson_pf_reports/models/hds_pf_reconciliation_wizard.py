# -*- coding: utf-8 -*-
import base64
import io
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
from odoo.exceptions import UserError# pyrefly: ignore [missing-import]

try:
    # pyrefly: ignore [missing-import]
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HdsPfReconciliationWizard(models.TransientModel):
    _name = 'hds.pf.reconciliation.wizard'
    _inherit = 'hds.pf.report.wizard.base'
    _description = 'PF Reconciliation Report Wizard'

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    state = fields.Selection([('draft', 'Draft'), ('generated', 'Generated')], string='State', default='draft')
    xlsx_file = fields.Binary(string='Reconciliation Excel (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    @api.depends('month', 'year')
    def _compute_name(self):
        m_dict = dict(self._fields['month'].selection)
        for rec in self:
            rec.name = f"PF Accounting Reconciliation / {m_dict.get(rec.month, '')}-{rec.year}"

    def action_export_xlsx(self):
        self.ensure_one()
        payslips = self._get_confirmed_payslips([('employee_id.hds_in_epf_applicable', '=', True)])

        if not payslips:
            raise UserError(_("No confirmed payslips found for EPF-applicable employees in period (%s).") % self._get_month_label())

        rows = []
        tot_payroll_pf = 0.0
        tot_account_pf = 0.0
        tot_diff = 0.0

        for payslip in payslips:
            emp = payslip.employee_id
            # Payroll PF total (EPF + EPF_ER + EPS)
            ee_epf = abs(sum(payslip.line_ids.filtered(lambda l: l.code == 'EPF').mapped('total')))
            er_epf = abs(sum(payslip.line_ids.filtered(lambda l: l.code == 'EPF_ER').mapped('total')))
            er_eps = abs(sum(payslip.line_ids.filtered(lambda l: l.code == 'EPS').mapped('total')))
            payroll_pf = ee_epf + er_epf + er_eps

            # Accounting PF from move_id
            account_pf = 0.0
            if payslip.move_id:
                for move_line in payslip.move_id.line_ids:
                    # Match move lines related to PF accounts / rules
                    line_code = getattr(move_line.salary_rule_id, 'code', '') if hasattr(move_line, 'salary_rule_id') else ''
                    line_name = (move_line.name or '').upper()
                    if line_code in ('EPF', 'EPF_ER', 'EPS') or 'PF' in line_name or 'PROVIDENT' in line_name:
                        account_pf += (move_line.credit or move_line.debit or 0.0)

            # If no move lines were explicitly tagged with rule, fallback to payroll_pf matching if move_id exists
            if payslip.move_id and account_pf == 0.0:
                account_pf = payroll_pf

            diff = payroll_pf - account_pf

            rows.append({
                'employee': emp.name,
                'payslip_number': payslip.number or payslip.name,
                'move_name': payslip.move_id.name if payslip.move_id else 'Not Posted',
                'payroll_pf': round(payroll_pf, 2),
                'account_pf': round(account_pf, 2),
                'diff': round(diff, 2),
                'status': 'Reconciled' if abs(diff) < 0.01 else 'Discrepancy Found',
            })

            tot_payroll_pf += payroll_pf
            tot_account_pf += account_pf
            tot_diff += diff

        month_label = self._get_month_label().replace('-', '_')
        xlsx_filename = f"PF_Reconciliation_{month_label}.xlsx"

        output = io.BytesIO()
        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet('Reconciliation')
            sheet.set_column(0, 0, 26)  # Employee
            sheet.set_column(1, 1, 20)  # Payslip Ref
            sheet.set_column(2, 2, 22)  # Journal Entry Ref
            sheet.set_column(3, 3, 18)  # Payroll PF Total
            sheet.set_column(4, 4, 24)  # Accounting Entry PF Total
            sheet.set_column(5, 5, 16)  # Difference
            sheet.set_column(6, 6, 16)  # Status

            header_fmt = workbook.add_format({
                'bold': True,
                'bg_color': '#1F4E78',
                'font_color': '#FFFFFF',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'text_wrap': True,
            })
            num_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1, 'align': 'right', 'valign': 'vcenter'})
            text_fmt = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter'})

            sheet.set_row(0, 26)
            headers = ['Employee', 'Payslip Ref', 'Journal Entry Ref', 'Payroll PF Total', 'Accounting Entry PF Total', 'Difference', 'Status']
            for col_idx, text in enumerate(headers):
                sheet.write(0, col_idx, text, header_fmt)

            for row_idx, r in enumerate(rows, start=1):
                sheet.write(row_idx, 0, r['employee'], text_fmt)
                sheet.write(row_idx, 1, r['payslip_number'], text_fmt)
                sheet.write(row_idx, 2, r['move_name'], text_fmt)
                sheet.write(row_idx, 3, r['payroll_pf'], num_fmt)
                sheet.write(row_idx, 4, r['account_pf'], num_fmt)
                sheet.write(row_idx, 5, r['diff'], num_fmt)
                sheet.write(row_idx, 6, r['status'], text_fmt)

            workbook.close()
            output.seek(0)
            xlsx_content = output.read()
        else:
            xlsx_content = b"Excel export requires xlsxwriter library."

        try:
            from odoo.tools import BinaryBytes# pyrefly: ignore [missing-import]
            file_data = BinaryBytes(xlsx_content, filename=xlsx_filename)
        except Exception:
            file_data = base64.b64encode(xlsx_content).decode('utf-8')

        self.write({
            'state': 'generated',
            'xlsx_file': file_data,
            'xlsx_filename': xlsx_filename,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=xlsx_file&filename_field=xlsx_filename&download=true',
            'target': 'self',
        }

# -*- coding: utf-8 -*-
import base64
import io
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError

try:
    # pyrefly: ignore [missing-import]
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HdsPfEcrWizard(models.Model):
    _name = 'hds.pf.ecr.wizard'
    _inherit = 'hds.pf.report.wizard.base'
    _description = 'EPFO ECR Export Wizard'
    _order = 'id desc'

    report_type = fields.Selection([
        ('epf_report', 'EPF Report'),
        ('epf_summary', 'EPF Summary'),
    ], string='Report Type', default='epf_report', required=True)

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
    ], string='State', default='draft')

    txt_file = fields.Binary(string='ECR Text File (.txt)', readonly=True)
    txt_filename = fields.Char(string='Text Filename', readonly=True)
    xlsx_file = fields.Binary(string='Report Excel File (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    record_count = fields.Integer(string='Total Employees', readonly=True)
    total_epf_wages = fields.Float(string='Total EPF Wages', readonly=True)
    total_epf_deduction = fields.Float(string='Total Employee EPF', readonly=True)
    total_eps_contribution = fields.Float(string='Total Employer EPS', readonly=True)
    total_epf_er_contribution = fields.Float(string='Total Employer EPF', readonly=True)

    @api.depends('month', 'year', 'report_type')
    def _compute_name(self):
        month_dict = dict(self._fields['month'].selection)
        report_dict = dict(self._fields['report_type'].selection)
        for rec in self:
            m_label = month_dict.get(rec.month, '')
            r_label = report_dict.get(rec.report_type, 'EPF Report')
            rec.name = f"{r_label} / {m_label}-{rec.year}"

    def _get_ecr_data(self):
        self.ensure_one()
        payslips = self._get_confirmed_payslips([('employee_id.hds_in_epf_applicable', '=', True)])

        # Pre-export statutory UAN compliance validation for ECR upload
        if self.report_type != 'epf_summary' and payslips:
            from odoo.addons.hudson_in_payroll.services.compliance.statutory_compliance_service import StatutoryComplianceValidationService# pyrefly: ignore [missing-import]
            compliance_service = StatutoryComplianceValidationService(self.env)
            compliance_service.validate_scope_compliance(
                employees=payslips.mapped('employee_id'),
                statutory_type='epf',
                report_title='EPF-ECR'
            )

        date_from, date_to = self._get_date_range()
        eps_ceiling = self.env['hr.rule.parameter'].get_pf_parameter('EPS_WAGE_CEILING', date=date_to) or 15000.0
        edli_ceiling = self.env['hr.rule.parameter'].get_pf_parameter('EDLI_WAGE_CEILING', date=date_to) or eps_ceiling

        ecr_rows = []
        summary_rows = []
        tot_gross_wages = 0.0
        tot_wages = 0.0
        tot_eps_wages = 0.0
        tot_edli_wages = 0.0
        tot_ee_epf = 0.0
        tot_er_eps = 0.0
        tot_er_epf = 0.0
        tot_edli = 0.0
        tot_admin = 0.0
        tot_vpf = 0.0
        tot_pf_amount_sum = 0.0
        tot_overall_contrib = 0.0

        for payslip in payslips:
            emp = payslip.employee_id
            uan = emp.hds_in_uan or ''
            member_name = emp.name or ''
            emp_ref = getattr(emp, 'registration_number', False) or getattr(emp, 'barcode', False) or ''
            # PF Account Number from the employee's Statutory Information (never the bank account)
            acc_num = emp.hds_in_pf_member_id or ''

            pf_vals = self._get_pf_line_amounts(payslip)

            gross_line = payslip.line_ids.filtered(lambda l: l.code == 'GROSS')
            gross_wages = gross_line.total if gross_line else (payslip.contract_id.wage if payslip.contract_id else 0.0)

            epf_wages = pf_vals['pf_wage']
            eps_wages = min(epf_wages, eps_ceiling) if getattr(emp, 'hds_in_eps_applicable', True) else 0.0
            edli_wages = min(epf_wages, edli_ceiling) if getattr(emp, 'hds_in_edli_applicable', True) else 0.0

            ee_epf = pf_vals['ee_epf']
            vpf_amt = pf_vals.get('vpf', 0.0)
            er_epf = pf_vals['er_epf']
            er_eps = pf_vals['er_eps']
            edli_amt = pf_vals.get('edli', 0.0)
            admin_amt = pf_vals.get('admin', 0.0)

            # Dynamic NCP Days (Non-Contributory Period) strictly derived from LOP / Unpaid Days
            snapshot_lop = 0
            if getattr(payslip, 'hds_snapshot_id', False) and getattr(payslip.hds_snapshot_id, 'lop_days', False):
                snapshot_lop = int(round(payslip.hds_snapshot_id.lop_days or 0))

            worked_lop = 0
            if payslip.worked_days_line_ids:
                unpaid_codes = ('UNPAID', 'ABSENT', 'LEAVE_UNPAID', 'LOP', 'SHORTAGE', 'UNPAID_LEAVE')
                unpaid_lines = payslip.worked_days_line_ids.filtered(lambda l: (l.code or '').upper() in unpaid_codes)
                if unpaid_lines:
                    worked_lop = int(round(sum(unpaid_lines.mapped('number_of_days'))))

            ncp_days = max(snapshot_lop, worked_lop)

            refund_advances = 0

            ecr_rows.append({
                'uan': uan,
                'name': member_name,
                'gross': round(gross_wages, 2),
                'epf_wages': round(epf_wages, 2),
                'eps_wages': round(eps_wages, 2),
                'edli_wages': round(edli_wages, 2),
                'ee_epf': round(ee_epf, 2),
                'er_epf': round(er_epf, 2),
                'er_eps': round(er_eps, 2),
                'ncp_days': ncp_days,
                'refund': refund_advances,
            })

            tot_pf_amount = round(ee_epf + vpf_amt, 2)
            tot_contrib = round(ee_epf + vpf_amt + tot_pf_amount + edli_amt + admin_amt, 2)

            summary_rows.append({
                'employee_id': emp_ref,
                'employee_name': member_name,
                'account_number': acc_num,
                'uan': uan,
                'pf_wages': round(epf_wages, 2),
                'employee_pf_amount': round(ee_epf, 2),
                'vpf_amount': round(vpf_amt, 2),
                'pf_amount': tot_pf_amount,
                'eps_amount': round(er_eps, 2),
                'edli': round(edli_amt, 2),
                'admin_charge': round(admin_amt, 2),
                'total_contribution': tot_contrib,
            })

            tot_gross_wages += gross_wages
            tot_wages += epf_wages
            tot_eps_wages += eps_wages
            tot_edli_wages += edli_wages
            tot_ee_epf += ee_epf
            tot_er_eps += er_eps
            tot_er_epf += er_epf
            tot_edli += edli_amt
            tot_admin += admin_amt
            tot_vpf += vpf_amt
            tot_pf_amount_sum += tot_pf_amount
            tot_overall_contrib += tot_contrib

        est_name = self.company_id.name or ''
        est_id = getattr(self.company_id, 'hds_in_epf_employer_id', False) or getattr(self.company_id, 'vat', False) or ''

        return {
            'ecr_rows': ecr_rows,
            'summary_rows': summary_rows,
            'tot_gross_wages': round(tot_gross_wages, 2),
            'tot_wages': round(tot_wages, 2),
            'tot_eps_wages': round(tot_eps_wages, 2),
            'tot_edli_wages': round(tot_edli_wages, 2),
            'tot_ee_epf': round(tot_ee_epf, 2),
            'tot_er_eps': round(tot_er_eps, 2),
            'tot_er_epf': round(tot_er_epf, 2),
            'tot_edli': round(tot_edli, 2),
            'tot_admin': round(tot_admin, 2),
            'tot_vpf': round(tot_vpf, 2),
            'tot_pf_amount': round(tot_pf_amount_sum, 2),
            'tot_overall_contrib': round(tot_overall_contrib, 2),
            'record_count': len(ecr_rows),
            'est_name': est_name,
            'est_id': est_id,
        }

    def action_print_pdf(self):
        self.ensure_one()
        data = self._get_ecr_data()
        if not data.get('ecr_rows'):
            raise UserError(_("No employee records found for the selected period (%s).") % self._get_month_label())
        return self.env.ref('hudson_pf_reports.action_report_pf_ecr').report_action(self)

    def _generate_ecr_report_files(self):
        self.ensure_one()
        data = self._get_ecr_data()
        ecr_rows = data['ecr_rows']
        summary_rows = data['summary_rows']
        tot_wages = data['tot_wages']
        tot_ee_epf = data['tot_ee_epf']
        tot_er_eps = data['tot_er_eps']
        tot_er_epf = data['tot_er_epf']

        month_label = self._get_month_label().replace('-', '_')
        txt_filename = f"EPFO_ECR_{month_label}.txt"

        if self.report_type == 'epf_summary':
            xlsx_filename = f"EPF_Summary_Report_{month_label}.xlsx"
        else:
            xlsx_filename = f"EPF_ECR_Report_{month_label}.xlsx"

        txt_lines = []
        for row in ecr_rows:
            line = f"{row['uan']}#~#{row['name']}#~#{int(round(row['gross']))}#~#{int(round(row['epf_wages']))}#~#{int(round(row['eps_wages']))}#~#{int(round(row['edli_wages']))}#~#{int(round(row['ee_epf']))}#~#{int(round(row['er_eps']))}#~#{int(round(row['er_epf']))}#~#{row['ncp_days']}#~#{row['refund']}"
            txt_lines.append(line)
        txt_content = "\n".join(txt_lines)

        output = io.BytesIO()
        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            header_fmt = workbook.add_format({
                'bold': True,
                'bg_color': '#1F4E78',
                'font_color': '#FFFFFF',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'text_wrap': True,
                'font_size': 9,
            })
            num_fmt = workbook.add_format({
                'num_format': '#,##0.00',
                'border': 1,
                'align': 'right',
                'valign': 'vcenter',
                'font_size': 9,
            })
            text_left_fmt = workbook.add_format({
                'border': 1,
                'align': 'left',
                'valign': 'vcenter',
                'font_size': 9,
            })
            text_center_fmt = workbook.add_format({
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'font_size': 9,
            })
            meta_label_fmt = workbook.add_format({'bold': True, 'font_size': 11, 'valign': 'vcenter'})
            meta_val_fmt = workbook.add_format({'font_size': 11, 'valign': 'vcenter'})
            empty_msg_fmt = workbook.add_format({
                'align': 'center',
                'valign': 'vcenter',
                'font_size': 10,
                'font_color': '#333333',
                'border': 1,
                'border_color': '#D9D9D9',
            })

            if self.report_type == 'epf_summary':
                sheet = workbook.add_worksheet('EPF Summary')
                sheet.set_column(0, 0, 16)   # EMPLOYEE ID
                sheet.set_column(1, 1, 26)   # EMPLOYEE NAME
                sheet.set_column(2, 2, 20)   # PF ACCOUNT NUMBER
                sheet.set_column(3, 3, 18)   # UAN
                sheet.set_column(4, 4, 18)   # PF WAGES
                sheet.set_column(5, 5, 16)   # PF AMOUNT
                sheet.set_column(6, 6, 16)   # VPF AMOUNT
                sheet.set_column(7, 7, 16)   # PF AMOUNT
                sheet.set_column(8, 8, 16)   # EPS AMOUNT
                sheet.set_column(9, 9, 14)   # EDLI
                sheet.set_column(10, 10, 20)  # PF ADMIN CHARGES
                sheet.set_column(11, 11, 22)  # TOTAL CONTRIBUTION

                title_fmt = workbook.add_format({
                    'bold': True,
                    'align': 'center',
                    'valign': 'vcenter',
                    'font_size': 11,
                })
                est_fmt = workbook.add_format({
                    'bold': True,
                    'align': 'left',
                    'valign': 'vcenter',
                    'font_size': 10,
                })
                th_fmt = workbook.add_format({
                    'bold': True,
                    'bg_color': '#B7CCE4',
                    'font_color': '#000000',
                    'border': 1,
                    'border_color': '#000000',
                    'align': 'center',
                    'valign': 'vcenter',
                    'font_size': 9,
                })
                data_text_fmt = workbook.add_format({
                    'align': 'left',
                    'valign': 'vcenter',
                    'font_size': 9,
                })
                data_center_fmt = workbook.add_format({
                    'align': 'center',
                    'valign': 'vcenter',
                    'font_size': 9,
                })
                data_num_fmt = workbook.add_format({
                    'align': 'right',
                    'valign': 'vcenter',
                    'num_format': '#,##0.00',
                    'font_size': 9,
                })
                total_label_fmt = workbook.add_format({
                    'bold': True,
                    'align': 'center',
                    'valign': 'vcenter',
                    'font_size': 10,
                })
                total_num_fmt = workbook.add_format({
                    'bold': True,
                    'align': 'right',
                    'valign': 'vcenter',
                    'num_format': '#,##0.00',
                    'font_size': 9,
                })
                note_fmt = workbook.add_format({
                    'align': 'left',
                    'valign': 'vcenter',
                    'font_size': 9,
                })

                # Row 1 (Index 0): Empty
                sheet.set_row(0, 18)

                # Row 2 (Index 1): Title
                sheet.set_row(1, 24)
                m_name = dict(self._fields['month'].selection).get(self.month, '')
                sheet.merge_range(1, 0, 1, 11, f"EPF Summary Contribution for {m_name} {self.year}", title_fmt)

                # Row 3 (Index 2): Empty
                sheet.set_row(2, 15)

                # Row 4 (Index 3): Establishment ID
                sheet.set_row(3, 20)
                sheet.write(3, 0, f"{data['est_name']} Establishment ID: {data['est_id']}", est_fmt)

                # Rows 5 & 6 (Indices 4 & 5): Grouped Headers
                sheet.set_row(4, 22)
                sheet.set_row(5, 22)

                sheet.merge_range(4, 0, 5, 0, 'EMPLOYEE ID', th_fmt)
                sheet.merge_range(4, 1, 5, 1, 'EMPLOYEE NAME', th_fmt)
                sheet.merge_range(4, 2, 5, 2, 'PF ACCOUNT NUMBER', th_fmt)
                sheet.merge_range(4, 3, 5, 3, 'UAN', th_fmt)
                sheet.merge_range(4, 4, 5, 4, 'PF WAGES', th_fmt)

                sheet.merge_range(4, 5, 4, 6, "Employee's Contribution", th_fmt)
                sheet.write(5, 5, 'PF AMOUNT', th_fmt)
                sheet.write(5, 6, 'VPF AMOUNT', th_fmt)

                sheet.merge_range(4, 7, 4, 10, "Employer's Contribution", th_fmt)
                sheet.write(5, 7, 'PF AMOUNT', th_fmt)
                sheet.write(5, 8, 'EPS AMOUNT', th_fmt)
                sheet.write(5, 9, 'EDLI', th_fmt)
                sheet.write(5, 10, 'PF ADMIN CHARGES', th_fmt)

                sheet.merge_range(4, 11, 5, 11, 'TOTAL CONTRIBUTION', th_fmt)

                if summary_rows:
                    # Data Rows (starting from Row 7, Index 6)
                    cur_row = 6
                    for r in summary_rows:
                        sheet.set_row(cur_row, 20)
                        sheet.write(cur_row, 0, r['employee_id'] or '', data_center_fmt)
                        sheet.write(cur_row, 1, r['employee_name'] or '', data_text_fmt)
                        sheet.write(cur_row, 2, r['account_number'] or '', data_center_fmt)
                        sheet.write(cur_row, 3, r['uan'] or '', data_center_fmt)
                        sheet.write(cur_row, 4, r['pf_wages'], data_num_fmt)
                        sheet.write(cur_row, 5, r['employee_pf_amount'], data_num_fmt)
                        sheet.write(cur_row, 6, r['vpf_amount'], data_num_fmt)
                        sheet.write(cur_row, 7, r['pf_amount'], data_num_fmt)
                        sheet.write(cur_row, 8, r['eps_amount'], data_num_fmt)
                        sheet.write(cur_row, 9, r['edli'], data_num_fmt)
                        sheet.write(cur_row, 10, r['admin_charge'], data_num_fmt)
                        sheet.write(cur_row, 11, r['total_contribution'], data_num_fmt)
                        cur_row += 1

                    # Empty row after data
                    sheet.set_row(cur_row, 15)
                    cur_row += 1

                    # Totals row
                    sheet.set_row(cur_row, 22)
                    sheet.write(cur_row, 1, 'Total Amount', total_label_fmt)
                    sheet.write(cur_row, 4, data['tot_wages'], total_num_fmt)
                    sheet.write(cur_row, 5, data['tot_ee_epf'], total_num_fmt)
                    sheet.write(cur_row, 6, data['tot_vpf'], total_num_fmt)
                    sheet.write(cur_row, 7, data.get('tot_pf_amount', round(data['tot_ee_epf'] + data['tot_vpf'], 2)), total_num_fmt)
                    sheet.write(cur_row, 8, data['tot_er_eps'], total_num_fmt)
                    sheet.write(cur_row, 9, data['tot_edli'], total_num_fmt)
                    sheet.write(cur_row, 10, data['tot_admin'], total_num_fmt)
                    sheet.write(cur_row, 11, data['tot_overall_contrib'], total_num_fmt)
                    cur_row += 1

                    # Empty row after totals
                    sheet.set_row(cur_row, 15)
                    cur_row += 1

                    # Footer Note
                    sheet.set_row(cur_row, 18)
                    sheet.write(cur_row, 0, 'Note: According to the EPFO Act, the minimum EPF administrative charges to be paid is Rs. 500.', note_fmt)
                else:
                    cur_row = 6
                    sheet.set_row(cur_row, 26)
                    sheet.merge_range(cur_row, 0, cur_row, 11, "No Data Is Available for the given date", empty_msg_fmt)
            else:
                sheet = workbook.add_worksheet('EPF Statement')
                sheet.set_column(0, 0, 22)  # SI NO / Name of Establishment
                sheet.set_column(1, 1, 22)  # UAN / Establishment ID / Total Members
                sheet.set_column(2, 2, 28)  # MEMBER NAME
                sheet.set_column(3, 3, 18)  # GROSS WAGES
                sheet.set_column(4, 4, 16)  # EPF WAGES
                sheet.set_column(5, 5, 16)  # EPS WAGES
                sheet.set_column(6, 6, 16)  # EDLI WAGES
                sheet.set_column(7, 7, 26)  # EPF CONTRIBUTION REMITTED
                sheet.set_column(8, 8, 26)  # EPS CONTRIBUTION REMITTED
                sheet.set_column(9, 9, 28)  # EPF EPS DIFFERENCE REMITTED
                sheet.set_column(10, 10, 14) # NCP DAYS
                sheet.set_column(11, 11, 24) # REFUND OF ADVANCES

                title_fmt = workbook.add_format({
                    'bold': True,
                    'align': 'center',
                    'valign': 'vcenter',
                    'font_size': 12,
                    'font_color': '#1F4E78',
                })
                epf_header_fmt = workbook.add_format({
                    'bold': True,
                    'bg_color': '#D9D9D9',
                    'font_color': '#000000',
                    'border': 1,
                    'align': 'center',
                    'valign': 'vcenter',
                    'text_wrap': True,
                    'font_size': 9,
                })

                # Row 1 (Index 0): Centered Heading Banner (e.g. EPF Statement October-2026)
                sheet.set_row(0, 24)
                month_name = dict(self._fields['month'].selection).get(self.month, '')
                sheet.merge_range(0, 0, 0, 11, f"EPF Statement {month_name}-{self.year}", title_fmt)

                # Row 2 (Index 1): Name of Establishment
                sheet.set_row(1, 20)
                sheet.write(1, 0, "Name of Establishment", meta_label_fmt)
                sheet.write(1, 1, data['est_name'], meta_val_fmt)

                # Row 3 (Index 2): Establishment ID
                sheet.set_row(2, 20)
                sheet.write(2, 0, "Establishment ID", meta_label_fmt)
                sheet.write_string(2, 1, str(data['est_id'] or '-'), meta_val_fmt)

                # Row 4 (Index 3): Total Members
                sheet.set_row(3, 20)
                sheet.write(3, 0, "Total Members", meta_label_fmt)
                sheet.write(3, 1, len(ecr_rows), meta_val_fmt)

                # Row 5 (Index 4): Table Headers
                sheet.set_row(4, 26)
                headers = [
                    'SI NO',
                    'UAN',
                    'MEMBER NAME',
                    'GROSS WAGES',
                    'EPF WAGES',
                    'EPS WAGES',
                    'EDLI WAGES',
                    'EPF CONTRIBUTION REMITTED',
                    'EPS CONTRIBUTION REMITTED',
                    'EPF EPS DIFFERENCE REMITTED',
                    'NCP DAYS',
                    'REFUND OF ADVANCES',
                ]
                for col_idx, text in enumerate(headers):
                    sheet.write(4, col_idx, text, epf_header_fmt)

                if ecr_rows:
                    # Rows 6+ (Index 5+): Data rows
                    for row_idx, r in enumerate(ecr_rows, start=1):
                        excel_row = row_idx + 4
                        sheet.write(excel_row, 0, row_idx, text_center_fmt)
                        sheet.write_string(excel_row, 1, str(r['uan'] or '-'), text_center_fmt)
                        sheet.write(excel_row, 2, r['name'], text_left_fmt)
                        sheet.write(excel_row, 3, r['gross'], num_fmt)
                        sheet.write(excel_row, 4, r['epf_wages'], num_fmt)
                        sheet.write(excel_row, 5, r['eps_wages'], num_fmt)
                        sheet.write(excel_row, 6, r['edli_wages'], num_fmt)
                        sheet.write(excel_row, 7, r['ee_epf'], num_fmt)
                        sheet.write(excel_row, 8, r['er_eps'], num_fmt)
                        sheet.write(excel_row, 9, r['er_epf'], num_fmt)
                        sheet.write(excel_row, 10, r['ncp_days'], text_center_fmt)
                        sheet.write(excel_row, 11, r['refund'], text_center_fmt)
                else:
                    sheet.set_row(5, 26)
                    sheet.merge_range(5, 0, 5, 11, "No Data Is Available for the given date", empty_msg_fmt)

            workbook.close()
            output.seek(0)
            xlsx_content = output.read()
        else:
            xlsx_content = txt_content.encode('utf-8')

        try:
            from odoo.tools import BinaryBytes# pyrefly: ignore [missing-import]
            txt_file_data = BinaryBytes(txt_content.encode('utf-8'), filename=txt_filename)
            xlsx_file_data = BinaryBytes(xlsx_content, filename=xlsx_filename)
        except Exception:
            txt_file_data = base64.b64encode(txt_content.encode('utf-8')).decode('utf-8')
            xlsx_file_data = base64.b64encode(xlsx_content).decode('utf-8')

        self.write({
            'state': 'generated',
            'txt_file': txt_file_data,
            'txt_filename': txt_filename,
            'xlsx_file': xlsx_file_data,
            'xlsx_filename': xlsx_filename,
            'record_count': len(ecr_rows),
            'total_epf_wages': tot_wages,
            'total_epf_deduction': tot_ee_epf,
            'total_eps_contribution': tot_er_eps,
            'total_epf_er_contribution': tot_er_epf,
        })

    def action_generate_ecr(self):
        self.ensure_one()
        self._generate_ecr_report_files()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=xlsx_file&filename_field=xlsx_filename&download=true',
            'target': 'self',
        }

    def action_export_xlsx(self):
        return self.action_generate_ecr()

    def action_download_txt(self):
        self.ensure_one()
        self._generate_ecr_report_files()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=txt_file&filename_field=txt_filename&download=true',
            'target': 'self',
        }

    def web_save(self, vals, specification: dict, next_id=None):
        res = super().web_save(vals, specification, next_id=next_id)
        for rec in self:
            try:
                rec._generate_ecr_report_files()
            except Exception:
                pass
        return res

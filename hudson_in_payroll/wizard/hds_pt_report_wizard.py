# -*- coding: utf-8 -*-
import base64
import calendar
import io
from datetime import date
from odoo import api, fields, models, _# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError# pyrefly: ignore [missing-import]

try:
    import xlsxwriter# pyrefly: ignore [missing-import]
except ImportError:
    xlsxwriter = None


class HdsPtReportWizard(models.Model):
    """
    Unified Professional Tax (PT) Report.
    Modeled in the exact same format and structure as the ESIC and Labour Statutory Reports.
    Provides monthly/periodic selection, multi-company and state filtering, Excel export, and live summary statistics.
    """
    _name = 'hds.pt.report.wizard'
    _description = 'Professional Tax (PT) Report'
    _order = 'id desc'

    @api.model
    def _default_year(self):
        return fields.Date.today().year

    @api.model
    def _default_month(self):
        return str(fields.Date.today().month)

    year = fields.Integer(
        string='Year',
        default=_default_year,
        required=True
    )
    month = fields.Selection([
        ('1', 'January'),
        ('2', 'February'),
        ('3', 'March'),
        ('4', 'April'),
        ('5', 'May'),
        ('6', 'June'),
        ('7', 'July'),
        ('8', 'August'),
        ('9', 'September'),
        ('10', 'October'),
        ('11', 'November'),
        ('12', 'December'),
    ], string='Month', default=_default_month, required=True)

    report_type = fields.Selection([
        ('pt_report', 'Professional Tax Register'),
        ('pt_summary', 'Monthly PT Summary'),
        ('pt_state_summary', 'State-wise PT Summary'),
    ], string='Report Type', default='pt_summary', required=True)

    payslip_state = fields.Selection([
        ('all', 'All States (Draft, Verify, Done, Paid)'),
        ('confirmed', 'Confirmed & Paid (Done, Paid)'),
    ], string='Payslip Status', default='all', required=True)

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    state_id = fields.Many2one(
        'res.country.state',
        string='Work State',
        domain="[('country_id.code', '=', 'IN')]",
        help="Optional state filter (e.g. Maharashtra, Karnataka, West Bengal)"
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee Filter',
        help="Optional employee filter"
    )

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
    ], string='State', default='draft')

    xlsx_file = fields.Binary(string='PT Excel File (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    record_count = fields.Integer(string='Total Employees Covered', readonly=True)
    total_pt_wages = fields.Float(string='Total Gross / PT Wages', readonly=True)
    total_pt_deduction = fields.Float(string='Total PT Deductions', readonly=True)

    @api.depends('month', 'year', 'report_type')
    def _compute_name(self):
        month_dict = dict(self._fields['month'].selection)
        report_dict = dict(self._fields['report_type'].selection)
        for rec in self:
            m_label = month_dict.get(rec.month, '')
            r_label = report_dict.get(rec.report_type, 'Monthly PT Summary')
            rec.name = f"{r_label} / {m_label}-{rec.year}"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            try:
                data = rec._get_pt_data()
                rec.write({
                    'record_count': data.get('record_count', 0),
                    'total_pt_wages': data.get('tot_wages', 0.0),
                    'total_pt_deduction': data.get('tot_pt', 0.0),
                })
            except Exception:
                pass
        return records

    def _get_date_range(self):
        self.ensure_one()
        year = int(self.year)
        month = int(self.month)
        last_day = calendar.monthrange(year, month)[1]
        date_from = date(year, month, 1)
        date_to = date(year, month, last_day)
        return date_from, date_to

    def _get_month_label(self):
        self.ensure_one()
        month_dict = dict(self._fields['month'].selection)
        return f"{month_dict.get(self.month, '')} {self.year}"

    def _get_employee_state_name(self, emp, contract=None):
        """Resolves employee work state cleanly from contract, work location, or employee profile."""
        if contract and hasattr(contract, 'hds_in_work_state_id') and contract.hds_in_work_state_id:
            return contract.hds_in_work_state_id.name or contract.hds_in_work_state_id.code or ''
        if emp.work_location_id and emp.work_location_id.address_id and emp.work_location_id.address_id.state_id:
            return emp.work_location_id.address_id.state_id.name or ''
        if emp.company_id and emp.company_id.state_id:
            return emp.company_id.state_id.name or ''
        return 'Not Specified'

    def _get_pt_data(self):
        self.ensure_one()
        date_from, date_to = self._get_date_range()

        state_sel = getattr(self, 'payslip_state', 'all')
        if state_sel == 'done':
            states = ['done']
        elif state_sel == 'paid':
            states = ['paid']
        elif state_sel == 'confirmed':
            states = ['done', 'paid']
        else:
            states = ['draft', 'verify', 'done', 'paid']

        domain = [
            ('state', 'in', states),
            ('company_id', '=', self.company_id.id),
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
            ('employee_id.hds_in_pt_applicable', '=', True),
        ]
        if self.employee_id:
            domain.append(('employee_id', '=', self.employee_id.id))

        all_slips = self.env['hr.payslip'].search(domain, order='date_to desc, id desc')

        # Filter payslips where employee or contract matches state_id if state_id is selected
        if self.state_id:
            filtered_slips = self.env['hr.payslip']
            for p in all_slips:
                emp_state = getattr(p.contract_id, 'hds_in_work_state_id', False) or (
                    p.employee_id.work_location_id.address_id.state_id if (p.employee_id.work_location_id and p.employee_id.work_location_id.address_id) else False
                ) or p.company_id.state_id
                if emp_state and emp_state.id == self.state_id.id:
                    filtered_slips |= p
            all_slips = filtered_slips

        priority = {'paid': 4, 'done': 3, 'verify': 2, 'draft': 1}
        best_slip_by_emp = {}
        for slip in all_slips:
            emp_id = slip.employee_id.id
            if emp_id not in best_slip_by_emp:
                best_slip_by_emp[emp_id] = slip
            else:
                curr_prio = priority.get(slip.state, 0)
                best_prio = priority.get(best_slip_by_emp[emp_id].state, 0)
                if curr_prio > best_prio:
                    best_slip_by_emp[emp_id] = slip

        payslips = self.env['hr.payslip'].browse([s.id for s in best_slip_by_emp.values()])

        if not payslips:
            raise UserError(_("No payslips found for the selected period (%s) matching criteria.") % self._get_month_label())

        # Pre-export statutory PT compliance validation
        from odoo.addons.hudson_in_payroll.services.compliance.statutory_compliance_service import StatutoryComplianceValidationService# pyrefly: ignore [missing-import]
        compliance_service = StatutoryComplianceValidationService(self.env)
        compliance_service.validate_scope_compliance(
            employees=payslips.mapped('employee_id'),
            statutory_type='pt',
            report_title='Professional Tax Report'
        )

        pt_rows = []
        tot_wages = 0.0
        tot_pt = 0.0

        for payslip in payslips:
            emp = payslip.employee_id
            lines = payslip.line_ids

            pt_lines = lines.filtered(lambda l: l.code in ('PT', 'PROF_TAX', 'PROFESSIONAL_TAX'))
            pt_amount = abs(sum(pt_lines.mapped('total'))) if pt_lines else 0.0

            gross_lines = lines.filtered(lambda l: l.code in ('PT_GROSS', 'PT_WAGE', 'GROSS'))
            gross_wage = abs(gross_lines[0].total) if gross_lines else (payslip.contract_id.wage if payslip.contract_id else 0.0)

            emp_code = emp.identification_id or getattr(emp, 'registration_number', False) or getattr(emp, 'barcode', False) or f"EMP{emp.id:04d}"
            state_name = self._get_employee_state_name(emp, payslip.contract_id)

            pt_rows.append({
                'employee_code': emp_code,
                'employee_name': emp.name or '',
                'state_name': state_name,
                'department': emp.department_id.name if emp.department_id else '',
                'gross_wage': round(gross_wage, 2),
                'pt_amount': round(pt_amount, 2),
                'payslip_number': payslip.number or payslip.name or '',
            })

            tot_wages += gross_wage
            tot_pt += pt_amount

        # State-wise grouping
        state_groups = {}
        for r in pt_rows:
            st = r['state_name']
            if st not in state_groups:
                state_groups[st] = {'count': 0, 'wages': 0.0, 'pt': 0.0}
            state_groups[st]['count'] += 1
            state_groups[st]['wages'] += r['gross_wage']
            state_groups[st]['pt'] += r['pt_amount']

        state_summary_rows = [
            {'state_name': st, 'count': d['count'], 'wages': round(d['wages'], 2), 'pt': round(d['pt'], 2)}
            for st, d in sorted(state_groups.items())
        ]

        return {
            'pt_rows': pt_rows,
            'state_summary_rows': state_summary_rows,
            'tot_wages': round(tot_wages, 2),
            'tot_pt': round(tot_pt, 2),
            'record_count': len(pt_rows),
            'company_name': self.company_id.name or '',
            'state_label': self.state_id.name if self.state_id else 'All Work States',
        }

    def action_print_pdf(self):
        self.ensure_one()
        data = self._get_pt_data()
        if not data.get('pt_rows'):
            raise UserError(_("No employee records found for the selected period (%s).") % self._get_month_label())
        return self.env.ref('hudson_in_payroll.action_report_pt').report_action(self)

    def action_generate_xlsx(self):
        self.ensure_one()
        data = self._get_pt_data()
        pt_rows = data['pt_rows']
        tot_wages = data['tot_wages']
        tot_pt = data['tot_pt']

        month_label = self._get_month_label().replace(' ', '_')
        xlsx_filename = f"Monthly_PT_Summary_{month_label}.xlsx"

        output = io.BytesIO()
        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet('Monthly PT Summary')

            # Ensure grid lines are visible on screen
            sheet.hide_gridlines(0)

            # Modern Styling Theme (matching LWF, ECR-ECF, and ESIC reports)
            title_fmt = workbook.add_format({
                'bold': True,
                'font_size': 18,
                'align': 'center',
                'valign': 'vcenter',
                'font_color': '#000000',
            })
            company_fmt = workbook.add_format({
                'font_size': 11,
                'valign': 'vcenter',
                'font_color': '#000000',
            })
            subheader_fmt = workbook.add_format({
                'font_size': 10,
                'valign': 'vcenter',
                'font_color': '#000000',
            })
            period_fmt = workbook.add_format({
                'font_size': 10,
                'align': 'right',
                'valign': 'vcenter',
                'font_color': '#000000',
            })
            header_fmt = workbook.add_format({
                'bold': True,
                'bg_color': '#E0E0E0',
                'font_color': '#000000',
                'font_size': 10,
                'border': 1,
                'border_color': '#D9D9D9',
                'align': 'left',
                'valign': 'vcenter',
            })
            header_center_fmt = workbook.add_format({
                'bold': True,
                'bg_color': '#E0E0E0',
                'font_color': '#000000',
                'font_size': 10,
                'border': 1,
                'border_color': '#D9D9D9',
                'align': 'center',
                'valign': 'vcenter',
            })
            header_right_fmt = workbook.add_format({
                'bold': True,
                'bg_color': '#E0E0E0',
                'font_color': '#000000',
                'font_size': 10,
                'border': 1,
                'border_color': '#D9D9D9',
                'align': 'right',
                'valign': 'vcenter',
            })
            text_fmt = workbook.add_format({
                'font_size': 10,
                'border': 1,
                'border_color': '#D9D9D9',
                'valign': 'vcenter',
                'align': 'left',
            })
            center_fmt = workbook.add_format({
                'font_size': 10,
                'border': 1,
                'border_color': '#D9D9D9',
                'valign': 'vcenter',
                'align': 'center',
            })
            curr_fmt = workbook.add_format({
                'font_size': 10,
                'num_format': '#,##0.00',
                'border': 1,
                'border_color': '#D9D9D9',
                'align': 'right',
                'valign': 'vcenter',
            })
            tot_label_fmt = workbook.add_format({
                'bold': True,
                'font_size': 10,
                'bg_color': '#E0E0E0',
                'border': 1,
                'border_color': '#D9D9D9',
                'valign': 'vcenter',
                'align': 'center',
            })
            tot_num_fmt = workbook.add_format({
                'bold': True,
                'font_size': 10,
                'bg_color': '#E0E0E0',
                'border': 1,
                'border_color': '#D9D9D9',
                'num_format': '#,##0.00',
                'align': 'right',
                'valign': 'vcenter',
            })

            # Row 1 (Index 0): Merged Title A1:G1
            sheet.merge_range(0, 0, 0, 6, "Professional Tax Monthly Summary", title_fmt)
            sheet.set_row(0, 36)

            # Row 2 (Index 1): Company Name in A2
            sheet.write(1, 0, self.company_id.name or '', company_fmt)
            sheet.set_row(1, 20)

            # Row 3 (Index 2): PT Registration No in A3, Period in F3:G3
            pt_reg = (
                getattr(self.company_id, 'hds_in_professional_tax_registration_no', False)
                or getattr(self.company_id, 'hds_in_pt_registration_no', False)
                or getattr(self.company_id, 'pt_registration_no', False)
                or ''
            )
            pt_reg_text = f"PT Registration No: {pt_reg}" if pt_reg else "PT Registration No:"
            sheet.write(2, 0, pt_reg_text, subheader_fmt)
            period_str = f"Period: {self._get_month_label()}"
            sheet.merge_range(2, 5, 2, 6, period_str, period_fmt)
            sheet.set_row(2, 20)

            # Column widths
            sheet.set_column(0, 0, 6)   # Sr.
            sheet.set_column(1, 1, 16)  # Employee ID
            sheet.set_column(2, 2, 26)  # Employee Name
            sheet.set_column(3, 3, 22)  # Department
            sheet.set_column(4, 4, 20)  # Work State
            sheet.set_column(5, 5, 22)  # Gross Salary (INR)
            sheet.set_column(6, 6, 22)  # PT Deduction (INR)

            # Row 4 (Index 3): Column Headers
            headers = [
                ('Sr.', header_center_fmt),
                ('Employee ID', header_fmt),
                ('Employee Name', header_fmt),
                ('Department', header_fmt),
                ('Work State', header_fmt),
                ('Gross Salary (INR)', header_right_fmt),
                ('PT Deduction (INR)', header_right_fmt),
            ]
            sheet.set_row(3, 26)
            for col_idx, (text, fmt) in enumerate(headers):
                sheet.write(3, col_idx, text, fmt)

            # Rows 5+ (Index 4+): Data Rows
            for idx, r in enumerate(pt_rows, start=1):
                row_idx = 3 + idx
                sheet.set_row(row_idx, 20)
                sheet.write(row_idx, 0, idx, center_fmt)
                sheet.write(row_idx, 1, r.get('employee_code', '') or '', text_fmt)
                sheet.write(row_idx, 2, r.get('employee_name', '') or '', text_fmt)
                sheet.write(row_idx, 3, r.get('department', '') or '', text_fmt)
                sheet.write(row_idx, 4, r.get('state_name', '') or '', text_fmt)
                sheet.write(row_idx, 5, r.get('gross_wage', 0.0), curr_fmt)
                sheet.write(row_idx, 6, r.get('pt_amount', 0.0), curr_fmt)

            # Total Row
            tot_row_idx = 4 + len(pt_rows)
            sheet.set_row(tot_row_idx, 22)
            sheet.write(tot_row_idx, 0, 'TOTAL', tot_label_fmt)
            for c in range(1, 5):
                sheet.write(tot_row_idx, c, '', tot_label_fmt)
            sheet.write(tot_row_idx, 5, round(tot_wages, 2), tot_num_fmt)
            sheet.write(tot_row_idx, 6, round(tot_pt, 2), tot_num_fmt)

            # Optional Sheet 2: State-wise Summary (if multiple states exist)
            if len(data.get('state_summary_rows', [])) > 1:
                st_sheet = workbook.add_worksheet('State-wise Summary')
                st_sheet.hide_gridlines(0)

                st_sheet.merge_range(0, 0, 0, 3, "Professional Tax - State-wise Summary", title_fmt)
                st_sheet.set_row(0, 36)

                st_sheet.write(1, 0, self.company_id.name or '', company_fmt)
                st_sheet.set_row(1, 20)

                st_sheet.write(2, 0, f"Period: {self._get_month_label()}", subheader_fmt)
                st_sheet.set_row(2, 20)

                st_sheet.set_column(0, 0, 26)  # Work State
                st_sheet.set_column(1, 1, 18)  # Employee Count
                st_sheet.set_column(2, 2, 24)  # Total Gross Wages (INR)
                st_sheet.set_column(3, 3, 24)  # Total PT Deductions (INR)

                st_headers = [
                    ('Work State', header_fmt),
                    ('Employee Count', header_center_fmt),
                    ('Total Gross Wages (INR)', header_right_fmt),
                    ('Total PT Deductions (INR)', header_right_fmt),
                ]
                st_sheet.set_row(3, 26)
                for c_idx, (t_text, t_fmt) in enumerate(st_headers):
                    st_sheet.write(3, c_idx, t_text, t_fmt)

                for s_idx, s in enumerate(data['state_summary_rows'], start=1):
                    s_row = 3 + s_idx
                    st_sheet.set_row(s_row, 20)
                    st_sheet.write(s_row, 0, s['state_name'], text_fmt)
                    st_sheet.write(s_row, 1, s['count'], center_fmt)
                    st_sheet.write(s_row, 2, s['wages'], curr_fmt)
                    st_sheet.write(s_row, 3, s['pt'], curr_fmt)

                s_tot_row = 4 + len(data['state_summary_rows'])
                st_sheet.set_row(s_tot_row, 22)
                st_sheet.write(s_tot_row, 0, 'TOTAL', tot_label_fmt)
                st_sheet.write(s_tot_row, 1, len(pt_rows), tot_label_fmt)
                st_sheet.write(s_tot_row, 2, round(tot_wages, 2), tot_num_fmt)
                st_sheet.write(s_tot_row, 3, round(tot_pt, 2), tot_num_fmt)

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
            'record_count': len(pt_rows),
            'total_pt_wages': tot_wages,
            'total_pt_deduction': tot_pt,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=xlsx_file&filename_field=xlsx_filename&download=true',
            'target': 'new',
        }

    def action_download_xlsx(self):
        self.ensure_one()
        if not self.xlsx_file:
            return self.action_generate_xlsx()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=xlsx_file&filename_field=xlsx_filename&download=true',
            'target': 'new',
        }

    @api.onchange('month', 'year', 'payslip_state', 'company_id')
    def _onchange_report_filters(self):
        try:
            data = self._get_pt_data()
            self.record_count = data.get('record_count', 0)
            self.total_pt_wages = data.get('tot_wages', 0.0)
            self.total_pt_deduction = data.get('tot_pt', 0.0)
        except Exception:
            pass


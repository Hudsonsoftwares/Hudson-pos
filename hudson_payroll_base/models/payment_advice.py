import base64
import csv
import io
import re
from datetime import date
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError

try:
    # pyrefly: ignore [missing-import]
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HudsonPayrollPaymentAdvice(models.Model):
    """Bank Payment Advice statement generated from a pay run for salary disbursement."""
    _name = 'hudson.payroll.payment.advice'
    _description = 'Payroll Payment Advice'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Advice Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    payslip_run_id = fields.Many2one(
        'hr.payslip.run',
        string='Pay Run',
        required=False,
        ondelete='cascade',
        readonly=True
    )
    payslip_id = fields.Many2one(
        'hr.payslip',
        string='Payslip',
        required=False,
        ondelete='cascade',
        readonly=True
    )
    date = fields.Date(
        string='Advice Date',
        required=True,
        default=fields.Date.context_today
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    company_partner_id = fields.Many2one(
        'res.partner',
        string='Company Partner',
        related='company_id.partner_id',
        readonly=True
    )
    company_bank_id = fields.Many2one(
        'res.partner.bank',
        string='Disbursing Bank Account',
        domain="[('partner_id', '=', company_partner_id), '|', ('company_id', '=', company_id), ('company_id', '=', False)]",
        check_company=True,
        help="Select the company bank account used to disburse salaries"
    )
    payment_method = fields.Selection([
        ('enet_rtgs', 'ENet RTGS'),
        ('enet_neft', 'ENet NEFT'),
        ('enet_fund_transfer', 'ENet Fund Transfer'),
        ('enet_demand_draft', 'ENet Demand Draft'),
        ('enet_intra', 'ENet Intra'),
    ], string='Payment Method', default='enet_rtgs')
    enet_transaction_type = fields.Selection([
        ('auto', 'Auto (Smart Route: IFT / RTGS / NEFT)'),
        ('ift', 'IFT (Internal Fund Transfer - Within HDFC)'),
        ('neft', 'NEFT (Inter-Bank)'),
        ('rtgs', 'RTGS (High Value >= 2 Lakhs)'),
        ('imps', 'IMPS (Immediate Payment Service)'),
    ], string='ENet Transaction Type', default='auto')
    enet_client_code = fields.Char(string='Corporate / Client Code')
    line_ids = fields.One2many(
        'hudson.payroll.payment.advice.line',
        'advice_id',
        string='Payment Lines'
    )
    total_amount = fields.Float(
        string='Total Disbursed',
        compute='_compute_total_amount',
        store=True,
        digits='Payroll'
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
    ], string='Status', default='draft', tracking=True)

    note = fields.Text(string='Notes / Instructions')

    @api.depends('line_ids.net_amount')
    def _compute_total_amount(self):
        for advice in self:
            advice.total_amount = sum(advice.line_ids.mapped('net_amount'))

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.company_id:
            banks = self.company_id.partner_id.bank_ids.filtered(lambda b: not b.company_id or b.company_id == self.company_id)
            if self.company_bank_id and self.company_bank_id not in banks:
                self.company_bank_id = banks[:1] or False
            elif not self.company_bank_id:
                self.company_bank_id = banks[:1] or False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hudson.payroll.payment.advice') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        return self.write({'state': 'confirmed'})

    def action_set_to_draft(self):
        return self.write({'state': 'draft'})

    @staticmethod
    def _get_employee_code(emp):
        """Safely extracts employee code across standard and custom employee models."""
        if not emp:
            return ''
        return (
            getattr(emp, 'registration_number', False)
            or getattr(emp, 'barcode', False)
            or getattr(emp, 'identification_id', False)
            or getattr(emp, 'biometric_code', False)
            or str(emp.id)
        )

    def _create_download_attachment(self, filename, content, mimetype):
        """Creates an ir.attachment storing content via raw or datas depending on Odoo version."""
        attach_vals = {
            'name': filename,
            'res_model': self._name,
            'res_id': self.id,
            'type': 'binary',
            'mimetype': mimetype,
        }
        if 'raw' in self.env['ir.attachment']._fields:
            attach_vals['raw'] = content
        else:
            attach_vals['datas'] = base64.b64encode(content)
        return self.env['ir.attachment'].create(attach_vals)

    def action_export_csv(self):
        """Generates a bank-ready generic CSV disbursement statement and returns a download action."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("No payment advice lines found to export."))

        output = io.StringIO()
        writer = csv.writer(output, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)

        def fmt_date(value):
            return value.strftime('%d/%m/%Y') if value else ''

        # Header row (Odoo Online payment advice CSV; BIC is the IFSC code)
        writer.writerow([
            'Sequence',
            'Payment Date',
            'Report Date',
            'Payment Period',
            'Employee name',
            'Bank account',
            'IFSC',
            'Amount to pay',
        ])

        report_date = fields.Date.context_today(self)
        run = self.payslip_run_id
        for idx, line in enumerate(self.line_ids, start=1):
            slip = line.payslip_id or self.payslip_id
            period_start = slip.date_from if slip else (run.date_start if run else False)
            period_end = slip.date_to if slip else (run.date_end if run else False)
            period = f"{fmt_date(period_start)} - {fmt_date(period_end)}" if period_start and period_end else ''
            writer.writerow([
                idx,
                fmt_date(self.date),
                fmt_date(report_date),
                period,
                line.employee_id.name or '',
                line.acc_number or '',
                self._get_line_ifsc(line),
                f"{line.net_amount or 0.0:,.2f}",
            ])

        csv_content = output.getvalue().encode('utf-8-sig')
        output.close()

        clean_name = re.sub(r'[\\/*?:"<>|]', '_', self.name or 'Payment_Advice').replace(' ', '_')
        filename = f"Payment_Advice_{clean_name}.csv"
        attachment = self._create_download_attachment(filename, csv_content, 'text/csv')

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def _get_enet_transaction_type(self, line, chosen_mode=None):
        """Evaluates ENet transaction type based on payment_method or explicit transaction type."""
        mode = chosen_mode or self.payment_method or self.enet_transaction_type or 'enet_rtgs'
        tx_map = {
            'enet_rtgs': 'RTGS',
            'enet_neft': 'NEFT',
            'enet_fund_transfer': 'FT',
            'enet_demand_draft': 'DD',
            'enet_intra': 'INTRA',
        }
        if mode in tx_map:
            return tx_map[mode]
        elif mode and mode.upper() in ('RTGS', 'NEFT', 'FT', 'DD', 'INTRA', 'IFT', 'IMPS'):
            return mode.upper()

        emp_bic = (line.bank_bic or '').strip().upper()
        co_bank = self.company_bank_id
        co_bic = (getattr(co_bank, 'bank_bic', '') or '').strip().upper() if co_bank else ''

        # Smart Routing: Within HDFC or same bank BIC prefix -> INTRA
        if emp_bic.startswith('HDFC') or (co_bic and emp_bic.startswith(co_bic[:4])):
            return 'INTRA'
        # Inter-bank high-value >= 2 Lakhs -> RTGS
        elif (line.net_amount or 0.0) >= 200000.0:
            return 'RTGS'
        # Standard inter-bank -> NEFT
        else:
            return 'NEFT'

    @staticmethod
    def _get_line_ifsc(line):
        """IFSC code of the employee's bank account: BIC/SWIFT field, else the stored line value, else Clearing Number."""
        bank_acc = line.bank_account_id
        return (
            getattr(bank_acc, 'bank_bic', False)
            or line.bank_bic
            or getattr(bank_acc, 'clearing_number', False)
            or ''
        ).strip()

    @staticmethod
    def _format_enet_amount(amount):
        """Bank upload amount without thousands separators or trailing zeros: 10945, 268171.67."""
        text = f"{amount or 0.0:.2f}"
        return text.rstrip('0').rstrip('.') if '.' in text else text

    def _get_customer_reference_number(self):
        """
        Derives the Customer Reference Number for ENet RTGS upload in the format:
        PAYORDER/OUT/<MM-YYYY>/<number> (e.g. PAYORDER/OUT/10-2026/013).
        Dynamically extracted from the advice date and advice sequence number/id without hardcoding.
        """
        self.ensure_one()
        advice_date = self.date or date.today()
        period_str = advice_date.strftime('%m-%Y')

        seq_num = None
        if self.name and self.name != _('New'):
            digits = re.findall(r'\d+', self.name)
            if digits:
                try:
                    seq_num = int(digits[-1])
                except (ValueError, TypeError):
                    pass
        if seq_num is None:
            seq_num = self.id or 1

        return f"PAYORDER/OUT/{period_str}/{seq_num:03d}"

    def action_export_enet(self, payment_method=None, enet_tx_type=None, narration=None):
        """Generates HDFC ENet CMS formatted bulk salary upload CSV file."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("No payment advice lines found to export."))

        mode_tx = payment_method or enet_tx_type or self.payment_method or self.enet_transaction_type or 'enet_rtgs'
        val_date_str = (self.date or date.today()).strftime('%d/%m/%Y')
        customer_ref = self._get_customer_reference_number()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)

        # HDFC ENet CMS bulk upload header (28 standard banking columns)
        writer.writerow([
            'Transaction Type',
            'Beneficiary Code',
            'Beneficiary Account Number',
            'Amount',
            'Beneficiary Name',
            'Drawee Location',
            'DD Printing Location',
            'Beneficiary Address 1',
            'Beneficiary Address 2',
            'Beneficiary Address 3',
            'Beneficiary Address 4',
            'Beneficiary Address 5',
            'Instruction Reference Number',
            'Customer Reference Number',
            'Payment Details 1',
            'Payment Details 2',
            'Payment Details 3',
            'Payment Details 4',
            'Payment Details 5',
            'Payment Details 6',
            'Payment Details 7',
            'Cheque Number',
            'Value Date',
            'MICR Number',
            'IFSC Code',
            'Beneficiary Bank Name',
            'Beneficiary Bank Branch Name',
            'Beneficiary Email ID',
        ])

        for idx, line in enumerate(self.line_ids, start=1):
            emp = line.employee_id
            writer.writerow([
                self._get_enet_transaction_type(line, chosen_mode=mode_tx),  # Transaction Type
                idx,                                                         # Beneficiary Code
                line.acc_number or '',                                       # Beneficiary Account Number
                self._format_enet_amount(line.net_amount),                   # Amount
                (emp.name or '').replace(',', ' ').strip(),                  # Beneficiary Name
                '', '',                                                      # Drawee / DD Printing Location (DD only)
                '', '', '', '', '',                                          # Beneficiary Address 1-5
                '',                                                          # Instruction Reference Number
                customer_ref,                                                # Customer Reference Number
                '', '', '', '', '', '', '',                                  # Payment Details 1-7
                '',                                                          # Cheque Number
                val_date_str,                                                # Value Date
                '',                                                          # MICR Number
                self._get_line_ifsc(line),                                   # IFSC Code
                '',                                                          # Beneficiary Bank Name
                '',                                                          # Beneficiary Bank Branch Name
                emp.work_email or '',                                        # Beneficiary Email ID
            ])

        csv_content = output.getvalue().encode('utf-8-sig')
        output.close()

        clean_name = re.sub(r'[\\/*?:"<>|]', '_', self.name or 'Salary_Upload').replace(' ', '_')
        filename = f"ENet_Salary_Upload_{clean_name}.csv"
        attachment = self._create_download_attachment(filename, csv_content, 'text/csv')

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_export_xlsx(self):
        """Generates and downloads a formatted Excel (.xlsx) file."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("No payment advice lines found to export."))
        if not self.company_bank_id:
            raise UserError(_("Company Bank Account is mandatory. Please select or configure a Company Bank Account before generating the Excel Payment Advice."))

        if not xlsxwriter:
            return self.action_export_csv()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Payment Advice')

        # Amount format in the company currency, e.g. ₹10,945.00 (symbol taken from the currency, not hardcoded)
        currency = self.company_id.currency_id
        symbol = (currency.symbol or '').replace('"', '')
        if symbol and currency.position == 'after':
            amount_format = f'#,##0.00"{symbol}"'
        elif symbol:
            amount_format = f'"{symbol}"#,##0.00'
        else:
            amount_format = '#,##0.00'

        fmt_bold = workbook.add_format({'bold': True})
        fmt_header = workbook.add_format({'bold': True, 'bg_color': '#D9D9D9', 'valign': 'vcenter'})
        fmt_cell = workbook.add_format({'valign': 'vcenter'})
        fmt_text = workbook.add_format({'valign': 'vcenter', 'num_format': '@'})
        fmt_serial = workbook.add_format({'valign': 'vcenter', 'align': 'left'})
        fmt_amount = workbook.add_format({'valign': 'vcenter', 'num_format': amount_format})
        fmt_total_label = workbook.add_format({'bold': True})
        fmt_total_amount = workbook.add_format({'bold': True, 'num_format': amount_format})

        worksheet.set_column('A:A', 10)
        worksheet.set_column('B:B', 26)
        worksheet.set_column('C:C', 8)
        worksheet.set_column('D:D', 26)
        worksheet.set_column('E:E', 20)
        worksheet.set_column('F:F', 20)

        target_name = self.payslip_id.name if self.payslip_id else (self.payslip_run_id.name if self.payslip_run_id else self.name)
        comp_bank_acc = (getattr(self.company_bank_id, 'account_number', False) or getattr(self.company_bank_id, 'acc_number', '')) or ''

        # Company details
        worksheet.write_string(0, 0, _("Company Name : %s") % (self.company_id.name or ''), fmt_bold)
        worksheet.write_string(1, 0, _("Company Bank Account : %s") % comp_bank_acc, fmt_bold)

        # Column headers
        headers = [_("Sl No."), _("Name Of Employee"), _("C/D"), _("Bank Account No."), _("IFSC Code"), _("By Salary")]
        for col, header in enumerate(headers):
            worksheet.write_string(2, col, header, fmt_header)

        # One line per employee; account numbers as text so long numbers / leading zeros are kept
        row = 3
        first_amount_row = row
        total_net = 0.0
        for idx, line in enumerate(self.line_ids, start=1):
            ifsc = self._get_line_ifsc(line)
            worksheet.write_number(row, 0, idx, fmt_serial)
            worksheet.write_string(row, 1, line.employee_id.name or '', fmt_cell)
            worksheet.write_string(row, 2, 'C', fmt_cell)
            worksheet.write_string(row, 3, line.acc_number or '', fmt_text)
            worksheet.write_string(row, 4, ifsc, fmt_text)
            worksheet.write_number(row, 5, line.net_amount or 0.0, fmt_amount)
            total_net += (line.net_amount or 0.0)
            row += 1
        last_amount_row = row - 1

        # Total, two empty rows below the last employee
        total_row = row + 2
        worksheet.write_string(total_row, 4, _("Total:"), fmt_total_label)
        worksheet.write_formula(
            total_row, 5,
            f"=SUM(F{first_amount_row + 1}:F{last_amount_row + 1})",
            fmt_total_amount,
            total_net,
        )

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        clean_target = re.sub(r'[\\/*?:"<>|]', '_', target_name or 'Payment_Advice').replace(' ', '_')
        filename = f"Payment_Advice_{clean_target}.xlsx"
        attachment = self._create_download_attachment(
            filename,
            xlsx_data,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    @staticmethod
    def _format_long_date(value):
        """1 January 2027 (no leading zero on the day, works on Windows too)."""
        return f"{value.day} {value.strftime('%B %Y')}" if value else ''

    def get_period_label(self):
        """'1 January 2027 to 31 January 2027' from the pay run (or single payslip) period."""
        self.ensure_one()
        if self.payslip_run_id and self.payslip_run_id.date_start and self.payslip_run_id.date_end:
            start, end = self.payslip_run_id.date_start, self.payslip_run_id.date_end
        elif self.payslip_id and self.payslip_id.date_from and self.payslip_id.date_to:
            start, end = self.payslip_id.date_from, self.payslip_id.date_to
        else:
            return ''
        return _("%(start)s to %(end)s") % {
            'start': self._format_long_date(start),
            'end': self._format_long_date(end),
        }

    def get_amount_in_words(self):
        """Total amount in words; Indian numbering (lakh/crore) for INR, Odoo's standard text otherwise."""
        self.ensure_one()
        currency = self.company_id.currency_id
        amount = self.total_amount or 0.0
        if currency.name != 'INR':
            return currency.amount_to_text(amount)
        try:
            from num2words import num2words
        except ImportError:
            return currency.amount_to_text(amount)

        integral, _sep, fractional = f"{amount:.{currency.decimal_places}f}".partition('.')
        unit = (currency.currency_unit_label or currency.name or '').lower()
        subunit = (currency.currency_subunit_label or '').lower()
        words = f"{num2words(int(integral), lang='en_IN')} {unit}".strip()
        if fractional and int(fractional) and subunit:
            words += f" and {num2words(int(fractional), lang='en_IN')} {subunit}"
        return words

    def action_print_pdf(self):
        self.ensure_one()
        if not self.company_bank_id:
            raise UserError(_("Company Bank Account is mandatory. Please select or configure a Company Bank Account before generating the PDF Payment Advice."))
        return self.env.ref('hudson_payroll_base.action_report_payment_advice').report_action(self)


class HudsonPayrollPaymentAdviceLine(models.Model):
    """Line item representing an individual employee bank disbursement."""
    _name = 'hudson.payroll.payment.advice.line'
    _description = 'Payroll Payment Advice Line'
    _order = 'employee_id'

    advice_id = fields.Many2one(
        'hudson.payroll.payment.advice',
        string='Payment Advice',
        required=True,
        ondelete='cascade',
        index=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='advice_id.company_id',
        store=True,
        readonly=True,
        index=True
    )
    payslip_id = fields.Many2one(
        'hr.payslip',
        string='Payslip',
        required=True,
        ondelete='cascade'
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True
    )
    department_id = fields.Many2one(
        'hr.department',
        related='employee_id.department_id',
        string='Department',
        store=True,
        readonly=True
    )
    bank_account_id = fields.Many2one(
        'res.partner.bank',
        string='Bank Account',
        compute='_compute_bank_details',
        store=True,
        readonly=False
    )
    bank_name = fields.Char(
        string='Bank Name',
        compute='_compute_bank_details',
        store=True,
        readonly=False
    )
    acc_number = fields.Char(
        string='Account Number',
        compute='_compute_bank_details',
        store=True,
        readonly=False
    )
    bank_bic = fields.Char(
        string='IFSC / BIC / Routing',
        compute='_compute_bank_details',
        store=True,
        readonly=False
    )
    net_amount = fields.Float(
        string='Net Payable Amount',
        digits='Payroll',
        default=0.0
    )
    has_bank_account = fields.Boolean(
        string='Bank Configured',
        compute='_compute_bank_details',
        store=True
    )

    @api.depends('employee_id', 'payslip_id')
    def _compute_bank_details(self):
        for line in self:
            slip = line.payslip_id
            bank_acc = False
            if slip and slip.bank_account_id:
                bank_acc = slip.bank_account_id
            elif line.employee_id:
                emp = line.employee_id
                bank_acc = getattr(emp, 'bank_account_id', False) or (emp.bank_account_ids and emp.bank_account_ids[0]) or False
            line.bank_account_id = bank_acc
            bank_name = (getattr(bank_acc, 'bank_name', '') or getattr(bank_acc, 'acc_holder_name', '')) if bank_acc else ''
            line.bank_name = bank_name or line.bank_name or ''
            bank_num = (getattr(bank_acc, 'account_number', False) or getattr(bank_acc, 'acc_number', '')) if bank_acc else ''
            line.acc_number = bank_num or line.acc_number or ''
            bic = (getattr(bank_acc, 'bank_bic', '') or getattr(bank_acc, 'routing_number', '')) if bank_acc else ''
            line.bank_bic = bic or line.bank_bic or ''
            line.has_bank_account = bool(line.acc_number)

# -*- coding: utf-8 -*-
import base64
import io
from datetime import date
from odoo import api, fields, models, _
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HudsonPayrollPayRunPayWizard(models.TransientModel):
    """Wizard to execute Pay Run / Payslip payment, generate bank payment advice, Cheque, NEFT, PDF and XLSX."""
    _name = 'hr.payslip.run.pay.wizard'
    _description = 'Pay Run / Payslip Payment Wizard'

    payslip_run_id = fields.Many2one(
        'hr.payslip.run',
        string='Pay Run',
        required=False,
        readonly=True,
    )
    payslip_id = fields.Many2one(
        'hr.payslip',
        string='Payslip',
        required=False,
        readonly=True,
    )
    mode = fields.Selection([
        ('advice', 'Payment Advice'),
        ('manual', 'Manually'),
        ('csv', 'CSV'),
        ('enet', 'ENet'),
    ], string='Mode', default='advice', required=True)

    payment_method = fields.Selection([
        ('enet_rtgs', 'ENet RTGS'),
        ('enet_neft', 'ENet NEFT'),
        ('enet_fund_transfer', 'ENet Fund Transfer'),
        ('enet_demand_draft', 'ENet Demand Draft'),
        ('enet_intra', 'ENet Intra'),
    ], string='Payment Method', default='enet_rtgs')

    payment_date = fields.Date(
        string='Payment Date',
        required=True,
        default=fields.Date.context_today,
        help="Date on which the salary disbursement will be executed."
    )
    include_unpaid = fields.Boolean(
        string='Include Unpaid',
        default=True,
        help="Include payslips that have not yet been marked as paid."
    )
    report_name = fields.Char(
        string='Report Name',
        help="Custom name for the generated payment report or advice."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        compute='_compute_company_id',
        store=True,
        readonly=True
    )
    company_partner_id = fields.Many2one(
        'res.partner',
        string='Company Partner',
        related='company_id.partner_id',
        readonly=True
    )
    company_bank_id = fields.Many2one(
        'res.partner.bank',
        string='Company Bank Account',
        domain="['|', ('partner_id', '=', company_partner_id), ('company_id', '=', company_id)]",
        check_company=True,
        help="Disbursing bank account of the company."
    )
    by_cheque = fields.Boolean(
        string='By Cheque',
        default=False
    )
    cheque_number = fields.Char(
        string='Cheque Number',
        help="Reference number of the corporate disbursement cheque."
    )
    cheque_date = fields.Date(
        string='Cheque Date',
        default=fields.Date.context_today,
        help="Date printed on the disbursement cheque."
    )
    by_neft = fields.Boolean(
        string='By NEFT',
        default=True,
        help="Process electronic bank transfer via NEFT / RTGS / IMPS."
    )
    missing_bank_employee_count = fields.Integer(
        string='Missing Bank Employee Count',
        compute='_compute_missing_bank_employees',
    )
    missing_bank_employee_names = fields.Char(
        string='Employees Without Bank Account',
        compute='_compute_missing_bank_employees',
    )

    @api.depends('payslip_run_id', 'payslip_id')
    def _compute_company_id(self):
        for wiz in self:
            if wiz.payslip_run_id:
                wiz.company_id = wiz.payslip_run_id.company_id
            elif wiz.payslip_id:
                wiz.company_id = wiz.payslip_id.company_id
            else:
                wiz.company_id = self.env.company

    @api.depends('payslip_run_id', 'payslip_run_id.slip_ids', 'payslip_id', 'include_unpaid')
    def _compute_missing_bank_employees(self):
        for wiz in self:
            if wiz.payslip_id:
                slips = wiz.payslip_id
            elif wiz.payslip_run_id:
                slips = wiz.payslip_run_id.slip_ids.filtered(lambda s: s.state in ('done', 'paid'))
            else:
                slips = self.env['hr.payslip']
            if not wiz.include_unpaid:
                slips = slips.filtered(lambda s: not getattr(s, 'paid', False))
            missing = slips.filtered(lambda s: not s.has_bank_account)
            wiz.missing_bank_employee_count = len(missing)
            wiz.missing_bank_employee_names = ", ".join(missing.mapped('employee_id.name')) if missing else False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # 1. Check individual payslip context
        slip_id = self.env.context.get('default_payslip_id')
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')
        if not slip_id and active_model == 'hr.payslip' and active_id:
            slip_id = active_id
        
        if slip_id:
            slip = self.env['hr.payslip'].browse(slip_id).exists()
            if slip:
                res['payslip_id'] = slip.id
                if slip.payslip_run_id:
                    res['payslip_run_id'] = slip.payslip_run_id.id
                if 'report_name' in fields_list and not res.get('report_name'):
                    res['report_name'] = f"Payment Advice - {slip.name}"
                company = slip.company_id or self.env.company
                bank_acc = company.partner_id.bank_ids and company.partner_id.bank_ids.filtered(lambda b: not b.company_id or b.company_id == company)[:1] or False
                if not bank_acc:
                    bank_acc = self.env['res.partner.bank'].search([
                        '|', ('partner_id', '=', company.partner_id.id), ('company_id', '=', company.id),
                    ], limit=1)
                if bank_acc and 'company_bank_id' in fields_list:
                    res['company_bank_id'] = bank_acc.id
                return res

        # 2. Check pay run context
        active_run_id = self.env.context.get('default_payslip_run_id') or (active_id if active_model == 'hr.payslip.run' else False)
        if active_run_id:
            run = self.env['hr.payslip.run'].browse(active_run_id).exists()
            if run:
                res['payslip_run_id'] = run.id
                if 'report_name' in fields_list and not res.get('report_name'):
                    res['report_name'] = f"Payment Advice - {run.name}"
                company = run.company_id or self.env.company
                bank_acc = getattr(run, 'company_bank_id', False)
                if not bank_acc:
                    bank_acc = company.partner_id.bank_ids and company.partner_id.bank_ids.filtered(lambda b: not b.company_id or b.company_id == company)[:1] or False
                if not bank_acc:
                    bank_acc = self.env['res.partner.bank'].search([
                        '|', ('partner_id', '=', company.partner_id.id), ('company_id', '=', company.id),
                    ], limit=1)
                if bank_acc and 'company_bank_id' in fields_list:
                    res['company_bank_id'] = bank_acc.id
        return res

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.company_id and not self.company_bank_id:
            company = self.company_id
            bank_acc = company.partner_id.bank_ids and company.partner_id.bank_ids.filtered(lambda b: not b.company_id or b.company_id == company)[:1] or False
            if not bank_acc:
                bank_acc = self.env['res.partner.bank'].search([
                    '|', ('partner_id', '=', company.partner_id.id), ('company_id', '=', company.id),
                ], limit=1)
            if bank_acc:
                self.company_bank_id = bank_acc

    def _ensure_payment_advice(self):
        """Creates or updates the payment advice with current run's or payslip's lines."""
        self.ensure_one()
        if self.mode == 'advice' and not self.company_bank_id:
            raise UserError(_("Company Bank Account is mandatory. Please select or add a Company Bank Account before generating Payment Advice, PDF, or Excel."))

        if self.payslip_id:
            if self.payslip_id.state not in ('done', 'paid'):
                raise UserError(_("Only validated payslips can be paid. Please validate payslip '%(slip)s' first.")
                                % {'slip': self.payslip_id.name})
            slips_to_include = self.payslip_id
        elif self.payslip_run_id:
            run = self.payslip_run_id
            if not run.slip_ids:
                raise UserError(_("No payslips found in this pay run to process payment."))
            # Only validated slips; cancelled ones are skipped, draft ones block payment
            slips_to_include = run._get_payable_slips()
            if not self.include_unpaid:
                slips_to_include = slips_to_include.filtered(lambda s: not getattr(s, 'paid', False))
        else:
            raise UserError(_("No payslip or pay run specified to process payment."))

        # Validation: Verify all included employees have a bank account configured
        slips_missing_bank = slips_to_include.filtered(lambda s: not s.has_bank_account)
        if slips_missing_bank:
            emp_list = "\n • ".join(slips_missing_bank.mapped('employee_id.name'))
            raise UserError(_(
                "Payment Advice cannot be created!\n\n"
                "The following employee(s) do not have a bank account configured:\n"
                " • %(employees)s\n\n"
                "Please configure bank account details for these employee(s) before creating Payment Advice or marking as Paid."
            ) % {'employees': emp_list})

        advice = False
        if self.payslip_id and getattr(self.payslip_id, 'advice_id', False):
            advice = self.payslip_id.advice_id
        elif self.payslip_run_id and getattr(self.payslip_run_id, 'advice_id', False):
            advice = self.payslip_run_id.advice_id

        company = self.company_id or self.env.company
        note_str = f"Cheque No: {self.cheque_number or 'N/A'}, Date: {self.cheque_date or 'N/A'}" if self.by_cheque else "Processed via NEFT / Online Banking"

        if not advice:
            advice_vals = {
                'date': self.payment_date,
                'company_id': company.id,
                'company_bank_id': self.company_bank_id.id if self.company_bank_id else False,
                'payment_method': self.payment_method or 'enet_rtgs',
                'note': note_str,
            }
            if self.payslip_run_id:
                advice_vals['payslip_run_id'] = self.payslip_run_id.id
            if self.payslip_id:
                advice_vals['payslip_id'] = self.payslip_id.id
            advice = self.env['hudson.payroll.payment.advice'].create(advice_vals)
            if self.payslip_run_id:
                self.payslip_run_id.advice_id = advice
                if self.company_bank_id:
                    self.payslip_run_id.company_bank_id = self.company_bank_id
            if self.payslip_id:
                self.payslip_id.advice_id = advice
        else:
            advice_vals = {
                'date': self.payment_date,
                'payment_method': self.payment_method or 'enet_rtgs',
            }
            if self.company_bank_id:
                advice_vals['company_bank_id'] = self.company_bank_id.id
                if self.payslip_run_id:
                    self.payslip_run_id.company_bank_id = self.company_bank_id
            if self.by_cheque:
                advice_vals['note'] = note_str
            advice.write(advice_vals)

        # Populate lines
        lines_vals = []
        for slip in slips_to_include:
            net_amt = slip.net_wage or sum(l.total for l in slip.line_ids if l.category_id.code == 'NET')
            lines_vals.append((0, 0, {
                'payslip_id': slip.id,
                'employee_id': slip.employee_id.id,
                'net_amount': net_amt,
            }))

        advice.line_ids = [(5, 0, 0)] + lines_vals
        return advice

    def action_mark_paid(self):
        """Marks payslips as paid, updates pay run state if applicable, and confirms advice."""
        self.ensure_one()
        if self.mode == 'advice' and not self.company_bank_id:
            raise UserError(_("Company Bank Account is mandatory. Please select or add a Company Bank Account before marking as Paid."))
        advice = self._ensure_payment_advice()
        paid_context = {'hds_payment_date': self.payment_date} if self.payment_date else {}
        if self.payslip_id:
            self.payslip_id.with_context(**paid_context).action_payslip_paid()
            run = self.payslip_id.payslip_run_id
            active_slips = run.slip_ids.filtered(lambda s: s.state != 'cancel') if run else False
            if active_slips and all(s.state == 'paid' for s in active_slips):
                run.write({'state': 'paid'})
        elif self.payslip_run_id:
            run = self.payslip_run_id
            run._get_payable_slips().with_context(**paid_context).action_payslip_paid()
            run.write({'state': 'paid'})

        advice.action_confirm()
        return {'type': 'ir.actions.act_window_close'}

    def action_create_pdf(self):
        """Generates and downloads PDF Payment Advice report."""
        self.ensure_one()
        if not self.company_bank_id:
            raise UserError(_("Company Bank Account is mandatory. Please select or add a Company Bank Account before generating the PDF Payment Advice."))
        advice = self._ensure_payment_advice()
        return self.env.ref('hudson_payroll_base.action_report_payment_advice').report_action(advice)

    def action_create_xlsx(self):
        """Generates and downloads a formatted Excel (.xlsx) file."""
        self.ensure_one()
        if not self.company_bank_id:
            raise UserError(_("Company Bank Account is mandatory. Please select or add a Company Bank Account before generating the Excel Payment Advice."))
        advice = self._ensure_payment_advice()
        return advice.action_export_xlsx()

    def action_create_csv(self):
        """Generates and downloads a generic bank-ready CSV file."""
        self.ensure_one()
        advice = self._ensure_payment_advice()
        return advice.action_export_csv()

    def action_create_enet(self):
        """Generates and downloads HDFC ENet CMS formatted bulk upload file."""
        self.ensure_one()
        advice = self._ensure_payment_advice()
        advice.write({
            'payment_method': self.payment_method or 'enet_rtgs',
        })
        return advice.action_export_enet(payment_method=self.payment_method)

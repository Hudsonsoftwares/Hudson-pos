# -*- coding: utf-8 -*-
import calendar
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class HdsInBonus(models.Model):
    _name = 'hds.in.bonus'
    _description = 'Bonus Document'
    _order = 'id desc'

    name = fields.Char(
        string="Bonus Name",
        required=True,
        help="Title of the bonus document (e.g. Diwali Bonus 2026)."
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        required=True,
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        related='company_id.currency_id',
        store=True,
        readonly=True
    )

    bonus_category = fields.Selection([
        ('statutory', 'Statutory Bonus'),
        ('performance', 'Performance Bonus'),
        ('festival', 'Festival Bonus'),
        ('ex_gratia', 'Ex-Gratia'),
        ('attendance', 'Attendance Bonus'),
        ('referral', 'Referral Bonus'),
        ('joining', 'Joining Bonus'),
        ('retention', 'Retention Bonus'),
        ('productivity', 'Productivity Bonus'),
        ('sales', 'Sales Incentive'),
        ('custom', 'Custom Bonus'),
    ], string="Bonus Category", default='festival', required=True)

    date_from = fields.Date(
        string="Period From",
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
        help="Start date of the bonus period."
    )
    date_to = fields.Date(
        string="Period To",
        required=True,
        default=lambda self: fields.Date.today(),
        help="End date of the bonus period."
    )

    @api.onchange('date_from')
    def _onchange_date_from(self):
        if self.date_from:
            last_day = calendar.monthrange(self.date_from.year, self.date_from.month)[1]
            self.date_to = self.date_from.replace(day=last_day)
    payment_date = fields.Date(
        string="Payment Date",
        required=True,
        default=fields.Date.today,
        help="Scheduled date for bonus payment."
    )
    payment_method = fields.Selection([
        ('monthly_payroll', 'Include in Monthly Payroll'),
        ('separate_payroll', 'Separate Bonus Payroll'),
    ], string="Payment Method", required=True, default='monthly_payroll')

    notes = fields.Text(string="Notes")

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('manager_approved', 'Manager Approved'),
        ('hr_approved', 'HR Approved'),
        ('approved', 'Finance Approved / Ready for Payroll'),
        ('processed', 'Processed in Payroll'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default='draft', copy=False, index=True)

    # -------------------------------------------------------------------------
    # ELIGIBILITY CRITERIA
    # -------------------------------------------------------------------------
    min_service_period_months = fields.Integer(
        string="Minimum Service Period (Months)",
        default=0,
        help="Employees with fewer months of service will be excluded."
    )
    require_confirmed_employee = fields.Boolean(
        string="Requires Confirmed Employee",
        default=False,
        help="If checked, only confirmed employees will be eligible."
    )

    # -------------------------------------------------------------------------
    # TARGET SCOPE
    # -------------------------------------------------------------------------
    employee_selection_type = fields.Selection([
        ('all', 'All Employees'),
        ('department', 'Department'),
        ('job', 'Job Position'),
        ('manual', 'Manual Selection'),
    ], string="Target Scope", default='all', required=True)

    target_department_ids = fields.Many2many(
        'hr.department',
        'hds_bonus_department_rel',
        'bonus_id',
        'department_id',
        string="Eligible Departments",
        domain="[('company_id', '=', company_id)]"
    )
    target_job_ids = fields.Many2many(
        'hr.job',
        'hds_bonus_job_rel',
        'bonus_id',
        'job_id',
        string="Eligible Job Positions",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]"
    )

    # -------------------------------------------------------------------------
    # CALCULATION ENGINE
    # -------------------------------------------------------------------------
    calculation_method = fields.Selection([
        ('fixed', 'Fixed Amount'),
        ('percentage_basic', 'Percentage of Basic'),
        ('percentage_gross', 'Percentage of Gross'),
        ('percentage_ctc', 'Percentage of CTC'),
        ('formula', 'Formula Based (Python)'),
        ('years_of_service', 'Years of Service Based'),
        ('attendance', 'Attendance Based'),
        ('performance_rating', 'Performance Rating Based'),
    ], string="Calculation Method", default='fixed', required=True)

    fixed_amount = fields.Monetary(
        string="Fixed Amount",
        currency_field='currency_id',
        default=0.0
    )
    percentage = fields.Float(
        string="Percentage (%)",
        default=0.0,
        help="Percentage to apply against Basic, Gross, or CTC salary."
    )
    formula_python = fields.Text(
        string="Python Formula",
        default="result = contract.basic_salary * 0.12",
        help="Python expression evaluating bonus amount into 'result'."
    )

    # -------------------------------------------------------------------------
    # TAX & ACCOUNTING CONFIGURATION
    # -------------------------------------------------------------------------
    tax_treatment = fields.Selection([
        ('taxable', 'Subject to TDS (Fully Taxable)'),
        ('exempt', 'Exempt from TDS'),
        ('partial', 'Partially Taxable'),
    ], string="TDS Tax Treatment", default='taxable', required=True)

    tax_exempt_limit = fields.Monetary(
        string="Tax Exemption Limit",
        currency_field='currency_id',
        default=0.0
    )

    bonus_expense_account_id = fields.Many2one('account.account', string="Bonus Expense Account")
    bonus_payable_account_id = fields.Many2one('account.account', string="Bonus Payable Account")
    journal_id = fields.Many2one('account.journal', string="Payroll / Bonus Journal")
    move_id = fields.Many2one('account.move', string="Journal Entry", readonly=True, copy=False)

    # -------------------------------------------------------------------------
    # SEPARATE BONUS PAYROLL CONFIGURATION
    # -------------------------------------------------------------------------
    struct_id = fields.Many2one(
        'hr.payroll.structure',
        string="Payroll Structure",
        domain="[('company_id', '=', company_id)]",
        default=lambda self: self.company_id.hds_in_regular_struct_id or self.env.ref('hudson_payroll_base.structure_base', raise_if_not_found=False)
    )

    payslip_run_id = fields.Many2one(
        'hr.payslip.run',
        string="Payslip Batch",
        readonly=True,
        copy=False,
        help="Linked Payslip Batch created when Separate Bonus Payroll is processed."
    )

    payslip_count = fields.Integer(
        string="Payslips Generated",
        compute='_compute_payslip_count'
    )

    # -------------------------------------------------------------------------
    # AUDIT TRAIL
    # -------------------------------------------------------------------------
    manager_approved_by = fields.Many2one('res.users', string="Manager Approved By", readonly=True, copy=False)
    manager_approved_date = fields.Datetime(string="Manager Approved Date", readonly=True, copy=False)

    hr_approved_by = fields.Many2one('res.users', string="HR Approved By", readonly=True, copy=False)
    hr_approved_date = fields.Datetime(string="HR Approved Date", readonly=True, copy=False)

    finance_approved_by = fields.Many2one('res.users', string="Finance Approved By", readonly=True, copy=False)
    finance_approved_date = fields.Datetime(string="Finance Approved Date", readonly=True, copy=False)

    line_ids = fields.One2many(
        'hds.in.bonus.line',
        'bonus_id',
        string="Bonus Lines",
        copy=True
    )

    @api.depends('line_ids.payslip_id', 'payslip_run_id')
    def _compute_payslip_count(self):
        for record in self:
            payslips = record.line_ids.mapped('payslip_id')
            if record.payslip_run_id:
                payslips |= record.payslip_run_id.slip_ids
            record.payslip_count = len(payslips)

    def action_view_payslips(self):
        self.ensure_one()
        payslips = self.line_ids.mapped('payslip_id')
        if self.payslip_run_id:
            payslips |= self.payslip_run_id.slip_ids
        action = self.env["ir.actions.actions"]._for_xml_id("hudson_payroll_base.action_hr_payslip")
        if len(payslips) > 1:
            action['domain'] = [('id', 'in', payslips.ids)]
        elif len(payslips) == 1:
            form_view = [(self.env.ref('hudson_payroll_base.hr_payslip_view_form').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + [v for v in action['views'] if v[1] != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = payslips.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    def action_view_payslip_run(self):
        self.ensure_one()
        if not self.payslip_run_id:
            raise UserError(_("No Payslip Batch generated yet."))
        return {
            'name': _('Bonus Payslip Batch'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.run',
            'res_id': self.payslip_run_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_generate_lines(self):
        """Automatically find eligible employees and calculate Bonus Lines."""
        self.ensure_one()
        if self.state not in ('draft', 'submitted'):
            raise UserError(_("You can only generate lines for Draft or Submitted bonus documents."))

        # Determine target employees
        domain = [('company_id', '=', self.company_id.id)]
        if self.employee_selection_type == 'department':
            if not self.target_department_ids:
                raise UserError(_("Please select at least one eligible department."))
            domain.append(('department_id', 'in', self.target_department_ids.ids))
        elif self.employee_selection_type == 'job':
            if not self.target_job_ids:
                raise UserError(_("Please select at least one eligible job position."))
            domain.append(('job_id', 'in', self.target_job_ids.ids))

        employees = self.env['hr.employee'].search(domain)

        # Apply eligibility filters (minimum service period & confirmation requirement)
        eligible_employees = self.env['hr.employee']
        today = fields.Date.today()

        for emp in employees:
            if self.min_service_period_months > 0 and emp.first_contract_date:
                service_days = (today - emp.first_contract_date).days
                if service_days < (self.min_service_period_months * 30):
                    continue

            eligible_employees |= emp

        if not eligible_employees:
            raise UserError(_("No employees match the specified selection and eligibility criteria."))

        self.line_ids.unlink()
        line_vals = []

        for emp in eligible_employees:
            contracts = self.env['hr.version'].search([
                ('employee_id', '=', emp.id),
                ('active', '=', True)
            ], order='id desc')
            contract = next((c for c in contracts if getattr(c, 'is_current', True)), False)
            if not contract and contracts:
                contract = contracts[0]
            if not contract:
                contract = self.env['hr.version'].search([
                    ('employee_id', '=', emp.id)
                ], order='id desc', limit=1)

            amount = self._calculate_employee_bonus_amount(emp, contract)

            line_vals.append({
                'bonus_id': self.id,
                'employee_id': emp.id,
                'contract_id': contract.id if contract else False,
                'amount': round(amount, 2),
            })

        self.env['hds.in.bonus.line'].create(line_vals)
        return True

    def _calculate_employee_bonus_amount(self, emp, contract):
        wage = float(contract.wage or 0.0) if contract else 0.0
        basic = float(contract.basic_salary or contract.wage or 0.0) if contract else 0.0
        ctc = float(contract.hds_in_employer_cost_annual or (wage * 12.0)) if contract else 0.0

        if self.calculation_method == 'fixed':
            return self.fixed_amount
        elif self.calculation_method == 'percentage_basic':
            return basic * (self.percentage / 100.0)
        elif self.calculation_method == 'percentage_gross':
            return wage * (self.percentage / 100.0)
        elif self.calculation_method == 'percentage_ctc':
            return (ctc / 12.0) * (self.percentage / 100.0)
        elif self.calculation_method == 'years_of_service':
            years = 1.0
            if emp.first_contract_date:
                diff_days = (fields.Date.today() - emp.first_contract_date).days
                years = max(1.0, round(diff_days / 365.25, 1))
            return self.fixed_amount * years if self.fixed_amount > 0 else (basic * (self.percentage / 100.0) * years)
        elif self.calculation_method == 'formula':
            localdict = {'contract': contract, 'employee': emp, 'basic': basic, 'gross': wage, 'ctc': ctc, 'result': 0.0}
            try:
                exec(self.formula_python or "result=0.0", localdict)
                return float(localdict.get('result', 0.0))
            except (SyntaxError, NameError, TypeError, ZeroDivisionError, ValueError) as e:
                _logger.warning("Formula evaluation error for bonus %s (Employee ID: %s): %s", self.name, emp.id if emp else 'N/A', str(e), exc_info=True)
                return 0.0
            except Exception as e:
                _logger.error("Unexpected error evaluating bonus formula for %s (Employee ID: %s): %s", self.name, emp.id if emp else 'N/A', str(e), exc_info=True)
                return 0.0
        return self.fixed_amount

    def action_open_import_wizard(self):
        self.ensure_one()
        return {
            'name': _('Import Bonus Lines'),
            'type': 'ir.actions.act_window',
            'res_model': 'hds.in.bonus.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_bonus_id': self.id}
        }

    # Workflow Approval Actions
    def action_submit(self):
        for record in self:
            if not record.line_ids:
                record.action_generate_lines()
            record.write({'state': 'submitted'})
        return True

    def action_manager_approve(self):
        for record in self:
            record.write({
                'state': 'manager_approved',
                'manager_approved_by': self.env.user.id,
                'manager_approved_date': fields.Datetime.now()
            })
        return True

    def action_hr_approve(self):
        for record in self:
            record.write({
                'state': 'hr_approved',
                'hr_approved_by': self.env.user.id,
                'hr_approved_date': fields.Datetime.now()
            })
        return True

    def action_approve(self):
        for record in self:
            if not record.line_ids:
                raise UserError(_("Cannot approve a bonus document without bonus lines."))
            record.write({
                'state': 'approved',
                'finance_approved_by': self.env.user.id,
                'finance_approved_date': fields.Datetime.now()
            })
        return True

    def action_reject(self):
        for record in self:
            record.write({'state': 'cancelled'})
        return True

    def action_cancel(self):
        for record in self:
            if record.state in ('processed', 'paid'):
                raise UserError(_("You cannot cancel a processed or paid bonus."))
            record.write({'state': 'cancelled'})
        return True

    def action_draft(self):
        for record in self:
            record.write({'state': 'draft'})
        return True

    def action_mark_paid(self):
        for record in self:
            record.write({'state': 'paid'})
        return True

    def action_process_bonus(self):
        """Process Approved Bonus document into Payroll inputs or Separate Bonus Payslips."""
        for record in self:
            if record.state not in ('approved', 'hr_approved', 'manager_approved'):
                raise UserError(_("Only Approved bonuses can be processed."))
            if not record.line_ids:
                raise UserError(_("No bonus lines found to process."))

            valid_lines = record.line_ids.filtered(lambda l: l.amount > 0.0)
            if not valid_lines:
                raise UserError(_("All bonus lines have 0 amount."))

            if record.payment_method == 'monthly_payroll':
                record._process_monthly_payroll(valid_lines)
            elif record.payment_method == 'separate_payroll':
                record._process_separate_payroll(valid_lines)

            record.write({'state': 'processed'})
        return True

    def action_generate_separate_payroll(self):
        """Dedicated action button to generate separate bonus payroll batch."""
        for record in self:
            valid_lines = record.line_ids.filtered(lambda l: l.amount > 0.0)
            if not valid_lines:
                raise UserError(_("No bonus lines with amount > 0 found."))
            record._process_separate_payroll(valid_lines)
            if record.state in ('draft', 'submitted'):
                record.write({'state': 'approved'})
        return self.action_view_payslip_run()

    def _process_monthly_payroll(self, lines):
        """Option 1: Include in Monthly Payroll - generates/updates BONUS inputs on draft payslips."""
        for line in lines:
            if not line.contract_id:
                continue
            payslips = self.env['hr.payslip'].search([
                ('employee_id', '=', line.employee_id.id),
                ('state', '=', 'draft'),
                ('date_from', '<=', self.payment_date),
                ('date_to', '>=', self.payment_date),
            ])
            for payslip in payslips:
                input_line = payslip.input_line_ids.filtered(lambda i: i.code == 'BONUS')
                if input_line:
                    input_line.write({'amount': line.amount, 'name': self.name})
                else:
                    self.env['hr.payslip.input'].create({
                        'name': self.name,
                        'code': 'BONUS',
                        'amount': line.amount,
                        'payslip_id': payslip.id,
                        'contract_id': line.contract_id.id,
                        'date_from': self.date_from,
                        'date_to': self.date_to,
                    })
                payslip.action_compute_sheet()

    def _process_separate_payroll(self, lines):
        """Option 2: Separate Bonus Payroll - creates Payslip Batch and Bonus Payslips."""
        struct = self.struct_id or self.company_id.hds_in_regular_struct_id or self.env.ref('hudson_payroll_base.structure_base', raise_if_not_found=False)
        if not struct:
            struct = self.env['hr.payroll.structure'].search([('code', '=', 'REGULAR')], limit=1)
        if not struct:
            raise UserError(_("No Payroll Structure configured."))

        if not self.payslip_run_id:
            batch = self.env['hr.payslip.run'].create({
                'name': f"{self.name} - Bonus Payroll",
                'date_start': self.date_from,
                'date_end': self.date_to,
            })
            self.payslip_run_id = batch.id
        else:
            batch = self.payslip_run_id

        for line in lines:
            if not line.contract_id:
                continue
            payslip = self.env['hr.payslip'].search([
                ('employee_id', '=', line.employee_id.id),
                ('payslip_run_id', '=', batch.id),
            ], limit=1)

            if not payslip:
                payslip = self.env['hr.payslip'].create({
                    'name': f"Bonus Slip - {line.employee_id.name}",
                    'employee_id': line.employee_id.id,
                    'contract_id': line.contract_id.id,
                    'struct_id': struct.id,
                    'date_from': self.date_from,
                    'date_to': self.date_to,
                    'payslip_run_id': batch.id,
                    'company_id': self.company_id.id,
                    'input_line_ids': [(0, 0, {
                        'name': self.name,
                        'code': 'BONUS',
                        'amount': line.amount,
                        'contract_id': line.contract_id.id,
                        'date_from': self.date_from,
                        'date_to': self.date_to,
                    })]
                })
            else:
                input_line = payslip.input_line_ids.filtered(lambda i: i.code == 'BONUS')
                if input_line:
                    input_line.write({'amount': line.amount, 'name': self.name})
                else:
                    self.env['hr.payslip.input'].create({
                        'name': self.name,
                        'code': 'BONUS',
                        'amount': line.amount,
                        'payslip_id': payslip.id,
                        'contract_id': line.contract_id.id,
                        'date_from': self.date_from,
                        'date_to': self.date_to,
                    })

            line.payslip_id = payslip.id
            payslip.action_compute_sheet()


class HdsInBonusLine(models.Model):
    _name = 'hds.in.bonus.line'
    _description = 'Bonus Document Line'
    _order = 'bonus_id, id'

    bonus_id = fields.Many2one(
        'hds.in.bonus',
        string="Bonus Document",
        required=True,
        ondelete='cascade',
        index=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        required=True
    )
    contract_id = fields.Many2one(
        'hr.version',
        string="Contract"
    )
    department_id = fields.Many2one(
        'hr.department',
        related='employee_id.department_id',
        string="Department",
        store=True
    )
    job_id = fields.Many2one(
        'hr.job',
        related='employee_id.job_id',
        string="Job Position",
        store=True
    )
    amount = fields.Monetary(
        string="Bonus Amount",
        currency_field='currency_id',
        required=True,
        default=0.0
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='bonus_id.currency_id',
        store=True,
        readonly=True
    )
    state = fields.Selection(
        related='bonus_id.state',
        string="Status",
        store=True
    )
    payslip_id = fields.Many2one(
        'hr.payslip',
        string="Payslip",
        readonly=True
    )

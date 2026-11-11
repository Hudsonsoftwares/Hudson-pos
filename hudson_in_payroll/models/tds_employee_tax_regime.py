# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError


class TdsEmployeeTaxRegime(models.Model):
    """
    TDS Employee Tax Regime Selection & Financial Year Locking Framework.
    Maps an employee to their selected income tax regime ('new' or 'old') per Financial Year.

    Enforces mandatory server-side Tax Regime Locking once payroll has been processed for the FY.
    """
    _name = 'tds.employee.tax.regime'
    _description = 'Employee Tax Regime Selection per Financial Year'
    _order = 'financial_year_id desc, employee_id, id'
    _sql_constraints = [
        ('emp_fy_regime_uniq', 'unique(employee_id, financial_year_id)',
         'An employee can have only one Tax Regime selection per Financial Year!')
    ]

    name = fields.Char(
        string="Title",
        compute='_compute_name',
        store=True,
        help="Display title."
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        required=True,
        ondelete='cascade',
        help="Target employee selecting tax regime."
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        related='employee_id.company_id',
        store=True,
        readonly=True
    )
    @api.model
    def _default_financial_year_id(self):
        company = self.env.company
        if company and company.hds_in_default_tax_year:
            return company.hds_in_default_tax_year.id
        today = fields.Date.today()
        fy = self.env['tds.financial.year'].search([
            ('start_date', '<=', today),
            ('end_date', '>=', today),
            ('active', '=', True),
            ('is_closed', '=', False)
        ], limit=1)
        return fy.id if fy else False

    financial_year_id = fields.Many2one(
        'tds.financial.year',
        string="Tax Year",
        required=True,
        default=_default_financial_year_id,
        ondelete='restrict',
        help="Tax Year covered by this regime selection."
    )

    regime_id = fields.Many2one(
        'tds.tax.regime',
        string="Selected Tax Regime",
        required=True,
        ondelete='restrict',
        help="Selected statutory tax regime ('new' New Tax Regime Income-tax Act, 2025 — Section 202(1) or 'old' Regime)."
    )
    regime_code = fields.Selection(
        related='regime_id.code',
        string="Regime Code",
        store=True,
        readonly=True
    )
    is_locked = fields.Boolean(
        string="Regime Selection Locked",
        default=False,
        help="Set to True automatically once payroll processing commences for this Financial Year."
    )
    lock_reason = fields.Char(
        string="Lock Reason",
        help="Explanation of why regime selection was locked."
    )
    state = fields.Selection([
        ('draft', 'Draft / Declared'),
        ('confirmed', 'Confirmed / Active'),
    ], string="Selection Status", default='confirmed', required=True)

    @api.depends('employee_id.name', 'financial_year_id.name', 'regime_id.name')
    def _compute_name(self):
        for rec in self:
            emp_name = rec.employee_id.name if rec.employee_id else 'Employee'
            fy_name = rec.financial_year_id.name if rec.financial_year_id else 'FY'
            reg_name = rec.regime_id.name if rec.regime_id else 'Regime'
            rec.name = f"{emp_name} - {fy_name} [{reg_name}]"

    @api.constrains('regime_id', 'employee_id')
    def _check_company_regime_policy(self):
        """
        Enforce Company Tax Regime Policy:
        - If Company policy is 'new', only New Tax Regime is permitted.
        - If Company policy is 'old', only Old Tax Regime is permitted.
        - If Company policy is 'flexible', employee can select either New or Old.
        """
        for rec in self:
            company = rec.company_id or (rec.employee_id and rec.employee_id.company_id) or self.env.company
            policy = getattr(company, 'hds_in_default_tax_regime', 'flexible')
            if policy == 'new' and rec.regime_code != 'new':
                raise ValidationError(_(
                    "Company policy mandates the New Tax Regime Income-tax Act, 2025 — Section 202(1) for all employees. "
                    "Individual selection of the Old Tax Regime is prohibited."
                ))
            elif policy == 'old' and rec.regime_code != 'old':
                raise ValidationError(_(
                    "Company policy mandates the Old Tax Regime for all employees. "
                    "Individual selection of the New Tax Regime is prohibited."
                ))

    @api.constrains('regime_id', 'employee_id', 'financial_year_id')
    def _check_tax_regime_locking(self):
        """
        Server-side Tax Regime Locking Constraint:
        Prevents arbitrary regime modification once payslips exist for the employee within the target FY.
        Allows override only when env.context contains 'ignore_regime_lock'.
        """
        for rec in self:
            if not rec.employee_id or not rec.financial_year_id:
                continue

            # Check if payslips exist for this employee in this financial year
            fy = rec.financial_year_id
            domain = [
                ('employee_id', '=', rec.employee_id.id),
                ('date_from', '>=', fy.start_date),
                ('date_to', '<=', fy.end_date),
                ('state', 'in', ['done', 'paid', 'confirmed'])
            ]
            payslip_count = self.env['hr.payslip'].search_count(domain) if 'hr.payslip' in self.env else 0
            if payslip_count > 0:
                rec.is_locked = True
                rec.lock_reason = f"Locked: {payslip_count} processed payslip(s) exist in FY {fy.name}."
                if not self.env.context.get('ignore_regime_lock'):
                    raise ValidationError(_(
                        "Tax Regime Selection is LOCKED for employee '%s' in Financial Year '%s' "
                        "because %d processed payslips exist for this tax period. "
                        "Tax Regime modifications are strictly prohibited after payroll processing commences, "
                        "except via an authorized administrative override."
                    ) % (rec.employee_id.name, fy.name, payslip_count))

    def action_administrative_unlock(self):
        """
        Payroll Manager Administrative Action to unlock tax regime selection for audit correction.
        """
        self.ensure_one()
        if not self.env.user.has_group('hudson_payroll_base.group_payroll_manager'):
            raise ValidationError(_("Only a Payroll Manager can execute an administrative tax regime unlock."))

        self.with_context(ignore_regime_lock=True).write({
            'is_locked': False,
            'lock_reason': f"Unlocked administratively by {self.env.user.name} on {fields.Date.today()}."
        })

        # Log audit entry
        if 'hds.in.payroll.audit' in self.env:
            self.env['hds.in.payroll.audit'].create({
                'employee_id': self.employee_id.id,
                'company_id': self.company_id.id,
                'user_id': self.env.uid,
                'statutory_module': 'tds',
                'rule_code': 'TAX_REGIME_UNLOCK',
                'calculation_date': fields.Date.today(),
                'calculation_type': 'manual_override',
                'messages': (
                    f"Tax Regime Administrative Unlock: {self.employee_id.name} [{self.financial_year_id.name}]. "
                    f"Unlocked by {self.env.user.name}. Reason: {self.lock_reason or 'N/A'}"
                ),
                'status': 'success',
            })

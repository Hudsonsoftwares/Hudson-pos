import json
# pyrefly: ignore [missing-import]
from markupsafe import Markup
# pyrefly: ignore [missing-import]
from odoo import api, fields, models
from ..services.tds.other_income_aggregation_service import OtherIncomeAggregationService


class TdsEmployeeIncomeDeclaration(models.Model):
    """
    Module 2 - Regime-Neutral Employee Income Declaration Model.
    Captures non-payroll income sources (Income from Other Sources, Let-Out Property Income/Loss,
    Bank Interest, Dividends) and Previous Employer Salary details.
    
    Regime-Neutral Architecture:
    These income declarations are evaluated under BOTH the Old Tax Regime and New Tax Regime Income-tax Act, 2025 — Section 202(1).
    """
    _name = 'tds.employee.income.declaration'
    _description = 'Employee Non-Payroll & Previous Employer Income Declaration'
    _order = 'financial_year_id desc, employee_id, id'
    _sql_constraints = [
        ('emp_fy_inc_uniq', 'unique(employee_id, financial_year_id)',
         'An employee can have only one Income Declaration record per Financial Year!')
    ]

    _INCOME_AUDIT_FIELDS = [
        'savings_bank_interest',
        'fixed_deposit_interest',
        'dividend_income',
        'other_sources_income',
        'total_other_sources_income',
        'annual_let_out_rent',
        'municipal_taxes_paid',
        'let_out_interest_paid',
        'net_house_property_income_loss',
        'prev_employer_taxable_gross',
        'prev_employer_tds',
        'prev_employer_pt',
        'prev_employer_pf',
        'state',
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
        help="Target employee declaring additional income."
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
        help="Financial Year for which additional income is declared."
    )


    # -------------------------------------------------------------------------
    # SECTION A: INCOME FROM OTHER SOURCES (Regime Neutral)
    # -------------------------------------------------------------------------
    savings_bank_interest = fields.Monetary(
        string="Savings Account Interest (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Annual interest earned on savings bank accounts."
    )
    fixed_deposit_interest = fields.Monetary(
        string="Fixed Deposit / Time Deposit Interest (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Annual interest earned on term deposits / fixed deposits."
    )
    dividend_income = fields.Monetary(
        string="Dividend Income (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Annual taxable dividend income earned from shares or mutual funds."
    )
    other_sources_income = fields.Monetary(
        string="Other Miscellaneous Income (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Any other taxable income from gifts, family pension, or commissions."
    )
    total_other_sources_income = fields.Monetary(
        string="Total Income from Other Sources (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
        help="Sum of all declared Income from Other Sources."
    )

    # -------------------------------------------------------------------------
    # SECTION B: INCOME / LOSS FROM LET OUT HOUSE PROPERTY (Regime Neutral)
    # -------------------------------------------------------------------------
    annual_let_out_rent = fields.Monetary(
        string="Gross Annual Rent Received (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Gross annual rent received or receivable for let-out house property."
    )
    municipal_taxes_paid = fields.Monetary(
        string="Municipal Taxes Paid (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Municipal/property taxes actually paid to local authorities during the FY."
    )
    net_annual_value = fields.Monetary(
        string="Net Annual Value (NAV) (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
        help="NAV = Gross Rent - Municipal Taxes Paid."
    )
    property_standard_deduction = fields.Monetary(
        string="Statutory 30% NAV Deduction (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
        help="Statutory 30% standard deduction under Section 24(a)."
    )
    let_out_interest_paid = fields.Monetary(
        string="Let-Out Property Housing Loan Interest (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Total interest paid on housing loan for let-out property under Section 24(b) (uncapped)."
    )
    net_house_property_income_loss = fields.Monetary(
        string="Net Income / Loss from Let-Out Property (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
        help="Net Income/Loss = NAV - 30% NAV - Let-Out Loan Interest."
    )
    effective_house_property_gti_impact = fields.Monetary(
        string="Effective House Property GTI Impact (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
        help="Effective House Property impact on Gross Total Income (after regime adjustment and prior-year carry-forward loss set-off u/s 71B)."
    )
    house_property_loss_ids = fields.One2many(
        'tds.house.property.loss.carryforward',
        related='employee_id.house_property_loss_ids',
        string="House Property Loss Carry-Forward (71B)",
        readonly=False
    )

    # -------------------------------------------------------------------------
    # SECTION C: PREVIOUS EMPLOYER SALARY & TAXES (Mid-Year Joiner)
    # -------------------------------------------------------------------------
    prev_employer_taxable_gross = fields.Monetary(
        string="Previous Employer Taxable Salary (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Gross taxable salary received from previous employer in current FY."
    )
    prev_employer_tds = fields.Monetary(
        string="Previous Employer TDS Deducted (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Total Income Tax (TDS) deducted by previous employer."
    )
    prev_employer_pt = fields.Monetary(
        string="Previous Employer PT Deducted (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Professional Tax deducted by previous employer."
    )
    prev_employer_pf = fields.Monetary(
        string="Previous Employer EPF (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Employer EPF contribution at previous employer."
    )

    total_net_additional_income = fields.Monetary(
        string="Total Net Declared Income (Other + Property + Prev Salary) (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
        help="Combined net additional income to be factored into TDS taxable income."
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        related='company_id.currency_id',
        readonly=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string="Status", default='draft', required=True)
    regime_code = fields.Selection([
        ('new', 'New Tax Regime'),
        ('old', 'Old Tax Regime'),
    ], string="Tax Regime", compute='_compute_regime_code', store=False)

    @api.depends('employee_id', 'financial_year_id')
    def _compute_regime_code(self):
        for rec in self:
            regime = 'new'
            if rec.employee_id and rec.financial_year_id:
                reg_rec = self.env['tds.employee.tax.regime'].search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('financial_year_id', '=', rec.financial_year_id.id)
                ], limit=1)
                if reg_rec and reg_rec.regime_type:
                    regime = reg_rec.regime_type
            rec.regime_code = regime

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_income_declaration_ir_attachment_rel',
        'income_decl_id',
        'attachment_id',
        string="Proof Documents (Form 12B / Rent Proof / Interest Cert)",
        help="Upload Form 12B, rent receipts, or bank interest statements."
    )

    @api.depends('employee_id.name', 'financial_year_id.name')
    def _compute_name(self):
        for rec in self:
            emp = rec.employee_id.name if rec.employee_id else 'Employee'
            fy = rec.financial_year_id.name if rec.financial_year_id else 'FY'
            rec.name = f"Income Declaration - {emp} [{fy}]"

    @api.depends(
        'savings_bank_interest', 'fixed_deposit_interest', 'dividend_income', 'other_sources_income',
        'annual_let_out_rent', 'municipal_taxes_paid', 'let_out_interest_paid',
        'prev_employer_taxable_gross'
    )
    def _compute_totals(self):
        for rec in self:
            # Section A Total
            rec.total_other_sources_income = (
                rec.savings_bank_interest +
                rec.fixed_deposit_interest +
                rec.dividend_income +
                rec.other_sources_income
            )

            # Section B Property Computation
            nav = max(0.0, rec.annual_let_out_rent - rec.municipal_taxes_paid)
            rec.net_annual_value = nav
            std_ded = nav * 0.30
            rec.property_standard_deduction = std_ded
            net_hp = nav - std_ded - rec.let_out_interest_paid
            rec.net_house_property_income_loss = net_hp

            # Effective House Property GTI Impact (Regime Adjusted + Prior Year Loss Set-Off)
            other_inc_svc = OtherIncomeAggregationService(self.env)
            eval_date = fields.Date.today()
            regime = 'new'
            if rec.employee_id and rec.financial_year_id:
                reg_rec = self.env['tds.employee.tax.regime'].sudo().search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('financial_year_id', '=', rec.financial_year_id.id)
                ], limit=1)
                if reg_rec and reg_rec.regime_code:
                    regime = reg_rec.regime_code

            eff_hp = other_inc_svc.calculate_effective_hp_impact(net_hp, regime_code=regime, eval_date=eval_date)
            if eff_hp > 0.0 and rec.employee_id and rec.financial_year_id:
                emp_id = rec.employee_id.id if hasattr(rec.employee_id, 'id') else rec.employee_id
                fy_id = rec.financial_year_id.id if hasattr(rec.financial_year_id, 'id') else rec.financial_year_id
                eff_hp = other_inc_svc.apply_previous_carry_forward_losses(
                    employee_id=emp_id,
                    financial_year_id=fy_id,
                    positive_hp_income=eff_hp,
                    regime_code=regime,
                    eval_date=eval_date
                )
            rec.effective_house_property_gti_impact = eff_hp

            # Overall Net Income Addition
            rec.total_net_additional_income = (
                rec.total_other_sources_income +
                rec.effective_house_property_gti_impact +
                rec.prev_employer_taxable_gross
            )

    def action_submit(self):
        self.write({'state': 'submitted'})

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_reject(self):
        self.write({'state': 'rejected'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def write(self, vals):
        if self.env.context.get('no_tds_audit'):
            return super().write(vals)

        tracked = [f for f in self._INCOME_AUDIT_FIELDS if hasattr(self, f)]
        old_state = {}
        for rec in self:
            old_dict = {}
            for f in tracked:
                old_dict[f] = getattr(rec, f, None)
            old_state[rec.id] = old_dict

        res = super().write(vals)

        if 'hds.in.payroll.audit' in self.env:
            for rec in self:
                if not rec.employee_id:
                    continue
                rec_old = old_state.get(rec.id, {})
                old_diff = {}
                new_diff = {}
                for f in tracked:
                    old_v = rec_old.get(f)
                    new_v = getattr(rec, f, None)
                    if isinstance(old_v, (int, float)) and isinstance(new_v, (int, float)):
                        if round(float(old_v or 0.0), 2) != round(float(new_v or 0.0), 2):
                            old_diff[f] = float(old_v or 0.0)
                            new_diff[f] = float(new_v or 0.0)
                    elif old_v != new_v:
                        if old_v or new_v:
                            old_diff[f] = old_v
                            new_diff[f] = new_v

                if new_diff:
                    calc_date = fields.Date.today()
                    self.env['hds.in.payroll.audit'].sudo().create({
                        'employee_id': rec.employee_id.id,
                        'company_id': rec.company_id.id or self.env.company.id,
                        'user_id': self.env.uid,
                        'statutory_module': 'tds',
                        'rule_code': 'TDS_OTHER_INCOME',
                        'calculation_type': 'tax_declaration',
                        'calculation_date': calc_date,
                        'inputs_json': json.dumps(old_diff, default=str),
                        'outputs_json': json.dumps(new_diff, default=str),
                        'status': 'success',
                    })
                    audit_model = self.env['hds.in.payroll.audit']
                    label_map = {
                        'savings_bank_interest': 'Savings Account Interest',
                        'fixed_deposit_interest': 'Fixed Deposit Interest',
                        'dividend_income': 'Dividend Income',
                        'other_sources_income': 'Other Miscellaneous Income',
                        'total_other_sources_income': 'Total Other Sources Income',
                        'annual_let_out_rent': 'Gross Annual Rent (Let-Out Property)',
                        'municipal_taxes_paid': 'Municipal Taxes Paid',
                        'let_out_interest_paid': 'Housing Loan Interest (Let-Out Property)',
                        'net_house_property_income_loss': 'Net Property Income / Loss',
                        'prev_employer_taxable_gross': 'Previous Employer Taxable Salary',
                        'prev_employer_tds': 'Previous Employer TDS Deducted',
                        'prev_employer_pt': 'Previous Employer PT Deducted',
                        'prev_employer_pf': 'Previous Employer EPF',
                        'state': 'Income Declaration Status',
                    }
                    diff_html_parts = []
                    for k in self._INCOME_AUDIT_FIELDS:
                        if k in new_diff:
                            old_f = audit_model._format_audit_value(k, old_diff.get(k))
                            new_f = audit_model._format_audit_value(k, new_diff.get(k))
                            lbl = label_map.get(k, k.replace('_', ' ').title())
                            diff_html_parts.append(
                                f'<div style="line-height: 1.45; margin-bottom: 1px;">'
                                f'<span style="color: #212529;">{old_f}</span>'
                                f'<span style="color: #495057;"> → </span>'
                                f'<b style="color: #008784;">{new_f}</b>'
                                f' <span style="color: #6c757d; font-style: italic;">({lbl})</span>'
                                f'</div>'
                            )
                    if diff_html_parts and rec.employee_id and hasattr(rec.employee_id, 'message_post'):
                        today_str = fields.Date.today().strftime('%b %d, %Y').replace(' 0', ' ')
                        fy_str = rec.financial_year_id.name if rec.financial_year_id else ''
                        emp_body = (
                            f'<div style="font-weight: 600; margin-bottom: 2px;">Other Income &amp; House Property Update ({fy_str}):</div>'
                            f'<div style="color: #008784; font-weight: bold; margin-bottom: 3px;">→ As of {today_str}</div>'
                            + ''.join(diff_html_parts)
                        )
                        rec.employee_id.message_post(body=Markup(emp_body), subtype_xmlid='mail.mt_note')
        return res

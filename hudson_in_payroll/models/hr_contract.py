# -*- coding: utf-8 -*-
import json
import logging
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _


class HrVersion(models.Model):
    """
    Extends Contract model (hr.version in Odoo 19 Community) to calculate
    projected Monthly and Annual Employer Cost to Company (CTC).
    """
    _inherit = 'hr.version'

    hds_in_employer_cost_monthly = fields.Monetary(
        string="Employer Cost (Monthly)",
        compute='_compute_employer_cost',
        store=True,
        currency_field='currency_id',
        help="Monthly Cost to Company (Gross Salary + Employer Contributions)."
    )

    hds_in_employer_cost_annual = fields.Monetary(
        string="Employer Cost to Company (CTC)",
        compute='_compute_employer_cost',
        store=True,
        currency_field='currency_id',
        help="Annual Employer Cost to Company (CTC)."
    )

    hds_in_tds_applicable = fields.Boolean(
        string="Enable TDS",
        related='employee_id.hds_in_tds_applicable',
        readonly=False,
        store=True,
        help="Enable Indian Income Tax (TDS) withholding computation for this employee."
    )
    hds_in_is_agnipath = fields.Boolean(
        string="Employee under Agnipath Scheme",
        related='employee_id.hds_in_is_agnipath',
        readonly=False,
        store=True,
        help="Check if the employee is enrolled under the Agnipath Scheme (eligible for Section 80CCH Agniveer Corpus Fund deduction)."
    )

    # Benefits (Indian Payroll)
    benefit_phone = fields.Monetary(
        string='Phone Subscription',
        tracking=True,
        currency_field='currency_id',
        help="Monthly Phone Subscription benefit"
    )
    benefit_internet = fields.Monetary(
        string='Internet Subscription',
        tracking=True,
        currency_field='currency_id',
        help="Monthly Internet Subscription benefit"
    )
    benefit_meal_vouchers = fields.Monetary(
        string='Meal Vouchers',
        tracking=True,
        currency_field='currency_id',
        help="Monthly Meal Vouchers benefit"
    )
    benefit_transport = fields.Monetary(
        string='Company Transport',
        tracking=True,
        currency_field='currency_id',
        help="Monthly Company Transport benefit"
    )

    # Insurance Benefits (Medical Insurance & Dependent Coverage)
    benefit_medical_insurance_per_person = fields.Monetary(
        string='Medical Insurance',
        tracking=True,
        currency_field='currency_id',
        help="Monthly medical insurance premium rate per person."
    )
    benefit_insured_spouse = fields.Boolean(
        string='Insured Spouse',
        default=False,
        tracking=True,
        help="Include spouse in medical insurance coverage."
    )
    benefit_insured_first_child = fields.Boolean(
        string='Insured First-Child',
        default=False,
        tracking=True,
        help="Include first child in medical insurance coverage."
    )
    benefit_insured_second_child = fields.Boolean(
        string='Insured Second-Child',
        default=False,
        tracking=True,
        help="Include second child in medical insurance coverage."
    )
    benefit_medical_insurance_amount = fields.Monetary(
        string='Medical Insurance Amount',
        compute='_compute_benefit_medical_insurance_amount',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help="Total monthly medical insurance amount based on covered persons."
    )

    @api.depends(
        'benefit_medical_insurance_per_person',
        'benefit_insured_spouse',
        'benefit_insured_first_child',
        'benefit_insured_second_child'
    )
    def _compute_benefit_medical_insurance_amount(self):
        for rec in self:
            rate = float(rec.benefit_medical_insurance_per_person or 0.0)
            if rate <= 0.0:
                rec.benefit_medical_insurance_amount = 0.0
            else:
                count = 1  # Employee is covered by default
                if rec.benefit_insured_spouse:
                    count += 1
                if rec.benefit_insured_first_child:
                    count += 1
                if rec.benefit_insured_second_child:
                    count += 1
                rec.benefit_medical_insurance_amount = round(count * rate, 2)

    @api.onchange('benefit_medical_insurance_per_person')
    def _onchange_benefit_medical_insurance_per_person(self):
        if (self.benefit_medical_insurance_per_person or 0.0) <= 0.0:
            self.benefit_insured_spouse = False
            self.benefit_insured_first_child = False
            self.benefit_insured_second_child = False
            self.benefit_medical_insurance_amount = 0.0

    benefit_employer_cost_monthly = fields.Monetary(
        string="Employer Benefit Cost (Monthly)",
        compute='_compute_benefit_employer_cost',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help="Total monthly employer benefit cost (sum of Phone, Internet, Meal Vouchers, Company Transport, and Medical Insurance benefits)."
    )
    benefit_employer_cost_yearly = fields.Monetary(
        string="Employer Benefit Cost (Yearly)",
        compute='_compute_benefit_employer_cost',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help="Total annual employer benefit cost (Monthly Benefit Cost * 12)."
    )

    @api.depends(
        'benefit_phone', 'benefit_internet', 'benefit_meal_vouchers', 'benefit_transport',
        'benefit_medical_insurance_amount'
    )
    def _compute_benefit_employer_cost(self):
        for rec in self:
            monthly = round(
                float(rec.benefit_phone or 0.0) +
                float(rec.benefit_internet or 0.0) +
                float(rec.benefit_meal_vouchers or 0.0) +
                float(rec.benefit_transport or 0.0) +
                float(rec.benefit_medical_insurance_amount or 0.0),
                2
            )
            rec.benefit_employer_cost_monthly = monthly
            rec.benefit_employer_cost_yearly = round(monthly * 12.0, 2)




    def _is_india_localization(self):
        """
        Centralized payroll localization check for hr.version.
        Returns True only if India localization is active for this contract/template.
        """
        self.ensure_one()
        return bool(self.is_india_localization)

    @api.depends(
        'wage', 'basic_salary', 'da', 'struct_id', 'struct_id.rule_ids', 'company_id', 'company_id.country_id',
        'employee_id.hds_in_pf_contribution_basis', 'employee_id.hds_in_pf_employer_basis',
        'employee_id.hds_in_epf_applicable', 'employee_id.hds_in_eps_applicable',
        'employee_id.hds_in_esic_applicable', 'employee_id.hds_in_lwf_applicable',
        'employee_id.private_state_id', 'employee_id.work_location_id', 'employee_id.address_id'
    )
    def _compute_employer_cost(self, employee=None):
        for contract in self:
            if not contract._is_india_localization():
                contract.hds_in_employer_cost_monthly = 0.0
                contract.hds_in_employer_cost_annual = 0.0
                emp = employee or contract.employee_id
                if emp:
                    emp.hds_in_employer_cost_monthly = 0.0
                    emp.hds_in_employer_cost_annual = 0.0
                continue

            wage = float(contract.wage or 0.0)
            breakdown = float(getattr(contract, 'breakdown_total', 0.0) or 0.0)
            if breakdown <= 0.0:
                breakdown = float(
                    (getattr(contract, 'basic_salary', 0.0) or 0.0) + (getattr(contract, 'hra', 0.0) or 0.0) +
                    (getattr(contract, 'da', 0.0) or 0.0) + (getattr(contract, 'standard_allowance', 0.0) or 0.0) +
                    (getattr(contract, 'performance_bonus', 0.0) or 0.0) + (getattr(contract, 'retention_bonus', 0.0) or 0.0) +
                    (getattr(contract, 'lta_allowance', 0.0) or 0.0) + (getattr(contract, 'fixed_allowance', 0.0) or 0.0)
                )
            if wage <= 0.0 and breakdown > 0.0:
                wage = breakdown
            elif breakdown > wage > 0.0:
                wage = breakdown

            employer_contrib_monthly = 0.0

            if contract.struct_id:
                ctc_rules = contract.struct_id.get_all_rules()
                if isinstance(ctc_rules, models.Model):
                    rules = ctc_rules.filtered(lambda r: r.hds_in_contributes_to_employer_cost and r.active)
                else:
                    rule_ids = [r[0] if isinstance(r, (tuple, list)) else getattr(r, 'id', r) for r in ctc_rules]
                    rules = self.env['hr.salary.rule'].browse(rule_ids).filtered(
                        lambda r: r.hds_in_contributes_to_employer_cost and r.active
                    )
            else:
                rules = self.env['hr.salary.rule'].search([('hds_in_contributes_to_employer_cost', '=', True), ('active', '=', True)])

            for rule in rules:
                if rule.amount_select == 'fix':
                    employer_contrib_monthly += rule.amount_fix
                elif rule.amount_select == 'percentage':
                    employer_contrib_monthly += (wage * rule.amount_percentage / 100.0)
                elif rule.amount_select == 'code':
                    employer_contrib_monthly += self._estimate_statutory_rule_amount(contract, rule, employee=employee)

            monthly_ctc = round(wage + employer_contrib_monthly, 2)
            contract.hds_in_employer_cost_monthly = monthly_ctc
            contract.hds_in_employer_cost_annual = round(monthly_ctc * 12.0, 2)
            emp = employee or contract.employee_id
            if emp:
                emp.hds_in_employer_cost_monthly = monthly_ctc
                emp.hds_in_employer_cost_annual = round(monthly_ctc * 12.0, 2)

    @api.onchange('wage', 'basic_salary', 'da', 'struct_id', 'employee_id')
    def _onchange_contract_ctc_inputs(self):
        if self._is_india_localization():
            self._compute_employer_cost()

    @api.onchange('contract_template_id')
    def _onchange_contract_template_id(self):
        if hasattr(super(), '_onchange_contract_template_id'):
            super()._onchange_contract_template_id()
        if self._is_india_localization():
            self._compute_employer_cost()
        else:
            self.hds_in_employer_cost_monthly = 0.0
            self.hds_in_employer_cost_annual = 0.0

    _SALARY_AUDIT_FIELDS = [
        'wage', 'wage_type', 'salary_calculation_type',
        'basic_salary', 'basic_salary_percent', 'basic_salary_percentage',
        'hra', 'hra_percent', 'hra_percentage',
        'da', 'da_percent', 'da_percentage',
        'fixed_allowance', 'fixed_allowance_percent', 'fixed_allowance_percentage',
        'standard_allowance', 'standard_allowance_percent', 'standard_allowance_percentage',
        'performance_bonus', 'performance_bonus_percent', 'performance_bonus_percentage',
        'retention_bonus', 'retention_bonus_percent', 'retention_bonus_percentage',
        'lta_allowance', 'lta_percent', 'lta_percentage',
        'pay_by_attendance', 'enable_attendance_threshold', 'min_attendance_threshold_days',
        'benefit_phone', 'benefit_internet', 'benefit_meal_vouchers', 'benefit_transport',
        'benefit_medical_insurance_per_person', 'benefit_insured_spouse',
        'benefit_insured_first_child', 'benefit_insured_second_child',
        'benefit_medical_insurance_amount',
    ]

    @api.model_create_multi
    def create(self, vals_list):
        contracts = super().create(vals_list)
        for contract in contracts:
            if contract._is_india_localization():
                contract._compute_employer_cost()
                if contract.employee_id and contract.wage:
                    contract._sync_employee_esic_default()
            else:
                contract.hds_in_employer_cost_monthly = 0.0
                contract.hds_in_employer_cost_annual = 0.0

            # Log baseline salary setup in Audit Trail
            if 'hds.in.payroll.audit' in self.env and contract.employee_id and contract.wage:
                new_diff = {}
                old_diff = {}
                for f in self._SALARY_AUDIT_FIELDS:
                    if hasattr(contract, f):
                        val = getattr(contract, f, None)
                        if val:
                            new_diff[f] = val
                            old_diff[f] = 0.0 if isinstance(val, (int, float)) else None
                if new_diff:
                    calc_date = (
                        contract.contract_date_start or
                        getattr(contract, 'date_version', False) or
                        fields.Date.today()
                    )
                    self.env['hds.in.payroll.audit'].sudo().create({
                        'employee_id': contract.employee_id.id,
                        'company_id': contract.company_id.id or self.env.company.id,
                        'user_id': self.env.uid,
                        'statutory_module': 'revision',
                        'rule_code': 'SALARY_CHANGE',
                        'calculation_type': 'contract_creation',
                        'calculation_date': calc_date,
                        'inputs_json': json.dumps(old_diff, default=str),
                        'outputs_json': json.dumps(new_diff, default=str),
                        'status': 'success',
                    })
        return contracts

    def write(self, vals):
        tracked_keys = [f for f in self._SALARY_AUDIT_FIELDS if f in vals]
        old_state = {}
        if tracked_keys:
            for contract in self:
                old_state[contract.id] = {
                    f: getattr(contract, f, None)
                    for f in self._SALARY_AUDIT_FIELDS
                    if hasattr(contract, f)
                }

        res = super().write(vals)

        # Audit Trail Logging for Wage and Salary component changes
        if tracked_keys and 'hds.in.payroll.audit' in self.env:
            for contract in self:
                emp = contract.employee_id
                if not emp:
                    continue
                contract_old = old_state.get(contract.id, {})
                old_diff = {}
                new_diff = {}
                for f, old_val in contract_old.items():
                    new_val = getattr(contract, f, None)
                    if isinstance(old_val, float) and isinstance(new_val, float):
                        if round(old_val, 2) != round(new_val, 2):
                            old_diff[f] = old_val
                            new_diff[f] = new_val
                    elif old_val != new_val:
                        old_diff[f] = old_val
                        new_diff[f] = new_val

                if new_diff:
                    calc_date = (
                        contract.contract_date_start or
                        getattr(contract, 'date_version', False) or
                        fields.Date.today()
                    )
                    self.env['hds.in.payroll.audit'].sudo().create({
                        'employee_id': emp.id,
                        'company_id': contract.company_id.id or self.env.company.id,
                        'user_id': self.env.uid,
                        'statutory_module': 'revision',
                        'rule_code': 'SALARY_CHANGE',
                        'calculation_type': 'contract_revision',
                        'calculation_date': calc_date,
                        'inputs_json': json.dumps(old_diff, default=str),
                        'outputs_json': json.dumps(new_diff, default=str),
                        'status': 'success',
                    })

        if any(f in vals for f in ('wage', 'employee_id', 'struct_id', 'contract_template_id', 'basic_salary', 'hra', 'da')):
            for contract in self.with_context(no_statutory_audit=True):
                if contract._is_india_localization():
                    contract._compute_employer_cost()
                    if contract.employee_id and contract.wage:
                        contract._sync_employee_esic_default()
                else:
                    contract.hds_in_employer_cost_monthly = 0.0
                    contract.hds_in_employer_cost_annual = 0.0
        return res

    @api.onchange('wage', 'employee_id')
    def _onchange_wage_sync_esic(self):
        for contract in self:
            if not contract._is_india_localization():
                continue
            if contract.employee_id:
                eval_date = fields.Date.today()
                if contract.date_start and contract.date_start > eval_date:
                    eval_date = contract.date_start
                default_esic = contract.employee_id._evaluate_default_esic_applicable(
                    gross_wage=contract.wage,
                    eval_date=eval_date
                )
                if contract.employee_id.hds_in_esic_applicable and not default_esic:
                    from ..services.esic.contribution_period_service import ESICContributionPeriodService
                    period_service = ESICContributionPeriodService(self.env)
                    if period_service.is_covered_for_contribution_period(contract.employee_id, eval_date=eval_date):
                        default_esic = True

                contract.employee_id.hds_in_esic_applicable = default_esic
                if not default_esic:
                    contract.employee_id.hds_in_esic_ip_status = 'exempt'
                    contract.employee_id.hds_in_esic_exit_reason = 'wage_exceeded'
                else:
                    if contract.employee_id.hds_in_esic_ip_status == 'exempt':
                        contract.employee_id.hds_in_esic_ip_status = 'active'
                        contract.employee_id.hds_in_esic_exit_reason = False

    @api.onchange('wage', 'employee_id', 'date_start')
    def _onchange_wage_check_tds_threshold(self):
        """
        Dynamically checks whether the entered monthly wage projects an annual taxable salary
        exceeding the statutory zero-tax threshold (Standard Deduction + Section 87A Rebate).
        If threshold is exceeded and TDS is not yet enabled, automatically selects 'Enable TDS'
        and displays an informative advisory warning popup to the payroll administrator.
        """
        for contract in self:
            if not contract._is_india_localization():
                continue

            company = contract.company_id or (contract.employee_id.company_id if contract.employee_id else False) or self.env.company
            if not getattr(company, 'hds_in_tds_applicable', False):
                continue

            wage = float(contract.wage or 0.0)
            if wage <= 0.0:
                continue

            # If TDS is already enabled on contract or employee, do not show repeated alert
            if contract.hds_in_tds_applicable or (contract.employee_id and contract.employee_id.hds_in_tds_applicable):
                continue

            annual_gross = wage * 12.0
            eval_date = contract.date_start or fields.Date.today()

            emp = contract.employee_id
            regime = False
            if emp:
                regime = getattr(emp, 'hds_in_tax_regime', False) or (
                    emp.hds_in_current_tax_regime_id.code
                    if hasattr(emp, 'hds_in_current_tax_regime_id') and emp.hds_in_current_tax_regime_id
                    else False
                )
            if not regime:
                regime = getattr(company, 'hds_in_default_tax_regime', 'new') or 'new'
            regime_code = (regime or 'new').lower()

            from odoo.addons.hudson_in_payroll.services.tds.tds_parameter_service import TdsParameterService
            tds_param_svc = TdsParameterService(self.env)
            std_deduction = tds_param_svc.get_parameter('STD_DEDUCTION', eval_date=eval_date, regime=regime_code) or (
                75000.0 if regime_code == 'new' else 50000.0
            )
            rebate_limit = tds_param_svc.get_parameter('87A_LIMIT', eval_date=eval_date, regime=regime_code) or (
                1200000.0 if regime_code == 'new' else 500000.0
            )

            tax_free_threshold = rebate_limit + std_deduction

            if annual_gross > tax_free_threshold:
                contract.hds_in_tds_applicable = True
                if emp:
                    emp.hds_in_tds_applicable = True

                regime_label = _("New Tax Regime (Section 115BAC)") if regime_code == 'new' else _("Old Tax Regime")
                return {
                    'warning': {
                        'title': _("Statutory TDS Notice: Tax Liability Detected"),
                        'message': _(
                            "The entered monthly wage of ₹%(monthly_wage)s (Annual Gross: ₹%(annual_gross)s) "
                            "exceeds the dynamic tax-free threshold of ₹%(threshold)s "
                            "(Standard Deduction: ₹%(std_ded)s + Section 87A Rebate: ₹%(rebate)s under %(regime)s).\n\n"
                            "The 'Enable TDS' option has been automatically selected for this employee to ensure statutory compliance."
                        ) % {
                            'monthly_wage': f"{wage:,.2f}",
                            'annual_gross': f"{annual_gross:,.2f}",
                            'threshold': f"{tax_free_threshold:,.2f}",
                            'std_ded': f"{std_deduction:,.2f}",
                            'rebate': f"{rebate_limit:,.2f}",
                            'regime': regime_label,
                        }
                    }
                }

    def _sync_employee_esic_default(self):
        """
        Updates default ESIC applicability on employee when contract wage changes,
        while maintaining manual override capability and enforcing Regulation 31 continuity.
        """
        self.ensure_one()
        if not self._is_india_localization():
            return
        employee = self.employee_id
        if not employee:
            return
        eval_date = fields.Date.today()
        if self.date_start and self.date_start > eval_date:
            eval_date = self.date_start
        default_esic = employee._evaluate_default_esic_applicable(
            gross_wage=self.wage,
            eval_date=eval_date
        )
        if employee.hds_in_esic_applicable and not default_esic:
            from ..services.esic.contribution_period_service import ESICContributionPeriodService
            period_service = ESICContributionPeriodService(self.env)
            if period_service.is_covered_for_contribution_period(employee, eval_date=eval_date):
                default_esic = True

        vals = {'hds_in_esic_applicable': default_esic}
        if not default_esic:
            vals['hds_in_esic_ip_status'] = 'exempt'
            vals['hds_in_esic_exit_reason'] = 'wage_exceeded'
        else:
            if employee.hds_in_esic_ip_status == 'exempt':
                vals['hds_in_esic_ip_status'] = 'active'
                vals['hds_in_esic_exit_reason'] = False
        employee.write(vals)

    def _estimate_statutory_rule_amount(self, contract, rule, employee=None):
        """
        Estimates contract-level statutory employer cost by delegating directly
        to EPFService and ESICService and reusing the exact same statutory calculation engine,
        wage rules, applicability flags, contribution basis, and effective-dated parameters.
        No statutory constants or rates are hardcoded.
        """
        if not contract._is_india_localization():
            return 0.0

        code_text = rule.amount_python_compute or ''
        rule_code = rule.code or ''
        employee = employee or contract.employee_id
        env_no_audit = self.with_context(no_statutory_audit=True).env

        from ..services.epf.epf_service import EPFService, ContractPayslipAdapter
        adapter = ContractPayslipAdapter(contract, employee=employee)

        # EPF Contribution Rules
        if any(k in code_text for k in ('compute_employer_total_pf', 'compute_employer_epf', 'compute_employer_eps', 'compute_employer_edli', 'compute_epf_admin', 'compute_edli_admin')) or rule_code in ('EMPLOYER_EPF', 'EPS', 'EPF_SHARE', 'EDLI', 'EPF_ADMIN', 'EDLI_ADMIN'):
            if employee and hasattr(employee, 'hds_in_epf_applicable') and not employee.hds_in_epf_applicable:
                return 0.0
            epf_svc = EPFService(env_no_audit)
            if 'compute_employer_total_pf' in code_text or ('compute_employer_epf' in code_text and 'compute_employer_epf_share' not in code_text) or rule_code == 'EMPLOYER_EPF':
                return epf_svc.compute_employer_epf(adapter)
            elif 'compute_employer_epf_share' in code_text or rule_code == 'EPF_SHARE':
                return epf_svc.compute_employer_epf_share(adapter)
            elif 'compute_employer_eps' in code_text or rule_code == 'EPS':
                return epf_svc.compute_employer_eps(adapter)
            elif 'compute_employer_edli' in code_text or rule_code == 'EDLI':
                return epf_svc.compute_employer_edli(adapter)
            elif 'compute_epf_admin' in code_text or rule_code == 'EPF_ADMIN':
                return epf_svc.compute_epf_admin(adapter)
            elif 'compute_edli_admin' in code_text or rule_code == 'EDLI_ADMIN':
                return epf_svc.compute_edli_admin(adapter)

        # ESIC Employer Contribution Rule
        elif 'compute_esic_employer' in code_text or rule_code == 'ESIC_ER':
            if employee and hasattr(employee, 'hds_in_esic_applicable') and not employee.hds_in_esic_applicable:
                return 0.0
            from ..services.esic.esic_service import ESICService
            esic_svc = ESICService(env_no_audit)
            return esic_svc.compute_esic_employer(adapter)

        # LWF Employer Contribution Rule
        elif 'compute_lwf_employer' in code_text or rule_code == 'LWF_ER':
            if employee and hasattr(employee, 'hds_in_lwf_applicable') and not employee.hds_in_lwf_applicable:
                return 0.0
            company = getattr(contract, 'company_id', False) or (employee.company_id if employee else False) or self.env.company
            from ..services.payroll.work_location_service import PayrollWorkLocationService
            from ..services.lwf.lwf_rate_service import LWFRateService
            eval_date = contract.date_start or fields.Date.today()
            work_state = PayrollWorkLocationService(self.env).get_work_state(employee)
            rate_cfg = LWFRateService(self.env).get_rate_config(work_state, eval_date=eval_date, company=company)
            if rate_cfg:
                er_contrib = float(rate_cfg.empl_contribution or 0.0)
                freq = rate_cfg.deduction_frequency or 'monthly'
                if freq == 'half_yearly':
                    return round((er_contrib * 2.0) / 12.0, 2)
                elif freq == 'annual':
                    return round(er_contrib / 12.0, 2)
                return er_contrib
            return 0.0

        return 0.0

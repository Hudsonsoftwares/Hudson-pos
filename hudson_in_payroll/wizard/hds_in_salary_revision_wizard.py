# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError, ValidationError
from ..services.revision.salary_preview_service import SalaryPreviewService
from ..services.revision.salary_revision_service import SalaryRevisionService


class HdsInSalaryRevisionWizard(models.TransientModel):
    """
    Transient UI Wizard for initiating and previewing Salary Revisions.
    Contains zero payroll calculation logic; delegates preview and confirmation to pure service classes.
    """
    _name = 'hds.in.salary.revision.wizard'
    _description = 'Hudson Indian Payroll Salary Revision Wizard'

    def _get_employee_contract(self, employee, date=False):
        """Resolves the employee's contract version: the one in force on the revision's effective
        date (a revision builds on it), else the current one."""
        if not employee:
            return False
        date = fields.Date.to_date(date)
        if date and hasattr(employee, '_get_version'):
            version = employee._get_version(date)
            if version:
                return version
        contract = getattr(employee, 'version_id', False) or getattr(employee, 'contract_id', False)
        if contract:
            return contract
        contracts = self.env['hr.version'].search([('employee_id', '=', employee.id)])
        if contracts:
            open_contracts = contracts.filtered(lambda c: getattr(c, 'state', False) == 'open')
            target_list = open_contracts if open_contracts else contracts
            def _sort_key(c):
                start = getattr(c, 'contract_date_start', False) or getattr(c, 'date_start', False)
                return start or fields.Date.today()
            return target_list.sorted(_sort_key, reverse=True)[0]
        return False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        active_model = self.env.context.get('active_model')
        default_employee_id = self.env.context.get('default_employee_id')

        emp_id = None
        active_ids = self.env.context.get('active_ids') or []
        if active_model == 'hr.employee' and len(active_ids) > 1 and 'employee_ids' in fields_list:
            res['employee_ids'] = [(6, 0, active_ids)]
            active_id = active_id or active_ids[0]
        if active_model == 'hr.employee' and active_id:
            emp_id = active_id
            res['is_employee_readonly'] = True
        elif default_employee_id:
            emp_id = default_employee_id
            res['is_employee_readonly'] = True

        if emp_id:
            employee = self.env['hr.employee'].browse(emp_id)
            res['employee_id'] = employee.id
            if employee.company_id:
                res['company_id'] = employee.company_id.id
            code = getattr(employee, 'registration_number', None) or getattr(employee, 'identification_id', None) or False
            res['employee_code'] = str(code) if code else False
            contract = self._get_employee_contract(employee, res.get('effective_date'))
            if contract:
                res['contract_id'] = contract.id
                res['current_wage'] = contract.wage or 0.0
                res['current_employer_cost_monthly'] = getattr(contract, 'hds_in_employer_cost_monthly', 0.0) or 0.0
                res['current_employer_cost_annual'] = getattr(contract, 'hds_in_employer_cost_annual', 0.0) or 0.0
                if getattr(contract, 'struct_id', False):
                    res['struct_id'] = contract.struct_id.id
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('employee_id') and not vals.get('company_id'):
                emp = self.env['hr.employee'].browse(vals['employee_id'])
                if emp.company_id:
                    vals['company_id'] = emp.company_id.id
        return super().create(vals_list)

    # Section 1: Employee Information
    is_employee_readonly = fields.Boolean(
        string="Is Employee Fixed",
        default=False,
        help="Locks employee selection when the wizard is initiated directly from an employee profile."
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        default=lambda self: self.env.company,
        required=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]"
    )
    employee_code = fields.Char(
        string="Employee Code",
        compute='_compute_employee_code',
        readonly=True,
        help="Employee Code / Registration Number from employee profile."
    )
    department_id = fields.Many2one('hr.department', string="Department", related='employee_id.department_id', readonly=True)
    # Salary Increase on several employees at once (employee list > Actions)
    employee_ids = fields.Many2many('hr.employee', string="Employees",
                                    help="Employees receiving the same salary increase.")
    employee_count = fields.Integer(compute='_compute_employee_count')
    job_id = fields.Many2one('hr.job', string="Designation", related='employee_id.job_id', readonly=True)
    currency_id = fields.Many2one('res.currency', string="Currency", related='company_id.currency_id', readonly=True)
    contract_id = fields.Many2one('hr.version', string="Current Contract", compute='_compute_contract_info', readonly=False, store=True)
    current_wage = fields.Monetary(string="Current Gross Salary", currency_field='currency_id', compute='_compute_contract_info', readonly=False, store=True)
    current_employer_cost_monthly = fields.Monetary(string="Current Employer Cost (Monthly)", currency_field='currency_id', compute='_compute_contract_info', readonly=False, store=True)
    current_employer_cost_annual = fields.Monetary(string="Current Employer Cost (Annual)", currency_field='currency_id', compute='_compute_contract_info', readonly=False, store=True)
    struct_id = fields.Many2one('hr.payroll.structure', string="Payroll Structure", compute='_compute_contract_info', readonly=False, store=True)

    @api.depends('employee_id', 'effective_date')
    def _compute_contract_info(self):
        for wizard in self:
            if wizard.employee_id:
                contract = wizard._get_employee_contract(wizard.employee_id, wizard.effective_date)
                if contract:
                    wizard.contract_id = contract.id
                    wizard.current_wage = contract.wage or 0.0
                    wizard.current_employer_cost_monthly = getattr(contract, 'hds_in_employer_cost_monthly', 0.0) or 0.0
                    wizard.current_employer_cost_annual = getattr(contract, 'hds_in_employer_cost_annual', 0.0) or 0.0
                    wizard.struct_id = contract.struct_id.id if getattr(contract, 'struct_id', False) else False
                else:
                    wizard.contract_id = False
                    wizard.current_wage = getattr(wizard.employee_id, 'wage', 0.0) or 0.0
                    wizard.current_employer_cost_monthly = 0.0
                    wizard.current_employer_cost_annual = 0.0
                    wizard.struct_id = False
            else:
                wizard.contract_id = False
                wizard.current_wage = 0.0
                wizard.current_employer_cost_monthly = 0.0
                wizard.current_employer_cost_annual = 0.0
                wizard.struct_id = False

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id:
            if self.employee_id.company_id:
                self.company_id = self.employee_id.company_id
            code = getattr(self.employee_id, 'registration_number', None) or getattr(self.employee_id, 'identification_id', None) or False
            self.employee_code = str(code) if code else False
        else:
            self.employee_code = False
        self._compute_contract_info()
        self._onchange_breakdown_distribution_mode()

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.employee_id and self.employee_id.company_id and self.company_id:
            if self.employee_id.company_id != self.company_id:
                self.employee_id = False
                self.employee_code = False
                self._compute_contract_info()
                self._onchange_breakdown_distribution_mode()

    @api.constrains('employee_id', 'company_id')
    def _check_employee_company(self):
        for wizard in self:
            if wizard.employee_id and wizard.company_id and wizard.employee_id.company_id:
                if wizard.employee_id.company_id != wizard.company_id:
                    raise ValidationError(_(
                        "The selected employee (%s) belongs to %s, but the salary revision wizard is set to %s."
                    ) % (wizard.employee_id.name, wizard.employee_id.company_id.name, wizard.company_id.name))

    @api.depends('employee_id')
    def _compute_employee_code(self):
        for wizard in self:
            emp = wizard.employee_id
            if emp:
                code = getattr(emp, 'registration_number', None) or getattr(emp, 'identification_id', None) or False
                wizard.employee_code = str(code) if code else False
            else:
                wizard.employee_code = False

    # Section 2: Revision Details
    effective_date = fields.Date(string="Effective Date", default=lambda self: self._default_effective_date(),
                                 required=True, help="1st of the month from which the new salary applies (today or later).")

    @api.model
    def _default_effective_date(self):
        today = fields.Date.context_today(self)
        return today if today.day == 1 else (today.replace(day=1) + relativedelta(months=1))
    revision_type = fields.Selection([
        ('annual_increment', 'Annual Increment'),
        ('promotion', 'Promotion'),
        ('correction', 'Salary Correction'),
        ('manual', 'Manual Salary Revision'),
    ], string="Revision Type", default='annual_increment', required=True)

    computation_type = fields.Selection([
        ('percentage', 'Percentage'),
        ('fixed_amount', 'Fixed Amount'),
    ], string="Increase Type", default='percentage', required=True)

    increase_percentage = fields.Float(string="Increase Percentage (%)", default=10.0)
    increase_amount = fields.Float(string="Increase Amount (₹)", default=0.0)

    # Section 3: Revision Basis ("Applies On")
    revision_basis = fields.Selection([
        ('full_wage', 'Full Wage'),
        ('capped_wage', 'Capped Wage'),
    ], string="Applies On", default='full_wage', required=True,
        help="Full Wage: the increase rate applies to the whole wage. Capped Wage: the rate applies to the wage "
             "only up to the capped amount (e.g. 10% with a ₹30,000 cap on a ₹50,000 wage adds ₹3,000).")

    capped_wage_amount = fields.Monetary(string="Capped Wage Amount", currency_field='currency_id',
                                         help="Part of the wage the increase rate applies to.")
    extra_amount = fields.Monetary(string="Extra Amount", currency_field='currency_id',
                                   help="Fixed amount added to the wage on top of the increase rate.")

    # Section 3b: Salary Breakdown Update Mode
    breakdown_distribution_mode = fields.Selection([
        ('auto_structure', 'Auto Generate from Salary Structure (Default)'),
        ('copy_current', 'Copy Current Breakdown & Edit ⭐ (Recommended)'),
        ('manual_adjust', 'Manually Adjust Salary Components'),
        ('keep_existing', 'Keep Existing Salary Breakdown'),
    ], string="Salary Breakdown Update Mode", default='auto_structure', required=True)

    # Auto Generate Mode Preview Fields
    auto_preview_basic_salary = fields.Monetary(string="Current Basic", currency_field='currency_id', compute='_compute_auto_breakdown_preview')
    auto_preview_revised_basic = fields.Monetary(string="Revised Basic", currency_field='currency_id', compute='_compute_auto_breakdown_preview')
    auto_preview_hra = fields.Monetary(string="Current HRA", currency_field='currency_id', compute='_compute_auto_breakdown_preview')
    auto_preview_revised_hra = fields.Monetary(string="Revised HRA", currency_field='currency_id', compute='_compute_auto_breakdown_preview')
    auto_preview_da = fields.Monetary(string="Current DA", currency_field='currency_id', compute='_compute_auto_breakdown_preview')
    auto_preview_revised_da = fields.Monetary(string="Revised DA", currency_field='currency_id', compute='_compute_auto_breakdown_preview')
    auto_preview_travel = fields.Monetary(string="Current Travel", currency_field='currency_id', compute='_compute_auto_breakdown_preview')
    auto_preview_revised_travel = fields.Monetary(string="Revised Travel", currency_field='currency_id', compute='_compute_auto_breakdown_preview')
    auto_preview_meal = fields.Monetary(string="Current Meal", currency_field='currency_id', compute='_compute_auto_breakdown_preview')
    auto_preview_revised_meal = fields.Monetary(string="Revised Meal", currency_field='currency_id', compute='_compute_auto_breakdown_preview')
    auto_preview_medical = fields.Monetary(string="Current Medical", currency_field='currency_id', compute='_compute_auto_breakdown_preview')
    auto_preview_revised_medical = fields.Monetary(string="Revised Medical", currency_field='currency_id', compute='_compute_auto_breakdown_preview')
    auto_preview_other = fields.Monetary(string="Current Other", currency_field='currency_id', compute='_compute_auto_breakdown_preview')
    auto_preview_revised_other = fields.Monetary(string="Revised Other", currency_field='currency_id', compute='_compute_auto_breakdown_preview')
    auto_preview_fixed = fields.Monetary(string="Current Fixed", currency_field='currency_id', compute='_compute_auto_breakdown_preview')
    auto_preview_revised_fixed = fields.Monetary(string="Revised Fixed", currency_field='currency_id', compute='_compute_auto_breakdown_preview')

    # Manual Adjustment Fields (Visible when mode is copy_current or manual_adjust)
    manual_basic_salary = fields.Monetary(string="Basic Salary", currency_field='currency_id')
    manual_hra = fields.Monetary(string="HRA", currency_field='currency_id')
    manual_da = fields.Monetary(string="DA", currency_field='currency_id')
    manual_travel_allowance = fields.Monetary(string="Travel Allowance", currency_field='currency_id')
    manual_meal_allowance = fields.Monetary(string="Meal Allowance", currency_field='currency_id')
    manual_medical_allowance = fields.Monetary(string="Medical Allowance", currency_field='currency_id')
    manual_other_allowance = fields.Monetary(string="Other Allowance", currency_field='currency_id')
    manual_fixed_allowance = fields.Monetary(string="Fixed Allowance", currency_field='currency_id')

    manual_breakdown_total = fields.Monetary(
        string="Allocated Components",
        currency_field='currency_id',
        compute='_compute_manual_breakdown_totals'
    )
    manual_breakdown_remaining = fields.Monetary(
        string="Remaining Amount",
        currency_field='currency_id',
        compute='_compute_manual_breakdown_totals'
    )
    manual_breakdown_is_equal = fields.Boolean(
        string="Is Valid Manual Distribution",
        compute='_compute_manual_breakdown_totals'
    )

    @api.onchange('breakdown_distribution_mode', 'contract_id')
    def _onchange_breakdown_distribution_mode(self):
        """Populates manual input fields with current contract breakdown when entering manual edit modes."""
        if self.breakdown_distribution_mode in ('copy_current', 'manual_adjust') and self.contract_id:
            c = self.contract_id
            self.manual_basic_salary = c.basic_salary or 0.0
            self.manual_hra = c.hra or 0.0
            self.manual_da = c.da or 0.0
            self.manual_travel_allowance = c.travel_allowance or 0.0
            self.manual_meal_allowance = c.meal_allowance or 0.0
            self.manual_medical_allowance = c.medical_allowance or 0.0
            self.manual_other_allowance = c.other_allowance or 0.0
            self.manual_fixed_allowance = c.fixed_allowance or 0.0

    @api.depends('revised_wage', 'contract_id', 'breakdown_distribution_mode')
    def _compute_auto_breakdown_preview(self):
        from ..services.payroll.salary_breakdown_service import SalaryBreakdownService
        breakdown_service = SalaryBreakdownService(self.env)
        for wizard in self:
            c = wizard.contract_id
            wizard.auto_preview_basic_salary = c.basic_salary or 0.0 if c else 0.0
            wizard.auto_preview_hra = c.hra or 0.0 if c else 0.0
            wizard.auto_preview_da = c.da or 0.0 if c else 0.0
            wizard.auto_preview_travel = c.travel_allowance or 0.0 if c else 0.0
            wizard.auto_preview_meal = c.meal_allowance or 0.0 if c else 0.0
            wizard.auto_preview_medical = c.medical_allowance or 0.0 if c else 0.0
            wizard.auto_preview_other = c.other_allowance or 0.0 if c else 0.0
            wizard.auto_preview_fixed = c.fixed_allowance or 0.0 if c else 0.0

            rev = breakdown_service.calculate_breakdown(c, wizard.revised_wage or 0.0)
            wizard.auto_preview_revised_basic = rev['basic_salary']
            wizard.auto_preview_revised_hra = rev['hra']
            wizard.auto_preview_revised_da = rev['da']
            wizard.auto_preview_revised_travel = rev['travel_allowance']
            wizard.auto_preview_revised_meal = rev['meal_allowance']
            wizard.auto_preview_revised_medical = rev['medical_allowance']
            wizard.auto_preview_revised_other = rev['other_allowance']
            wizard.auto_preview_revised_fixed = rev['fixed_allowance']

    @api.depends('revised_wage', 'manual_basic_salary', 'manual_hra', 'manual_da',
                 'manual_travel_allowance', 'manual_meal_allowance', 'manual_medical_allowance',
                 'manual_other_allowance', 'manual_fixed_allowance')
    def _compute_manual_breakdown_totals(self):
        for wizard in self:
            total = (
                (wizard.manual_basic_salary or 0.0) +
                (wizard.manual_hra or 0.0) +
                (wizard.manual_da or 0.0) +
                (wizard.manual_travel_allowance or 0.0) +
                (wizard.manual_meal_allowance or 0.0) +
                (wizard.manual_medical_allowance or 0.0) +
                (wizard.manual_other_allowance or 0.0) +
                (wizard.manual_fixed_allowance or 0.0)
            )
            revised = wizard.revised_wage or 0.0
            remaining = round(revised - total, 2)
            wizard.manual_breakdown_total = total
            wizard.manual_breakdown_remaining = remaining
            wizard.manual_breakdown_is_equal = abs(remaining) < 0.01

    def action_auto_balance_remaining(self):
        """
        Calculates unallocated remaining amount and assigns it to fixed_allowance
        to balance the salary breakdown to revised_wage.
        """
        self.ensure_one()
        revised = self.revised_wage or 0.0
        allocated_others = (
            (self.manual_basic_salary or 0.0) +
            (self.manual_hra or 0.0) +
            (self.manual_da or 0.0) +
            (self.manual_travel_allowance or 0.0) +
            (self.manual_meal_allowance or 0.0) +
            (self.manual_medical_allowance or 0.0) +
            (self.manual_other_allowance or 0.0)
        )
        remaining = round(revised - allocated_others, 2)
        if remaining < 0.0:
            remaining = 0.0
        self.manual_fixed_allowance = remaining
        self._compute_manual_breakdown_totals()
        return True

    def _get_manual_breakdown_dict(self):
        self.ensure_one()
        return {
            'basic_salary': self.manual_basic_salary or 0.0,
            'hra': self.manual_hra or 0.0,
            'da': self.manual_da or 0.0,
            'travel_allowance': self.manual_travel_allowance or 0.0,
            'meal_allowance': self.manual_meal_allowance or 0.0,
            'medical_allowance': self.manual_medical_allowance or 0.0,
            'other_allowance': self.manual_other_allowance or 0.0,
            'fixed_allowance': self.manual_fixed_allowance or 0.0,
        }

    # Section 4: Reason & Notes
    reason = fields.Text(string="Reason for Revision")
    notes = fields.Text(string="Notes")

    # Dynamic Visibility Flags for Preview Sections
    preview_show_pf = fields.Boolean(string="Show PF Section", compute='_compute_payroll_preview')
    preview_show_esic = fields.Boolean(string="Show ESIC Section", compute='_compute_payroll_preview')
    preview_show_pt = fields.Boolean(string="Show PT Row", compute='_compute_payroll_preview')
    preview_show_lwf = fields.Boolean(string="Show LWF Row", compute='_compute_payroll_preview')

    # Section 5: Computed Live Impact Preview
    revised_wage = fields.Monetary(string="Revised Gross Salary", currency_field='currency_id', compute='_compute_payroll_preview')
    wage_difference = fields.Monetary(string="Gross Salary Difference", currency_field='currency_id', compute='_compute_payroll_preview')

    preview_old_ctc = fields.Monetary(string="Current Employer Cost", currency_field='currency_id', compute='_compute_payroll_preview')
    preview_new_ctc = fields.Monetary(string="Estimated Employer Cost", currency_field='currency_id', compute='_compute_payroll_preview')

    preview_old_epf_wage = fields.Monetary(string="Current EPF Wage", currency_field='currency_id', compute='_compute_payroll_preview')
    preview_new_epf_wage = fields.Monetary(string="Estimated EPF Wage", currency_field='currency_id', compute='_compute_payroll_preview')

    preview_old_ee_epf = fields.Monetary(string="Current Employee EPF", currency_field='currency_id', compute='_compute_payroll_preview')
    preview_new_ee_epf = fields.Monetary(string="Estimated Employee EPF", currency_field='currency_id', compute='_compute_payroll_preview')

    preview_old_er_pf = fields.Monetary(string="Current Employer PF", currency_field='currency_id', compute='_compute_payroll_preview')
    preview_new_er_pf = fields.Monetary(string="Estimated Employer PF", currency_field='currency_id', compute='_compute_payroll_preview')

    preview_old_eps = fields.Monetary(string="Current EPS", currency_field='currency_id', compute='_compute_payroll_preview')
    preview_new_eps = fields.Monetary(string="Estimated EPS", currency_field='currency_id', compute='_compute_payroll_preview')

    preview_old_edli = fields.Monetary(string="Current EDLI", currency_field='currency_id', compute='_compute_payroll_preview')
    preview_new_edli = fields.Monetary(string="Estimated EDLI", currency_field='currency_id', compute='_compute_payroll_preview')

    preview_old_esic_app = fields.Boolean(string="Current ESIC Coverage", compute='_compute_payroll_preview')
    preview_new_esic_app = fields.Boolean(string="Estimated ESIC Coverage", compute='_compute_payroll_preview')

    preview_old_ee_esic = fields.Monetary(string="Current Employee ESIC", currency_field='currency_id', compute='_compute_payroll_preview')
    preview_new_ee_esic = fields.Monetary(string="Estimated Employee ESIC", currency_field='currency_id', compute='_compute_payroll_preview')
    preview_old_er_esic = fields.Monetary(string="Current Employer ESIC", currency_field='currency_id', compute='_compute_payroll_preview')
    preview_new_er_esic = fields.Monetary(string="Estimated Employer ESIC", currency_field='currency_id', compute='_compute_payroll_preview')

    preview_esic_cur_period_label = fields.Char(string="Current ESIC Period Label", compute='_compute_payroll_preview')
    preview_esic_cur_period_status = fields.Boolean(string="Current ESIC Period Status", compute='_compute_payroll_preview')
    preview_esic_next_period_label = fields.Char(string="Next ESIC Period Label", compute='_compute_payroll_preview')
    preview_esic_next_period_status = fields.Boolean(string="Next ESIC Period Status", compute='_compute_payroll_preview')
    preview_esic_next_period_reason = fields.Text(string="Next ESIC Period Reason", compute='_compute_payroll_preview')

    preview_pt_amount = fields.Monetary(string="Estimated Professional Tax", currency_field='currency_id', compute='_compute_payroll_preview')
    preview_old_pt_amount = fields.Monetary(string="Current Professional Tax", currency_field='currency_id', compute='_compute_payroll_preview')
    preview_lwf_amount = fields.Monetary(string="Estimated Labour Welfare Fund", currency_field='currency_id', compute='_compute_payroll_preview')

    @api.depends(
        'employee_id', 'current_wage', 'revision_basis', 'capped_wage_amount',
        'computation_type', 'increase_percentage', 'increase_amount', 'extra_amount', 'effective_date',
        'breakdown_distribution_mode', 'manual_basic_salary', 'manual_hra', 'manual_da',
        'manual_travel_allowance', 'manual_meal_allowance', 'manual_medical_allowance',
        'manual_other_allowance', 'manual_fixed_allowance'
    )
    def _compute_payroll_preview(self):
        for wizard in self:
            wage_base = wizard.current_wage
            if (not wage_base or wage_base <= 0.0) and wizard.employee_id:
                contract = wizard._get_employee_contract(wizard.employee_id)
                if contract and contract.wage:
                    wage_base = contract.wage
                    wizard.current_wage = wage_base
                    if not wizard.contract_id:
                        wizard.contract_id = contract.id

            if not wizard.employee_id or wage_base <= 0.0:
                wizard.revised_wage = 0.0
                wizard.wage_difference = 0.0
                wizard.preview_show_pf = False
                wizard.preview_show_esic = False
                wizard.preview_show_pt = False
                wizard.preview_show_lwf = False
                wizard.preview_old_ctc = 0.0
                wizard.preview_new_ctc = 0.0
                wizard.preview_old_epf_wage = 0.0
                wizard.preview_new_epf_wage = 0.0
                wizard.preview_old_ee_epf = 0.0
                wizard.preview_new_ee_epf = 0.0
                wizard.preview_old_er_pf = 0.0
                wizard.preview_new_er_pf = 0.0
                wizard.preview_old_eps = 0.0
                wizard.preview_new_eps = 0.0
                wizard.preview_old_edli = 0.0
                wizard.preview_new_edli = 0.0
                wizard.preview_old_esic_app = False
                wizard.preview_new_esic_app = False
                wizard.preview_old_ee_esic = 0.0
                wizard.preview_new_ee_esic = 0.0
                wizard.preview_old_er_esic = 0.0
                wizard.preview_new_er_esic = 0.0
                wizard.preview_esic_cur_period_label = False
                wizard.preview_esic_cur_period_status = False
                wizard.preview_esic_next_period_label = False
                wizard.preview_esic_next_period_status = False
                wizard.preview_esic_next_period_reason = False
                wizard.preview_pt_amount = 0.0
                wizard.preview_old_pt_amount = 0.0
                wizard.preview_lwf_amount = 0.0
                continue

            revised_wage = wizard._get_revised_wage(wage_base)

            wizard.revised_wage = revised_wage
            wizard.wage_difference = revised_wage - wage_base

            # Set section visibility flags
            wizard.preview_show_pf = bool(wizard.employee_id.hds_in_epf_applicable)
            company = wizard.company_id or wizard.employee_id.company_id or wizard.env.company
            wizard.preview_show_esic = bool(company.hds_in_esic_applicable and wizard.employee_id.hds_in_esic_applicable)

            # Delegate preview simulation to SalaryPreviewService with distribution mode
            preview_service = SalaryPreviewService(wizard.env)
            manual_dict = wizard._get_manual_breakdown_dict() if wizard.breakdown_distribution_mode in ('manual_adjust', 'copy_current') else None
            preview = preview_service.calculate_preview(
                wizard.employee_id,
                wage_base,
                revised_wage,
                effective_date=wizard.effective_date,
                mode=wizard.breakdown_distribution_mode,
                manual_dict=manual_dict
            )

            wizard.preview_show_pt = bool(preview.get('pt_applicable', False) or preview.get('pt_amount', 0.0) > 0.0)
            wizard.preview_show_lwf = bool(preview['lwf_amount'] > 0.0)

            wizard.preview_old_ctc = preview['old_ctc']
            wizard.preview_new_ctc = preview['new_ctc']
            wizard.preview_old_epf_wage = preview['old_epf_wage']
            wizard.preview_new_epf_wage = preview['new_epf_wage']
            wizard.preview_old_ee_epf = preview['old_ee_epf']
            wizard.preview_new_ee_epf = preview['new_ee_epf']
            wizard.preview_old_er_pf = preview['old_er_pf']
            wizard.preview_new_er_pf = preview['new_er_pf']
            wizard.preview_old_eps = preview['old_eps']
            wizard.preview_new_eps = preview['new_eps']
            wizard.preview_old_edli = preview['old_edli']
            wizard.preview_new_edli = preview['new_edli']
            wizard.preview_old_esic_app = preview['old_esic_app']
            wizard.preview_new_esic_app = preview['new_esic_app']
            wizard.preview_old_ee_esic = preview['old_ee_esic']
            wizard.preview_new_ee_esic = preview['new_ee_esic']
            wizard.preview_old_er_esic = preview['old_er_esic']
            wizard.preview_new_er_esic = preview['new_er_esic']
            wizard.preview_esic_cur_period_label = preview['esic_cur_period_label']
            wizard.preview_esic_cur_period_status = preview['esic_cur_period_status']
            wizard.preview_esic_next_period_label = preview['esic_next_period_label']
            wizard.preview_esic_next_period_status = preview['esic_next_period_status']
            wizard.preview_esic_next_period_reason = preview['esic_next_period_reason']
            wizard.preview_pt_amount = preview['pt_amount']
            wizard.preview_old_pt_amount = preview.get('old_pt_amount', 0.0)
            wizard.preview_lwf_amount = preview['lwf_amount']

    @api.onchange('revision_basis')
    def _salary_increase_values(self):
        self.ensure_one()
        return {
            'company_id': self.company_id.id,
            'effective_date': self.effective_date,
            'revision_type': self.revision_type,
            'computation_type': self.computation_type,
            'increase_percentage': self.increase_percentage,
            'increase_amount': self.increase_amount,
            'extra_amount': self.extra_amount,
            'revision_basis': self.revision_basis,
            'capped_wage_amount': self.capped_wage_amount,
            'breakdown_distribution_mode': self.breakdown_distribution_mode,
            'reason': self.reason,
            'notes': self.notes,
        }

    def action_confirm_salary_increase(self):
        """Salary Increase dialog: one revision per employee, each through the same checks and
        revision service as the detailed wizard. Any error cancels the whole increase."""
        self.ensure_one()
        employees = self.employee_ids or self.employee_id
        if len(employees) <= 1:
            return self.action_confirm_revision()
        values = self._salary_increase_values()
        revisions = self.env['hds.in.salary.revision']
        Wizard = self.with_context(active_id=False, active_ids=False, active_model=False)
        for employee in employees:
            wizard = Wizard.create(dict(values, employee_id=employee.id,
                                        company_id=employee.company_id.id or values['company_id']))
            try:
                action = wizard.action_confirm_revision()
            except (ValidationError, UserError) as error:
                raise UserError(_("%(employee)s: %(error)s", employee=employee.name, error=error.args[0])) from error
            revisions |= revisions.browse(action.get('res_id'))
        action = self.env['ir.actions.act_window']._for_xml_id('hudson_in_payroll.action_hds_in_salary_revision_history')
        action.update({'domain': [('id', 'in', revisions.ids)], 'context': {}})
        return action

    def action_open_detailed_revision(self):
        """Advanced: read-only comparison of the current and the new salary (breakdown, PF, ESIC,
        statutory deductions) for the values entered in the Salary Increase dialog."""
        self.ensure_one()
        return self._salary_increase_dialog('hudson_in_payroll.hds_in_salary_increase_comparison_view_form',
                                            _("Salary Increase - Comparison"))

    def action_back_to_salary_increase(self):
        """Back from the comparison to the Salary Increase dialog, keeping the values."""
        self.ensure_one()
        return self._salary_increase_dialog('hudson_in_payroll.hds_in_salary_increase_wizard_view_form',
                                            _("Salary Increase"))

    def _salary_increase_dialog(self, view_xmlid, name):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref(view_xmlid).id, 'form')],
            'target': 'new',
            'context': dict(self.env.context, active_model='hr.employee', active_id=self.employee_id.id,
                            active_ids=self.employee_id.ids),
        }

    def _onchange_revision_basis(self):
        if self.revision_basis != 'capped_wage':
            self.capped_wage_amount = 0.0

    @api.depends('employee_ids')
    def _compute_employee_count(self):
        for wizard in self:
            wizard.employee_count = len(wizard.employee_ids)

    def _get_revised_wage(self, wage):
        """New wage (as Odoo's Salary Increase): the increase rate applies to the full wage, or to the
        wage only up to the capped amount, and the extra amount is added on top. The fixed-amount
        mode of the detailed wizard adds its amount to the wage."""
        self.ensure_one()
        wage = wage or 0.0
        if self.computation_type == 'fixed_amount':
            return wage + (self.increase_amount or 0.0)
        base = wage
        if self.revision_basis == 'capped_wage':
            base = min(wage, self.capped_wage_amount or 0.0)
        return wage + base * (self.increase_percentage or 0.0) / 100.0 + (self.extra_amount or 0.0)

    def action_confirm_revision(self):
        """
        Confirms salary revision and delegates execution to SalaryRevisionService.
        """
        self.ensure_one()

        if self.revision_basis == 'capped_wage' and self.capped_wage_amount <= 0.0:
            raise ValidationError(_("Capped Wage Amount must be greater than zero when 'Capped Wage' is selected."))

        if self.computation_type == 'percentage':
            if self.increase_percentage < 0.0 or (self.extra_amount or 0.0) < 0.0:
                raise ValidationError(_("The Increase Rate and the Extra Amount cannot be negative."))
            if self.increase_percentage <= 0.0 and (self.extra_amount or 0.0) <= 0.0:
                raise ValidationError(_("Enter an Increase Rate or an Extra Amount."))

        if self.computation_type == 'fixed_amount' and self.increase_amount <= 0.0:
            raise ValidationError(_("Increase Amount must be greater than zero."))

        if self.breakdown_distribution_mode in ('manual_adjust', 'copy_current'):
            if not self.manual_breakdown_is_equal:
                raise ValidationError(_(
                    "Manual Salary Breakdown total (₹%s) does not match Revised Gross Salary (₹%s). "
                    "Difference: ₹%s."
                ) % (self.manual_breakdown_total, self.revised_wage, self.manual_breakdown_remaining))

        revision_service = SalaryRevisionService(self.env)
        revision_record = revision_service.execute_salary_revision(self)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Salary Revision History'),
            'res_model': 'hds.in.salary.revision',
            'res_id': revision_record.id,
            'view_mode': 'form',
            'target': 'current',
        }

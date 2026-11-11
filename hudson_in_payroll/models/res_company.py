# -*- coding: utf-8 -*-
import re
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _auto_init(self):
        res = super()._auto_init()
        self._ensure_hds_in_columns()
        return res

    @api.model
    def _ensure_hds_in_columns(self):
        """Ensures all hds_in fields on res_company exist in PostgreSQL to prevent UndefinedColumn errors."""
        if getattr(self.env.registry, '_hds_in_company_cols_synced', False):
            return
        from odoo import tools
        if not tools.sql.table_exists(self.env.cr, 'res_company'):
            return
        columns_to_ensure = [
            ('hds_in_is_india_company', 'BOOLEAN'),
            ('hds_in_epf_applicable', 'BOOLEAN DEFAULT TRUE'),
            ('hds_in_epf_employer_id', 'VARCHAR'),
            ('hds_in_eps_applicable', 'BOOLEAN DEFAULT TRUE'),
            ('hds_in_edli_applicable', 'BOOLEAN DEFAULT TRUE'),
            ('hds_in_edli_registration_number', 'VARCHAR'),
            ('hds_in_enable_statutory_audit', 'BOOLEAN DEFAULT TRUE'),
            ('hds_in_esic_applicable', 'BOOLEAN DEFAULT TRUE'),
            ('hds_in_esic_employer_code', 'VARCHAR'),
            ('hds_in_esic_registration_no', 'VARCHAR'),
            ('hds_in_esic_branch_office', 'VARCHAR'),
            ('hds_in_esic_contribution_period_type', "VARCHAR DEFAULT 'apr_sep_oct_mar'"),
            ('hds_in_esic_custom_period1_start_month', "VARCHAR DEFAULT '4'"),
            ('hds_in_esic_custom_period1_end_month', "VARCHAR DEFAULT '9'"),
            ('hds_in_esic_custom_period2_start_month', "VARCHAR DEFAULT '10'"),
            ('hds_in_esic_custom_period2_end_month', "VARCHAR DEFAULT '3'"),
            ('hds_in_enable_lwf', 'BOOLEAN DEFAULT FALSE'),
            ('hds_in_lwf_registration_no', 'VARCHAR'),
            ('hds_in_enable_gratuity', 'BOOLEAN DEFAULT FALSE'),
            ('hds_in_gratuity_registration_no', 'VARCHAR'),
            ('hds_in_enable_professional_tax', 'BOOLEAN DEFAULT FALSE'),
            ('hds_in_professional_tax_registration_no', 'VARCHAR'),
            ('hds_in_tds_applicable', 'BOOLEAN DEFAULT FALSE'),
            ('hds_in_tan', 'VARCHAR(10)'),
            ('hds_in_default_tax_regime', 'VARCHAR'),
            ('hds_in_default_tax_year', 'INTEGER'),
            ('hds_in_enable_leave_encashment', 'BOOLEAN DEFAULT TRUE'),
            ('hds_in_leave_encashment_registration_no', 'VARCHAR'),
            ('hds_in_enable_notice_pay_settlement', 'BOOLEAN DEFAULT TRUE'),
            ('hds_in_notice_period_unit', "VARCHAR DEFAULT 'days'"),
            ('hds_in_regular_struct_id', 'INTEGER'),
            ('hds_in_retention_min_service_months', 'INTEGER DEFAULT 12'),
            ('hds_in_retention_exclude_notice_period', 'BOOLEAN DEFAULT TRUE'),
            ('hds_in_bonus_apply_tds', 'BOOLEAN DEFAULT TRUE'),
            ('hds_in_bonus_apply_pf', 'BOOLEAN DEFAULT FALSE'),
            ('hds_in_bonus_apply_esi', 'BOOLEAN DEFAULT FALSE'),
            ('hds_in_bonus_apply_pt', 'BOOLEAN DEFAULT FALSE'),
            ('enable_attendance_threshold', 'BOOLEAN DEFAULT TRUE'),
            ('min_attendance_threshold_days', 'NUMERIC DEFAULT 14.0'),
        ]
        try:
            with self.env.cr.savepoint():
                for col, col_def in columns_to_ensure:
                    self.env.cr.execute(f"ALTER TABLE res_company ADD COLUMN IF NOT EXISTS {col} {col_def};")
                self.env.registry._hds_in_company_cols_synced = True
        except Exception:
            pass

    def fetch(self, field_names=None):
        if not getattr(self.env.registry, '_hds_in_company_cols_synced', False):
            self._ensure_hds_in_columns()
        return super().fetch(field_names=field_names)

    hds_in_is_india_company = fields.Boolean(
        string="Is India Company",
        compute='_compute_hds_in_is_india_company',
        store=True,
        help="Technical flag indicating whether company country is India (IN)."
    )

    @api.depends('country_id', 'country_id.code')
    def _compute_hds_in_is_india_company(self):
        for company in self:
            company.hds_in_is_india_company = bool(
                company.country_id and company.country_id.code == 'IN'
            )

    hds_in_epf_applicable = fields.Boolean(
        string="EPF Applicable",
        default=True,
        help="Enable Employee Provident Fund (EPF) calculations."
    )
    hds_in_epf_employer_id = fields.Char(
        string="EPF Employer ID",
        help="Employer Establishment Code for EPF."
    )
    hds_in_eps_applicable = fields.Boolean(
        string="EPS Applicable",
        compute='_compute_hds_in_epf_subschemes',
        store=True,
        readonly=False,
        help="Enable Employee Pension Scheme (EPS) calculations."
    )
    hds_in_edli_applicable = fields.Boolean(
        string="EDLI Applicable",
        compute='_compute_hds_in_epf_subschemes',
        store=True,
        readonly=False,
        help="Enable Employee Deposit Linked Insurance (EDLI) calculations."
    )
    hds_in_edli_registration_number = fields.Char(
        string="EDLI Registration Number",
        help="Registration/Policy Number for EDLI."
    )
    hds_in_enable_statutory_audit = fields.Boolean(
        string="Enable Statutory Calculation Audit Logging",
        default=True,
        help="Record detailed calculation input/output/parameter audit logs for statutory compliance."
    )

    @api.depends('hds_in_epf_applicable')
    def _compute_hds_in_epf_subschemes(self):
        for company in self:
            company.hds_in_eps_applicable = company.hds_in_epf_applicable
            company.hds_in_edli_applicable = company.hds_in_epf_applicable

    @api.onchange('hds_in_epf_applicable')
    def _onchange_hds_in_epf_applicable(self):
        for company in self:
            company.hds_in_eps_applicable = company.hds_in_epf_applicable
            company.hds_in_edli_applicable = company.hds_in_epf_applicable

    # ESIC Company Configuration Fields
    hds_in_esic_applicable = fields.Boolean(
        string="Enable ESIC",
        default=True,
        help="Enable Employee State Insurance (ESIC) statutory compliance for this company."
    )
    hds_in_esic_employer_code = fields.Char(
        string="ESIC IP Number",
        help="Enter the 17-digit ESIC Code / IP Number allotted by the Employees' State Insurance Corporation."
    )
    hds_in_esic_registration_no = fields.Char(
        string="ESIC Registration Number",
        help="Enter the ESIC Registration Number of the company."
    )
    hds_in_esic_branch_office = fields.Char(
        string="ESIC Branch Office",
        help="Optional. Specify the ESIC Branch/Sub Office associated with this employer."
    )
    hds_in_esic_contribution_period_type = fields.Selection([
        ('apr_sep_oct_mar', 'April – September & October – March (Standard / Set A)'),
        ('jul_dec_jan_jun', 'July – December & January – June (Set B)'),
        ('may_oct_nov_apr', 'May – October & November – April (Set C)'),
        ('custom', 'Custom Contribution Periods'),
    ], string="Contribution Periods Cycle", default='apr_sep_oct_mar',
       help="Statutory ESIC Contribution Period cycle under Regulation 4 of ESI (General) Regulations, 1950.")
    hds_in_esic_custom_period1_start_month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'), ('4', 'April'),
        ('5', 'May'), ('6', 'June'), ('7', 'July'), ('8', 'August'),
        ('9', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December')
    ], string="Period 1 Start Month", default='4')
    hds_in_esic_custom_period1_end_month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'), ('4', 'April'),
        ('5', 'May'), ('6', 'June'), ('7', 'July'), ('8', 'August'),
        ('9', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December')
    ], string="Period 1 End Month", default='9')
    hds_in_esic_custom_period2_start_month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'), ('4', 'April'),
        ('5', 'May'), ('6', 'June'), ('7', 'July'), ('8', 'August'),
        ('9', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December')
    ], string="Period 2 Start Month", default='10')
    hds_in_esic_custom_period2_end_month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'), ('4', 'April'),
        ('5', 'May'), ('6', 'June'), ('7', 'July'), ('8', 'August'),
        ('9', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December')
    ], string="Period 2 End Month", default='3')

    # LWF Company Configuration Fields
    hds_in_enable_lwf = fields.Boolean(
        string="Enable Labour Welfare Fund (LWF)",
        default=False,
        help="Enable Labour Welfare Fund (LWF) statutory compliance for this company."
    )
    hds_in_lwf_registration_no = fields.Char(
        string="LWF Registration Number",
        help="Statutory Registration / Establishment Code under Labour Welfare Fund Act."
    )

    # Gratuity Company Configuration Fields
    hds_in_enable_gratuity = fields.Boolean(
        string="Enable Gratuity",
        default=False,
        help="Determines whether the company is covered under the Payment of Gratuity Act."
    )
    hds_in_gratuity_registration_no = fields.Char(
        string="Gratuity Registration Number",
        help="Stores the company's gratuity registration/reference number for statutory records."
    )

    # Professional Tax (PT) Company Configuration Fields
    hds_in_enable_professional_tax = fields.Boolean(
        string="Enable Professional Tax",
        default=False,
        help="Determines whether the company is liable to deduct Professional Tax."
    )
    hds_in_professional_tax_registration_no = fields.Char(
        string="Professional Tax Registration Number",
        help="Stores the company's Professional Tax Registration Number (PTRC/PTEC or equivalent, depending on the state)."
    )

    # Tax Deducted at Source (TDS) Company Configuration Fields
    hds_in_tds_applicable = fields.Boolean(
        string="Enable TDS",
        default=False,
        help="Master switch to enable or disable Tax Deducted at Source (TDS) for the company. When disabled, TDS services skip all tax calculations."
    )
    hds_in_tan = fields.Char(
        string="TAN",
        size=10,
        help="Tax Deduction and Collection Account Number allotted by the Income Tax Department (10 characters, e.g. ABCD12345E)."
    )
    # Deductor details of the quarterly TDS return (Form 138 text file)
    hds_in_company_pan = fields.Char(
        string="Company PAN",
        size=10,
        help="Permanent Account Number of the company (deductor), printed in the quarterly TDS return (e.g. ABCDE1234F)."
    )
    hds_in_deductor_type = fields.Selection([
        ('A', 'Central Government'),
        ('S', 'State Government'),
        ('D', 'Statutory Body (Central Govt.)'),
        ('E', 'Statutory Body (State Govt.)'),
        ('G', 'Autonomous Body (Central Govt.)'),
        ('H', 'Autonomous Body (State Govt.)'),
        ('L', 'Local Authority (Central Govt.)'),
        ('N', 'Local Authority (State Govt.)'),
        ('K', 'Company'),
        ('M', 'Branch / Division of Company'),
        ('P', 'Association of Persons (AOP)'),
        ('T', 'Association of Persons (Trust)'),
        ('J', 'Artificial Juridical Person'),
        ('B', 'Body of Individuals'),
        ('Q', 'Individual / HUF'),
        ('F', 'Firm'),
    ], string="Deductor Type", default='K',
        help="Deductor category of the quarterly TDS return.")
    hds_in_tds_responsible_name = fields.Char(
        string="Responsible Person",
        help="Person responsible for deducting tax, printed in the quarterly TDS return.")
    hds_in_tds_responsible_designation = fields.Char(string="Designation")
    hds_in_tds_responsible_email = fields.Char(string="Responsible Person Email")
    hds_in_tds_responsible_mobile = fields.Char(string="Responsible Person Mobile")
    hds_in_default_tax_regime = fields.Selection(
        selection=[
            ('new', 'New Tax Regime Income-tax Act, 2025 — Section 202(1)'),
            ('old', 'Old Tax Regime'),
            ('flexible', 'Flexible (Employee Choice)'),
        ],
        string="Default Tax Regime",
        default='new',
        help="Company Tax Regime policy:\n"
             "- New Regime: Mandates New Tax Regime Income-tax Act, 2025 — Section 202(1) for all employees.\n"
             "- Old Regime: Mandates Old Tax Regime for all employees.\n"
             "- Flexible: Allows individual employees to choose their preferred tax regime."
    )
    hds_in_default_tax_year = fields.Many2one(
        'tds.financial.year',
        string="Default Tax Year",
        help="Stores the company's active/default tax year for TDS calculations."
    )

    # Leave Encashment Company Configuration Fields
    hds_in_enable_leave_encashment = fields.Boolean(
        string="Enable Leave Encashment",
        default=True,
        help="Enable Leave Encashment statutory and policy calculations for this company."
    )
    hds_in_leave_encashment_registration_no = fields.Char(
        string="Leave Encashment Policy Number",
        help="Optional registration or policy reference for Leave Encashment."
    )

    # Notice Pay Company Configuration Fields
    hds_in_enable_notice_pay_settlement = fields.Boolean(
        string="Enable Notice Pay Settlement",
        default=True,
        help="When enabled, Notice Pay earnings or shortfall recovery will be calculated in Final Settlement."
    )
    hds_in_notice_period_unit = fields.Selection([
        ('days', 'Days'),
        ('months', 'Months'),
    ], string="Notice Period Unit", default='days', required=True,
       help="Unit for company contract expiration notice period (Days or Calendar Months).")

    def compute_notice_period_end_date(self, start_date, notice_period_val=None, unit=None):
        """
        Calculates the notice period end date based on start_date, notice_period_val, and unit ('days' or 'months')
        using calendar-month semantics for Months.
        """
        if not start_date:
            return False
        val = notice_period_val if notice_period_val is not None else getattr(self, 'contract_expiration_notice_period', 0)
        u = unit or getattr(self, 'hds_in_notice_period_unit', 'days') or 'days'
        s_date = fields.Date.from_string(start_date)

        if u == 'months':
            from dateutil.relativedelta import relativedelta
            return s_date + relativedelta(months=int(val or 0))
        else:
            from datetime import timedelta
            return s_date + timedelta(days=int(val or 0))

    # Payroll & Bonus Management Configuration Fields
    hds_in_regular_struct_id = fields.Many2one(
        'hr.payroll.structure',
        string="Regular Payroll Structure",
        help="Default Salary Structure used for regular monthly payroll processing."
    )
    hds_in_retention_min_service_months = fields.Integer(
        string="Retention Bonus Min Service (Months)",
        default=12,
        help="Minimum months of service required for Retention Bonus eligibility."
    )
    hds_in_retention_exclude_notice_period = fields.Boolean(
        string="Exclude Notice Period from Retention Bonus",
        default=True,
        help="If checked, employees currently serving notice period will not be eligible for Retention Bonus."
    )
    hds_in_bonus_apply_tds = fields.Boolean(
        string="Apply TDS on Bonus",
        default=True,
        help="If checked, Tax Deducted at Source (TDS) applies to bonuses (Performance & Retention Bonus)."
    )
    hds_in_bonus_apply_pf = fields.Boolean(
        string="Apply PF on Bonus",
        default=False,
        help="If checked, Provident Fund (PF) rule applies to Bonus Payroll."
    )
    hds_in_bonus_apply_esi = fields.Boolean(
        string="Apply ESI on Bonus",
        default=False,
        help="If checked, Employee State Insurance (ESI) rule applies to Bonus Payroll."
    )
    hds_in_bonus_apply_pt = fields.Boolean(
        string="Apply Professional Tax on Bonus",
        default=False,
        help="If checked, Professional Tax (PT) rule applies to Bonus Payroll."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('hds_in_tan'):
                vals['hds_in_tan'] = vals['hds_in_tan'].strip().upper()
            if 'hds_in_epf_applicable' in vals:
                vals['hds_in_eps_applicable'] = vals['hds_in_epf_applicable']
                vals['hds_in_edli_applicable'] = vals['hds_in_epf_applicable']
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('hds_in_tan'):
            vals['hds_in_tan'] = vals['hds_in_tan'].strip().upper()
        if 'hds_in_epf_applicable' in vals:
            vals['hds_in_eps_applicable'] = vals['hds_in_epf_applicable']
            vals['hds_in_edli_applicable'] = vals['hds_in_epf_applicable']
        res = super().write(vals)
        if 'hds_in_enable_lwf' in vals or 'hds_in_enable_leave_encashment' in vals:
            self.env.transaction.invalidate_ormcache()
            self.env.invalidate_all()
        return res


    @api.constrains('partner_id', 'hds_in_enable_lwf', 'hds_in_enable_professional_tax')
    def _check_company_state_statutory(self):
        """Ensures company address has a state when statutory compliance modules (LWF / PT) are active."""
        if not self.env.context.get('validate_statutory_threshold'):
            if not self.env.registry.ready or self.env.context.get('install_mode') or self.env.context.get('skip_statutory_threshold_check'):
                return
        for company in self:
            if company.hds_in_enable_lwf or company.hds_in_enable_professional_tax:
                if not company.partner_id or not company.partner_id.state_id:
                    raise ValidationError(_(
                        "Company State is required! Please configure the State in Company Address "
                        "(Settings > Companies > Address) for statutory payroll calculations (LWF, Professional Tax)."
                    ))

    @api.constrains('hds_in_enable_lwf', 'partner_id')
    def _check_company_lwf_minimum_headcount(self):
        """
        Ensures that enabling LWF at the company level strictly complies with the state's
        statutory minimum employee count threshold. If the active headcount in the company's
        state is below the mandated threshold, LWF cannot be enabled.
        """
        if not self.env.context.get('validate_statutory_threshold'):
            if not self.env.registry.ready or self.env.context.get('install_mode') or self.env.context.get('skip_statutory_threshold_check'):
                return

        today = fields.Date.today()
        for company in self:
            if not company.hds_in_enable_lwf:
                continue
            state = company.partner_id.state_id if company.partner_id else False
            if not state:
                continue

            rate_config = self.env['lwf.state.rate'].search([
                ('state_id', '=', state.id),
                ('date_from', '<=', today),
                '|', ('date_to', '=', False), ('date_to', '>=', today),
            ], order='date_from desc, id desc', limit=1)

            if rate_config and rate_config.min_employee_count > 0:
                base_domain = [('company_id', '=', company.id), ('active', '=', True)]
                state_domain = base_domain + [
                    '|',
                    ('address_id.state_id', '=', state.id),
                    '|',
                    '&', ('address_id.state_id', '=', False), ('work_location_id.address_id.state_id', '=', state.id),
                    '&', ('address_id.state_id', '=', False), ('work_location_id.address_id.state_id', '=', False),
                ]
                headcount = self.env['hr.employee'].search_count(state_domain)
                if headcount < rate_config.min_employee_count:
                    raise ValidationError(_(
                        "Cannot enable Labour Welfare Fund (LWF) for company '%(company)s'!\n\n"
                        "• Registered State: %(state)s\n"
                        "• Statutory Minimum Required Headcount: %(required)s employees\n"
                        "• Current Active Headcount in %(state)s: %(current)s employees\n\n"
                        "The company active headcount is below the statutory threshold mandated by "
                        "the %(state)s Labour Welfare Fund Act. LWF cannot be enabled at company level until "
                        "the minimum employee threshold is reached, or update the threshold in 'Configure State Rates & Thresholds' if government rules have changed."
                    ) % {
                        'company': company.name,
                        'state': state.name,
                        'required': rate_config.min_employee_count,
                        'current': headcount,
                    })


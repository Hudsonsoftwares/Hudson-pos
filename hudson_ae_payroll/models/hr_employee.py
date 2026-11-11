# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

GCC_COUNTRY_CODES = {'SA', 'KW', 'BH', 'OM', 'QA'}


class HrEmployee(models.Model):
    """
    UAE Employee Statutory Classification Extension.

    Stores statutory classification context without financial calculations:
    - Employee Category (UAE National / GCC National / Other) automatically derived from Nationality
    - GCC Home Country with strict consistency validation against Nationality
    - Applicable Emirate defaulted from company with manual override capability
    - Pension Authority derived 100% dynamically from the applicable Emirate
    - Continuous Service Start Date & Overtime Eligibility
    """
    _inherit = 'hr.employee'

    uae_employee_category = fields.Selection([
        ('uae_national', 'UAE National'),
        ('gcc_national', 'GCC National'),
        ('expatriate', 'Other / Expatriate'),
    ], string='UAE Employee Category',
        compute='_compute_uae_employee_category',
        store=True,
        readonly=True,
        help='Statutory classification context derived automatically from nationality.')

    uae_gcc_country_id = fields.Many2one(
        'res.country',
        string='GCC Country / Home Country',
        domain="[('code', 'in', ('SA', 'KW', 'BH', 'OM', 'QA'))]",
        compute='_compute_uae_gcc_country_id',
        store=True,
        readonly=False,
        help='Applicable GCC home country for social security extension scheme. Defaults from employee nationality.'
    )

    uae_emirate_id = fields.Many2one(
        'uae.emirate',
        string='Applicable Emirate',
        compute='_compute_uae_emirate_id',
        store=True,
        readonly=False,
        help="Employee's applicable Emirate governing statutory pension administration, defaulted from company."
    )

    uae_jurisdiction_type = fields.Selection([
        ('mainland', 'Mainland'),
        ('free_zone', 'Free Zone'),
    ], string='Jurisdiction Type',
        compute='_compute_uae_jurisdiction_context',
        store=True,
        readonly=False,
        help='Mainland vs Free Zone jurisdiction classification, defaulted from company.'
    )

    uae_jurisdiction_id = fields.Many2one(
        'uae.payroll.jurisdiction',
        string='Applicable Jurisdiction',
        compute='_compute_uae_jurisdiction_context',
        store=True,
        readonly=False,
        domain="[('emirate_id', '=', uae_emirate_id), ('jurisdiction_type', '=', uae_jurisdiction_type)]",
        help='Specific operating jurisdiction profile governing regulatory and pension authority rules.'
    )

    uae_pension_authority_id = fields.Many2one(
        'uae.pension.authority',
        string='Pension Authority',
        compute='_compute_uae_pension_authority_id',
        store=True,
        readonly=True,
        help='Statutory pension authority resolved dynamically from Emirate and Jurisdiction configuration.'
    )

    uae_pension_authority_status = fields.Selection([
        ('valid', 'Valid / Authority Enabled'),
        ('authority_not_enabled_at_company', 'Authority Not Enabled at Company'),
        ('not_applicable', 'Not Applicable'),
    ], string='Pension Authority Status',
        compute='_compute_uae_pension_authority_status',
        store=True,
        help='Validates whether the derived pension authority is enabled for statutory compliance at the employer company.')

    uae_pension_authority_warning = fields.Char(
        string='Pension Authority Warning',
        compute='_compute_uae_pension_authority_status',
        store=True,
        help='Informational warning if pension authority is not enabled for the company.')

    uae_pension_scheme_id = fields.Many2one(
        'uae.pension.scheme',
        string='Applicable Pension Scheme',
        domain="['|', ('active', '=', True), ('id', '=', uae_pension_scheme_id)]",
        context={'active_test': False},
        help='Determines which statutory pension scheme (Legacy vs New Law) applies to the individual employee.'
    )

    uae_pension_registration_status = fields.Selection([
        ('pending_verification', 'Pending Verification'),
        ('not_registered', 'Not Registered'),
        ('registered', 'Registered'),
        ('exempt', 'Exempt'),
        ('not_applicable', 'Not Applicable'),
    ], string='Pension Registration Status',
        default='pending_verification',
        compute='_compute_pension_registration_status',
        store=True,
        readonly=False,
        help='Tracks the statutory pension/social security registration status.')

    uae_pension_registration_number = fields.Char(
        string='Pension Registration Number',
        help='Statutory registration / membership reference with the governing pension authority.'
    )

    uae_continuous_service_start_date = fields.Date(
        string='Continuous Service Start Date',
        help='Legally relevant continuous service start date (for service thresholds, pension cutover, and future EOSB calculations).'
    )

    uae_overtime_eligibility = fields.Selection([
        ('eligible', 'Eligible'),
        ('exempt', 'Exempt'),
        ('pending_verification', 'Pending Verification'),
    ], string='Overtime Eligibility',
        default='eligible',
        help='Employee classification context for statutory overtime rules.')

    uae_statutory_status = fields.Selection([
        ('draft', 'Draft'),
        ('pending_verification', 'Pending Verification'),
        ('verified', 'Verified'),
    ], string='Statutory Status',
        default='draft',
        help='Ensures employee statutory profile data is reviewed and verified prior to payroll processing.')

    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================

    @api.depends('country_id', 'country_id.code')
    def _compute_uae_employee_category(self):
        """Derive statutory classification automatically from the employee's Nationality."""
        for employee in self:
            code = (employee.country_id.code or '').upper()
            if code in ('AE', 'ARE'):
                employee.uae_employee_category = 'uae_national'
            elif code in GCC_COUNTRY_CODES:
                employee.uae_employee_category = 'gcc_national'
            else:
                employee.uae_employee_category = 'expatriate'

    @api.depends('country_id', 'uae_employee_category')
    def _compute_uae_gcc_country_id(self):
        """Automatically default GCC Country from employee's nationality."""
        for employee in self:
            if employee.uae_employee_category == 'gcc_national' and employee.country_id:
                if (employee.country_id.code or '').upper() in GCC_COUNTRY_CODES:
                    employee.uae_gcc_country_id = employee.country_id
                elif not employee.uae_gcc_country_id:
                    employee.uae_gcc_country_id = False
            elif employee.uae_employee_category != 'gcc_national':
                employee.uae_gcc_country_id = False

    @api.depends('work_location_id', 'work_location_id.uae_emirate_id', 'company_id', 'company_id.uae_emirate_id')
    def _compute_uae_emirate_id(self):
        """
        Derive applicable Emirate hierarchically when not explicitly set:
        1. Physical work location Emirate (if configured)
        2. Employer company Emirate (if configured)
        """
        for employee in self:
            if not employee.uae_emirate_id:
                if employee.work_location_id and hasattr(employee.work_location_id, 'uae_emirate_id') and employee.work_location_id.uae_emirate_id:
                    employee.uae_emirate_id = employee.work_location_id.uae_emirate_id
                elif employee.company_id and employee.company_id.uae_emirate_id:
                    employee.uae_emirate_id = employee.company_id.uae_emirate_id
                else:
                    employee.uae_emirate_id = False

    @api.onchange('company_id', 'work_location_id')
    def _onchange_company_or_work_location(self):
        if self.work_location_id and hasattr(self.work_location_id, 'uae_emirate_id') and self.work_location_id.uae_emirate_id:
            self.uae_emirate_id = self.work_location_id.uae_emirate_id
        elif self.company_id and self.company_id.uae_emirate_id:
            self.uae_emirate_id = self.company_id.uae_emirate_id

    @api.depends('company_id', 'company_id.uae_jurisdiction_id', 'company_id.uae_jurisdiction_type')
    def _compute_uae_jurisdiction_context(self):
        """Default jurisdiction classification from company when not explicitly set."""
        for employee in self:
            if not employee.uae_jurisdiction_id:
                if employee.company_id and employee.company_id.uae_jurisdiction_id:
                    employee.uae_jurisdiction_id = employee.company_id.uae_jurisdiction_id
                    employee.uae_jurisdiction_type = employee.company_id.uae_jurisdiction_type

    @api.onchange('uae_emirate_id')
    def _onchange_uae_emirate_id(self):
        if self.uae_jurisdiction_id and self.uae_emirate_id:
            if self.uae_jurisdiction_id.emirate_id and self.uae_jurisdiction_id.emirate_id != self.uae_emirate_id:
                self.uae_jurisdiction_id = False
        self._compute_uae_pension_authority_id()
        self._compute_uae_pension_authority_status()

    @api.onchange('uae_jurisdiction_type')
    def _onchange_uae_jurisdiction_type(self):
        if self.uae_jurisdiction_id and self.uae_jurisdiction_type:
            if self.uae_jurisdiction_id.jurisdiction_type != self.uae_jurisdiction_type:
                self.uae_jurisdiction_id = False
        self._compute_uae_pension_authority_id()
        self._compute_uae_pension_authority_status()

    @api.onchange('uae_jurisdiction_id')
    def _onchange_uae_jurisdiction_id(self):
        if self.uae_jurisdiction_id:
            if not self.uae_emirate_id and self.uae_jurisdiction_id.emirate_id:
                self.uae_emirate_id = self.uae_jurisdiction_id.emirate_id
            if not self.uae_jurisdiction_type and self.uae_jurisdiction_id.jurisdiction_type:
                self.uae_jurisdiction_type = self.uae_jurisdiction_id.jurisdiction_type
        self._compute_uae_pension_authority_id()
        self._compute_uae_pension_authority_status()

    @api.depends(
        'uae_emirate_id', 'uae_emirate_id.pension_authority_id',
        'uae_jurisdiction_id', 'uae_jurisdiction_id.pension_authority_id',
        'company_id', 'company_id.uae_jurisdiction_id', 'company_id.uae_jurisdiction_id.pension_authority_id',
        'company_id.uae_emirate_id', 'company_id.uae_emirate_id.pension_authority_id',
        'uae_employee_category'
    )
    def _compute_uae_pension_authority_id(self):
        """
        Derive Pension Authority dynamically using configured mapping:
        Applicable Emirate + Applicable Jurisdiction / Jurisdiction Type -> Pension Authority Resolver.

        Resolution Priority:
        1. Employee's Applicable Jurisdiction (if configured with pension_authority_id)
        2. Employer Company's Jurisdiction (if configured with pension_authority_id)
        3. Employee's Applicable Emirate (emirate-level master mapping)
        4. Employer Company's Emirate (company emirate master mapping)
        """
        for employee in self:
            if employee.uae_employee_category in ('uae_national', 'gcc_national'):
                authority = False
                # 1. Employee Jurisdiction level mapping
                if employee.uae_jurisdiction_id and employee.uae_jurisdiction_id.pension_authority_id:
                    authority = employee.uae_jurisdiction_id.pension_authority_id
                # 2. Company Jurisdiction level mapping
                elif employee.company_id and employee.company_id.uae_jurisdiction_id and employee.company_id.uae_jurisdiction_id.pension_authority_id:
                    authority = employee.company_id.uae_jurisdiction_id.pension_authority_id
                # 3. Employee Emirate level mapping
                elif employee.uae_emirate_id and employee.uae_emirate_id.pension_authority_id:
                    authority = employee.uae_emirate_id.pension_authority_id
                # 4. Company Emirate level mapping
                elif employee.company_id and employee.company_id.uae_emirate_id and employee.company_id.uae_emirate_id.pension_authority_id:
                    authority = employee.company_id.uae_emirate_id.pension_authority_id

                employee.uae_pension_authority_id = authority
            else:
                employee.uae_pension_authority_id = False

    @api.depends(
        'uae_pension_authority_id', 'company_id',
        'company_id.hds_ae_enable_gpssa', 'company_id.hds_ae_enable_adpf',
        'uae_employee_category'
    )
    def _compute_uae_pension_authority_status(self):
        """
        Validate whether the derived pension authority is enabled for the employer company.
        Does not block employee record creation/saving, but flags AUTHORITY_NOT_ENABLED_AT_COMPANY
        and raises validation when attempting to mark statutory status as verified or run payroll.
        """
        for employee in self:
            if employee.uae_employee_category not in ('uae_national', 'gcc_national') or not employee.uae_pension_authority_id:
                employee.uae_pension_authority_status = 'not_applicable'
                employee.uae_pension_authority_warning = False
                continue

            company = employee.company_id
            authority = employee.uae_pension_authority_id
            if not company or not company.is_pension_authority_enabled(authority):
                employee.uae_pension_authority_status = 'authority_not_enabled_at_company'
                employee.uae_pension_authority_warning = _(
                    "Pension Authority '%(authority)s' (derived from Emirate '%(emirate)s') is not enabled for company '%(company)s'. "
                    "Enable %(auth_code)s in Company UAE Payroll Configuration before verifying statutory status or processing pension."
                ) % {
                    'authority': authority.name,
                    'emirate': employee.uae_emirate_id.name if employee.uae_emirate_id else _('Unspecified'),
                    'company': company.name if company else _('Company'),
                    'auth_code': authority.code or authority.name,
                }
            else:
                employee.uae_pension_authority_status = 'valid'
                employee.uae_pension_authority_warning = False

    @api.onchange('company_id', 'uae_emirate_id', 'uae_jurisdiction_id', 'uae_pension_authority_id')
    def _onchange_filter_pension_schemes(self):
        """Dynamically clear incompatible schemes and return domain for UI."""
        if self.uae_pension_scheme_id:
            if self.company_id and self.company_id.uae_pension_scheme_ids:
                if self.uae_pension_scheme_id not in self.company_id.uae_pension_scheme_ids:
                    self.uae_pension_scheme_id = False
            if self.uae_pension_scheme_id and self.uae_pension_scheme_id.pension_authority_ids and self.uae_pension_authority_id:
                if self.uae_pension_authority_id not in self.uae_pension_scheme_id.pension_authority_ids:
                    self.uae_pension_scheme_id = False

        domain = [('active', '=', True)]
        if self.company_id and self.company_id.uae_pension_scheme_ids:
            domain = [('id', 'in', self.company_id.uae_pension_scheme_ids.ids), ('active', '=', True)]
        if self.uae_pension_authority_id:
            domain += ['|', ('pension_authority_ids', '=', False), ('pension_authority_ids', 'in', [self.uae_pension_authority_id.id])]
        return {'domain': {'uae_pension_scheme_id': domain}}

    @api.depends('uae_employee_category')
    def _compute_pension_registration_status(self):
        """Update registration status default context when category changes."""
        for employee in self:
            if employee.uae_employee_category == 'expatriate':
                employee.uae_pension_registration_status = 'not_applicable'
            elif employee.uae_pension_registration_status == 'not_applicable':
                employee.uae_pension_registration_status = 'pending_verification'

    # =========================================================================
    # CONSTRAINTS & VALIDATIONS
    # =========================================================================

    @api.constrains('country_id', 'uae_gcc_country_id', 'uae_employee_category')
    def _check_uae_gcc_country(self):
        """Validate that GCC Country cannot differ from the employee's actual nationality."""
        for employee in self:
            if employee.uae_employee_category == 'gcc_national' and employee.country_id:
                if employee.uae_gcc_country_id and employee.uae_gcc_country_id != employee.country_id:
                    raise ValidationError(_(
                        "GCC Country '%s' cannot differ from employee's actual nationality '%s' for employee '%s'.",
                        employee.uae_gcc_country_id.name, employee.country_id.name, employee.name
                    ))

    @api.constrains('uae_continuous_service_start_date', 'birthday')
    def _check_uae_continuous_service_date(self):
        for employee in self:
            if employee.uae_continuous_service_start_date and employee.birthday:
                if employee.uae_continuous_service_start_date < employee.birthday:
                    raise ValidationError(_(
                        "Continuous Service Start Date (%s) cannot be earlier than the employee's Birthday (%s) for employee '%s'.",
                        employee.uae_continuous_service_start_date, employee.birthday, employee.name
                    ))

    @api.constrains('uae_pension_registration_status', 'uae_pension_registration_number')
    def _check_uae_pension_registration(self):
        for employee in self:
            if employee.uae_pension_registration_status in ('exempt', 'not_applicable') and employee.uae_pension_registration_number:
                pass

    @api.constrains('uae_pension_registration_status', 'uae_pension_authority_status', 'uae_statutory_status')
    def _check_pension_registration_and_verification(self):
        """
        Block pension registration or verified statutory status with active registration
        if the governing pension authority is not enabled for the company.
        """
        for employee in self:
            if employee.uae_pension_authority_status == 'authority_not_enabled_at_company':
                if employee.uae_pension_registration_status == 'registered':
                    raise ValidationError(employee.uae_pension_authority_warning or _(
                        "Cannot register employee for pension: Pension Authority is not enabled at the company."
                    ))
                if employee.uae_statutory_status == 'verified' and employee.uae_pension_registration_status in ('registered', 'pending_verification'):
                    raise ValidationError(employee.uae_pension_authority_warning or _(
                        "Cannot mark statutory status as Verified: Pension Authority is not enabled for the company."
                    ))

    @api.constrains('uae_pension_scheme_id', 'company_id', 'uae_pension_authority_id')
    def _check_uae_pension_scheme_applicability(self):
        """Validate that assigned pension scheme is permitted by company and matches resolved authority."""
        for employee in self:
            scheme = employee.uae_pension_scheme_id
            if not scheme:
                continue

            company = employee.company_id
            if company and company.uae_pension_scheme_ids and scheme not in company.uae_pension_scheme_ids:
                permitted_names = ', '.join(company.uae_pension_scheme_ids.mapped('name'))
                raise ValidationError(_(
                    "Pension Scheme '%(scheme)s' is not enabled for company '%(company)s'. "
                    "Permitted schemes: %(permitted)s."
                ) % {
                    'scheme': scheme.name,
                    'company': company.name,
                    'permitted': permitted_names,
                })

            if scheme.pension_authority_ids and employee.uae_pension_authority_id:
                if employee.uae_pension_authority_id not in scheme.pension_authority_ids:
                    auth_names = ', '.join(scheme.pension_authority_ids.mapped('name'))
                    raise ValidationError(_(
                        "Pension Scheme '%(scheme)s' applies only to authority '%(scheme_auths)s', "
                        "which does not match employee's resolved authority '%(emp_auth)s'."
                    ) % {
                        'scheme': scheme.name,
                        'scheme_auths': auth_names,
                        'emp_auth': employee.uae_pension_authority_id.name,
                    })

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('uae_pension_scheme_id'):
                scheme = self.env['uae.pension.scheme'].with_context(active_test=False).browse(vals['uae_pension_scheme_id'])
                if scheme.exists() and not scheme.active:
                    raise ValidationError(_(
                        "Cannot assign an inactive or archived Pension Scheme ('%s'). Please select an active scheme."
                    ) % scheme.name)
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('uae_pension_scheme_id'):
            scheme = self.env['uae.pension.scheme'].with_context(active_test=False).browse(vals['uae_pension_scheme_id'])
            if scheme.exists() and not scheme.active:
                for employee in self:
                    if employee.uae_pension_scheme_id != scheme:
                        raise ValidationError(_(
                            "Cannot assign an inactive or archived Pension Scheme ('%s'). Please select an active scheme."
                        ) % scheme.name)
        return super().write(vals)


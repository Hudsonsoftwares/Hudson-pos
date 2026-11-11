# -*- coding: utf-8 -*-
import re
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hds_in_epf_applicable = fields.Boolean(
        related='company_id.hds_in_epf_applicable',
        readonly=False,
        string="EPF Applicable"
    )
    hds_in_epf_employer_id = fields.Char(
        related='company_id.hds_in_epf_employer_id',
        readonly=False,
        string="EPF Employer ID"
    )
    hds_in_eps_applicable = fields.Boolean(
        related='company_id.hds_in_eps_applicable',
        readonly=False,
        string="EPS Applicable"
    )
    hds_in_edli_applicable = fields.Boolean(
        related='company_id.hds_in_edli_applicable',
        readonly=False,
        string="EDLI Applicable"
    )
    hds_in_edli_registration_number = fields.Char(
        related='company_id.hds_in_edli_registration_number',
        readonly=False,
        string="EDLI Registration Number"
    )

    # ESIC Company Configuration Related Fields
    hds_in_esic_applicable = fields.Boolean(
        related='company_id.hds_in_esic_applicable',
        readonly=False,
        string="Enable ESIC"
    )
    hds_in_esic_employer_code = fields.Char(
        related='company_id.hds_in_esic_employer_code',
        readonly=False,
        string="ESIC IP Number"
    )
    hds_in_esic_registration_no = fields.Char(
        related='company_id.hds_in_esic_registration_no',
        readonly=False,
        string="ESIC Registration Number"
    )
    hds_in_esic_branch_office = fields.Char(
        related='company_id.hds_in_esic_branch_office',
        readonly=False,
        string="ESIC Branch Office"
    )
    hds_in_esic_contribution_period_type = fields.Selection(
        related='company_id.hds_in_esic_contribution_period_type',
        readonly=False,
        string="Contribution Periods Cycle"
    )
    hds_in_esic_custom_period1_start_month = fields.Selection(
        related='company_id.hds_in_esic_custom_period1_start_month',
        readonly=False,
        string="Period 1 Start Month"
    )
    hds_in_esic_custom_period1_end_month = fields.Selection(
        related='company_id.hds_in_esic_custom_period1_end_month',
        readonly=False,
        string="Period 1 End Month"
    )
    hds_in_esic_custom_period2_start_month = fields.Selection(
        related='company_id.hds_in_esic_custom_period2_start_month',
        readonly=False,
        string="Period 2 Start Month"
    )
    hds_in_esic_custom_period2_end_month = fields.Selection(
        related='company_id.hds_in_esic_custom_period2_end_month',
        readonly=False,
        string="Period 2 End Month"
    )

    # LWF Company Configuration Related Fields
    hds_in_enable_lwf = fields.Boolean(
        related='company_id.hds_in_enable_lwf',
        readonly=False,
        string="Enable Labour Welfare Fund (LWF)"
    )
    hds_in_lwf_registration_no = fields.Char(
        related='company_id.hds_in_lwf_registration_no',
        readonly=False,
        string="LWF Registration Number"
    )
    hds_in_lwf_threshold_info = fields.Html(
        string="LWF Statutory Threshold Status",
        compute='_compute_hds_in_lwf_threshold_info',
        sanitize=False,
    )


    # Gratuity Company Configuration Related Fields
    hds_in_enable_gratuity = fields.Boolean(
        related='company_id.hds_in_enable_gratuity',
        readonly=False,
        string="Enable Gratuity"
    )
    hds_in_gratuity_registration_no = fields.Char(
        related='company_id.hds_in_gratuity_registration_no',
        readonly=False,
        string="Gratuity Registration Number"
    )

    # Leave Encashment Company Configuration Related Fields
    hds_in_enable_leave_encashment = fields.Boolean(
        related='company_id.hds_in_enable_leave_encashment',
        readonly=False,
        string="Enable Leave Encashment"
    )
    hds_in_leave_encashment_registration_no = fields.Char(
        related='company_id.hds_in_leave_encashment_registration_no',
        readonly=False,
        string="Leave Encashment Policy Number"
    )

    # Professional Tax (PT) Company Configuration Related Fields
    hds_in_enable_professional_tax = fields.Boolean(
        related='company_id.hds_in_enable_professional_tax',
        readonly=False,
        string="Enable Professional Tax"
    )
    hds_in_professional_tax_registration_no = fields.Char(
        related='company_id.hds_in_professional_tax_registration_no',
        readonly=False,
        string="Professional Tax Registration Number"
    )

    # Tax Deducted at Source (TDS) Company Configuration Related Fields
    hds_in_tds_applicable = fields.Boolean(
        related='company_id.hds_in_tds_applicable',
        readonly=False,
        string="Enable TDS"
    )
    hds_in_tan = fields.Char(
        related='company_id.hds_in_tan',
        readonly=False,
        string="TAN"
    )
    hds_in_company_pan = fields.Char(related='company_id.hds_in_company_pan', readonly=False)
    hds_in_deductor_type = fields.Selection(related='company_id.hds_in_deductor_type', readonly=False)
    hds_in_tds_responsible_name = fields.Char(related='company_id.hds_in_tds_responsible_name', readonly=False)
    hds_in_tds_responsible_designation = fields.Char(related='company_id.hds_in_tds_responsible_designation', readonly=False)
    hds_in_tds_responsible_email = fields.Char(related='company_id.hds_in_tds_responsible_email', readonly=False)
    hds_in_tds_responsible_mobile = fields.Char(related='company_id.hds_in_tds_responsible_mobile', readonly=False)
    hds_in_default_tax_regime = fields.Selection(
        related='company_id.hds_in_default_tax_regime',
        readonly=False,
        string="Default Tax Regime"
    )
    hds_in_default_tax_year = fields.Many2one(
        related='company_id.hds_in_default_tax_year',
        readonly=False,
        string="Default Tax Year"
    )
    tds_month_division = fields.Integer(
        related='hds_in_default_tax_year.tds_month_division',
        readonly=False,
        string="TDS Month Division",
        help="Number of months to divide annual estimated TDS tax liability across regular monthly pay periods."
    )


    # Payroll Structure Settings
    hds_in_regular_struct_id = fields.Many2one(
        related='company_id.hds_in_regular_struct_id',
        readonly=False,
        string="Regular Payroll Structure"
    )
    # Retention Bonus Settings
    hds_in_retention_min_service_months = fields.Integer(
        related='company_id.hds_in_retention_min_service_months',
        readonly=False,
        string="Retention Bonus Min Service (Months)"
    )

    # Notice Pay Settlement Configuration Related Fields
    contract_expiration_notice_period = fields.Integer(
        related='company_id.contract_expiration_notice_period',
        readonly=False,
        string="Notice Period Length"
    )
    hds_in_enable_notice_pay_settlement = fields.Boolean(
        related='company_id.hds_in_enable_notice_pay_settlement',
        readonly=False,
        string="Enable Notice Pay Settlement"
    )
    hds_in_notice_period_unit = fields.Selection(
        related='company_id.hds_in_notice_period_unit',
        readonly=False,
        string="Notice Period Unit"
    )

    hds_in_is_india_company = fields.Boolean(
        string="Is India Company",
        compute='_compute_hds_in_is_india_company'
    )

    @api.depends('company_id', 'company_id.country_id')
    def _compute_hds_in_is_india_company(self):
        for record in self:
            country = record.company_id.country_id
            record.hds_in_is_india_company = bool(
                country and country.code == 'IN'
            )

    @api.depends('company_id', 'company_id.partner_id.state_id')
    def _compute_hds_in_lwf_threshold_info(self):
        today = fields.Date.today()
        for record in self:
            comp = record.company_id
            state = comp.partner_id.state_id if (comp and comp.partner_id) else False
            if not state:
                record.hds_in_lwf_threshold_info = (
                    '<div class="alert alert-warning py-1 px-2 mb-1" style="font-size: 12px;">'
                    '⚠️ <strong>Company State not configured:</strong> Please set State in Company Address to verify LWF statutory applicability.'
                    '</div>'
                )
                continue

            rate_config = self.env['lwf.state.rate'].search([
                ('state_id', '=', state.id),
                ('date_from', '<=', today),
                '|', ('date_to', '=', False), ('date_to', '>=', today),
            ], order='date_from desc, id desc', limit=1)

            if not rate_config:
                record.hds_in_lwf_threshold_info = (
                    f'<div class="alert alert-secondary py-1 px-2 mb-1" style="font-size: 12px;">'
                    f'ℹ️ No active statutory LWF rule configured for <strong>{state.name}</strong>.'
                    f'</div>'
                )
                continue

            base_domain = [('company_id', '=', comp.id), ('active', '=', True)]
            state_domain = base_domain + [
                '|',
                ('address_id.state_id', '=', state.id),
                '|',
                '&', ('address_id.state_id', '=', False), ('work_location_id.address_id.state_id', '=', state.id),
                '&', ('address_id.state_id', '=', False), ('work_location_id.address_id.state_id', '=', False),
            ]
            headcount = self.env['hr.employee'].search_count(state_domain)
            min_req = rate_config.min_employee_count

            if min_req > 0 and headcount < min_req:
                record.hds_in_lwf_threshold_info = (
                    f'<div class="alert alert-warning py-1 px-2 mb-1" style="font-size: 12px; border-left: 3px solid #f0ad4e;">'
                    f'⚠️ <strong>Statutory Threshold Not Met:</strong> {state.name} mandates at least <strong>{min_req}</strong> employees. '
                    f'Current active count in {state.name}: <strong>{headcount}</strong> (Below Threshold).'
                    f'</div>'
                )
            else:
                req_text = f"Minimum required: {min_req}" if min_req > 0 else "Applies to all establishments"
                record.hds_in_lwf_threshold_info = (
                    f'<div class="alert alert-success py-1 px-2 mb-1" style="font-size: 12px; border-left: 3px solid #5cb85c;">'
                    f'✅ <strong>Eligible for LWF:</strong> {state.name} ({req_text}). '
                    f'Current active count in {state.name}: <strong>{headcount}</strong>.'
                    f'</div>'
                )

    @api.onchange('hds_in_enable_lwf')
    def _onchange_hds_in_enable_lwf(self):
        if not self.hds_in_enable_lwf:
            return
        comp = self.company_id
        state = comp.partner_id.state_id if (comp and comp.partner_id) else False
        if not state:
            return
        today = fields.Date.today()
        rate_config = self.env['lwf.state.rate'].search([
            ('state_id', '=', state.id),
            ('date_from', '<=', today),
            '|', ('date_to', '=', False), ('date_to', '>=', today),
        ], order='date_from desc, id desc', limit=1)

        if rate_config and rate_config.min_employee_count > 0:
            base_domain = [('company_id', '=', comp.id), ('active', '=', True)]
            state_domain = base_domain + [
                '|',
                ('address_id.state_id', '=', state.id),
                '|',
                '&', ('address_id.state_id', '=', False), ('work_location_id.address_id.state_id', '=', state.id),
                '&', ('address_id.state_id', '=', False), ('work_location_id.address_id.state_id', '=', False),
            ]
            headcount = self.env['hr.employee'].search_count(state_domain)
            if headcount < rate_config.min_employee_count:
                return {
                    'warning': {
                        'title': _("Statutory Minimum Headcount Not Met"),
                        'message': _(
                            "Labour Welfare Fund (LWF) in %(state)s requires at least %(min_req)s active employees.\n\n"
                            "Your company currently has only %(current)s active employees in %(state)s. "
                            "Enabling LWF is not permitted until the statutory employee threshold is reached, "
                            "or adjust the statutory threshold if state laws have changed."
                        ) % {
                            'state': state.name,
                            'min_req': rate_config.min_employee_count,
                            'current': headcount,
                        }
                    }
                }

    def set_values(self):
        tan_pattern = re.compile(r'^[A-Z]{4}[0-9]{5}[A-Z]{1}$')
        for record in self:
            if record.hds_in_tds_applicable:
                tan = (record.hds_in_tan or '').strip().upper()
                if not tan:
                    raise ValidationError(_(
                        "TAN (Tax Deduction and Collection Account Number) is mandatory when TDS is enabled."
                    ))
                if not tan_pattern.match(tan):
                    raise ValidationError(_(
                        "Invalid TAN format '%s'. TAN must be 10 characters long with 4 uppercase letters, 5 digits, and 1 letter (e.g. ABCD12345E)."
                    ) % record.hds_in_tan)
                if not record.hds_in_default_tax_regime:
                    raise ValidationError(_(
                        "Default Tax Regime is mandatory when TDS is enabled."
                    ))
                record.hds_in_tan = tan
                pan = (record.hds_in_company_pan or '').strip().upper()
                if pan and not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan):
                    raise ValidationError(_(
                        "Invalid Company PAN '%s'. PAN must be 10 characters: 5 letters, 4 digits and 1 letter (e.g. ABCDE1234F)."
                    ) % record.hds_in_company_pan)
                if pan != (record.hds_in_company_pan or ''):
                    record.hds_in_company_pan = pan
            if not self.env.registry.ready or self.env.context.get('install_mode') or self.env.context.get('skip_statutory_threshold_check'):
                continue
            if (record.hds_in_enable_lwf or record.hds_in_enable_professional_tax):
                comp = record.company_id
                if comp and comp.partner_id and not comp.partner_id.state_id:
                    raise ValidationError(_(
                        "Company State is required! Please configure the State in Company Address "
                        "(Settings > Companies > Address) for statutory payroll calculations (LWF, Professional Tax)."
                    ))
            if record.hds_in_enable_lwf and not self.env.context.get('skip_statutory_threshold_check'):
                if not (self.env.context.get('test_enable') and not self.env.context.get('validate_statutory_threshold')):
                    comp = record.company_id
                    state = comp.partner_id.state_id if (comp and comp.partner_id) else False
                    if state:
                        today = fields.Date.today()
                        rate_config = self.env['lwf.state.rate'].search([
                            ('state_id', '=', state.id),
                            ('date_from', '<=', today),
                            '|', ('date_to', '=', False), ('date_to', '>=', today),
                        ], order='date_from desc, id desc', limit=1)
                        if rate_config and rate_config.min_employee_count > 0:
                            base_domain = [('company_id', '=', comp.id), ('active', '=', True)]
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
                                    "Cannot enable Labour Welfare Fund (LWF) for %(company)s!\n\n"
                                    "• Registered State: %(state)s\n"
                                    "• Statutory Minimum Required Headcount: %(required)s employees\n"
                                    "• Current Active Headcount in %(state)s: %(current)s employees\n\n"
                                    "The company active headcount is below the statutory threshold mandated by "
                                    "the %(state)s Labour Welfare Fund Act. LWF cannot be enabled until the threshold is met, "
                                    "or update the threshold via 'Configure State Rates & Thresholds' if statutory rules have been revised."
                                ) % {
                                    'company': comp.name,
                                    'state': state.name,
                                    'required': rate_config.min_employee_count,
                                    'current': headcount,
                                })
        super().set_values()


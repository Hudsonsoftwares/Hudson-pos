# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models


class HrContract(models.Model):
    """Extension of employee contract (hr.version in Odoo 19) to link salary structures and pay frequencies."""
    _inherit = 'hr.version'

    struct_id = fields.Many2one(
        'hr.payroll.structure',
        string='Salary Structure',
        help="Default salary structure applied to this employee contract"
    )
    structure_type_id = fields.Many2one(
        'hr.payroll.structure.type',
        string='Structure Type',
        help="Category defining pay rules and statutory defaults"
    )
    schedule_pay = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('semi-annually', 'Semi-annually'),
        ('annually', 'Annually'),
        ('weekly', 'Weekly'),
        ('bi-weekly', 'Bi-weekly'),
        ('bi-monthly', 'Bi-monthly'),
    ], string='Scheduled Pay', default='monthly', index=True)

    # Salary Breakdown Components
    basic_salary = fields.Monetary(string='Basic Salary', tracking=True)
    hra = fields.Monetary(string='House Rent Allowance', tracking=True, help="House Rent Allowance")
    da = fields.Monetary(string='Dearness Allowance', tracking=True, help="Dearness Allowance")
    standard_allowance = fields.Monetary(string='Standard Allowance', tracking=True)
    performance_bonus = fields.Monetary(string='Performance Bonus', tracking=True)
    retention_bonus = fields.Monetary(string='Retention Bonus', tracking=True)
    lta_allowance = fields.Monetary(string='Leave Travel Allowance', tracking=True, help="Monthly Leave Travel Allowance (LTA)")
    travel_allowance = fields.Monetary(string='Travel Allowance')
    meal_allowance = fields.Monetary(string='Meal Allowance')
    medical_allowance = fields.Monetary(string='Medical Allowance')
    other_allowance = fields.Monetary(string='Other Allowance')
    fixed_allowance = fields.Monetary(string='Fixed Allowance', tracking=True)
    pay_by_attendance = fields.Boolean(
        string='Pay by Attendance',
        default=True,
        tracking=True,
        help="If enabled, attendance adjustments (overtime / shortage) apply to payslips."
    )
    enable_attendance_threshold = fields.Boolean(
        string='Enable Attendance Threshold',
        default=True,
        tracking=True,
        help="If enabled, when Pay by Attendance is OFF, employee must work at least the minimum threshold days to receive 100% fixed salary."
    )
    min_attendance_threshold_days = fields.Float(
        string='Minimum Attendance Days',
        default=14.0,
        tracking=True,
        help="Minimum days required in the month to qualify for full fixed salary when Pay by Attendance is OFF. If worked days are below this, salary is prorated. If 0 days worked, salary is 0."
    )
    threshold_enabled_manually_set = fields.Boolean(
        string='Threshold Enabled Manually Set',
        default=False,
        copy=False,
        help="Flag indicating whether threshold enabled was manually customized for this contract."
    )
    threshold_days_manually_set = fields.Boolean(
        string='Threshold Days Manually Set',
        default=False,
        copy=False,
        help="Flag indicating whether threshold days was manually customized for this contract."
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        if 'enable_attendance_threshold' in fields_list:
            try:
                res['enable_attendance_threshold'] = getattr(company, 'enable_attendance_threshold', True)
            except Exception:
                res['enable_attendance_threshold'] = True
        if 'min_attendance_threshold_days' in fields_list:
            try:
                res['min_attendance_threshold_days'] = getattr(company, 'min_attendance_threshold_days', 14.0) or 14.0
            except Exception:
                res['min_attendance_threshold_days'] = 14.0
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env['res.company'].browse(vals.get('company_id')) if vals.get('company_id') else self.env.company
            try:
                comp_days = getattr(company, 'min_attendance_threshold_days', 14.0) or 14.0
                comp_enabled = getattr(company, 'enable_attendance_threshold', True)
            except Exception:
                comp_days = 14.0
                comp_enabled = True

            if 'min_attendance_threshold_days' in vals and not vals.get('threshold_days_manually_set'):
                if abs(float(vals['min_attendance_threshold_days'] or 0.0) - comp_days) > 0.001:
                    vals['threshold_days_manually_set'] = True
                else:
                    vals['threshold_days_manually_set'] = False
            elif 'min_attendance_threshold_days' not in vals:
                vals['min_attendance_threshold_days'] = comp_days
                vals['threshold_days_manually_set'] = False

            if 'enable_attendance_threshold' in vals and not vals.get('threshold_enabled_manually_set'):
                if vals['enable_attendance_threshold'] != comp_enabled:
                    vals['threshold_enabled_manually_set'] = True
                else:
                    vals['threshold_enabled_manually_set'] = False
            elif 'enable_attendance_threshold' not in vals:
                vals['enable_attendance_threshold'] = comp_enabled
                vals['threshold_enabled_manually_set'] = False
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('sync_from_company'):
            for rec in self:
                comp = rec.company_id or self.env.company
                try:
                    comp_days = getattr(comp, 'min_attendance_threshold_days', 14.0) or 14.0
                    comp_enabled = getattr(comp, 'enable_attendance_threshold', True)
                except Exception:
                    comp_days = 14.0
                    comp_enabled = True

                local_vals = vals.copy()
                if 'min_attendance_threshold_days' in local_vals and 'threshold_days_manually_set' not in local_vals:
                    if abs(float(local_vals['min_attendance_threshold_days'] or 0.0) - comp_days) > 0.001:
                        local_vals['threshold_days_manually_set'] = True
                    else:
                        local_vals['threshold_days_manually_set'] = False

                if 'enable_attendance_threshold' in local_vals and 'threshold_enabled_manually_set' not in local_vals:
                    if local_vals['enable_attendance_threshold'] != comp_enabled:
                        local_vals['threshold_enabled_manually_set'] = True
                    else:
                        local_vals['threshold_enabled_manually_set'] = False

                super(HrContract, rec).write(local_vals)
            return True
        return super().write(vals)

    def action_reset_to_company_threshold(self):
        for rec in self:
            comp = rec.company_id or self.env.company
            try:
                comp_days = getattr(comp, 'min_attendance_threshold_days', 14.0) or 14.0
                comp_enabled = getattr(comp, 'enable_attendance_threshold', True)
            except Exception:
                comp_days = 14.0
                comp_enabled = True
            rec.with_context(sync_from_company=True).write({
                'min_attendance_threshold_days': comp_days,
                'enable_attendance_threshold': comp_enabled,
                'threshold_days_manually_set': False,
                'threshold_enabled_manually_set': False,
            })

    @api.onchange('company_id')
    def _onchange_company_attendance_threshold(self):
        for rec in self:
            comp = rec.company_id or self.env.company
            try:
                if not rec.threshold_days_manually_set:
                    rec.min_attendance_threshold_days = getattr(comp, 'min_attendance_threshold_days', 14.0) or 14.0
                if not rec.threshold_enabled_manually_set:
                    rec.enable_attendance_threshold = getattr(comp, 'enable_attendance_threshold', True)
            except Exception:
                pass

    # Breakdown Percentages
    basic_salary_percent = fields.Float(string='Basic %', compute='_compute_breakdown_percentages', digits=(16, 2))
    hra_percent = fields.Float(string='HRA %', compute='_compute_breakdown_percentages', digits=(16, 2))
    da_percent = fields.Float(string='DA %', compute='_compute_breakdown_percentages', digits=(16, 2))
    standard_allowance_percent = fields.Float(string='Standard Allowance %', compute='_compute_breakdown_percentages', digits=(16, 2))
    performance_bonus_percent = fields.Float(string='Performance Bonus %', compute='_compute_breakdown_percentages', digits=(16, 2))
    retention_bonus_percent = fields.Float(string='Retention Bonus %', compute='_compute_breakdown_percentages', digits=(16, 2))
    lta_percent = fields.Float(string='LTA %', compute='_compute_breakdown_percentages', digits=(16, 2))
    travel_allowance_percent = fields.Float(string='Travel %', compute='_compute_breakdown_percentages', digits=(16, 2))
    meal_allowance_percent = fields.Float(string='Meal %', compute='_compute_breakdown_percentages', digits=(16, 2))
    medical_allowance_percent = fields.Float(string='Medical %', compute='_compute_breakdown_percentages', digits=(16, 2))
    other_allowance_percent = fields.Float(string='Other %', compute='_compute_breakdown_percentages', digits=(16, 2))
    fixed_allowance_percent = fields.Float(string='Fixed %', compute='_compute_breakdown_percentages', digits=(16, 2))

    # Breakdown Totals & Validation
    breakdown_total = fields.Monetary(string='Total Breakdown', compute='_compute_breakdown_totals')
    breakdown_diff = fields.Monetary(string='Difference', compute='_compute_breakdown_totals')
    breakdown_is_equal = fields.Boolean(string='Is Valid Breakdown', compute='_compute_breakdown_totals')

    # Country & Localization Flags
    company_country_code = fields.Char(
        string="Company Country Code",
        related='company_id.country_id.code',
        readonly=True,
        store=True
    )
    country_code = fields.Char(
        string="Country Code",
        compute='_compute_country_code',
        store=True,
        readonly=True
    )
    is_india_localization = fields.Boolean(
        string="Is India Localization",
        compute='_compute_country_code',
        store=True
    )
    is_uae_localization = fields.Boolean(
        string="Is UAE Localization",
        compute='_compute_country_code',
        store=True
    )

    @api.depends('company_id.country_id.code', 'structure_type_id.country_id.code')
    def _compute_country_code(self):
        for rec in self:
            code = (
                (rec.structure_type_id.country_id and rec.structure_type_id.country_id.code)
                or (rec.company_id and rec.company_id.country_id and rec.company_id.country_id.code)
                or (self.env.company.country_id and self.env.company.country_id.code)
                or ''
            )
            rec.country_code = code.upper() if code else ''
            rec.is_india_localization = (rec.country_code == 'IN')
            rec.is_uae_localization = (rec.country_code == 'AE')

    @api.depends('wage', 'basic_salary', 'hra', 'da', 'standard_allowance', 'performance_bonus', 'retention_bonus', 'lta_allowance',
                 'travel_allowance', 'meal_allowance', 'medical_allowance', 'other_allowance', 'fixed_allowance')
    def _compute_breakdown_percentages(self):
        for rec in self:
            total = rec.wage or 0.0
            if total > 0.0:
                rec.basic_salary_percent = ((rec.basic_salary or 0.0) / total) * 100.0
                rec.hra_percent = ((rec.hra or 0.0) / total) * 100.0
                rec.da_percent = ((rec.da or 0.0) / total) * 100.0
                rec.standard_allowance_percent = ((rec.standard_allowance or 0.0) / total) * 100.0
                rec.performance_bonus_percent = ((rec.performance_bonus or 0.0) / total) * 100.0
                rec.retention_bonus_percent = ((rec.retention_bonus or 0.0) / total) * 100.0
                rec.lta_percent = ((rec.lta_allowance or 0.0) / total) * 100.0
                rec.travel_allowance_percent = ((rec.travel_allowance or 0.0) / total) * 100.0
                rec.meal_allowance_percent = ((rec.meal_allowance or 0.0) / total) * 100.0
                rec.medical_allowance_percent = ((rec.medical_allowance or 0.0) / total) * 100.0
                rec.other_allowance_percent = ((rec.other_allowance or 0.0) / total) * 100.0
                rec.fixed_allowance_percent = ((rec.fixed_allowance or 0.0) / total) * 100.0
            else:
                rec.basic_salary_percent = 0.0
                rec.hra_percent = 0.0
                rec.da_percent = 0.0
                rec.standard_allowance_percent = 0.0
                rec.performance_bonus_percent = 0.0
                rec.retention_bonus_percent = 0.0
                rec.lta_percent = 0.0
                rec.travel_allowance_percent = 0.0
                rec.meal_allowance_percent = 0.0
                rec.medical_allowance_percent = 0.0
                rec.other_allowance_percent = 0.0
                rec.fixed_allowance_percent = 0.0

    @api.depends('wage', 'basic_salary', 'hra', 'da', 'standard_allowance', 'performance_bonus', 'retention_bonus', 'lta_allowance',
                 'travel_allowance', 'meal_allowance', 'medical_allowance', 'other_allowance', 'fixed_allowance')
    def _compute_breakdown_totals(self):
        for rec in self:
            parts = (
                (rec.basic_salary or 0.0) +
                (rec.hra or 0.0) +
                (rec.da or 0.0) +
                (rec.standard_allowance or 0.0) +
                (rec.performance_bonus or 0.0) +
                (rec.retention_bonus or 0.0) +
                (rec.lta_allowance or 0.0) +
                (rec.travel_allowance or 0.0) +
                (rec.meal_allowance or 0.0) +
                (rec.medical_allowance or 0.0) +
                (rec.other_allowance or 0.0) +
                (rec.fixed_allowance or 0.0)
            )
            rec.breakdown_total = parts
            rec.breakdown_diff = (rec.wage or 0.0) - parts
            rec.breakdown_is_equal = abs(rec.breakdown_diff) < 0.01

    @api.onchange('structure_type_id')
    def _onchange_structure_type_id(self):
        if self.structure_type_id:
            default_struct = self.structure_type_id.default_struct_id or self.env['hr.payroll.structure'].search([
                ('type_id', '=', self.structure_type_id.id)
            ], limit=1)
            if default_struct:
                self.struct_id = default_struct
            if self.structure_type_id.schedule_pay:
                self.schedule_pay = self.structure_type_id.schedule_pay

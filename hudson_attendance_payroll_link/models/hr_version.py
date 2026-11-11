# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models

class HrVersion(models.Model):
    _inherit = 'hr.version'

    # ------------------------------------------------------------------
    # Calendar-derived standards (used for shortage & day-rate calc)
    # ------------------------------------------------------------------
    standard_working_days_per_month = fields.Float(
        string='Standard Working Days per Month',
        compute='_compute_calendar_standards',
        store=True,
        readonly=True,
        help="Stable annual average monthly working days derived from Working Schedule: (working_days_per_week * 52 / 12).",
    )
    standard_hours_per_day = fields.Float(
        string='Standard Hours per Day',
        compute='_compute_calendar_standards',
        store=True,
        readonly=True,
        help="Standard hours per working day derived from Working Schedule.",
    )

    # ------------------------------------------------------------------
    # Salary calculation type
    # ------------------------------------------------------------------
    salary_calculation_type = fields.Selection([
        ('fixed', 'Fixed Salary (Pro-rated by Attendance)'),
    ], string='Salary Calculation Type', default='fixed', required=True)

    # ------------------------------------------------------------------
    # Base hourly rate (used for shortage deduction)
    # ------------------------------------------------------------------
    hourly_rate = fields.Float(
        string='Computed Hourly Rate',
        compute='_compute_hourly_rate',
        store=True,
        help="Computed standard hourly rate: Monthly Salary / (Working Days × Hours per Day)"
    )

    # ------------------------------------------------------------------
    # Shortage deduction rate (writable with manual-override tracking)
    # ------------------------------------------------------------------
    shortage_deduction_rate_per_hour = fields.Float(
        compute='_compute_shortage_deduction_rate_per_hour',
        store=True,
        readonly=False,
        string='Shortage Deduction Rate (per hour)'
    )
    shortage_rate_manually_set = fields.Boolean(
        string='Shortage Rate Manually Set',
        default=False,
        store=True,
    )

    # ------------------------------------------------------------------
    # create / write overrides — maintain shortage rate auto-sync
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('salary_calculation_type'):
                vals['salary_calculation_type'] = 'fixed'
            wage = vals.get('wage', 0.0)

            days = vals.get('standard_working_days_per_month')
            if days is None:
                days = self.env.company.standard_working_days_per_month or 26.0
            hours = vals.get('standard_hours_per_day')
            if hours is None:
                hours = self.env.company.standard_hours_per_day or 8.0

            divisor = days * hours
            hourly = wage / divisor if divisor else 0.0

            # Determine if shortage rate is custom
            if 'shortage_deduction_rate_per_hour' in vals and vals.get('shortage_deduction_rate_per_hour') != 0.0:
                if abs(vals['shortage_deduction_rate_per_hour'] - hourly) > 0.01:
                    vals['shortage_rate_manually_set'] = True
            else:
                vals['shortage_deduction_rate_per_hour'] = hourly
                vals['shortage_rate_manually_set'] = False

        return super(HrVersion, self).create(vals_list)

    def write(self, vals):
        for rec in self:
            local_vals = vals.copy()

            wage = local_vals.get('wage', rec.wage)
            days = local_vals.get('standard_working_days_per_month', rec.standard_working_days_per_month)
            hours = local_vals.get('standard_hours_per_day', rec.standard_hours_per_day)

            divisor = days * hours
            computed_hourly = wage / divisor if divisor else 0.0

            # Check for manual edits to Shortage Rate
            if 'shortage_deduction_rate_per_hour' in local_vals:
                if abs(local_vals['shortage_deduction_rate_per_hour'] - computed_hourly) > 0.01:
                    local_vals['shortage_rate_manually_set'] = True
                else:
                    local_vals['shortage_rate_manually_set'] = False
            elif any(k in local_vals for k in ['wage', 'standard_working_days_per_month', 'standard_hours_per_day']):
                # Auto-update if config changes and NOT custom
                if not rec.shortage_rate_manually_set:
                    local_vals['shortage_deduction_rate_per_hour'] = computed_hourly

            super(HrVersion, rec).write(local_vals)
        return True

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('resource_calendar_id', 'resource_calendar_id.hours_per_day', 'resource_calendar_id.attendance_ids')
    def _compute_calendar_standards(self):
        for rec in self:
            cal = rec.resource_calendar_id
            if cal:
                if cal.hours_per_day:
                    rec.standard_hours_per_day = float(cal.hours_per_day)
                elif cal.attendance_ids:
                    days_dict = {}
                    for att in cal.attendance_ids:
                        span = att.hour_to - att.hour_from
                        days_dict[att.dayofweek] = days_dict.get(att.dayofweek, 0.0) + span
                    rec.standard_hours_per_day = (sum(days_dict.values()) / len(days_dict)) if days_dict else 8.0
                else:
                    rec.standard_hours_per_day = 8.0

                if cal.attendance_ids:
                    working_days_per_week = len(set(cal.attendance_ids.mapped('dayofweek')))
                    rec.standard_working_days_per_month = (working_days_per_week * 52.0) / 12.0
                else:
                    rec.standard_working_days_per_month = 26.0
            else:
                rec.standard_hours_per_day = 8.0
                rec.standard_working_days_per_month = 26.0

    @api.depends('wage', 'standard_working_days_per_month', 'standard_hours_per_day', 'resource_calendar_id')
    def _compute_hourly_rate(self):
        for rec in self:
            divisor = rec.standard_working_days_per_month * rec.standard_hours_per_day
            rec.hourly_rate = rec.wage / divisor if divisor else 0.0

    @api.depends('hourly_rate', 'shortage_rate_manually_set')
    def _compute_shortage_deduction_rate_per_hour(self):
        for rec in self:
            if not rec.shortage_rate_manually_set:
                rec.shortage_deduction_rate_per_hour = rec.hourly_rate
            else:
                rec.shortage_deduction_rate_per_hour = rec.shortage_deduction_rate_per_hour or 0.0

    # ------------------------------------------------------------------
    # Onchanges
    # ------------------------------------------------------------------
    @api.onchange('shortage_deduction_rate_per_hour')
    def _onchange_shortage_deduction_rate_per_hour(self):
        for rec in self:
            if rec.hourly_rate and abs(rec.shortage_deduction_rate_per_hour - rec.hourly_rate) > 0.01:
                rec.shortage_rate_manually_set = True

    @api.onchange('wage', 'standard_working_days_per_month', 'standard_hours_per_day')
    def _onchange_hourly_rate_config(self):
        for rec in self:
            divisor = rec.standard_working_days_per_month * rec.standard_hours_per_day
            computed_hourly = rec.wage / divisor if divisor else 0.0
            rec.hourly_rate = computed_hourly
            if not rec.shortage_rate_manually_set:
                rec.shortage_deduction_rate_per_hour = computed_hourly

    # ------------------------------------------------------------------
    # Period helpers (used by shortage / day-rate salary rules)
    # ------------------------------------------------------------------
    def _get_period_scheduled_hours(self, date_from, date_to):
        """Private helper: Returns total scheduled working hours for the period from resource.calendar."""
        self.ensure_one()
        data = self.env['hr.payslip']._get_attendance_vs_schedule(self, date_from, date_to)
        return data.get('total_period_scheduled_hours') or (data.get('scheduled_hours', 0.0) + data.get('out_of_contract_hours', 0.0))

    def _get_period_scheduled_days(self, date_from, date_to):
        """Private helper: Returns total scheduled working days for the period from resource.calendar."""
        self.ensure_one()
        data = self.env['hr.payslip']._get_attendance_vs_schedule(self, date_from, date_to)
        return data.get('total_period_scheduled_days') or (data.get('scheduled_days', 0.0) + data.get('out_of_contract_days', 0.0))

    def get_period_shortage_rate(self, date_from, date_to):
        """Public method: Returns hourly shortage rate for the payslip period based on scheduled hours."""
        self.ensure_one()
        if not self.pay_by_attendance:
            return 0.0
        sched_hrs = self._get_period_scheduled_hours(date_from, date_to)
        return (self.wage / sched_hrs) if sched_hrs > 0.0 else 0.0

    def get_period_overtime_rate(self, date_from, date_to):
        """Backward-compatibility helper: Returns base hourly rate for overtime if called by legacy rules."""
        self.ensure_one()
        sched_hrs = self._get_period_scheduled_hours(date_from, date_to)
        if sched_hrs > 0.0:
            return self.wage / sched_hrs
        cal = self.resource_calendar_id
        fallback_hrs = (cal.hours_per_day * 26.0) if cal and cal.hours_per_day else 208.0
        return (self.wage / fallback_hrs) if fallback_hrs > 0.0 else 0.0

    def get_period_day_rate(self, date_from, date_to):
        """Public method: Returns daily rate for the payslip period based on scheduled days."""
        self.ensure_one()
        sched_days = self._get_period_scheduled_days(date_from, date_to)
        if sched_days > 0.0:
            return self.wage / sched_days
        divisor = self.standard_working_days_per_month or 26.0
        return self.wage / divisor if divisor else 0.0

    def action_reset_to_computed_rates(self):
        """Resets shortage rate to auto-computed value (clears manual override)."""
        for rec in self:
            divisor = rec.standard_working_days_per_month * rec.standard_hours_per_day
            computed_hourly = rec.wage / divisor if divisor else 0.0
            rec.write({
                'shortage_rate_manually_set': False,
                'shortage_deduction_rate_per_hour': computed_hourly,
            })

    @api.model
    def _get_whitelist_fields_from_template(self):
        res = super(HrVersion, self)._get_whitelist_fields_from_template() if hasattr(super(HrVersion, self), '_get_whitelist_fields_from_template') else []
        res.extend([
            'basic_salary', 'hra', 'da', 'travel_allowance', 'meal_allowance',
            'medical_allowance', 'other_allowance', 'fixed_allowance',
            'pay_by_attendance', 'salary_calculation_type',
        ])
        return list(set(res))

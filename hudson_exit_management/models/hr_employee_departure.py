# -*- coding: utf-8 -*-
import re
from dateutil.relativedelta import relativedelta
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError


class HrEmployeeDeparture(models.Model):
    _inherit = 'hr.employee.departure'

    notice_period_start_date = fields.Date(
        string="Start of Notice Period",
        default=fields.Date.today,
        copy=False,
    )
    notice_period_end_date = fields.Date(
        string="Notice Period End",
        default=lambda self: fields.Date.today() + relativedelta(months=1),
        copy=False,
        help="Date at which the notice period ends and the employee departure takes place.",
    )
    notice_duration = fields.Char(
        string="Notice Duration",
        default="1 months",
        copy=False,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        dismissal = res.get('dismissal_date') or fields.Date.today()
        if 'notice_period_start_date' in fields_list or not res.get('notice_period_start_date'):
            res['notice_period_start_date'] = dismissal
        if 'notice_duration' in fields_list or not res.get('notice_duration'):
            res['notice_duration'] = "1 months"
        if 'notice_period_end_date' in fields_list or not res.get('notice_period_end_date'):
            start = res.get('notice_period_start_date') or dismissal
            res['notice_period_end_date'] = start + relativedelta(months=1)
        if 'departure_date' in fields_list:
            res['departure_date'] = res.get('notice_period_end_date') or dismissal
        if 'action_date' in fields_list:
            dep_date = res.get('departure_date') or res.get('notice_period_end_date') or dismissal
            res['action_date'] = dep_date + relativedelta(days=1)
        return res

    @api.model
    def _format_notice_duration(self, start_date, end_date):
        if not start_date or not end_date:
            return ""
        start_d = fields.Date.to_date(start_date)
        end_d = fields.Date.to_date(end_date)
        if end_d < start_d:
            return "0 days"
        rdelta = relativedelta(end_d, start_d)
        total_months = rdelta.years * 12 + rdelta.months
        if total_months > 0 and rdelta.days == 0:
            return f"{total_months} months"
        elif total_months > 0:
            return f"{total_months} months, {rdelta.days} days"
        else:
            days = (end_d - start_d).days
            return f"{days} days"

    @api.model
    def _parse_notice_duration_to_end_date(self, start_date, duration_str):
        if not start_date or not duration_str:
            return start_date
        start_d = fields.Date.to_date(start_date)
        m_year = re.search(r'(\d+)\s*(?:year|yr)', str(duration_str), re.IGNORECASE)
        m_month = re.search(r'(\d+)\s*(?:month|mo)', str(duration_str), re.IGNORECASE)
        m_week = re.search(r'(\d+)\s*(?:week|wk)', str(duration_str), re.IGNORECASE)
        m_day = re.search(r'(\d+)\s*(?:day|d)', str(duration_str), re.IGNORECASE)

        delta = relativedelta()
        matched = False
        if m_year:
            delta += relativedelta(years=int(m_year.group(1)))
            matched = True
        if m_month:
            delta += relativedelta(months=int(m_month.group(1)))
            matched = True
        if m_week:
            delta += relativedelta(weeks=int(m_week.group(1)))
            matched = True
        if m_day:
            delta += relativedelta(days=int(m_day.group(1)))
            matched = True

        if not matched:
            m_num = re.search(r'(\d+)', str(duration_str))
            if m_num:
                val = int(m_num.group(1))
                if val <= 12:
                    delta += relativedelta(months=val)
                else:
                    delta += relativedelta(days=val)
            else:
                delta += relativedelta(months=1)

        return start_d + delta

    @api.depends('dismissal_date', 'notice_period_end_date')
    def _compute_departure_date(self):
        for departure in self:
            departure.departure_date = departure.notice_period_end_date or departure.dismissal_date

    @api.depends('departure_date', 'notice_period_end_date', 'dismissal_date')
    def _compute_action_date(self):
        for departure in self:
            ref_date = departure.notice_period_end_date or departure.departure_date or departure.dismissal_date
            if ref_date:
                departure.action_date = ref_date + relativedelta(days=1)
            else:
                departure.action_date = False

    @api.constrains('notice_period_start_date', 'notice_period_end_date')
    def _check_notice_period_dates(self):
        for departure in self:
            if departure.notice_period_start_date and departure.notice_period_end_date:
                if departure.notice_period_end_date < departure.notice_period_start_date:
                    raise ValidationError(_("Notice Period End date cannot be earlier than Start of Notice Period."))

    @api.onchange('dismissal_date')
    def _onchange_dismissal_date(self):
        if self.dismissal_date:
            self.notice_period_start_date = self.dismissal_date
            if self.notice_duration:
                self.notice_period_end_date = self._parse_notice_duration_to_end_date(
                    self.notice_period_start_date, self.notice_duration
                )
            else:
                self.notice_period_end_date = self.dismissal_date + relativedelta(months=1)
                self.notice_duration = "1 months"
            self.departure_date = self.notice_period_end_date or self.dismissal_date
            self.action_date = (self.departure_date or self.dismissal_date) + relativedelta(days=1)

    @api.onchange('notice_period_start_date')
    def _onchange_notice_period_start_date(self):
        if self.notice_period_start_date:
            if self.notice_duration:
                self.notice_period_end_date = self._parse_notice_duration_to_end_date(
                    self.notice_period_start_date, self.notice_duration
                )
            else:
                self.notice_period_end_date = self.notice_period_start_date + relativedelta(months=1)
                self.notice_duration = "1 months"
            self.departure_date = self.notice_period_end_date or self.notice_period_start_date
            self.action_date = (self.departure_date or self.notice_period_start_date) + relativedelta(days=1)

    @api.onchange('notice_period_end_date')
    def _onchange_notice_period_end_date(self):
        if self.notice_period_end_date:
            if self.notice_period_start_date:
                self.notice_duration = self._format_notice_duration(
                    self.notice_period_start_date, self.notice_period_end_date
                )
            self.departure_date = self.notice_period_end_date
            self.action_date = self.notice_period_end_date + relativedelta(days=1)

    @api.onchange('notice_duration')
    def _onchange_notice_duration(self):
        if self.notice_duration and self.notice_period_start_date:
            self.notice_period_end_date = self._parse_notice_duration_to_end_date(
                self.notice_period_start_date, self.notice_duration
            )
            self.departure_date = self.notice_period_end_date
            self.action_date = self.notice_period_end_date + relativedelta(days=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            start_date = vals.get('notice_period_start_date') or vals.get('dismissal_date') or fields.Date.today()
            if not vals.get('notice_period_start_date'):
                vals['notice_period_start_date'] = start_date
            if not vals.get('notice_duration'):
                vals['notice_duration'] = "1 months"
            if not vals.get('notice_period_end_date'):
                vals['notice_period_end_date'] = fields.Date.to_date(start_date) + relativedelta(months=1)

            ref_dep_date = vals.get('notice_period_end_date') or vals.get('dismissal_date')
            if not vals.get('departure_date') or vals.get('departure_date') == vals.get('dismissal_date'):
                vals['departure_date'] = ref_dep_date
            if not vals.get('action_date'):
                vals['action_date'] = fields.Date.to_date(vals['departure_date']) + relativedelta(days=1)
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        for dep in self:
            if 'notice_period_end_date' in vals or 'dismissal_date' in vals:
                end_date = dep.notice_period_end_date or dep.dismissal_date
                if end_date and dep.departure_date != end_date:
                    dep.departure_date = end_date
                if end_date and dep.action_date != end_date + relativedelta(days=1):
                    dep.action_date = end_date + relativedelta(days=1)
        return res


class HrVersion(models.Model):
    _inherit = 'hr.version'

    notice_period_start_date = fields.Date(
        related='departure_id.notice_period_start_date',
        readonly=False,
        groups="hr.group_hr_user",
        string="Start of Notice Period",
    )
    notice_period_end_date = fields.Date(
        related='departure_id.notice_period_end_date',
        readonly=False,
        groups="hr.group_hr_user",
        string="Notice Period End",
    )
    notice_duration = fields.Char(
        related='departure_id.notice_duration',
        readonly=False,
        groups="hr.group_hr_user",
        string="Notice Duration",
    )


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    notice_period_start_date = fields.Date(
        related='version_id.notice_period_start_date',
        inherited=True,
        string="Start of Notice Period",
    )
    notice_period_end_date = fields.Date(
        related='version_id.notice_period_end_date',
        inherited=True,
        string="Notice Period End",
    )
    notice_duration = fields.Char(
        related='version_id.notice_duration',
        inherited=True,
        string="Notice Duration",
    )

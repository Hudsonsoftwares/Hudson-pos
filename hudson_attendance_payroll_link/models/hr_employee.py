import pytz
# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    salary_calculation_type = fields.Selection(
        related='current_version_id.salary_calculation_type',
        readonly=True,
        string='Salary Calculation Type',
    )

    @api.model
    def get_user_employee_details(self):
        res = super(HrEmployee, self).get_user_employee_details()
        if res and isinstance(res, list) and len(res) > 0:
            employee_data = res[0]
            if 'leave_lines' in employee_data:
                for line in employee_data['leave_lines']:
                    leave_type_name = line.get('type') or ''
                    if any(keyword in leave_type_name.lower() for keyword in ['public', 'holiday', 'bank', 'global']):
                        line['color'] = '#FF5722'  # Ornate Orange Color
        return res

    def get_work_days_dashboard(self, from_datetime, to_datetime,
                                compute_leaves=False, calendar=None,
                                domain=None):
        calendar = calendar or self.resource_calendar_id or self.company_id.resource_calendar_id
        if not calendar:
            # Fallback to the first available calendar in the system
            calendar = self.env['resource.calendar'].sudo().search([], limit=1)
        if not calendar:
            # If no calendars exist at all, return 0.0 to prevent a server crash
            return 0.0
        try:
            return super(HrEmployee, self).get_work_days_dashboard(
                from_datetime, to_datetime, compute_leaves=compute_leaves,
                calendar=calendar, domain=domain
            )
        except ZeroDivisionError:
            return 0.0

    def list_leaves(self, from_datetime, to_datetime, calendar=None, domain=None):
        """Backward-compatible helper returning (day, hours, leave_records) tuples for Odoo 20."""
        calendar = calendar or self.resource_calendar_id or self.company_id.resource_calendar_id
        tz_name = getattr(calendar, 'tz', False) or self.tz or self.company_id.tz or 'UTC'
        tz = pytz.timezone(tz_name)
        
        utc_from = from_datetime.astimezone(pytz.UTC).replace(tzinfo=None) if hasattr(from_datetime, 'tzinfo') and from_datetime.tzinfo else from_datetime
        utc_to = to_datetime.astimezone(pytz.UTC).replace(tzinfo=None) if hasattr(to_datetime, 'tzinfo') and to_datetime.tzinfo else to_datetime
        
        leaves = self.env['resource.calendar.leaves'].search([
            ('resource_id', 'in', [self.resource_id.id, False]),
            ('date_from', '<=', utc_to),
            ('date_to', '>=', utc_from),
        ])
        result = []
        for l in leaves:
            l_start = pytz.utc.localize(l.date_from).astimezone(tz) if l.date_from.tzinfo is None else l.date_from.astimezone(tz)
            day = l_start.date()
            hrs = (l.date_to - l.date_from).total_seconds() / 3600.0
            result.append((day, hrs, l))
        return result

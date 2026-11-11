# -*- coding: utf-8 -*-
from odoo import models, fields, api
import pytz

class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    def _validate_check_in_location(self, vals):
        if self.env.context.get('biometric_punch_processing'):
            return
        if hasattr(super(), '_validate_check_in_location'):
            super()._validate_check_in_location(vals)

    def _validate_check_out_location(self, vals):
        if self.env.context.get('biometric_punch_processing'):
            return
        if hasattr(super(), '_validate_check_out_location'):
            super()._validate_check_out_location(vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super(HrAttendance, self).create(vals_list)
        records._check_anomalies()
        return records

    def write(self, vals):
        res = super(HrAttendance, self).write(vals)
        self._check_anomalies()
        return res

    def _check_anomalies(self):
        if hasattr(super(HrAttendance, self), '_check_anomalies'):
            super(HrAttendance, self)._check_anomalies()
        for att in self:
            # 1. Unusual Working Hours (> 12 hours)
            if att.check_in and att.check_out:
                duration = (att.check_out - att.check_in).total_seconds() / 3600.0
                if duration > 12.0:
                    self.env['hudson.attendance.anomaly'].create({
                        'name': 'Unusual Working Hours',
                        'anomaly_type': 'unusual_hours',
                        'employee_id': att.employee_id.id,
                        'attendance_id': att.id,
                        'description': f"Employee worked {duration:.2f} hours, which exceeds the threshold of 12 hours."
                    })

            if att.check_in and att.employee_id.resource_calendar_id:
                calendar = att.employee_id.resource_calendar_id
                tz_name = getattr(calendar, 'tz', False) or getattr(att.employee_id, 'tz', False) or (att.employee_id.company_id and att.employee_id.company_id.tz) or self.env.company.tz or 'UTC'
                tz = pytz.timezone(tz_name)
                local_check_in = pytz.utc.localize(att.check_in).astimezone(tz)
                day = local_check_in.date()
                
                # Skip shift anomalies on Official Public Holidays (global leaves)
                is_public_holiday = bool(calendar.global_leave_ids.filtered(
                    lambda l: l.date_from.date() <= day <= l.date_to.date()
                ))
                if is_public_holiday:
                    continue
                
                weekday = str(att.check_in.weekday())
                shifts = calendar.attendance_ids.filtered(lambda a: a.dayofweek == weekday)
                if shifts:
                    shifts = shifts.sorted(key=lambda s: s.hour_from)
                    first_shift = shifts[0]
                    last_shift = shifts[-1]
                    
                    local_check_in = pytz.utc.localize(att.check_in).astimezone(tz)
                    check_in_hour = local_check_in.hour + local_check_in.minute / 60.0 + local_check_in.second / 3600.0
                    
                    if check_in_hour > (first_shift.hour_from + 0.25):
                        self.env['hudson.attendance.anomaly'].create({
                            'name': 'Late Arrival',
                            'anomaly_type': 'late_arrival',
                            'employee_id': att.employee_id.id,
                            'attendance_id': att.id,
                            'description': f"Check-in at {local_check_in.strftime('%H:%M')} is late compared to scheduled shift start {first_shift.hour_from:.2f}."
                        })

                    if att.check_out:
                        local_check_out = pytz.utc.localize(att.check_out).astimezone(tz)
                        check_out_hour = local_check_out.hour + local_check_out.minute / 60.0 + local_check_out.second / 3600.0
                        
                        if check_out_hour < (last_shift.hour_to - 0.25):
                            self.env['hudson.attendance.anomaly'].create({
                                'name': 'Early Departure',
                                'anomaly_type': 'early_departure',
                                'employee_id': att.employee_id.id,
                                'attendance_id': att.id,
                                'description': f"Check-out at {local_check_out.strftime('%H:%M')} is early compared to scheduled shift end {last_shift.hour_to:.2f}."
                            })

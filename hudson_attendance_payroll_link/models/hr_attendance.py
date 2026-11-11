import pytz
from datetime import datetime, time, timedelta
# pyrefly: ignore [missing-import]
from odoo import api, fields, models

class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    @api.model
    def _get_work_entry_type_for_datetime(self, employee, check_in_dt):
        if not check_in_dt:
            return False

        calendar = employee.resource_calendar_id if employee else False
        tz_name = (
            getattr(calendar, 'tz', False)
            or (employee and getattr(employee, 'tz', False))
            or (employee and employee.company_id and employee.company_id.tz)
            or self.env.company.tz
            or 'UTC'
        )
        try:
            tz = pytz.timezone(tz_name)
        except Exception:
            tz = pytz.UTC

        local_dt = pytz.utc.localize(check_in_dt).astimezone(tz) if check_in_dt.tzinfo is None else check_in_dt.astimezone(tz)
        day = local_dt.date()

        # 1. Weekend check (Saturday=5, Sunday=6)
        is_weekend = (day.weekday() in (5, 6))

        # 2. Public holiday check
        is_public_holiday = False
        day_start_utc = tz.localize(datetime.combine(day, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        day_end_utc = tz.localize(datetime.combine(day, time.max)).astimezone(pytz.UTC).replace(tzinfo=None)
        cal_ids = [False]
        if calendar:
            cal_ids.append(calendar.id)
        hol_domain = [
            ('resource_id', '=', False),
            ('date_from', '<=', day_end_utc),
            ('date_to', '>=', day_start_utc),
            ('calendar_id', 'in', cal_ids),
        ]
        comp_id = (employee and employee.company_id and employee.company_id.id) or self.env.company.id
        if comp_id:
            hol_domain.append(('company_id', 'in', [comp_id, False]))
        is_public_holiday = bool(self.env['resource.calendar.leaves'].search_count(hol_domain))

        is_holiday = is_weekend or is_public_holiday

        domain_base = [('active', '=', True)]
        if is_holiday:
            holiday_wet = self.env['hr.work.entry.type'].search(
                domain_base + [('name', '=ilike', 'WORK HOLIDAY')], limit=1
            )
            if not holiday_wet:
                holiday_wet = self.env['hr.work.entry.type'].search(
                    domain_base + [('name', 'ilike', 'HUDSON WORK HOLIDAY')], limit=1
                )
            if not holiday_wet:
                holiday_wet = self.env['hr.work.entry.type'].search(
                    domain_base + [('code', '=', 'WORK_HOLIDAY')], limit=1
                )
            if not holiday_wet:
                holiday_wet = self.env['hr.work.entry.type'].search(
                    domain_base + [('code', '=', '002.00'), ('name', 'ilike', 'holiday')], limit=1
                )
            return holiday_wet
        else:
            work_wet = self.env['hr.work.entry.type'].search(
                domain_base + [('name', '=ilike', 'WORK OT')], limit=1
            )
            if not work_wet:
                work_wet = self.env['hr.work.entry.type'].search(
                    domain_base + [('name', '=ilike', 'HUDSON WORK')], limit=1
                )
            if not work_wet:
                work_wet = self.env['hr.work.entry.type'].search(
                    domain_base + [('code', '=', '002.00'), ('country_id', '=', False)], limit=1
                )
            if not work_wet:
                work_wet = self.env['hr.work.entry.type'].search(
                    domain_base + [('code', '=', '002.00'), ('name', 'not ilike', 'holiday')], limit=1
                )
            return work_wet

    @api.model
    def default_get(self, fields_list):
        res = super(HrAttendance, self).default_get(fields_list)
        if 'work_entry_type_id' in fields_list:
            now = fields.Datetime.now()
            emp = self.env.user.employee_id
            target_wet = self._get_work_entry_type_for_datetime(emp, now)
            if target_wet:
                res['work_entry_type_id'] = target_wet.id
        return res

    @api.onchange('check_in', 'employee_id')
    def _onchange_check_in_employee_work_entry_type(self):
        for att in self:
            if att.check_in:
                cur_wet = att.work_entry_type_id
                is_standard = not cur_wet or cur_wet.code in ('002.00', 'WORK_HOLIDAY', 'WORK_OT') or any(term in (cur_wet.name or '').upper() for term in ['WORK OT', 'WORK HOLIDAY', 'HUDSON WORK', 'WORK'])
                if is_standard:
                    target_wet = self._get_work_entry_type_for_datetime(att.employee_id, att.check_in)
                    if target_wet and target_wet != cur_wet:
                        att.work_entry_type_id = target_wet

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            check_in = vals.get('check_in')
            if check_in:
                check_in_dt = fields.Datetime.to_datetime(check_in)
                emp = self.env['hr.employee'].browse(vals.get('employee_id')) if vals.get('employee_id') else False
                wet_id = vals.get('work_entry_type_id')
                cur_wet = self.env['hr.work.entry.type'].browse(wet_id) if wet_id else False
                is_standard = not cur_wet or cur_wet.code in ('002.00', 'WORK_HOLIDAY', 'WORK_OT') or any(term in (cur_wet.name or '').upper() for term in ['WORK OT', 'WORK HOLIDAY', 'HUDSON WORK', 'WORK'])
                if is_standard:
                    target_wet = self._get_work_entry_type_for_datetime(emp, check_in_dt)
                    if target_wet:
                        vals['work_entry_type_id'] = target_wet.id
        records = super(HrAttendance, self).create(vals_list)
        for rec in records:
            ot = getattr(rec, 'overtime_hours', 0.0) or 0.0
            val = getattr(rec, 'validated_overtime_hours', 0.0) or 0.0
            if ot == 0.0 and val > 0.0:
                rec.sudo().write({'validated_overtime_hours': 0.0})
            elif ot > 0.0 and val > ot:
                rec.sudo().write({'validated_overtime_hours': ot})
        return records

    def write(self, vals):
        if 'check_in' in vals and 'work_entry_type_id' not in vals:
            check_in_dt = fields.Datetime.to_datetime(vals.get('check_in'))
            for rec in self:
                emp = rec.employee_id
                cur_wet = rec.work_entry_type_id
                is_standard = not cur_wet or cur_wet.code in ('002.00', 'WORK_HOLIDAY', 'WORK_OT') or any(term in (cur_wet.name or '').upper() for term in ['WORK OT', 'WORK HOLIDAY', 'HUDSON WORK', 'WORK'])
                if is_standard:
                    target_wet = self._get_work_entry_type_for_datetime(emp, check_in_dt)
                    if target_wet and target_wet != cur_wet:
                        vals['work_entry_type_id'] = target_wet.id
                        break
        res = super(HrAttendance, self).write(vals)
        for rec in self:
            ot = getattr(rec, 'overtime_hours', 0.0) or 0.0
            val = getattr(rec, 'validated_overtime_hours', 0.0) or 0.0
            if ot == 0.0 and val > 0.0:
                super(HrAttendance, rec).write({'validated_overtime_hours': 0.0})
            elif ot > 0.0 and val > ot:
                super(HrAttendance, rec).write({'validated_overtime_hours': ot})

            if vals.get('out_mode') == 'auto_check_out' or (vals.get('check_out') and rec.out_mode == 'auto_check_out'):
                rec._handle_auto_checkout_missing_punch()
        return res

    def _handle_auto_checkout_missing_punch(self):
        """
        When an employee is automatically checked out due to missing punch at shift end,
        automatically generate a Missing Punch anomaly and a Draft Regularization Request.
        """
        for att in self:
            if not att.check_in or not att.check_out:
                continue
            existing = self.env['hudson.attendance.anomaly'].search([
                ('attendance_id', '=', att.id),
                ('anomaly_type', '=', 'missing_punch')
            ], limit=1)
            if not existing:
                calendar = att.employee_id.resource_calendar_id
                tz_name = getattr(calendar, 'tz', False) or getattr(att.employee_id, 'tz', False) or (att.employee_id.company_id and att.employee_id.company_id.tz) or self.env.company.tz or 'UTC'
                tz = pytz.timezone(tz_name)
                local_check_in = pytz.utc.localize(att.check_in).astimezone(tz) if att.check_in.tzinfo is None else att.check_in.astimezone(tz)
                local_check_out = pytz.utc.localize(att.check_out).astimezone(tz) if att.check_out.tzinfo is None else att.check_out.astimezone(tz)

                anomaly = self.env['hudson.attendance.anomaly'].create({
                    'name': 'Missing Punch',
                    'anomaly_type': 'missing_punch',
                    'employee_id': att.employee_id.id,
                    'attendance_id': att.id,
                    'description': (
                        f"Employee checked in at {local_check_in.strftime('%Y-%m-%d %H:%M:%S')} "
                        f"but missed check-out. Automatically checked out at {local_check_out.strftime('%H:%M:%S')} "
                        f"based on scheduled shift."
                    )
                })
                self.env['hudson.attendance.regularization'].create({
                    'employee_id': att.employee_id.id,
                    'anomaly_id': anomaly.id,
                    'attendance_id': att.id,
                    'orig_check_in': att.check_in,
                    'orig_check_out': False,
                    'corrected_check_in': att.check_in,
                    'corrected_check_out': att.check_out,
                    'reason': 'Auto-generated for Missing Punch. Auto-closed at scheduled shift end with tolerance.',
                    'state': 'draft'
                })

    def _check_anomalies(self):
        if hasattr(super(HrAttendance, self), '_check_anomalies'):
            super(HrAttendance, self)._check_anomalies()
        for att in self:
            if att.check_in and att.check_out and att.employee_id.resource_calendar_id:
                calendar = att.employee_id.resource_calendar_id
                tz_name = getattr(calendar, 'tz', False) or getattr(att.employee_id, 'tz', False) or (att.employee_id.company_id and att.employee_id.company_id.tz) or self.env.company.tz or 'UTC'
                tz = pytz.timezone(tz_name)
                
                # Localize check-in date
                local_check_in = pytz.utc.localize(att.check_in).astimezone(tz)
                day = local_check_in.date()
                
                # Get scheduled hours for this day
                day_start = tz.localize(datetime.combine(day, time.min))
                day_end = tz.localize(datetime.combine(day, time.max))
                
                # Respect public holidays (leaves) when checking for shortfall
                is_public_holiday = bool(calendar.global_leave_ids.filtered(
                    lambda l: l.date_from.date() <= day <= l.date_to.date()
                ))
                scheduled_hours = 0.0 if is_public_holiday else calendar.get_work_hours_count(day_start, day_end, compute_leaves=False)
                
                if scheduled_hours > 0.0:
                    worked = att.worked_hours
                    if worked < (scheduled_hours - 0.25):
                        # Shortfall detected (worked hours less than scheduled minus 15 min tolerance)
                        existing = self.env['hudson.attendance.anomaly'].search([
                            ('attendance_id', '=', att.id),
                            ('anomaly_type', '=', 'hours_shortfall')
                        ])
                        if not existing:
                            anomaly = self.env['hudson.attendance.anomaly'].create({
                                'name': 'Hours Shortfall',
                                'anomaly_type': 'hours_shortfall',
                                'employee_id': att.employee_id.id,
                                'attendance_id': att.id,
                                'description': f"Employee worked {worked:.2f} hours, which falls short of scheduled {scheduled_hours:.2f} hours (tolerance 15 minutes)."
                            })
                            # Auto-create draft regularization request
                            self.env['hudson.attendance.regularization'].create({
                                'employee_id': att.employee_id.id,
                                'anomaly_id': anomaly.id,
                                'attendance_id': att.id,
                                'orig_check_in': att.check_in,
                                'orig_check_out': att.check_out,
                                'reason': 'Auto-generated for Hours Shortfall.',
                                'state': 'draft'
                            })

    @api.model
    def _cron_check_attendance_anomalies(self):
        """
        Daily cron to detect missing check-outs (Missing Punch) for past days.
        Automatically closes the open attendance at scheduled shift end so the employee
        is not locked out of check-in the next day, and generates a draft regularization.
        """
        # Find all open attendances (no check-out)
        open_attendances = self.search([('check_out', '=', False)])
        for att in open_attendances:
            if not att.check_in or not att.employee_id:
                continue
            calendar = att.employee_id.resource_calendar_id
            tz_name = getattr(calendar, 'tz', False) or getattr(att.employee_id, 'tz', False) or (att.employee_id.company_id and att.employee_id.company_id.tz) or self.env.company.tz or 'UTC'
            tz = pytz.timezone(tz_name)
            
            # Localize check-in and current time
            local_check_in = pytz.utc.localize(att.check_in).astimezone(tz) if att.check_in.tzinfo is None else att.check_in.astimezone(tz)
            local_now = datetime.now(tz)
            
            # Calculate check-in age in UTC to avoid flagging active night shifts
            age_seconds = (fields.Datetime.now() - att.check_in).total_seconds()
            
            # If the check_in is older than 14 hours and its localized date is strictly before today
            if age_seconds > 14 * 3600 and local_check_in.date() < local_now.date():
                # Compute scheduled shift end from calendar or fallback
                auto_checkout_dt = None
                if calendar:
                    day_start = tz.localize(datetime.combine(local_check_in.date(), time.min))
                    day_end = tz.localize(datetime.combine(local_check_in.date(), time.max))
                    intervals = calendar._work_intervals_batch(day_start, day_end).get(calendar.id, [])
                    if intervals:
                        last_interval = list(intervals)[-1]
                        auto_checkout_dt = last_interval[1].astimezone(pytz.UTC).replace(tzinfo=None)
                
                if not auto_checkout_dt:
                    end_local = tz.localize(datetime.combine(local_check_in.date(), time(18, 0, 0)))
                    auto_checkout_dt = end_local.astimezone(pytz.UTC).replace(tzinfo=None)
                    if auto_checkout_dt <= att.check_in:
                        auto_checkout_dt = att.check_in + timedelta(hours=8)

                # Close the attendance record safely with GPS validation bypassed
                att.with_context(disable_gps_validation=True, biometric_punch_processing=True).write({
                    'check_out': auto_checkout_dt,
                    'out_mode': 'auto_check_out',
                })

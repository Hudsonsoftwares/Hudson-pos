# -*- coding: utf-8 -*-
import pytz
from datetime import datetime, time, date as date_type
from dateutil.relativedelta import relativedelta
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _

class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _get_attendance_vs_schedule(self, contract, date_from, date_to):
        """
        Calculates scheduled, actual, shortage, and unpaid leave hours on a 
        day-by-day basis to reconcile shortages and unpaid leaves, 
        ensuring they are mutually exclusive.
        """
        if not hasattr(self.env, '_attendance_cache'):
            self.env._attendance_cache = {}
        cache_key = (contract.id, date_from, date_to)
        if cache_key in self.env._attendance_cache:
            return self.env._attendance_cache[cache_key]

        # 1. Setup timezone and datetime boundaries
        calendar = contract.resource_calendar_id or contract.employee_id.resource_calendar_id or contract.company_id.resource_calendar_id
        tz_name = getattr(calendar, 'tz', False) or getattr(contract.employee_id, 'tz', False) or (contract.company_id and contract.company_id.tz) or self.env.company.tz or 'UTC'
        tz = pytz.timezone(tz_name)
        
        # Localize day boundaries to contract/calendar timezone
        dt_from_local = tz.localize(datetime.combine(fields.Date.from_string(date_from), time.min))
        dt_to_local = tz.localize(datetime.combine(fields.Date.from_string(date_to), time.max))
        
        # Convert to naive UTC datetimes for database queries (check_in stored in UTC in DB)
        utc_day_from = dt_from_local.astimezone(pytz.UTC).replace(tzinfo=None)
        utc_day_to = dt_to_local.astimezone(pytz.UTC).replace(tzinfo=None)
        
        # 2. Query all attendances in the period (using UTC boundaries so early morning shifts on 1st are included)
        attendances = self.env['hr.attendance'].search([
            ('employee_id', '=', contract.employee_id.id),
            ('check_in', '>=', utc_day_from),
            ('check_in', '<=', utc_day_to),
        ])
        
        # Group attendances by their local check_in date
        attendances_by_date = {}
        for att in attendances:
            local_check_in = pytz.utc.localize(att.check_in).astimezone(tz)
            att_date = local_check_in.date()
            attendances_by_date.setdefault(att_date, []).append(att)
            
        # 3. Query all applied regularizations in the period
        regularizations = self.env['hudson.attendance.regularization'].search([
            ('employee_id', '=', contract.employee_id.id),
            ('state', '=', 'applied'),
            ('attendance_id.check_in', '>=', utc_day_from),
            ('attendance_id.check_in', '<=', utc_day_to),
        ])
        
        regularized_dates = set()
        for reg in regularizations:
            if reg.attendance_id:
                local_check_in = pytz.utc.localize(reg.attendance_id.check_in).astimezone(tz)
                regularized_dates.add(local_check_in.date())

        # 4. Get leave intervals (paid vs unpaid)
        unpaid_hours_by_date = {}
        paid_hours_by_date = {}
        unpaid_sandwich_dates = set()
        
        if calendar and contract.employee_id:
            emp = contract.employee_id
            leaves = self.env['hr.leave'].search([
                ('employee_id', '=', emp.id),
                ('state', '=', 'validate'),
                ('date_from', '<=', utc_day_to),
                ('date_to', '>=', utc_day_from),
            ])
            for leave in leaves:
                wet = getattr(leave, 'work_entry_type_id', None) or getattr(leave, 'holiday_status_id', None)
                is_unpaid = getattr(wet, 'unpaid', False) if wet else False
                is_sandwich_type = bool(getattr(wet, 'l10n_in_is_sandwich_leave', False) or getattr(leave, 'l10n_in_contains_sandwich_leaves', False))

                l_from = pytz.utc.localize(leave.date_from).astimezone(tz) if leave.date_from.tzinfo is None else leave.date_from.astimezone(tz)
                l_to = pytz.utc.localize(leave.date_to).astimezone(tz) if leave.date_to.tzinfo is None else leave.date_to.astimezone(tz)

                cur_l_date = max(l_from.date(), fields.Date.from_string(date_from))
                end_l_date = min(l_to.date(), fields.Date.from_string(date_to))

                while cur_l_date <= end_l_date:
                    day_dt_start = max(l_from, tz.localize(datetime.combine(cur_l_date, time.min)))
                    day_dt_end = min(l_to, tz.localize(datetime.combine(cur_l_date, time.max)))
                    day_leave_hours = calendar.get_work_hours_count(day_dt_start, day_dt_end, compute_leaves=False) if calendar else 8.0
                    if day_leave_hours > 0.0:
                        if is_unpaid:
                            unpaid_hours_by_date[cur_l_date] = unpaid_hours_by_date.get(cur_l_date, 0.0) + day_leave_hours
                            if is_sandwich_type:
                                unpaid_sandwich_dates.add(cur_l_date)
                        else:
                            paid_hours_by_date[cur_l_date] = paid_hours_by_date.get(cur_l_date, 0.0) + day_leave_hours
                    cur_l_date += relativedelta(days=1)

        # 4b. Pre-query mandatory public holidays from Time Off (resource.calendar.leaves)
        mandatory_holiday_dates = set()
        if calendar:
            holiday_leaves = self.env['resource.calendar.leaves'].search([
                ('calendar_id', 'in', [calendar.id, False]),
                ('resource_id', '=', False),
                ('date_from', '<=', utc_day_to),
                ('date_to', '>=', utc_day_from),
            ])
            for hl in holiday_leaves:
                if getattr(hl, 'is_mandatory', True):
                    hl_start = pytz.utc.localize(hl.date_from).astimezone(tz).date()
                    hl_end = pytz.utc.localize(hl.date_to).astimezone(tz).date()
                    cur_d = max(hl_start, fields.Date.from_string(date_from))
                    max_d = min(hl_end, fields.Date.from_string(date_to))
                    while cur_d <= max_d:
                        mandatory_holiday_dates.add(cur_d)
                        cur_d += relativedelta(days=1)

        # 4c. Process Sandwich Rule for Public Holidays:
        # If the unpaid leave type has sandwich leave enabled (l10n_in_is_sandwich_leave=True),
        # public holidays covered by or adjacent to unpaid leaves become unpaid (no payment given).
        # If sandwich leave is NOT enabled, public holidays are paid and not deducted as unpaid.
        d_from_dt = fields.Date.from_string(date_from)
        d_to_dt = fields.Date.from_string(date_to)

        for h_date in mandatory_holiday_dates:
            # If already marked as sandwich unpaid date (covered directly by sandwich unpaid leave)
            if h_date in unpaid_sandwich_dates:
                continue

            # Check if holiday is sandwiched between unpaid leaves that have sandwich enabled
            # Find previous scheduled working day
            prev_d = h_date - relativedelta(days=1)
            while prev_d >= d_from_dt:
                day_s = tz.localize(datetime.combine(prev_d, time.min))
                day_e = tz.localize(datetime.combine(prev_d, time.max))
                if calendar.get_work_hours_count(day_s, day_e, compute_leaves=False) > 0 and prev_d not in mandatory_holiday_dates:
                    break
                prev_d -= relativedelta(days=1)

            # Find next scheduled working day
            next_d = h_date + relativedelta(days=1)
            while next_d <= d_to_dt:
                day_s = tz.localize(datetime.combine(next_d, time.min))
                day_e = tz.localize(datetime.combine(next_d, time.max))
                if calendar.get_work_hours_count(day_s, day_e, compute_leaves=False) > 0 and next_d not in mandatory_holiday_dates:
                    break
                next_d += relativedelta(days=1)

            if prev_d in unpaid_sandwich_dates and next_d in unpaid_sandwich_dates:
                unpaid_sandwich_dates.add(h_date)
                day_s = tz.localize(datetime.combine(h_date, time.min))
                day_e = tz.localize(datetime.combine(h_date, time.max))
                h_hours = calendar.get_work_hours_count(day_s, day_e, compute_leaves=False) if calendar else 8.0
                unpaid_hours_by_date[h_date] = h_hours
            else:
                # If sandwich leave is NOT enabled for the unpaid type, this holiday is NOT unpaid.
                # Remove any accidental unpaid hours recorded for this holiday date so payment is given.
                if h_date not in unpaid_sandwich_dates:
                    unpaid_hours_by_date.pop(h_date, None)

        # 5. Day-by-day scheduled vs actual audit loop
        total_scheduled_hours = 0.0
        total_scheduled_days = 0.0
        total_out_of_contract_hours = 0.0
        total_out_of_contract_days = 0.0
        total_actual_hours = 0.0
        total_shortage_hours = 0.0
        total_shortage_days = 0.0
        total_unpaid_hours = 0.0
        total_unpaid_days = 0.0
        total_attendance_worked_hours = 0.0
        total_attendance_worked_days = 0.0
        # ── Earned Proration Model ──────────────────────────────────────────────
        # "Earned" = hours/days the employee is entitled to be paid for:
        #   actual biometric hours worked
        #   + paid leave hours (CL/SL/PL — employee still receives salary)
        #   + mandatory public holiday credits (paid even with 0 attendance)
        # Shortage hours are computed for information only (no deduction line).
        total_earned_hours = 0.0
        total_earned_days = 0.0

        d_from = fields.Date.from_string(date_from)
        d_to = fields.Date.from_string(date_to)
        day_std_hours = (calendar.hours_per_day if calendar and calendar.hours_per_day else 8.0)

        c_start = getattr(contract, 'contract_date_start', False) or getattr(contract, 'date_start', False)
        c_end = getattr(contract, 'contract_date_end', False) or getattr(contract, 'date_end', False)

        # Check if this payslip covers a partial month in a monthly pay schedule
        eval_start = d_from
        eval_end = d_to
        schedule_pay = getattr(getattr(contract, 'structure_type_id', None), 'schedule_pay', 'monthly') or 'monthly'
        if schedule_pay == 'monthly' and d_from.year == d_to.year and d_from.month == d_to.month:
            cal_start = d_from.replace(day=1)
            cal_end = (d_from + relativedelta(months=1, day=1)) - relativedelta(days=1)
            if d_from > cal_start or d_to < cal_end:
                eval_start = cal_start
                eval_end = cal_end

        current_date = eval_start
        end_date = eval_end
        
        while current_date <= end_date:
            # Check if this day is outside payslip period bounds OR outside contract bounds
            is_out_of_contract = False
            if current_date < d_from or current_date > d_to:
                is_out_of_contract = True
            elif c_start and current_date < c_start:
                is_out_of_contract = True
            elif c_end and current_date > c_end:
                is_out_of_contract = True

            if is_out_of_contract:
                # Scheduled hours for out-of-contract day
                out_day_hours = 0.0
                if calendar:
                    day_start = tz.localize(datetime.combine(current_date, time.min))
                    day_end = tz.localize(datetime.combine(current_date, time.max))
                    out_day_hours = calendar.get_work_hours_count(day_start, day_end, compute_leaves=False)
                else:
                    out_day_hours = day_std_hours
                
                if out_day_hours > 0.0:
                    total_out_of_contract_hours += out_day_hours
                    total_out_of_contract_days += min(1.0, out_day_hours / day_std_hours)
                
                current_date += relativedelta(days=1)
                continue

            # Scheduled work hours for the day from working calendar
            scheduled_hours = 0.0
            if calendar:
                day_start = tz.localize(datetime.combine(current_date, time.min))
                day_end = tz.localize(datetime.combine(current_date, time.max))
                # Total working hours defined on calendar for this day
                scheduled_hours = calendar.get_work_hours_count(day_start, day_end, compute_leaves=False)

            total_scheduled_hours += scheduled_hours
            if scheduled_hours > 0.0:
                total_scheduled_days += min(1.0, scheduled_hours / day_std_hours)

            # Actual worked hours for the day (standard shift, excluding split overtime records and holiday overtime)
            day_atts = attendances_by_date.get(current_date, [])
            std_day_atts = [att for att in day_atts if not getattr(att, 'source_attendance_id', False) and not getattr(att, 'time_rule_id', False)]
            actual_hours = sum(att.worked_hours for att in (std_day_atts if std_day_atts else day_atts))
            total_actual_hours += actual_hours

            unpaid_leave_hours = unpaid_hours_by_date.get(current_date, 0.0)
            paid_leave_hours = paid_hours_by_date.get(current_date, 0.0)
            denom = scheduled_hours if scheduled_hours > 0.0 else day_std_hours

            # Track standard biometric attendance hours and days (normal working shift)
            is_regularized = current_date in regularized_dates
            att_day_hours = scheduled_hours if is_regularized else (min(actual_hours, scheduled_hours) if scheduled_hours > 0.0 else actual_hours)
            if actual_hours > 0.0 or is_regularized:
                total_attendance_worked_hours += att_day_hours
                total_attendance_worked_days += min(1.0, att_day_hours / day_std_hours)

            # Unpaid leave accounting
            if unpaid_leave_hours > 0.0:
                total_unpaid_hours += unpaid_leave_hours
                total_unpaid_days += unpaid_leave_hours / denom

            # Shortage reconciliation (kept for informational / anomaly reporting)
            # Public holidays and approved regularizations incur NO shortage
            is_regularized = current_date in regularized_dates
            is_public_holiday = current_date in mandatory_holiday_dates
            is_sandwich_unpaid_holiday = is_public_holiday and (current_date in unpaid_sandwich_dates)

            if is_regularized or is_public_holiday:
                shortage_hours = 0.0
            else:
                # Leave takes priority, subtract leave hours from scheduled hours for shortage calculation
                remaining_scheduled = max(scheduled_hours - paid_leave_hours - unpaid_leave_hours, 0.0)
                shortage_hours = max(remaining_scheduled - actual_hours, 0.0)

            total_shortage_hours += shortage_hours
            if shortage_hours > 0.0:
                total_shortage_days += min(1.0, shortage_hours / denom)

            # ── Earned hours (Odoo Online proration model) ──────────────────
            # Public holiday:
            #   • If sandwich leave is enabled on unpaid type and employee is on unpaid leave:
            #     day_earned = 0.0 (NO payment given)
            #   • If sandwich leave is NOT enabled (or employee is active/paid):
            #     day_earned = scheduled_hours (payment IS given)
            # Regularized day: credit full scheduled day
            # Normal working day: actual_worked + paid_leave_hours (capped to scheduled)
            if is_public_holiday:
                if is_sandwich_unpaid_holiday:
                    day_earned = 0.0
                else:
                    day_earned = scheduled_hours  # paid public holiday credit
            elif is_regularized:
                day_earned = scheduled_hours
            else:
                day_earned = min(actual_hours + paid_leave_hours, scheduled_hours)

            total_earned_hours += day_earned
            if scheduled_hours > 0.0 and day_earned > 0.0:
                total_earned_days += min(1.0, day_earned / day_std_hours)

            current_date += relativedelta(days=1)

        # 6. Overtime calculation — reads from Standard Odoo 19 hr.attendance.overtime.line.
        #    Only lines that are:
        #      • status = 'approved'  (manager has validated them)
        #      • compensable_as_leave = False  (not converted to comp-off leave)
        #    are considered payable overtime for payroll.
        #    amount_rate on each line carries the rule rate (1.0, 1.5, 2.0 etc.) which
        #    the OT salary rule uses for weighted pay calculation.
        d_from = fields.Date.from_string(date_from) if not isinstance(date_from, date_type) else date_from
        d_to = fields.Date.from_string(date_to) if not isinstance(date_to, date_type) else date_to
        ot_lines = self.env['hr.attendance.overtime.line'].browse() if 'hr.attendance.overtime.line' in self.env else self.env['hr.attendance'].browse()
        net_overtime_hours = 0.0
        if 'hr.attendance.overtime.line' in self.env:
            ot_lines = self.env['hr.attendance.overtime.line'].search([
                ('employee_id', '=', contract.employee_id.id),
                ('date', '>=', d_from),
                ('date', '<=', d_to),
                ('status', '=', 'approved'),
                ('compensable_as_leave', '=', False),
            ])
            for ot_line in ot_lines:
                approved_hrs = ot_line.manual_duration if ot_line.manual_duration > 0.0 else ot_line.duration
                net_overtime_hours += max(approved_hrs, 0.0)
        else:
            has_time_rule = hasattr(self.env['hr.attendance'], 'time_rule_id')
            domain = [
                ('employee_id', '=', contract.employee_id.id),
                ('date', '>=', d_from),
                ('date', '<=', d_to),
            ]
            if has_time_rule:
                domain += ['|', ('source_attendance_id', '!=', False), ('time_rule_id', '!=', False)]
            else:
                domain += [('source_attendance_id', '!=', False)]
            ot_records = self.env['hr.attendance'].search(domain)
            for ot in ot_records:
                net_overtime_hours += max(ot.worked_hours, 0.0)
            ot_lines = ot_records

        total_period_scheduled_hours = total_scheduled_hours + total_out_of_contract_hours
        total_period_scheduled_days = total_scheduled_days + total_out_of_contract_days

        data = {
            'scheduled_hours': total_scheduled_hours,
            'scheduled_days': total_scheduled_days,
            'contract_scheduled_hours': total_scheduled_hours,
            'contract_scheduled_days': total_scheduled_days,
            'total_period_scheduled_hours': total_period_scheduled_hours,
            'total_period_scheduled_days': total_period_scheduled_days,
            'earned_hours': total_earned_hours,
            'earned_days': total_earned_days,
            'out_of_contract_hours': total_out_of_contract_hours,
            'out_of_contract_days': total_out_of_contract_days,
            'actual_hours': total_actual_hours,
            'validated_overtime_hours': net_overtime_hours,
            'overtime_hours_delta': net_overtime_hours,
            'overtime_lines': ot_lines,
            'shortage_hours_delta': total_shortage_hours,
            'shortage_days': total_shortage_days,
            'unpaid_hours': total_unpaid_hours,
            'unpaid_days': total_unpaid_days,
            'attendance_worked_hours': total_attendance_worked_hours,
            'attendance_worked_days': total_attendance_worked_days,
        }
        
        self.env._attendance_cache[cache_key] = data
        return data

    def _get_period_shortage_rate(self, contract, date_from, date_to):
        """Calculates period-exact hourly rate for Fixed Salary mode based on real scheduled hours."""
        data = self._get_attendance_vs_schedule(contract, date_from, date_to)
        sched_hrs = data.get('total_period_scheduled_hours') or (data.get('scheduled_hours', 0.0) + data.get('out_of_contract_hours', 0.0))
        return (contract.wage / sched_hrs) if sched_hrs > 0.0 else 0.0

    def _get_public_holiday_dates(self, contract, date_from, date_to):
        calendar = contract.resource_calendar_id or contract.employee_id.resource_calendar_id
        tz_name = (
            getattr(calendar, 'tz', False)
            or (contract.employee_id and getattr(contract.employee_id, 'tz', False))
            or (contract.company_id and contract.company_id.tz)
            or self.env.company.tz
            or 'UTC'
        )
        try:
            tz = pytz.timezone(tz_name)
        except Exception:
            tz = pytz.UTC

        d_from = fields.Date.from_string(date_from)
        d_to = fields.Date.from_string(date_to)
        day_start_utc = tz.localize(datetime.combine(d_from, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        day_end_utc = tz.localize(datetime.combine(d_to, time.max)).astimezone(pytz.UTC).replace(tzinfo=None)

        cal_ids = [False]
        if calendar:
            cal_ids.append(calendar.id)
        domain = [
            ('resource_id', '=', False),
            ('date_from', '<=', day_end_utc),
            ('date_to', '>=', day_start_utc),
            ('calendar_id', 'in', cal_ids),
        ]
        comp_id = contract.company_id.id if contract.company_id else self.env.company.id
        if comp_id:
            domain.append(('company_id', 'in', [comp_id, False]))

        holiday_leaves = self.env['resource.calendar.leaves'].search(domain)
        holiday_dates = set()
        for hl in holiday_leaves:
            hl_start = pytz.utc.localize(hl.date_from).astimezone(tz).date()
            hl_end = pytz.utc.localize(hl.date_to).astimezone(tz).date()
            cur = max(hl_start, d_from)
            end = min(hl_end, d_to)
            while cur <= end:
                holiday_dates.add(cur)
                cur += relativedelta(days=1)
        return holiday_dates

    def _get_dynamic_overtime_values(self, contract, worked_days=None):
        """
        Dynamically calculates (base_hourly_wage, rate_percentage, total_hours)
        for draft payslips based on the live overtime rule/ruleset pay rates.
        Once payslip is validated, it uses the preserved rate on the line.
        Supports both Odoo 20 (hr.time.rule / attendance excess splits) and
        legacy Odoo 19 (hr.attendance.overtime.line).
        """
        self.ensure_one()

        # Base hourly wage from SCHEDULED hours (not WORK100 which is now earned hours).
        # We must divide by the total scheduled hours for the payslip period.
        sched_hrs = 0.0
        att_data = self._get_attendance_vs_schedule(contract, self.date_from, self.date_to)
        sched_hrs = att_data.get('total_period_scheduled_hours') or (att_data.get('scheduled_hours', 0.0) + att_data.get('out_of_contract_hours', 0.0))
        if not sched_hrs or sched_hrs <= 0.0:
            cal = contract.resource_calendar_id
            sched_hrs = (cal.hours_per_day * 26.0) if cal and cal.hours_per_day else 208.0

        base_hourly = (contract.wage / sched_hrs) if sched_hrs > 0.0 else 0.0

        # Legacy Odoo 19 branch (hr.attendance.overtime.line)
        if 'hr.attendance.overtime.line' in self.env:
            OtLine = self.env['hr.attendance.overtime.line']
            ot_lines = OtLine.search([
                ('employee_id', '=', contract.employee_id.id),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
                ('status', '=', 'approved'),
                ('compensable_as_leave', '=', False),
            ])
            if not ot_lines:
                return 0.0, 100.0, 0.0

            # Applicable ruleset
            ruleset = getattr(contract, 'ruleset_id', False)
            if not ruleset and 'hr.attendance.overtime.ruleset' in self.env:
                ruleset = self.env['hr.attendance.overtime.ruleset'].search([
                    ('company_id', 'in', [contract.company_id.id, False])
                ], limit=1)

            is_draft = (not self.state or self.state == 'draft')
            total_hours = 0.0
            weighted_rate_sum = 0.0

            for line in ot_lines:
                approved_hrs = line.manual_duration if line.manual_duration > 0.0 else line.duration
                if approved_hrs <= 0.0:
                    continue

                if is_draft:
                    paid_rules = line.rule_ids.filtered(lambda r: r.paid)
                    if not paid_rules and ruleset:
                        paid_rules = ruleset.rule_ids.filtered(lambda r: r.paid)

                    if paid_rules:
                        mode = ruleset.rate_combination_mode if ruleset else 'max'
                        if mode == 'sum':
                            current_rate = 1.0 + sum((r.amount_rate - 1.0) for r in paid_rules)
                        else:
                            current_rate = max(paid_rules.mapped('amount_rate'))
                    else:
                        current_rate = line.amount_rate or 1.0

                    if abs((line.amount_rate or 1.0) - current_rate) > 0.001:
                        line.sudo().write({'amount_rate': current_rate})

                    rate_to_use = current_rate
                else:
                    rate_to_use = line.amount_rate if line.amount_rate and line.amount_rate > 0.0 else 1.0

                total_hours += approved_hrs
                weighted_rate_sum += approved_hrs * rate_to_use

            if total_hours <= 0.0:
                return 0.0, 100.0, 0.0

            effective_rate_pct = (weighted_rate_sum / total_hours) * 100.0
            return base_hourly, effective_rate_pct, total_hours

        # Odoo 20 branch (hr.time.rule / hr.attendance excess split records)
        import re
        total_hours = att_data.get('validated_overtime_hours', 0.0) or att_data.get('overtime_hours_delta', 0.0)
        ot_records = att_data.get('overtime_lines')
        if not ot_records and (hasattr(self.env['hr.attendance'], 'source_attendance_id') or hasattr(self.env['hr.attendance'], 'time_rule_id')):
            d_from = fields.Date.from_string(self.date_from)
            d_to = fields.Date.from_string(self.date_to)
            has_time_rule = hasattr(self.env['hr.attendance'], 'time_rule_id')
            domain = [
                ('employee_id', '=', contract.employee_id.id),
                ('date', '>=', d_from),
                ('date', '<=', d_to),
            ]
            if has_time_rule:
                domain += ['|', ('source_attendance_id', '!=', False), ('time_rule_id', '!=', False)]
            else:
                domain += [('source_attendance_id', '!=', False)]
            ot_records = self.env['hr.attendance'].search(domain)

        # Align with worked_days line if available
        if (not total_hours or total_hours <= 0.0) and worked_days:
            if hasattr(worked_days, 'OVERTIME') and worked_days.OVERTIME:
                total_hours = worked_days.OVERTIME.number_of_hours
            elif isinstance(worked_days, dict) and 'OVERTIME' in worked_days:
                total_hours = getattr(worked_days['OVERTIME'], 'number_of_hours', 0.0)

        if total_hours <= 0.0 and (not ot_records or not sum(ot_records.mapped('worked_hours'))):
            return 0.0, 100.0, 0.0

        weighted_rate_sum = 0.0
        rec_hours_sum = 0.0

        if ot_records:
            for ot in ot_records:
                h = max(getattr(ot, 'worked_hours', 0.0), 0.0)
                if h <= 0.0:
                    continue
                wet = getattr(ot, 'work_entry_type_id', False)
                rule = getattr(ot, 'time_rule_id', False)

                # Dynamically resolve live rule matching attendance date (e.g. Saturday/Sunday/Holiday vs Weekday)
                if (not self.state or self.state == 'draft') and getattr(ot, 'date', False) and 'hr.time.rule' in self.env:
                    weekday = ot.date.weekday()
                    day_fields = ['apply_monday', 'apply_tuesday', 'apply_wednesday', 'apply_thursday', 'apply_friday', 'apply_saturday', 'apply_sunday']
                    day_field = day_fields[weekday]
                    is_ph = False
                    if hasattr(self, '_get_public_holiday_dates'):
                        is_ph = ot.date in (self._get_public_holiday_dates(contract, self.date_from, self.date_to) or set())

                    rule_domain = [
                        ('company_id', 'in', [contract.company_id.id, False]),
                        ('active', '=', True),
                    ]
                    if is_ph:
                        rule_domain.append(('apply_on_public_holidays', '=', True))
                    else:
                        rule_domain.append((day_field, '=', True))

                    matched_rules = self.env['hr.time.rule'].search(rule_domain, order='sequence, id')
                    for mr in matched_rules:
                        if not mr.employee_domain or mr.employee_domain == '[]':
                            rule = mr
                            wet = mr.work_entry_type_id
                            break
                        try:
                            if contract.employee_id in mr._get_applicable_employees(contract.employee_id):
                                rule = mr
                                wet = mr.work_entry_type_id
                                break
                        except Exception:
                            pass

                # Strictly read Pay Rate from the Payroll tab (wet.amount_rate) or Time Rule (rule.amount_rate)
                # Ignore the record title/heading
                rate = 0.0
                if wet and getattr(wet, 'amount_rate', False):
                    rate = wet.amount_rate
                elif rule and getattr(rule, 'amount_rate', False):
                    rate = rule.amount_rate

                # Fallback if no rate specified: 1.0 (100%)
                if not rate or rate <= 0.0:
                    rate = 1.0

                weighted_rate_sum += h * rate
                rec_hours_sum += h

        if rec_hours_sum > 0.0:
            effective_rate = weighted_rate_sum / rec_hours_sum
            if total_hours <= 0.0:
                total_hours = rec_hours_sum
        else:
            effective_rate = 1.0

        effective_rate_pct = effective_rate * 100.0
        return base_hourly, effective_rate_pct, total_hours

    def _get_dynamic_overtime_pay(self, contract, worked_days=None):
        """Returns total overtime pay amount."""
        base_hourly, rate_pct, hours = self._get_dynamic_overtime_values(contract, worked_days)
        return hours * base_hourly * (rate_pct / 100.0)

    attendance_discrepancy_hours = fields.Float(
        string='Attendance Discrepancy Hours',
        compute='_compute_attendance_discrepancy',
        store=True,
    )
    has_attendance_discrepancy = fields.Boolean(
        string='Has Attendance Discrepancy',
        compute='_compute_attendance_discrepancy',
        store=True,
    )
    attendance_discrepancy_string = fields.Char(
        string='Attendance Mismatch String',
        compute='_compute_attendance_discrepancy_string',
    )

    @api.depends('worked_days_line_ids', 'employee_id', 'contract_id.pay_by_attendance', 'date_from', 'date_to', 'state')
    def _compute_attendance_discrepancy(self):
        for payslip in self:
            if payslip.contract_id and payslip.date_from and payslip.date_to:
                data = payslip._get_attendance_vs_schedule(payslip.contract_id, payslip.date_from, payslip.date_to)
                ot = data.get('overtime_hours_delta', 0.0)
                st = data.get('shortage_hours_delta', 0.0)
                is_pay_by_att = getattr(payslip.contract_id, 'pay_by_attendance', False)
                if not is_pay_by_att or payslip.state in ('done', 'paid'):
                    payslip.attendance_discrepancy_hours = max(0.0, ot)
                    payslip.has_attendance_discrepancy = False
                else:
                    payslip.attendance_discrepancy_hours = ot - st
                    payslip.has_attendance_discrepancy = abs(payslip.attendance_discrepancy_hours) > 0.01
            else:
                payslip.attendance_discrepancy_hours = 0.0
                payslip.has_attendance_discrepancy = False

    @api.depends('attendance_discrepancy_hours')
    def _compute_attendance_discrepancy_string(self):
        for payslip in self:
            val = payslip.attendance_discrepancy_hours
            sign = "+" if val >= 0 else ""
            payslip.attendance_discrepancy_string = f"{sign}{val:.1f} hrs"

    def action_view_attendance_discrepancy(self):
        self.ensure_one()
        calendar = self.contract_id.resource_calendar_id or self.employee_id.resource_calendar_id or self.company_id.resource_calendar_id
        tz_name = getattr(calendar, 'tz', False) or getattr(self.employee_id, 'tz', False) or (self.company_id and self.company_id.tz) or self.env.company.tz or 'UTC'
        tz = pytz.timezone(tz_name)
        dt_from_local = tz.localize(datetime.combine(fields.Date.from_string(self.date_from), time.min))
        dt_to_local = tz.localize(datetime.combine(fields.Date.from_string(self.date_to), time.max))
        utc_day_from = dt_from_local.astimezone(pytz.UTC).replace(tzinfo=None)
        utc_day_to = dt_to_local.astimezone(pytz.UTC).replace(tzinfo=None)
        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('check_in', '>=', utc_day_from),
            ('check_in', '<=', utc_day_to),
        ]
        return {
            'name': _('Attendances'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.attendance',
            'view_mode': 'list,form',
            'domain': domain,
        }

    @api.depends('worked_days_line_ids.number_of_days', 'worked_days_line_ids.number_of_hours', 'worked_days_line_ids.code',
                 'contract_id.pay_by_attendance', 'date_from', 'date_to', 'employee_id')
    def _compute_worked_days_totals(self):
        for slip in self:
            pay_by_att = slip.contract_id and getattr(slip.contract_id, 'pay_by_attendance', False)
            if pay_by_att and slip.contract_id and slip.date_from and slip.date_to:
                data = slip._get_attendance_vs_schedule(slip.contract_id, slip.date_from, slip.date_to)
                slip.total_worked_hours = data.get('attendance_worked_hours', 0.0)
                slip.total_worked_days = data.get('attendance_worked_days', 0.0)
            else:
                work_days = sum(l.number_of_days for l in slip.worked_days_line_ids if l.code == 'WORK100')
                work_hours = sum(l.number_of_hours for l in slip.worked_days_line_ids if l.code == 'WORK100')
                slip.total_worked_days = work_days
                slip.total_worked_hours = work_hours

    def action_compute_sheet(self):
        if hasattr(self.env, '_attendance_cache'):
            self.env._attendance_cache.clear()
        for payslip in self:
            payslip.worked_days_line_ids.unlink()
            lines = [(0, 0, line) for line in payslip.get_worked_day_lines(payslip.contract_id, payslip.date_from, payslip.date_to)]
            payslip.write({'worked_days_line_ids': lines})
        return super(HrPayslip, self).action_compute_sheet()

    def _get_fixed_salary_attendance_factor(self, contract, date_from=None, date_to=None):
        """
        Computes the salary proration factor (0.0 to 1.0) for fixed-salary contracts
        (pay_by_attendance is OFF) using the Hybrid Attendance Threshold (Option B).

        Logic:
          - If worked hours/days <= 0.01: factor = 0.0 (Full month unpaid / absent -> ₹0 salary).
          - If enable_attendance_threshold is False:
              - Standard behavior: if mid-month joiner/leaver, factor = active_worked_hours / total_sched_hours; else 1.0.
          - If enable_attendance_threshold is True:
              - Calculate effective threshold days (pro-rated for mid-month joiner/leaver if out_of_contract_days > 0).
              - If active worked days < effective threshold:
                  Salary is pro-rated to actual days worked:
                  factor = active_worked_hours / total_sched_hours
              - If active worked days >= effective threshold:
                  Employee receives 100% of their eligible fixed salary:
                  factor = scheduled_hours / total_sched_hours (1.0 if full month).
        """
        d_from = date_from or getattr(self, 'date_from', False)
        d_to = date_to or getattr(self, 'date_to', False)
        if not d_from or not d_to:
            return 1.0

        sched_data = self._get_attendance_vs_schedule(contract, d_from, d_to)
        sched_hours = float(sched_data.get('scheduled_hours', 0.0) or 0.0)
        sched_days = float(sched_data.get('scheduled_days', 0.0) or 0.0)
        out_hours = float(sched_data.get('out_of_contract_hours', 0.0) or 0.0)
        out_days = float(sched_data.get('out_of_contract_days', 0.0) or 0.0)
        unpaid_hours = float(sched_data.get('unpaid_hours', 0.0) or 0.0)
        unpaid_days = float(sched_data.get('unpaid_days', 0.0) or 0.0)

        total_sched_hours = float(sched_data.get('total_period_scheduled_hours') or (sched_hours + out_hours) or 0.0)
        total_sched_days = float(sched_data.get('total_period_scheduled_days') or (sched_days + out_days) or 0.0)

        active_worked_hours = max(0.0, sched_hours - unpaid_hours)
        active_worked_days = max(0.0, sched_days - unpaid_days)

        # 1. 0 days worked -> ₹0 salary
        if active_worked_hours <= 0.01 or active_worked_days <= 0.01:
            return 0.0

        # 2. If threshold is disabled on contract
        if not getattr(contract, 'enable_attendance_threshold', True):
            if out_hours > 0.0 and total_sched_hours > 0.0:
                return min(1.0, max(0.0, active_worked_hours / total_sched_hours))
            return 1.0

        # 3. Attendance Threshold calculation
        thresh_days = float(getattr(contract, 'min_attendance_threshold_days', 14.0) or 14.0)
        if out_hours > 0.0 and total_sched_days > 0.0:
            effective_thresh = thresh_days * (sched_days / total_sched_days)
        else:
            effective_thresh = thresh_days

        # Case A: Below threshold -> Prorate to actual worked hours
        if active_worked_days < effective_thresh:
            if total_sched_hours > 0.0:
                return min(1.0, max(0.0, active_worked_hours / total_sched_hours))
            return 0.0

        # Case B: Threshold met or exceeded -> 100% of eligible fixed salary
        if out_hours > 0.0 and total_sched_hours > 0.0:
            return min(1.0, max(0.0, sched_hours / total_sched_hours))
        return 1.0

    @api.model
    def get_worked_day_lines(self, contracts, date_from, date_to):
        res = super(HrPayslip, self).get_worked_day_lines(contracts, date_from, date_to)
        for contract in contracts:
            data = self._get_attendance_vs_schedule(contract, date_from, date_to)

            # ── Earned Proration Model ──────────────────────────────────────────
            # WORK100 reflects the hours the employee EARNED pay for:
            #   actual attendance + paid leaves + public holiday credits.
            # This drives the BASIC / HRA / DA proration in salary rules directly.
            # No SHORTAGE deduction line is generated; shortfalls are implicitly
            # reflected by the lower earned hours in WORK100.
            #
            # If pay_by_attendance is OFF: we keep scheduled hours (full salary).
            # If pay_by_attendance is ON:  we use earned hours (prorated salary).
            pay_by_att = getattr(contract, 'pay_by_attendance', False)

            if pay_by_att:
                work100_days = data.get('earned_days', 0.0)
                work100_hours = data.get('earned_hours', 0.0)
            else:
                work100_days = max(0.0, data.get('scheduled_days', 0.0) - data.get('unpaid_days', 0.0))
                work100_hours = max(0.0, data.get('scheduled_hours', 0.0) - data.get('unpaid_hours', 0.0))

            out_days = data.get('out_of_contract_days', 0.0)
            out_hours = data.get('out_of_contract_hours', 0.0)

            wage = float(getattr(contract, 'wage', 0.0) or getattr(contract, 'basic_salary', 0.0) or 0.0)
            sched_hours = data.get('scheduled_hours', 0.0)
            sched_days = data.get('scheduled_days', 0.0)
            out_days = data.get('out_of_contract_days', 0.0)
            out_hours = data.get('out_of_contract_hours', 0.0)
            total_month_hours = sched_hours + out_hours
            total_month_days = sched_days + out_days

            if pay_by_att:
                if total_month_hours > 0.0 and work100_hours >= 0.0:
                    work100_amount = round(wage * (work100_hours / total_month_hours), 2)
                elif total_month_days > 0.0 and work100_days >= 0.0:
                    work100_amount = round(wage * (work100_days / total_month_days), 2)
                else:
                    work100_amount = 0.0
            else:
                factor = self._get_fixed_salary_attendance_factor(contract, date_from, date_to)
                work100_amount = round(wage * factor, 2)

            # 1. Update or retain WORK100
            work100_found = False
            for line in list(res):
                if line.get('code') == 'WORK100' and line.get('contract_id') == contract.id:
                    line['number_of_days'] = work100_days
                    line['number_of_hours'] = work100_hours
                    line['amount'] = work100_amount
                    work100_found = True
            if not work100_found:
                res.insert(0, {
                    'name': _('Normal Working Days'),
                    'sequence': 2,
                    'code': 'WORK100',
                    'description': _('Normal Working Days'),
                    'number_of_days': work100_days,
                    'number_of_hours': work100_hours,
                    'contract_id': contract.id,
                    'amount': work100_amount,
                })

            # 2. Update or insert OUT_OF_CONTRACT
            if out_days > 0.01 or out_hours > 0.01:
                out_found = False
                for line in res:
                    if line.get('code') == 'OUT_OF_CONTRACT' and line.get('contract_id') == contract.id:
                        line['number_of_days'] = out_days
                        line['number_of_hours'] = out_hours
                        line['amount'] = 0.0
                        out_found = True
                if not out_found:
                    is_india = (getattr(contract, '_is_india_localization', None) and contract._is_india_localization()) or (contract.company_id and contract.company_id.country_id and contract.company_id.country_id.code == 'IN')
                    out_type_name = _('Out of Contract (India)') if is_india else _('Out of Contract')
                    res.insert(0, {
                        'name': out_type_name,
                        'sequence': 1,
                        'code': 'OUT_OF_CONTRACT',
                        'description': _('Out of Contract'),
                        'number_of_days': out_days,
                        'number_of_hours': out_hours,
                        'contract_id': contract.id,
                        'amount': 0.0,
                    })

            # 3. Unpaid Leave — recorded for attendance tracking and audit.
            #    Amount is 0.0 because in the Earned Proration model, unpaid leave hours
            #    are already excluded from WORK100 (non-payable), so no deduction or pay is tied here.
            if data.get('unpaid_days', 0.0) > 0.01 or data.get('unpaid_hours', 0.0) > 0.01:
                unpaid_hours = data.get('unpaid_hours', 0.0)
                unpaid_days = data.get('unpaid_days', 0.0)

                unpaid_found = False
                for l in res:
                    if l.get('code') == 'UNPAID' and l.get('contract_id') == contract.id:
                        l['number_of_days'] = unpaid_days
                        l['number_of_hours'] = unpaid_hours
                        l['amount'] = 0.0
                        unpaid_found = True
                if not unpaid_found:
                    res.append({
                        'name': _('Unpaid Leave'),
                        'sequence': 4,
                        'code': 'UNPAID',
                        'description': _('Unpaid Leave'),
                        'number_of_days': unpaid_days,
                        'number_of_hours': unpaid_hours,
                        'contract_id': contract.id,
                        'amount': 0.0,
                    })

            # NOTE: SHORTAGE line is intentionally NOT generated.
            # In the Earned Proration model, attendance shortfalls reduce WORK100 hours,
            # which in turn reduce BASIC/HRA/DA salary rule outputs directly.
            # There is no separate negative deduction line on the payslip.

            # 4. Overtime worked days line — uses Standard Odoo 19 overtime.line data.
            #    Gate: any approved, payable OT lines exist for the period.
            if data.get('overtime_hours_delta', 0.0) > 0.01:
                ot_hours = data['overtime_hours_delta']
                slip = self.filtered(lambda s: s.contract_id == contract)[:1] if len(self) > 1 else (self if len(self) == 1 else False)
                if slip and hasattr(slip, '_get_dynamic_overtime_pay'):
                    total_ot_amt = slip._get_dynamic_overtime_pay(contract)
                elif slip and hasattr(slip, '_get_dynamic_overtime_values'):
                    base_hourly, rate_pct, qty = slip._get_dynamic_overtime_values(contract)
                    total_ot_amt = qty * base_hourly * (rate_pct / 100.0)
                else:
                    base_hourly = (wage / sched_hours) if sched_hours > 0.0 else 0.0
                    total_ot_amt = base_hourly * 1.5 * ot_hours
                ot_found = False
                for l in res:
                    if l.get('code') == 'OVERTIME' and l.get('contract_id') == contract.id:
                        l['number_of_hours'] = ot_hours
                        l['amount'] = round(total_ot_amt, 2)
                        ot_found = True
                if not ot_found:
                    res.append({
                        'name': _('Overtime Hours'),
                        'sequence': 6,
                        'code': 'OVERTIME',
                        'description': _('Overtime Hours (Standard Odoo Ruleset)'),
                        'number_of_days': 0.0,
                        'number_of_hours': ot_hours,
                        'contract_id': contract.id,
                        'amount': round(total_ot_amt, 2),
                    })
        return res


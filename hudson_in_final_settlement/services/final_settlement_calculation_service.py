# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import fields, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError
import logging
import calendar as cal_mod
from datetime import datetime, date, timedelta
import pytz

_logger = logging.getLogger(__name__)


class FinalSettlementCalculationService:
    """
    Enterprise Settlement Orchestration Service for Hudson Indian Final Settlement Module.
    Single Responsibility: Orchestrate computation across pluggable statutory component services
    (Leave Encashment, Gratuity, PF, Notice Pay) and maintain idempotent breakdown lines on final.settlement.
    Does NOT contain statutory calculation formulas or validation rules.
    """

    def __init__(self, env):
        self.env = env

    def compute_settlement(self, settlement):
        """
        Orchestrates full settlement calculation for a given final.settlement record.

        :param settlement: final.settlement recordset (required)
        :return: dict summary of created/updated lines
        """
        if not settlement:
            raise ValueError(_("Final settlement record is required for calculation."))

        settlement.ensure_one()

        employee = settlement.employee_id
        if not employee:
            raise UserError(_("Please select an employee on the settlement record before calculating."))

        lwd = settlement.last_working_day or fields.Date.today()
        calc_results = []

        # 1. Compute Final Month Worked Salary Component
        salary_res = self._compute_final_month_salary_component(settlement, employee, lwd)
        if salary_res:
            calc_results.append(salary_res)

        # 2. Compute Normal / In-Service Leave Encashment Component (if any approved/paid)
        normal_le_res = self._compute_normal_leave_encashment_component(settlement, employee, lwd)
        if normal_le_res:
            calc_results.append(normal_le_res)

        # 3. Compute Statutory Exit Leave Encashment Component
        exit_le_res = self._compute_exit_leave_encashment_component(settlement, employee, lwd)
        if exit_le_res:
            calc_results.append(exit_le_res)

        # 4. Pluggable Extension Point for Gratuity Component
        gratuity_res = self._compute_gratuity_component(settlement, employee, lwd)
        if gratuity_res:
            if isinstance(gratuity_res, list):
                calc_results.extend([g for g in gratuity_res if g])
            else:
                calc_results.append(gratuity_res)

        # 4. Compute Professional Tax (PT) Statutory Reconciliation Component
        pt_res = self._compute_pt_reconciliation_component(settlement, employee, lwd)
        if pt_res:
            calc_results.append(pt_res)

        # 5. Compute Notice Pay / Notice Shortfall Component
        notice_res = self._compute_notice_pay_component(settlement, employee, lwd)
        if notice_res:
            calc_results.append(notice_res)

        # 6. Compute Payslip Statutory Deduction Components (EPF, PT, TDS, etc.)
        payslip_deductions = self._compute_payslip_deduction_components(settlement, settlement.payslip_id)
        if payslip_deductions:
            calc_results.extend(payslip_deductions)

        # 7. Synchronize lines idempotently
        updated_lines = self._sync_settlement_lines(settlement, calc_results)

        _logger.info("Successfully computed final settlement %s for employee %s: %s lines processed.",
                     settlement.name, employee.name, len(updated_lines))

        return {
            'settlement_id': settlement.id,
            'processed_lines': len(updated_lines),
            'total_earnings': settlement.total_earnings,
            'total_deductions': settlement.total_deductions,
            'net_amount': settlement.net_settlement_amount,
        }

    def _compute_payslip_deduction_components(self, settlement, payslip):
        """
        Extracts statutory employee deductions (e.g. EPF, PT, TDS, ESIC, LWF, UNPAID) from
        the linked settlement payslip to ensure the final settlement breakdown
        reflects all statutory withholdings and Net Settlement Amount equals Net Pay.
        """
        if not payslip or not payslip.exists():
            return []

        payslip.invalidate_recordset(['line_ids'])
        if not payslip.line_ids:
            return []

        deductions = []
        exclude_codes = {'TDS_GRATUITY', 'NOTICE_RECOVERY'}
        ded_lines = payslip.line_ids.filtered(
            lambda l: l.category_id.code in ('DED', 'DEDUCTION') and l.code not in exclude_codes and round(abs(l.total), 2) > 0.0
        )

        seq = 60
        for line in ded_lines:
            amt = round(abs(line.total), 2)
            desc = _("Statutory deduction (%s) synced from settlement payslip %s.") % (
                line.name, payslip.name or ''
            )
            deductions.append({
                'component_code': line.code,
                'component_name': line.name,
                'line_type': 'deduction',
                'sequence': seq,
                'amount': amt,
                'description': desc,
            })
            seq += 5

        return deductions

    def _compute_final_month_salary_component(self, settlement, employee, lwd):
        """
        Calculates Final Month Worked Salary earning component.
        Priority 1: If linked settlement payslip exists and is computed, sync exact earned regular salary.
        Priority 2: If no payslip exists, calculate prorated wage for the departure month up to LWD
                    using employee's working schedule (resource.calendar) or calendar days fallback.
        """
        try:
            if not lwd:
                lwd = settlement.last_working_day or fields.Date.today()
            if isinstance(lwd, str):
                lwd = fields.Date.from_string(lwd)

            # --- Priority 1: Linked Settlement Payslip ---
            payslip = settlement.payslip_id
            if payslip and payslip.exists():
                payslip.invalidate_recordset(['line_ids'])
                if payslip.line_ids:
                    exclude_codes = {
                        'GRATUITY', 'EXIT_LEAVE_ENCASH', 'LEAVE_ENCASH_EXIT',
                        'LEAVE_ENCASH', 'ENCASHMENT', 'LEAVE_ENCASHMENT'
                    }
                    regular_lines = payslip.line_ids.filtered(
                        lambda l: l.category_id.code in ('BASIC', 'ALW') and l.code not in exclude_codes
                    )
                    regular_earnings = sum(regular_lines.mapped('total'))
                    worked_salary = max(0.0, round(regular_earnings, 2))

                    month_label = lwd.strftime('%B %Y') if lwd else ''
                    desc = _("Worked salary for %s (%s to %s) synced from settlement payslip %s.") % (
                        month_label, payslip.date_from, payslip.date_to, payslip.name
                    )
                    return {
                        'component_code': 'FINAL_MONTH_SALARY',
                        'component_name': _('Final Month Worked Salary'),
                        'line_type': 'earning',
                        'sequence': 10,
                        'amount': worked_salary,
                        'description': desc,
                    }

            # --- Priority 2: Standalone Contract & Working Schedule Proration ---
            contract = getattr(employee, 'version_id', False) or self.env['hr.version'].search([
                ('employee_id', '=', employee.id)
            ], order='id desc', limit=1)

            monthly_wage = float(getattr(contract, 'wage', 0.0) or 0.0)
            if monthly_wage <= 0.0:
                basic = float(getattr(contract, 'basic_salary', 0.0) or 0.0)
                da = float(getattr(contract, 'da', 0.0) or 0.0)
                hra = float(getattr(contract, 'hra', 0.0) or 0.0)
                fixed = float(getattr(contract, 'fixed_allowance', 0.0) or 0.0)
                std_alw = float(getattr(contract, 'standard_allowance', 0.0) or 0.0)
                monthly_wage = basic + da + hra + fixed + std_alw

            if monthly_wage <= 0.0:
                return {
                    'component_code': 'FINAL_MONTH_SALARY',
                    'component_name': _('Final Month Worked Salary'),
                    'line_type': 'earning',
                    'sequence': 10,
                    'amount': 0.0,
                    'description': _('No wage or contract salary breakdown configured for employee.'),
                }

            month_start = date(lwd.year, lwd.month, 1)
            days_in_month = cal_mod.monthrange(lwd.year, lwd.month)[1]
            month_end = date(lwd.year, lwd.month, days_in_month)

            start_date = month_start
            if contract and getattr(contract, 'date_start', None):
                c_start = fields.Date.from_string(contract.date_start)
                if c_start and c_start > month_start:
                    start_date = c_start

            if lwd < start_date:
                return {
                    'component_code': 'FINAL_MONTH_SALARY',
                    'component_name': _('Final Month Worked Salary'),
                    'line_type': 'earning',
                    'sequence': 10,
                    'amount': 0.0,
                    'description': _('Last working day precedes contract start date.'),
                }

            month_label = lwd.strftime('%B %Y') if lwd else ''

            # --- Priority 2A: Upfront Attendance & Work Entries Evaluation ---
            if hasattr(self.env['hr.payslip'], '_get_attendance_vs_schedule') and contract:
                try:
                    att_data = self.env['hr.payslip']._get_attendance_vs_schedule(contract, month_start, month_end)
                    pay_by_att = getattr(contract, 'pay_by_attendance', False)

                    if pay_by_att:
                        actual_hours = float(att_data.get('actual_hours', 0.0) or 0.0)
                        actual_att_hours = float(att_data.get('attendance_worked_hours', 0.0) or 0.0)
                        work100_days = float(att_data.get('earned_days', 0.0) or 0.0)
                        work100_hours = float(att_data.get('earned_hours', 0.0) or 0.0)
                        sched_hours = float(att_data.get('scheduled_hours', 0.0) or 0.0)
                        out_hours = float(att_data.get('out_of_contract_hours', 0.0) or 0.0)
                        sched_days = float(att_data.get('scheduled_days', 0.0) or 0.0)
                        out_days = float(att_data.get('out_of_contract_days', 0.0) or 0.0)
                        total_m_hours = float(att_data.get('total_period_scheduled_hours', 0.0) or (sched_hours + out_hours) or 0.0)
                        total_m_days = float(att_data.get('total_period_scheduled_days', 0.0) or (sched_days + out_days) or 0.0)

                        # If employee has 0 biometric attendance and no approved paid leaves in the period
                        has_paid_leaves = False
                        if actual_hours <= 0.001 and actual_att_hours <= 0.001:
                            if 'hr.leave' in self.env:
                                leaves = self.env['hr.leave'].search([
                                    ('employee_id', '=', employee.id),
                                    ('state', '=', 'validate'),
                                    ('date_from', '<=', fields.Datetime.to_datetime(lwd)),
                                    ('date_to', '>=', fields.Datetime.to_datetime(start_date)),
                                ])
                                has_paid_leaves = any(
                                    not getattr(getattr(l, 'work_entry_type_id', None) or getattr(l, 'holiday_status_id', None), 'unpaid', False)
                                    for l in leaves
                                )

                        if (actual_hours <= 0.001 and actual_att_hours <= 0.001 and not has_paid_leaves) or (work100_days <= 0.001 or work100_hours <= 0.001):
                            return {
                                'component_code': 'FINAL_MONTH_SALARY',
                                'component_name': _('Final Month Worked Salary'),
                                'line_type': 'earning',
                                'sequence': 10,
                                'amount': 0.0,
                                'description': _('No attendance records found for departure period (%s to %s).') % (start_date, lwd),
                            }

                        if total_m_hours > 0.0:
                            amount = round(monthly_wage * (work100_hours / total_m_hours), 2)
                        elif total_m_days > 0.0:
                            amount = round(monthly_wage * (work100_days / total_m_days), 2)
                        else:
                            amount = 0.0

                        disp_w = int(work100_days) if work100_days.is_integer() else round(work100_days, 2)
                        disp_m = int(total_m_days) if total_m_days.is_integer() else round(total_m_days, 2)
                        return {
                            'component_code': 'FINAL_MONTH_SALARY',
                            'component_name': _('Final Month Worked Salary'),
                            'line_type': 'earning',
                            'sequence': 10,
                            'amount': amount,
                            'description': _('Prorated salary by attendance for %s (%s to %s): %s of %s scheduled working days.') % (
                                month_label, start_date, lwd, disp_w, disp_m
                            ),
                        }
                    else:
                        unpaid_days = float(att_data.get('unpaid_days', 0.0) or 0.0)
                        sched_days = float(att_data.get('scheduled_days', 0.0) or 0.0)
                        if unpaid_days > 0.0 and sched_days > 0.0 and unpaid_days >= sched_days:
                            return {
                                'component_code': 'FINAL_MONTH_SALARY',
                                'component_name': _('Final Month Worked Salary'),
                                'line_type': 'earning',
                                'sequence': 10,
                                'amount': 0.0,
                                'description': _('Full unpaid leave recorded for departure period (%s to %s).') % (start_date, lwd),
                            }
                except Exception as att_err:
                    _logger.warning("Attendance schedule pre-check failed for settlement %s: %s", settlement.name, str(att_err))

            # Full month worked case
            if start_date == month_start and lwd == month_end:
                return {
                    'component_code': 'FINAL_MONTH_SALARY',
                    'component_name': _('Final Month Worked Salary'),
                    'line_type': 'earning',
                    'sequence': 10,
                    'amount': round(monthly_wage, 2),
                    'description': _('Full month salary for %s (%s to %s).') % (month_label, start_date, lwd),
                }

            # Working schedule (resource.calendar) proration
            calendar = (
                getattr(employee, 'resource_calendar_id', False) or
                (contract and getattr(contract, 'resource_calendar_id', False)) or
                getattr(employee.company_id, 'resource_calendar_id', False)
            )

            worked_sched_days = 0.0
            month_sched_days = 0.0

            if calendar:
                try:
                    tz = pytz.timezone(calendar.tz or 'UTC')
                    dt_from = tz.localize(datetime.combine(start_date, datetime.min.time()))
                    dt_to = tz.localize(datetime.combine(lwd, datetime.max.time()))
                    worked_data = calendar.get_work_duration_data(dt_from, dt_to, compute_leaves=False)
                    worked_sched_days = float(worked_data.get('days', 0.0))

                    m_start_dt = tz.localize(datetime.combine(month_start, datetime.min.time()))
                    m_end_dt = tz.localize(datetime.combine(month_end, datetime.max.time()))
                    m_data = calendar.get_work_duration_data(m_start_dt, m_end_dt, compute_leaves=False)
                    month_sched_days = float(m_data.get('days', 0.0))
                except Exception as cal_err:
                    _logger.warning("Resource calendar calculation failed for settlement salary %s: %s", settlement.name, str(cal_err))
                    worked_sched_days = 0.0
                    month_sched_days = 0.0

            if worked_sched_days > 0.0 and month_sched_days > 0.0:
                amount = round(monthly_wage * (worked_sched_days / month_sched_days), 2)
                disp_w = int(worked_sched_days) if worked_sched_days.is_integer() else round(worked_sched_days, 2)
                disp_m = int(month_sched_days) if month_sched_days.is_integer() else round(month_sched_days, 2)
                month_label = lwd.strftime('%B %Y')
                desc = _('Prorated salary for %s (%s to %s): %s of %s scheduled working days.') % (
                    month_label, start_date, lwd, disp_w, disp_m
                )
            else:
                # Fallback to calendar days
                cal_worked_days = float((lwd - start_date).days + 1)
                amount = round(monthly_wage * (cal_worked_days / float(days_in_month)), 2)
                month_label = lwd.strftime('%B %Y')
                desc = _('Prorated salary for %s (%s to %s): %s of %s calendar days.') % (
                    month_label, start_date, lwd, int(cal_worked_days), days_in_month
                )

            return {
                'component_code': 'FINAL_MONTH_SALARY',
                'component_name': _('Final Month Worked Salary'),
                'line_type': 'earning',
                'sequence': 10,
                'amount': amount,
                'description': desc,
            }
        except Exception as e:
            _logger.warning("Final month salary computation failed for settlement %s: %s", settlement.name, str(e))
            return {
                'component_code': 'FINAL_MONTH_SALARY',
                'component_name': _('Final Month Worked Salary'),
                'line_type': 'earning',
                'sequence': 10,
                'amount': 0.0,
                'description': _('Final month salary calculation skipped (%s).') % str(e),
            }

    def _compute_normal_leave_encashment_component(self, settlement, employee, lwd):
        """
        Calculates In-Service / Normal Leave Encashment earning component (e.g. approved LER requests).
        Priority 1: If linked settlement payslip exists and has LEAVE_ENCASH, sync the exact amount.
        Priority 2: Compute via approved hds.leave.encashment.request records for the employee up to LWD.
        """
        try:
            amount = 0.0
            payslip = settlement.payslip_id
            if payslip and payslip.exists():
                payslip.invalidate_recordset(['line_ids'])
                normal_lines = payslip.line_ids.filtered(lambda l: l.code == 'LEAVE_ENCASH')
                if normal_lines:
                    amount = sum(normal_lines.mapped('total'))

            if amount <= 0.0 and 'hds.leave.encashment.request' in self.env:
                contract = getattr(employee, 'version_id', False) or self.env['hr.version'].search([
                    ('employee_id', '=', employee.id)
                ], order='id desc', limit=1)
                requests = self.env['hds.leave.encashment.request'].search([
                    ('employee_id', '=', employee.id),
                    ('state', '=', 'approved'),
                    ('request_date', '<=', lwd),
                    ('payslip_id', 'in', (False, payslip.id if payslip else False)),
                ])
                if requests:
                    amount = sum(req.calculate_payout_amount(contract=contract) for req in requests)

            if amount > 0.0:
                return {
                    'component_code': 'LEAVE_ENCASH',
                    'component_name': _('Normal Leave Encashment'),
                    'line_type': 'earning',
                    'sequence': 20,
                    'amount': round(float(amount), 2),
                    'description': _('In-service normal leave encashment from approved request(s).'),
                }
            return None
        except Exception as e:
            _logger.warning("Normal Leave Encashment computation skipped for settlement %s: %s", settlement.name, str(e))
            return None

    def _compute_exit_leave_encashment_component(self, settlement, employee, lwd):
        """
        Calculates Statutory Exit Leave Encashment earning component upon separation/departure.
        Priority 1: Compute via statutory LeaveEncashmentService with full calculation details (days + rate).
        Priority 2: If linked settlement payslip exists and has EXIT_LEAVE_ENCASH, sync the exact amount.
        Populates settlement.exit_leave_encash_days for Time Off allocation deduction upon approval.
        """
        try:
            amount = 0.0
            days = 0.0
            # pyrefly: ignore [missing-import]
            from odoo.addons.hudson_in_payroll.services.leave_encashment import LeaveEncashmentService
            contract = getattr(employee, 'version_id', False) or self.env['hr.version'].search([
                ('employee_id', '=', employee.id)
            ], order='id desc', limit=1)

            le_service = LeaveEncashmentService(self.env)
            val_result = le_service.validator.validate(
                employee=employee,
                last_working_day=lwd
            )
            if val_result.is_eligible:
                calc_data = le_service.data_service.prepare_calculation_data(
                    employee=employee,
                    contract=contract,
                    last_working_day=lwd or val_result.last_working_day,
                    calc_date=settlement.settlement_date
                )
                calc_result = le_service.calculator.calculate(calc_data)
                amount = float(calc_result.final_amount or 0.0)
                days = float(calc_result.leave_days_used or 0.0)

            # If linked settlement payslip exists and has EXIT_LEAVE_ENCASH, sync the exact amount
            payslip = settlement.payslip_id
            if payslip and payslip.exists():
                payslip.invalidate_recordset(['line_ids'])
                exit_lines = payslip.line_ids.filtered(lambda l: l.code in ('EXIT_LEAVE_ENCASH', 'LEAVE_ENCASH_EXIT'))
                if exit_lines:
                    payslip_amount = sum(exit_lines.mapped('total'))
                    if payslip_amount > 0:
                        amount = payslip_amount

            if amount <= 0.0 and settlement.leave_encash_gross_amount > 0.0:
                amount = float(settlement.leave_encash_gross_amount)

            # Check retirement status
            is_retirement = (settlement.exit_reason == 'retirement')
            if not is_retirement and settlement.departure_reason_id:
                if hasattr(settlement, '_map_departure_reason_to_exit_reason'):
                    is_retirement = (settlement._map_departure_reason_to_exit_reason(settlement.departure_reason_id) == 'retirement')
                else:
                    dep_name = (getattr(settlement.departure_reason_id, 'name', '') or '').lower()
                    if any(k in dep_name for k in ['retir', 'superannuat']):
                        is_retirement = True

            if settlement.leave_encash_exemption_amount is not False and settlement.leave_encash_exemption_amount is not None and settlement.leave_encash_exemption_amount > 0.0:
                exemption_limit = float(settlement.leave_encash_exemption_amount)
            else:
                try:
                    exemption_limit = float(self.env['hr.rule.parameter']._get_parameter_value(
                        'hds_in_leave_encashment_statutory_ceiling', settlement.settlement_date or fields.Date.today()
                    ) or self.env['hr.rule.parameter']._get_parameter_value(
                        'HDS_IN_TDS_LEAVE_ENCASHMENT_EXEMPTION_CEILING', settlement.settlement_date or fields.Date.today()
                    ) or 2500000.0)
                except Exception:
                    exemption_limit = 2500000.0
            exempt_amount = min(amount, exemption_limit) if amount > 0 else 0.0
            taxable_amount = max(0.0, amount - exemption_limit) if amount > 0 else 0.0

            settlement.write({
                'exit_leave_encash_days': days,
                'leave_encash_gross_amount': amount,
                'leave_encash_exemption_amount': exemption_limit,
                'leave_encash_taxable_amount': taxable_amount,
            })

            days_str = int(days) if days.is_integer() else f"{days:.2f}"
            if days > 0:
                desc = _('Statutory exit leave encashment (%s days) u/s 10(10AA) (Exempt: ₹%s, Taxable: ₹%s).') % (
                    days_str, f"{exempt_amount:,.2f}", f"{taxable_amount:,.2f}"
                )
            else:
                desc = _('Statutory exit leave encashment u/s 10(10AA) (Exempt: ₹%s, Taxable: ₹%s).') % (
                    f"{exempt_amount:,.2f}", f"{taxable_amount:,.2f}"
                )

            return {
                'component_code': 'EXIT_LEAVE_ENCASH',
                'component_name': _('Exit Leave Encashment'),
                'line_type': 'earning',
                'sequence': 25,
                'amount': float(amount or 0.0),
                'description': desc,
            }
        except Exception as e:
            _logger.warning("Exit Leave Encashment computation skipped/failed for settlement %s: %s", settlement.name, str(e))
            settlement.write({
                'leave_encash_gross_amount': 0.0,
                'leave_encash_taxable_amount': 0.0,
            })
            return {
                'component_code': 'EXIT_LEAVE_ENCASH',
                'component_name': _('Exit Leave Encashment'),
                'line_type': 'earning',
                'sequence': 25,
                'amount': 0.0,
                'description': _('Exit Leave Encashment not applicable or disabled (%s).') % str(e),
            }

    def _compute_leave_encashment_component(self, settlement, employee, lwd):
        """Deprecated alias: redirects to _compute_exit_leave_encashment_component."""
        return self._compute_exit_leave_encashment_component(settlement, employee, lwd)

    def _compute_gratuity_component(self, settlement, employee, lwd):
        """
        Calls GratuityService statutory SOA component to compute statutory gratuity.
        Gross formula gratuity is paid as an earning ('GRATUITY').
        Under Section 10(10)(iii), exemption is applied (default ₹20,00,000).
        Any excess taxable gratuity is consolidated into unified annual taxable salary
        and withheld through HDS_IN_TDS on the payslip.
        Fields gratuity_gross_amount, gratuity_exemption_amount, and gratuity_taxable_amount
        on settlement are populated.
        """
        try:
            contract = getattr(employee, 'version_id', False) or self.env['hr.version'].search([
                ('employee_id', '=', employee.id)
            ], order='id desc', limit=1)

            is_death_or_disablement = (settlement.exit_reason == 'death')
            gross_amount = 0.0

            # Priority 1: If linked settlement payslip exists and has GRATUITY, check amount
            payslip = settlement.payslip_id
            if payslip and payslip.exists():
                payslip.invalidate_recordset(['line_ids'])
                gratuity_lines = payslip.line_ids.filtered(lambda l: l.code == 'GRATUITY')
                if gratuity_lines:
                    gross_amount = sum(gratuity_lines.mapped('total'))

            # Priority 2: Compute via GratuityService
            try:
                from odoo.addons.hudson_in_payroll.services.gratuity.gratuity_service import GratuityService  # pyrefly: ignore [missing-import]
            except (ImportError, ValueError):
                from odoo.addons.hudson_in_payroll.services.gratuity import GratuityService  # pyrefly: ignore [missing-import]

            gratuity_service = GratuityService(self.env, localdict={'employee': employee, 'contract': contract})
            details = gratuity_service.compute_gratuity_details(
                separation_date=lwd,
                is_death_or_disablement=is_death_or_disablement
            )
            raw_amount = float(getattr(details, 'raw_gratuity_amount', 0.0) or 0.0)
            capped_amount = float(getattr(details, 'final_gratuity_amount', 0.0) or 0.0)

            # If raw formula gratuity is positive, use it as gross payable; otherwise fallback to capped_amount or payslip
            if raw_amount > 0.0:
                gross_amount = raw_amount
            elif gross_amount <= 0.0:
                gross_amount = capped_amount

            if gross_amount <= 0.0 and settlement.gratuity_gross_amount > 0.0:
                gross_amount = float(settlement.gratuity_gross_amount)

            exemption_limit = settlement.gratuity_exemption_amount if settlement.gratuity_exemption_amount is not False and settlement.gratuity_exemption_amount is not None else 2000000.0
            taxable_amount = max(0.0, gross_amount - exemption_limit) if gross_amount > 0 else 0.0

            # Persist breakdown on settlement record
            settlement.write({
                'gratuity_gross_amount': gross_amount,
                'gratuity_exemption_amount': exemption_limit,
                'gratuity_taxable_amount': taxable_amount,
            })

            lines = []
            if gross_amount > 0.0:
                lines.append({
                    'component_code': 'GRATUITY',
                    'component_name': _('Gratuity'),
                    'line_type': 'earning',
                    'sequence': 30,
                    'amount': float(gross_amount),
                    'description': _('Statutory gratuity calculated under Payment of Gratuity Act 1972 as of last working day %s.') % lwd,
                })
            else:
                lines.append({
                    'component_code': 'GRATUITY',
                    'component_name': _('Gratuity'),
                    'line_type': 'earning',
                    'sequence': 30,
                    'amount': 0.0,
                    'description': _('Gratuity not applicable or ineligible.'),
                })

            # Note: Under the unified annual tax architecture, standalone TDS_GRATUITY deduction line
            # is NOT added here. Taxable gratuity is included in the unified annual taxable income
            # projection and withheld via the single HDS_IN_TDS deduction line on the settlement payslip.

            return lines
        except Exception as e:
            _logger.warning("Gratuity computation skipped/failed for settlement %s: %s", settlement.name, str(e))
            settlement.write({
                'gratuity_gross_amount': 0.0,
                'gratuity_taxable_amount': 0.0,
            })
            return [{
                'component_code': 'GRATUITY',
                'component_name': _('Gratuity'),
                'line_type': 'earning',
                'sequence': 30,
                'amount': 0.0,
                'description': _('Gratuity not applicable or ineligible (%s).') % str(e),
            }]

    def _compute_gratuity_tds(self, settlement, employee, taxable_gratuity, lwd):
        """
        Computes incremental TDS on taxable gratuity using progressive income tax slabs
        and 4% Health & Education cess under Section 192 / Section 288B.
        """
        try:
            if not taxable_gratuity or taxable_gratuity <= 0.0:
                return 0.0

            lwd_date = fields.Date.from_string(lwd) if isinstance(lwd, str) else (lwd or fields.Date.today())
            fy_start_year = lwd_date.year if lwd_date.month >= 4 else lwd_date.year - 1
            fy_code = f"{fy_start_year}-{fy_start_year + 1}"

            financial_year = self.env['tds.financial.year'].search([
                '|',
                ('code', '=', fy_code),
                '&', ('start_date', '<=', lwd_date), ('end_date', '>=', lwd_date)
            ], limit=1)
            if not financial_year:
                financial_year = self.env['tds.financial.year'].search([('active', '=', True)], order='start_date desc', limit=1)

            regime_code = 'new'
            if 'tds.employee.tax.regime' in self.env:
                regime_rec = self.env['tds.employee.tax.regime'].search([
                    ('employee_id', '=', employee.id),
                    ('financial_year_id', '=', financial_year.id if financial_year else False)
                ], limit=1)
                if regime_rec and getattr(regime_rec, 'tax_regime', False):
                    regime_code = regime_rec.tax_regime.lower()
            elif hasattr(employee, 'tax_regime') and employee.tax_regime:
                regime_code = employee.tax_regime.lower()

            contract = getattr(employee, 'version_id', False) or self.env['hr.version'].search([
                ('employee_id', '=', employee.id)
            ], order='id desc', limit=1)

            annual_salary = 0.0
            if contract:
                wage = float(getattr(contract, 'wage', 0.0) or 0.0)
                if wage <= 0.0:
                    basic = float(getattr(contract, 'basic_salary', 0.0) or 0.0)
                    da = float(getattr(contract, 'da', 0.0) or 0.0)
                    hra = float(getattr(contract, 'hra', 0.0) or 0.0)
                    fixed = float(getattr(contract, 'fixed_allowance', 0.0) or 0.0)
                    std_alw = float(getattr(contract, 'standard_allowance', 0.0) or 0.0)
                    wage = basic + da + hra + fixed + std_alw
                annual_salary = float(getattr(contract, 'ctc', 0.0) or (wage * 12.0) or 0.0)

            # Try to get projected annual income from AnnualIncomeProjectionService if available
            try:
                from odoo.addons.hudson_in_payroll.services.tds.annual_income_projection_service import AnnualIncomeProjectionService  # pyrefly: ignore [missing-import]
                proj_svc = AnnualIncomeProjectionService(self.env)
                proj = proj_svc.project_annual_income(employee, eval_date=lwd_date, payslip=settlement.payslip_id)
                if proj and getattr(proj, 'gross_total_income', 0.0):
                    annual_salary = float(proj.gross_total_income)
                if proj and getattr(proj, 'regime_code', False):
                    regime_code = proj.regime_code.lower()
                if proj and getattr(proj, 'financial_year_id', False):
                    financial_year = self.env['tds.financial.year'].browse(proj.financial_year_id)
            except Exception:
                pass

            std_deduction = 75000.0 if regime_code == 'new' else 50000.0
            base_taxable_salary = max(0.0, annual_salary - std_deduction) if annual_salary > 0 else 0.0
            new_taxable_income = base_taxable_salary + taxable_gratuity

            from odoo.addons.hudson_in_payroll.services.tds.income_tax_slab_service import IncomeTaxSlabService  # pyrefly: ignore [missing-import]
            from odoo.addons.hudson_in_payroll.services.tds.health_education_cess_service import HealthEducationCessService  # pyrefly: ignore [missing-import]

            age_category = IncomeTaxSlabService.resolve_age_category(employee, financial_year, eval_date=lwd_date)
            slab_svc = IncomeTaxSlabService(self.env)

            res_before = slab_svc.calculate_base_tax(base_taxable_salary, financial_year, regime_code, age_category=age_category)
            res_after = slab_svc.calculate_base_tax(new_taxable_income, financial_year, regime_code, age_category=age_category)

            tax_before = float(getattr(res_before, 'base_tax_liability', 0.0) or 0.0)
            tax_after = float(getattr(res_after, 'base_tax_liability', 0.0) or 0.0)
            incremental_tax = max(0.0, tax_after - tax_before)

            cess_svc = HealthEducationCessService(self.env)
            cess_res = cess_svc.calculate_cess(incremental_tax, eval_date=lwd_date)
            additional_tds = float(getattr(cess_res, 'total_annual_tax_liability', 0.0) or 0.0)

            return round(additional_tds, 2)
        except Exception as e:
            _logger.warning("TDS on gratuity calculation failed for settlement %s: %s", settlement.name, str(e))
            return 0.0


    def _compute_pt_reconciliation_component(self, settlement, employee, lwd):
        """
        Calls ProfessionalTaxService statutory reconciliation component.
        If a settlement payslip is linked and already has a PT deduction line,
        skip standalone reconciliation to prevent double-deducting PT.
        """
        try:
            if settlement.payslip_id and settlement.payslip_id.exists():
                settlement.payslip_id.invalidate_recordset(['line_ids'])
                pt_lines = settlement.payslip_id.line_ids.filtered(lambda l: l.code == 'PT' and round(abs(l.total), 2) > 0.0)
                if pt_lines:
                    return None

            # pyrefly: ignore [missing-import]
            from odoo.addons.hudson_in_payroll.services.professional_tax.professional_tax_service import ProfessionalTaxService
            pt_service = ProfessionalTaxService(self.env)
            recon_res = pt_service.compute_pt_reconciliation_for_exit(employee, last_working_day=lwd)
            net_pt = float(recon_res.get('pt_net_payable', 0.0) or 0.0)
            if net_pt > 0.0:
                return {
                    'component_code': 'PT_RECON',
                    'component_name': _('Professional Tax (Reconciliation)'),
                    'line_type': 'deduction',
                    'sequence': 50,
                    'amount': net_pt,
                    'description': recon_res.get('description', _('Statutory PT reconciliation on exit as of %s.') % lwd),
                }
            return None
        except Exception as e:
            _logger.warning("PT reconciliation skipped/failed for settlement %s: %s", settlement.name, str(e))
            return None

    def _compute_notice_pay_component(self, settlement, employee, lwd):
        """
        Calculates Notice Pay Earning or Notice Shortfall Recovery Deduction.
        Uses employee working schedule (resource.calendar) to compute unserved working days
        and month scheduled working days divisor, ensuring fair and accurate proration.
        Falls back cleanly to calendar days if no schedule is assigned.
        """
        try:
            resignation = settlement.resignation_id
            contract = getattr(employee, 'version_id', False) or self.env['hr.version'].search([
                ('employee_id', '=', employee.id)
            ], order='id desc', limit=1)

            basic = float(getattr(contract, 'basic_salary', 0.0) or getattr(contract, 'wage', 0.0) or 0.0)
            da = float(getattr(contract, 'da', 0.0) or getattr(contract, 'da_amount', 0.0) or 0.0)
            wage_base = basic + da

            if resignation and getattr(resignation, 'expected_revealing_date', None) and getattr(resignation, 'approved_revealing_date', None):
                exp = fields.Date.from_string(resignation.expected_revealing_date)
                app = fields.Date.from_string(resignation.approved_revealing_date)
                if app and exp and app < exp and not getattr(resignation, 'notice_period_waived', False):
                    # Resolve employee working schedule / resource calendar
                    calendar = (
                        getattr(employee, 'resource_calendar_id', False) or
                        (contract and getattr(contract, 'resource_calendar_id', False)) or
                        getattr(employee.company_id, 'resource_calendar_id', False)
                    )

                    start_unserved = app + timedelta(days=1)
                    end_unserved = exp
                    ref_date = fields.Date.from_string(app or lwd or fields.Date.today())

                    shortfall_days = 0.0
                    month_sched_days = 0.0

                    if calendar:
                        try:
                            tz = pytz.timezone(calendar.tz or 'UTC')
                            # 1. Calculate unserved scheduled working days
                            dt_from = tz.localize(datetime.combine(start_unserved, datetime.min.time()))
                            dt_to = tz.localize(datetime.combine(end_unserved, datetime.max.time()))
                            duration_data = calendar.get_work_duration_data(dt_from, dt_to, compute_leaves=False)
                            shortfall_days = float(duration_data.get('days', 0.0))

                            # 2. Calculate total scheduled working days in departure month
                            days_in_month = cal_mod.monthrange(ref_date.year, ref_date.month)[1]
                            m_start = tz.localize(datetime.combine(date(ref_date.year, ref_date.month, 1), datetime.min.time()))
                            m_end = tz.localize(datetime.combine(date(ref_date.year, ref_date.month, days_in_month), datetime.max.time()))
                            m_data = calendar.get_work_duration_data(m_start, m_end, compute_leaves=False)
                            month_sched_days = float(m_data.get('days', 0.0))
                        except Exception as cal_err:
                            _logger.warning("Resource calendar calculation failed for settlement %s: %s. Using fallback.", settlement.name, str(cal_err))
                            shortfall_days = 0.0
                            month_sched_days = 0.0

                    # Fallbacks if schedule not configured or returned zero
                    if shortfall_days <= 0.0:
                        shortfall_days = float((exp - app).days)

                    if month_sched_days <= 0.0:
                        days_in_month = cal_mod.monthrange(ref_date.year, ref_date.month)[1] if ref_date else 30
                        month_sched_days = float(
                            getattr(contract, 'standard_working_days_per_month', 0.0) or
                            days_in_month or
                            26.0
                        )

                    daily_rate = (wage_base / month_sched_days) if (wage_base > 0.0 and month_sched_days > 0.0) else 0.0

                    if shortfall_days > 0 and daily_rate > 0.0:
                        amount = round(daily_rate * shortfall_days, 2)
                        display_days = int(shortfall_days) if shortfall_days.is_integer() else round(shortfall_days, 2)
                        return {
                            'component_code': 'NOTICE_RECOVERY',
                            'component_name': _('Notice Period Shortfall Recovery'),
                            'line_type': 'deduction',
                            'sequence': 40,
                            'amount': amount,
                            'description': _('Recovery for %s unserved scheduled working days.') % display_days,
                        }
            return None
        except Exception as e:
            _logger.warning("Notice pay calculation skipped for settlement %s: %s", settlement.name, str(e))
            return None

    def _sync_settlement_lines(self, settlement, component_results):
        """
        Idempotently creates or updates final.settlement.line records for settlement.
        Matches by component_code. If amount is >= 0, updates existing line or creates new line.
        """
        line_model = self.env['final.settlement.line']
        existing_lines = {l.component_code: l for l in settlement.line_ids}
        synced_line_ids = []

        for comp in component_results:
            code = comp['component_code']
            amount = float(comp.get('amount', 0.0))

            vals = {
                'component_name': comp['component_name'],
                'line_type': comp['line_type'],
                'amount': amount,
                'description': comp.get('description', ''),
            }
            if 'sequence' in comp:
                vals['sequence'] = comp['sequence']

            if code in existing_lines:
                line = existing_lines[code]
                line.write(vals)
                synced_line_ids.append(line.id)
            else:
                vals.update({
                    'settlement_id': settlement.id,
                    'component_code': code,
                })
                new_line = line_model.create(vals)
                synced_line_ids.append(new_line.id)

        # Clean up obsolete system-managed or payslip-synced lines that are no longer present
        new_codes = {comp['component_code'] for comp in component_results}
        system_codes = {
            'FINAL_MONTH_SALARY', 'LEAVE_ENCASH', 'EXIT_LEAVE_ENCASH',
            'GRATUITY', 'TDS_GRATUITY', 'PT_RECON', 'NOTICE_RECOVERY'
        }
        for code, line in list(existing_lines.items()):
            is_payslip_sync = bool(line.description and 'synced from settlement payslip' in line.description)
            if code not in new_codes and (code in system_codes or is_payslip_sync):
                line.unlink()

        # Trigger recomputation of totals on settlement with cache invalidated
        settlement.invalidate_recordset(['line_ids'])
        settlement._compute_settlement_totals()
        return synced_line_ids

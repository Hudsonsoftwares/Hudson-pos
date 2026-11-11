# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from datetime import datetime, time
import pytz
# pyrefly: ignore [missing-import]
from odoo import api, fields, models


class HrPayslipWorkedDays(models.Model):
    """Worked Days records for tracking attendance, leaves, and payable time during a payslip period."""
    _name = 'hr.payslip.worked.days'
    _description = 'Payslip Worked Days'
    _order = 'payslip_id, sequence'

    name = fields.Char(string='Description', required=True)
    payslip_id = fields.Many2one(
        'hr.payslip',
        string='Pay Slip',
        required=True,
        ondelete='cascade',
        index=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        related='payslip_id.employee_id',
        store=True,
        readonly=True,
        index=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='payslip_id.company_id',
        store=True,
        readonly=True,
        index=True
    )
    payslip_run_id = fields.Many2one(
        'hr.payslip.run',
        string='Pay Run',
        related='payslip_id.payslip_run_id',
        store=True,
        readonly=True,
        index=True
    )
    sequence = fields.Integer(string='Sequence', default=10, required=True, index=True)
    code = fields.Char(
        string='Code',
        required=True,
        help="The code that can be referenced in salary rules (e.g. WORK100, LEAVE100, LOP)"
    )
    number_of_days = fields.Float(string='Number of Days', default=0.0)
    number_of_hours = fields.Float(string='Number of Hours', default=0.0)
    currency_id = fields.Many2one(
        related='payslip_id.currency_id',
        string='Currency',
        readonly=True
    )
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        compute='_compute_amount',
        store=True,
        readonly=False,
        default=0.0,
        help="Monetary amount associated with this worked days category."
    )
    contract_id = fields.Many2one(
        'hr.version',
        string='Contract',
        help="The contract for which the worked days are computed"
    )

    @api.depends(
        'number_of_hours', 'number_of_days', 'code',
        'contract_id', 'contract_id.wage', 'contract_id.basic_salary',
        'payslip_id.date_from', 'payslip_id.date_to', 'payslip_id.contract_id'
    )
    def _compute_amount(self):
        for line in self:
            if line.code == 'OUT_OF_CONTRACT':
                line.amount = 0.0
                continue
            contract = line.contract_id or (line.payslip_id.contract_id if line.payslip_id else False)
            if not contract:
                line.amount = 0.0
                continue
            wage = float(getattr(contract, 'wage', 0.0) or getattr(contract, 'basic_salary', 0.0) or 0.0)
            slip = line.payslip_id
            d_from = slip.date_from if slip else False
            d_to = slip.date_to if slip else False

            sched_hours = 0.0
            sched_days = 0.0
            if slip and hasattr(slip, '_get_attendance_vs_schedule') and d_from and d_to:
                att_data = slip._get_attendance_vs_schedule(contract, d_from, d_to)
                sched_hours = att_data.get('scheduled_hours', 0.0)
                sched_days = att_data.get('scheduled_days', 0.0)
            if not sched_hours or sched_hours <= 0.0:
                cal = contract.resource_calendar_id or contract.employee_id.resource_calendar_id
                h_per_day = (cal.hours_per_day if cal and cal.hours_per_day else 8.0)
                if cal and d_from and d_to:
                    tz_name = getattr(cal, 'tz', False) or getattr(contract.employee_id, 'tz', False) or (contract.company_id and contract.company_id.tz) or self.env.company.tz or 'UTC'
                    tz = pytz.timezone(tz_name)
                    start_dt = tz.localize(datetime.combine(fields.Date.from_string(d_from), time.min))
                    end_dt = tz.localize(datetime.combine(fields.Date.from_string(d_to), time.max))
                    sched_hours = cal.get_work_hours_count(start_dt, end_dt, compute_leaves=False)
                if not sched_hours or sched_hours <= 0.0:
                    sched_hours = h_per_day * 26.0
                sched_days = sched_hours / h_per_day if h_per_day else 26.0

            if line.code == 'WORK100':
                pay_by_att = getattr(contract, 'pay_by_attendance', False)
                if pay_by_att:
                    if sched_hours > 0.0 and line.number_of_hours >= 0.0:
                        line.amount = round(wage * (line.number_of_hours / sched_hours), 2)
                    elif sched_days > 0.0 and line.number_of_days >= 0.0:
                        line.amount = round(wage * (line.number_of_days / sched_days), 2)
                    else:
                        line.amount = 0.0
                else:
                    if sched_hours > 0.0 and 0.0 < line.number_of_hours < sched_hours:
                        line.amount = round(wage * (line.number_of_hours / sched_hours), 2)
                    else:
                        line.amount = wage
            elif line.code == 'OVERTIME':
                if slip and hasattr(slip, '_get_dynamic_overtime_pay'):
                    line.amount = round(slip._get_dynamic_overtime_pay(contract), 2)
                elif slip and hasattr(slip, '_get_dynamic_overtime_values'):
                    base_hourly, rate_pct, qty = slip._get_dynamic_overtime_values(contract)
                    line.amount = round(qty * base_hourly * (rate_pct / 100.0), 2)
                else:
                    base_hourly = (wage / sched_hours) if sched_hours > 0.0 else 0.0
                    line.amount = round(base_hourly * 1.5 * line.number_of_hours, 2)
            elif line.code in ('UNPAID', 'LOP', 'ABSENT'):
                line.amount = 0.0
            else:
                if sched_days > 0.0 and line.number_of_days > 0.0:
                    line.amount = round(wage * (line.number_of_days / sched_days), 2)
                elif sched_hours > 0.0 and line.number_of_hours > 0.0:
                    line.amount = round(wage * (line.number_of_hours / sched_hours), 2)
                else:
                    line.amount = 0.0
    description = fields.Char(
        string='Description',
        compute='_compute_description',
        store=True,
        readonly=False,
    )

    def _compute_description(self):
        for line in self:
            if not line.description:
                if line.code == 'OUT_OF_CONTRACT':
                    line.description = "Out of Contract"
                elif line.code == 'WORK100':
                    line.description = "Normal Working Days"
                elif line.code == 'UNPAID':
                    line.description = "Unpaid Leave"
                elif line.code == 'SHORTAGE':
                    line.description = "Attendance Shortage"
                elif line.code == 'OVERTIME':
                    line.description = "Overtime Hours"
                else:
                    line.description = line.name or line.code

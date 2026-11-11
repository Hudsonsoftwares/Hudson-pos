# -*- coding: utf-8 -*-
from odoo import fields, models, _


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    hds_snapshot_id = fields.Many2one(
        'hds.hr.snapshot',
        string="HR Snapshot",
        readonly=True,
        copy=False,
        ondelete='set null',
        help="Frozen snapshot of HR, statutory, contract, and attendance details captured at confirmation."
    )

    def action_payslip_done(self):
        """Override payslip confirmation to freeze HR snapshot before changing state to done."""
        self.action_compute_sheet()
        self._hds_create_hr_snapshot()
        return super(HrPayslip, self).action_payslip_done()

    def _hds_create_hr_snapshot(self):
        """Creates a frozen HR snapshot record for each payslip upon initial confirmation."""
        for payslip in self:
            if payslip.hds_snapshot_id:
                continue

            emp = payslip.employee_id
            contract = payslip.contract_id
            company = payslip.company_id or self.env.company

            # 1. Period & Date
            payroll_period = payslip.date_from.strftime('%m/%Y') if payslip.date_from else ''
            snapshot_date = fields.Datetime.now()

            # 2. Descriptive employee details
            employee_code = emp.identification_id or '' if emp else ''
            department = emp.department_id.name or '' if emp and emp.department_id else ''
            designation = emp.job_id.name or '' if emp and emp.job_id else ''
            manager = emp.parent_id.name or '' if emp and emp.parent_id else ''

            # Defensive branch check
            branch = ''
            if emp and 'branch_id' in emp._fields:
                branch_obj = getattr(emp, 'branch_id', False)
                if branch_obj:
                    branch = getattr(branch_obj, 'name', '') or ''

            # Defensive joining date check (employee.joining_date or contract.date_start)
            joining_date = False
            if emp and 'joining_date' in emp._fields and getattr(emp, 'joining_date', False):
                joining_date = getattr(emp, 'joining_date')
            elif contract and getattr(contract, 'date_start', False):
                joining_date = getattr(contract, 'date_start')

            # Employment type label resolution via field._description_selection(env)
            employment_type = ''
            if emp and 'employee_type' in emp._fields:
                raw_type = getattr(emp, 'employee_type', False)
                if raw_type:
                    field_obj = emp._fields['employee_type']
                    if hasattr(field_obj, '_description_selection') and callable(getattr(field_obj, '_description_selection')):
                        sel_dict = dict(field_obj._description_selection(self.env))
                        employment_type = sel_dict.get(raw_type, str(raw_type))
                    elif hasattr(raw_type, 'name'):
                        employment_type = raw_type.name or ''
                    else:
                        employment_type = str(raw_type)
            if not employment_type and emp and hasattr(emp, 'employee_type_id') and emp.employee_type_id:
                employment_type = emp.employee_type_id.name or ''

            # Currency
            currency_id = company.currency_id.id if company and company.currency_id else False
            if not currency_id and contract and hasattr(contract, 'currency_id') and contract.currency_id:
                currency_id = contract.currency_id.id

            # Contract Monetary amounts (safely guarded against False contract)
            wage = contract.wage if contract else 0.0
            basic_salary = getattr(contract, 'basic_salary', 0.0) if contract else 0.0
            hra = getattr(contract, 'hra', 0.0) if contract else 0.0
            da = getattr(contract, 'da', 0.0) if contract else 0.0
            travel_allowance = getattr(contract, 'travel_allowance', 0.0) if contract else 0.0

            # Statutory details & selection resolution
            pf_wage_basis = ''
            stat_target = emp if (emp and 'hds_in_pf_contribution_basis' in emp._fields) else (
                contract if (contract and 'hds_in_pf_contribution_basis' in contract._fields) else False
            )
            if stat_target:
                raw_basis = getattr(stat_target, 'hds_in_pf_contribution_basis', False)
                if raw_basis:
                    basis_field = stat_target._fields['hds_in_pf_contribution_basis']
                    if hasattr(basis_field, '_description_selection') and callable(getattr(basis_field, '_description_selection')):
                        sel_dict = dict(basis_field._description_selection(self.env))
                        pf_wage_basis = sel_dict.get(raw_basis, str(raw_basis))
                    else:
                        pf_wage_basis = str(raw_basis)

            uan = getattr(emp, 'hds_in_uan', '') or '' if emp else ''
            pf_member_id = getattr(emp, 'hds_in_pf_member_id', '') or '' if emp else ''
            epf_applicable = bool(getattr(emp, 'hds_in_epf_applicable', False)) if emp else False
            eps_applicable = bool(getattr(emp, 'hds_in_eps_applicable', False)) if emp else False

            # Attendance details
            worked_lines = payslip.worked_days_line_ids
            lop_days = sum(worked_lines.filtered(lambda l: (l.code or '').upper() in ('UNPAID', 'ABSENT', 'SHORTAGE', 'LOP', 'LEAVE_UNPAID')).mapped('number_of_days')) if worked_lines else 0.0
            if hasattr(payslip, 'total_worked_days') and worked_lines:
                working_days = float(payslip.total_worked_days)
            elif worked_lines:
                work_days = sum(worked_lines.filtered(lambda l: (l.code or '').upper() not in ('UNPAID', 'ABSENT', 'SHORTAGE', 'LOP', 'LEAVE_UNPAID')).mapped('number_of_days'))
                working_days = max(0.0, work_days - lop_days)
            else:
                working_days = 0.0
            paid_days = working_days

            vals = {
                'payslip_id': payslip.id,
                'payroll_period': payroll_period,
                'snapshot_date': snapshot_date,
                'employee_id': emp.id if emp else False,
                'employee_code': employee_code,
                'department': department,
                'designation': designation,
                'manager': manager,
                'company_id': company.id if company else False,
                'branch': branch,
                'joining_date': joining_date,
                'employment_type': employment_type,
                'contract_id': contract.id if contract else False,
                'currency_id': currency_id,
                'wage': wage,
                'basic_salary': basic_salary,
                'hra': hra,
                'da': da,
                'travel_allowance': travel_allowance,
                'pf_wage_basis': pf_wage_basis,
                'uan': uan,
                'pf_member_id': pf_member_id,
                'epf_applicable': epf_applicable,
                'eps_applicable': eps_applicable,
                'working_days': working_days,
                'paid_days': paid_days,
                'lop_days': lop_days,
            }

            snapshot = self.env['hds.hr.snapshot'].sudo().create(vals)
            payslip.sudo().write({'hds_snapshot_id': snapshot.id})

    def action_view_hds_snapshot(self):
        """Action method called by the smart button on payslip form view."""
        self.ensure_one()
        if not self.hds_snapshot_id:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'name': _('HR Snapshot'),
            'type': 'ir.actions.act_window',
            'res_model': 'hds.hr.snapshot',
            'res_id': self.hds_snapshot_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

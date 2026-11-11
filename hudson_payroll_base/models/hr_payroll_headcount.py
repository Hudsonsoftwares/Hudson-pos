# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import api, fields, models, _


class HrPayrollHeadcount(models.Model):
    _name = 'hr.payroll.headcount'
    _description = 'Payroll Headcount Report'
    _order = 'date_from desc, id desc'

    def _default_name(self):
        today = fields.Date.today()
        company_name = self.env.company.name or ''
        return _("Headcount for %(company)s on the %(from_date)s") % {
            'company': company_name,
            'from_date': today,
        }

    name = fields.Char(string='Name', required=True, default=_default_name)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    date_from = fields.Date(string='From', required=True, default=fields.Date.today)
    date_to = fields.Date(string='To')
    line_ids = fields.One2many(
        'hr.payroll.headcount.line',
        'headcount_id',
        string='Department Breakdown'
    )
    employee_count = fields.Integer(
        string='Employees',
        compute='_compute_employee_count',
        store=True
    )

    @api.depends('line_ids.employee_count', 'line_ids.employee_ids')
    def _compute_employee_count(self):
        for rec in self:
            all_employees = rec.line_ids.mapped('employee_ids')
            rec.employee_count = len(all_employees) if all_employees else sum(rec.line_ids.mapped('employee_count'))

    @api.onchange('date_from', 'date_to', 'company_id')
    def _onchange_period(self):
        company_name = self.company_id.name or self.env.company.name or ''
        if self.date_from and self.date_to:
            self.name = _("Headcount for %(company)s from %(from_date)s to %(to_date)s") % {
                'company': company_name,
                'from_date': self.date_from,
                'to_date': self.date_to,
            }
        elif self.date_from:
            self.name = _("Headcount for %(company)s on the %(from_date)s") % {
                'company': company_name,
                'from_date': self.date_from,
            }

    def action_populate(self):
        """Populate running contracts for the given period and group by department."""
        self.ensure_one()
        end_date = self.date_to or self.date_from

        domain = [('company_id', '=', self.company_id.id)]
        if 'contract_date_start' in self.env['hr.version']._fields:
            domain += [
                '|', ('contract_date_start', '=', False), ('contract_date_start', '<=', end_date),
                '|', ('contract_date_end', '=', False), ('contract_date_end', '>=', self.date_from),
            ]
        if 'active' in self.env['hr.version']._fields:
            domain.append(('active', '=', True))

        contracts = self.env['hr.version'].search(domain, order='id desc')

        # Clear existing lines
        self.line_ids.unlink()

        # Group by department
        dept_contracts = defaultdict(lambda: self.env['hr.version'])
        for contract in contracts:
            dept = contract.department_id or contract.employee_id.department_id
            dept_contracts[dept] |= contract

        lines_to_create = []
        for dept, c_records in dept_contracts.items():
            employees = c_records.mapped('employee_id')
            lines_to_create.append({
                'headcount_id': self.id,
                'department_id': dept.id if dept else False,
                'employee_count': len(employees),
                'employee_ids': [(6, 0, employees.ids)],
            })

        if lines_to_create:
            self.env['hr.payroll.headcount.line'].create(lines_to_create)

        return True


class HrPayrollHeadcountLine(models.Model):
    _name = 'hr.payroll.headcount.line'
    _description = 'Payroll Headcount Line'
    _order = 'department_id, id'

    headcount_id = fields.Many2one(
        'hr.payroll.headcount',
        string='Headcount',
        required=True,
        ondelete='cascade'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='headcount_id.company_id',
        store=True,
        index=True,
        readonly=True
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]"
    )
    employee_count = fields.Integer(string='Employees')
    employee_ids = fields.Many2many(
        'hr.employee',
        'hr_payroll_headcount_line_employee_rel',
        'line_id',
        'employee_id',
        string='Employees List'
    )

# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools


class HdsInStatutoryReport(models.Model):
    """
    Enterprise Statutory Compliance Report SQL View Model.
    Unified, read-only reporting framework aggregating processed payroll audit data
    across all statutory compliance modules (EPF, ESIC, LWF, PT, Gratuity, TDS).
    """
    _name = 'hds.in.statutory.report'
    _description = 'Enterprise Statutory Compliance Report'
    _auto = False
    _order = 'calculation_date desc, id desc'
    _rec_name = 'rule_name'

    company_id = fields.Many2one('res.company', string="Company", readonly=True)
    employee_id = fields.Many2one('hr.employee', string="Employee", readonly=True)
    employee_code = fields.Char(string="Employee ID", readonly=True)
    department_id = fields.Many2one('hr.department', string="Department", readonly=True)
    state_id = fields.Many2one('res.country.state', string="Work State", readonly=True)
    payslip_id = fields.Many2one('hr.payslip', string="Payslip", readonly=True)
    date_from = fields.Date(string="Payroll From Date", readonly=True)
    date_to = fields.Date(string="Payroll To Date", readonly=True)
    statutory_module = fields.Selection([
        ('epf', 'Employee Provident Fund (EPF)'),
        ('esic', 'Employees State Insurance (ESIC)'),
        ('pt', 'Professional Tax (PT)'),
        ('lwf', 'Labour Welfare Fund (LWF)'),
        ('bonus', 'Statutory Bonus'),
        ('gratuity', 'Gratuity'),
        ('tds', 'Income Tax (TDS)'),
    ], string="Statutory Module", readonly=True)
    rule_code = fields.Char(string="Rule Code", readonly=True)
    rule_name = fields.Char(string="Statutory Rule", readonly=True)
    statutory_amount = fields.Float(string="Statutory Amount", digits=(16, 2), readonly=True)
    calculation_date = fields.Date(string="Processing Date", readonly=True)
    status = fields.Selection([
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ], string="Status", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    a.id AS id,
                    a.company_id AS company_id,
                    a.employee_id AS employee_id,
                    CAST(NULL AS varchar) AS employee_code,
                    CAST(NULL AS integer) AS department_id,
                    CAST(NULL AS integer) AS state_id,
                    a.payslip_id AS payslip_id,
                    p.date_from AS date_from,
                    p.date_to AS date_to,
                    a.statutory_module AS statutory_module,
                    a.rule_code AS rule_code,
                    COALESCE(pl.name, r.name->>'en_US', a.rule_code) AS rule_name,
                    COALESCE(pl.total, 0.0) AS statutory_amount,
                    a.calculation_date AS calculation_date,
                    a.status AS status
                FROM hds_in_payroll_audit a
                LEFT JOIN hr_payslip p ON p.id = a.payslip_id
                LEFT JOIN hr_salary_rule r ON r.code = a.rule_code
                LEFT JOIN hr_payslip_line pl ON (pl.slip_id = a.payslip_id AND pl.code = a.rule_code)
            )
        """)

# -*- coding: utf-8 -*-
from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSalaryCertificate(TransactionCase):
    """Salary Certificate (employee > Print): every value comes from the employee, its contract
    and its company."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'Certificate Test Co', 'phone': '0471 2345678'})
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=[cls.company.id]))
        cls.report = cls.env.ref('hudson_payroll_base.action_report_salary_certificate')
        cls.intern_type = cls.env['hr.employee.type'].search([], limit=1) or cls.env['hr.employee.type'].create({'name': 'Intern'})
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Certificate Employee', 'company_id': cls.company.id, 'job_title': 'Payroll Analyst',
            'passport_id': 'P1234567', 'country_id': cls.env.ref('base.in').id,
        })
        cls.employee.version_id.write({
            'wage': 45000.0, 'basic_salary': 22500.0, 'contract_date_start': date(2026, 6, 1),
            'employee_type_id': cls.intern_type.id,
        })

    def _html(self, employees):
        return self.report._render_qweb_html(self.report.report_name, employees.ids)[0].decode()

    def test_values_come_from_the_database(self):
        html = self._html(self.employee)
        for value in ('Certificate Employee', 'P1234567', 'India', 'Payroll Analyst', 'Certificate Test Co',
                      '0471 2345678', self.intern_type.name, '22,500.00', '45,000.00', self.env.user.name,
                      'Subject: Salary Certificate', 'This is to certify that the following individual'):
            self.assertIn(value, html, value)

    def test_one_page_per_employee_and_blank_values(self):
        other = self.env['hr.employee'].create({'name': 'Second Employee', 'company_id': self.company.id})
        html = self._html(self.employee | other)
        self.assertEqual(html.count('Subject: Salary Certificate'), 2)
        self.assertIn('Second Employee', html)

    def test_printing_is_limited_to_payroll(self):
        self.assertEqual(self.report.binding_model_id.model, 'hr.employee')
        self.assertEqual(set(self.report.group_ids.mapped(lambda g: g.get_external_id()[g.id])),
                         {'hudson_payroll_base.group_payroll_user', 'hudson_payroll_base.group_payroll_manager'})

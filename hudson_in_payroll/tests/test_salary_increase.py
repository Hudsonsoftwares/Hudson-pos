# -*- coding: utf-8 -*-
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSalaryIncrease(TransactionCase):
    """Salary Increase dialog (as in Odoo): the increase rate applies to the full wage or to the wage
    up to the capped amount, plus an extra amount; one or several employees at once. Each revision
    creates an employee version from its effective date (1st of a month, today or later)."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        today = fields.Date.context_today(self.env.user)
        self.date = today.replace(day=1) + relativedelta(months=1)
        self.employee = self._employee('Increase Employee A', 50000.0)
        self.other = self._employee('Increase Employee B', 20000.0)

    def _employee(self, name, wage):
        employee = self.env['hr.employee'].create({'name': name, 'company_id': self.company.id})
        vals = {'wage': wage, 'date_version': date(2026, 1, 1)}
        if 'contract_date_start' in self.env['hr.version']._fields:
            vals['contract_date_start'] = date(2026, 1, 1)
        employee.version_id.write(vals)
        return employee

    def _wizard(self, employees, **vals):
        return self.env['hds.in.salary.revision.wizard'].with_context(
            active_id=employees[:1].id, active_ids=employees.ids, active_model='hr.employee',
            default_increase_percentage=0.0,
        ).create(dict({'effective_date': self.date, 'computation_type': 'percentage',
                       'breakdown_distribution_mode': 'auto_structure'}, **vals))

    def _wage_on(self, employee, day):
        return employee._get_version(day).wage

    def test_full_wage(self):
        wizard = self._wizard(self.employee, increase_percentage=10.0, revision_basis='full_wage')
        self.assertEqual(wizard.revised_wage, 55000.0)

    def test_capped_wage_applies_rate_up_to_the_cap(self):
        # 10% on a ₹50,000 wage with a ₹30,000 cap adds ₹3,000
        wizard = self._wizard(self.employee, increase_percentage=10.0, revision_basis='capped_wage',
                              capped_wage_amount=30000.0)
        self.assertEqual(wizard.revised_wage, 53000.0)
        # A wage below the cap gets the rate on the whole wage
        wizard = self._wizard(self.other, increase_percentage=10.0, revision_basis='capped_wage',
                              capped_wage_amount=30000.0)
        self.assertEqual(wizard.revised_wage, 22000.0)

    def test_extra_amount(self):
        wizard = self._wizard(self.employee, increase_percentage=10.0, revision_basis='capped_wage',
                              capped_wage_amount=30000.0, extra_amount=1000.0)
        self.assertEqual(wizard.revised_wage, 54000.0)
        wizard = self._wizard(self.employee, increase_percentage=0.0, extra_amount=2500.0)
        self.assertEqual(wizard.revised_wage, 52500.0)
        # The detailed wizard's fixed amount mode is unchanged
        wizard = self._wizard(self.employee, computation_type='fixed_amount', increase_amount=4000.0)
        self.assertEqual(wizard.revised_wage, 54000.0)

    def test_revision_creates_a_dated_version(self):
        old_version = self.employee._get_version(self.date - relativedelta(days=1))
        wizard = self._wizard(self.employee, increase_percentage=10.0, revision_basis='capped_wage',
                              capped_wage_amount=30000.0, extra_amount=500.0)
        action = wizard.action_confirm_salary_increase()
        revision = self.env['hds.in.salary.revision'].browse(action['res_id'])
        self.assertEqual((revision.old_wage, revision.new_wage, revision.extra_amount), (50000.0, 53500.0, 500.0))
        new_version = revision.contract_id
        self.assertNotEqual(new_version, old_version)
        self.assertEqual(new_version.date_version, self.date)
        self.assertEqual(new_version.wage, 53500.0)
        # The earlier version (history) keeps the old salary; the new one applies from the date
        self.assertEqual(old_version.wage, 50000.0)
        self.assertEqual(self._wage_on(self.employee, self.date - relativedelta(days=1)), 50000.0)
        self.assertEqual(self._wage_on(self.employee, self.date), 53500.0)
        self.assertIn(new_version, self.employee.version_ids)

    def test_payslips_use_the_version_of_their_period(self):
        self._wizard(self.employee, increase_percentage=10.0).action_confirm_salary_increase()
        new_version = self.employee._get_version(self.date)
        old_version = self.employee._get_version(self.date - relativedelta(days=1))
        structure = self.env['hr.payroll.structure'].search([], limit=1)
        before = self.env['hr.payslip'].create({
            'name': 'Before', 'employee_id': self.employee.id, 'struct_id': structure.id,
            'date_from': self.date - relativedelta(months=1), 'date_to': self.date - relativedelta(days=1)})
        after = self.env['hr.payslip'].create({
            'name': 'After', 'employee_id': self.employee.id, 'struct_id': structure.id,
            'date_from': self.date, 'date_to': self.date + relativedelta(months=1, days=-1)})
        self.assertEqual(before.contract_id, old_version)
        self.assertEqual(after.contract_id, new_version)
        self.assertEqual(self.employee._hds_payroll_version(after.date_from, after.date_to), new_version)

    def test_confirm_several_employees(self):
        employees = self.employee | self.other
        wizard = self._wizard(employees, increase_percentage=10.0, revision_basis='capped_wage',
                              capped_wage_amount=30000.0)
        self.assertEqual(wizard.employee_count, 2)
        action = wizard.action_confirm_salary_increase()
        revisions = self.env['hds.in.salary.revision'].search(action['domain'])
        self.assertEqual(revisions.employee_id, employees)
        self.assertEqual(self._wage_on(self.employee, self.date), 53000.0)
        self.assertEqual(self._wage_on(self.other, self.date), 22000.0)

    def test_effective_date_rules(self):
        today = fields.Date.context_today(self.env.user)
        with self.assertRaises(ValidationError):  # in the past
            self._wizard(self.employee, increase_percentage=5.0,
                         effective_date=today.replace(day=1) - relativedelta(months=1)).action_confirm_salary_increase()
        with self.assertRaises(ValidationError):  # not the 1st of a month
            self._wizard(self.employee, increase_percentage=5.0,
                         effective_date=self.date + relativedelta(days=14)).action_confirm_salary_increase()
        # Default: the next 1st of a month (or today when it is the 1st)
        wizard = self.env['hds.in.salary.revision.wizard'].with_context(
            active_id=self.employee.id, active_model='hr.employee').create({'increase_percentage': 5.0})
        self.assertEqual(wizard.effective_date, today if today.day == 1 else self.date)

    def test_validation(self):
        with self.assertRaises(ValidationError):
            self._wizard(self.employee, increase_percentage=0.0, extra_amount=0.0).action_confirm_salary_increase()
        with self.assertRaises(ValidationError):
            self._wizard(self.employee, increase_percentage=10.0, revision_basis='capped_wage',
                         capped_wage_amount=0.0).action_confirm_salary_increase()
        # An error on one employee names it and cancels the whole increase
        self._wizard(self.other, increase_percentage=5.0).action_confirm_salary_increase()
        with self.assertRaises(UserError) as error:
            self._wizard(self.employee | self.other, increase_percentage=5.0).action_confirm_salary_increase()
        self.assertIn('Increase Employee B', str(error.exception))

    def test_advanced_shows_the_comparison(self):
        wizard = self._wizard(self.employee, increase_percentage=7.0, extra_amount=300.0)
        action = wizard.action_open_detailed_revision()
        comparison = self.env.ref('hudson_in_payroll.hds_in_salary_increase_comparison_view_form')
        self.assertEqual((action['res_id'], action['views']), (wizard.id, [(comparison.id, 'form')]))
        # Same values, current against new
        self.assertEqual((wizard.current_wage, wizard.revised_wage, wizard.wage_difference), (50000.0, 53800.0, 3800.0))
        # Back returns to the Salary Increase dialog with the values kept
        action = wizard.action_back_to_salary_increase()
        dialog = self.env.ref('hudson_in_payroll.hds_in_salary_increase_wizard_view_form')
        self.assertEqual((action['res_id'], action['views']), (wizard.id, [(dialog.id, 'form')]))
        self.assertEqual((wizard.increase_percentage, wizard.extra_amount), (7.0, 300.0))
        # Confirm from the comparison creates the revision as the dialog does
        action = wizard.action_confirm_salary_increase()
        self.assertEqual(self.env['hds.in.salary.revision'].browse(action['res_id']).new_wage, 53800.0)

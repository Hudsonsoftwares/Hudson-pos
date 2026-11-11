# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError
from ..services.revision.salary_revision_service import SalaryRevisionService


class TestSalaryRevisionEngine(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.hds_in_esic_applicable = True
        self.employee = self.env['hr.employee'].create({
            'name': 'Test Revision Employee',
            'hds_in_epf_applicable': True,
            'hds_in_esic_applicable': True,
            'company_id': self.company.id,
        })
        if hasattr(self.employee, 'contract_date_start'):
            self.employee.contract_date_start = '2026-01-01'
        if self.employee.version_id:
            self.contract = self.employee.version_id
            v_vals = {'wage': 20000.0, 'date_start': '2026-01-01', 'name': 'Contract - Test Revision Employee'}
            if hasattr(self.contract, 'contract_date_start'):
                v_vals['contract_date_start'] = '2026-01-01'
            self.contract.write(v_vals)
        else:
            c_vals = {
                'name': 'Contract - Test Revision Employee',
                'employee_id': self.employee.id,
                'wage': 20000.0,
                'date_start': '2026-01-01',
            }
            if 'contract_date_start' in self.env['hr.version']._fields:
                c_vals['contract_date_start'] = '2026-01-01'
            self.contract = self.env['hr.version'].create(c_vals)

    def test_01_salary_preview_simulation(self):
        """Validates simulated before and after breakdown for a +10% gross salary revision."""
        wizard = self.env['hds.in.salary.revision.wizard'].with_context(
            active_id=self.employee.id,
            active_model='hr.employee'
        ).create({
            'effective_date': '2026-04-01',
            'revision_type': 'annual_increment',
            'computation_type': 'percentage',
            'increase_percentage': 10.0,
            'revision_basis': 'full_wage',
        })

        self.assertEqual(wizard.current_wage, 20000.0)
        self.assertEqual(wizard.revised_wage, 22000.0)
        self.assertEqual(wizard.wage_difference, 2000.0)
        self.assertTrue(wizard.preview_old_esic_app)
        # Gross = ₹22,000 (> ₹21,000 ceiling for non-PWD) -> ESIC estimated coverage False
        self.assertFalse(wizard.preview_new_esic_app)

    def test_02_salary_revision_execution(self):
        """Validates end-to-end execution of salary revision via SalaryRevisionService."""
        wizard = self.env['hds.in.salary.revision.wizard'].with_context(
            active_id=self.employee.id,
            active_model='hr.employee'
        ).create({
            'effective_date': '2026-04-01',
            'revision_type': 'annual_increment',
            'computation_type': 'percentage',
            'increase_percentage': 10.0,
            'revision_basis': 'full_wage',
            'reason': 'Annual Increment 2026',
        })

        revision_record = wizard.action_confirm_revision()
        revision = self.env['hds.in.salary.revision'].browse(revision_record['res_id'])

        # 1. Immutable record created
        self.assertEqual(revision.employee_id.id, self.employee.id)
        self.assertEqual(revision.old_wage, 20000.0)
        self.assertEqual(revision.new_wage, 22000.0)
        self.assertEqual(revision.state, 'approved')

        # 2. Active contract updated
        self.assertEqual(self.contract.wage, 22000.0)

        # 3. Employee statutory defaults refreshed (ESIC becomes False as ₹22,000 > ₹21,000 ceiling)
        self.assertFalse(self.employee.hds_in_esic_applicable)

    def test_03_invalid_effective_date(self):
        """Validates that effective date preceding contract start date raises ValidationError."""
        wizard = self.env['hds.in.salary.revision.wizard'].with_context(
            active_id=self.employee.id,
            active_model='hr.employee'
        ).create({
            'effective_date': '2025-12-01', # Precedes contract start '2026-01-01'
            'revision_type': 'correction',
            'computation_type': 'fixed_amount',
            'increase_amount': 1000.0,
            'revision_basis': 'full_wage',
        })

        with self.assertRaises(ValidationError):
            wizard.action_confirm_revision()

    def test_04_epf_actual_basic_parity(self):
        """Validates parity when employee is configured with actual_pf_wage PF contribution basis."""
        self.employee.hds_in_pf_contribution_basis = 'actual_pf_wage'
        wizard = self.env['hds.in.salary.revision.wizard'].with_context(
            active_id=self.employee.id,
            active_model='hr.employee'
        ).create({
            'effective_date': '2026-04-01',
            'revision_type': 'annual_increment',
            'computation_type': 'percentage',
            'increase_percentage': 10.0,
            'revision_basis': 'full_wage',
        })

        # When contribution basis is 'actual_pf_wage', EPF wage is actual basic (₹11,000)
        self.assertEqual(wizard.preview_new_epf_wage, 11000.0)
        self.assertEqual(wizard.preview_new_ee_epf, 1320.0)

    def test_05_contract_breakdown_regeneration_and_isolation(self):
        """Validates that salary revision regenerates contract breakdown components and preserves multi-employee isolation."""
        # Setup Employee B (Other employee)
        emp_b = self.env['hr.employee'].create({
            'name': 'Other Employee',
            'company_id': self.company.id,
        })
        if emp_b.version_id:
            contract_b = emp_b.version_id
            contract_b.write({
                'name': 'Contract - Other Employee',
                'wage': 15000.0,
                'basic_salary': 7500.0,
                'hra': 3000.0,
                'fixed_allowance': 4500.0,
                'date_start': '2026-01-01',
            })
        else:
            contract_b = self.env['hr.version'].create({
                'name': 'Contract - Other Employee',
                'employee_id': emp_b.id,
                'wage': 15000.0,
                'basic_salary': 7500.0,
                'hra': 3000.0,
                'fixed_allowance': 4500.0,
                'date_start': '2026-01-01',
            })

        # Set initial breakdown on Employee A
        self.contract.write({
            'wage': 20000.0,
            'basic_salary': 10000.0,
            'hra': 4000.0,
            'fixed_allowance': 6000.0,
        })

        # Revise Employee A from ₹20,000 to ₹25,000
        wizard = self.env['hds.in.salary.revision.wizard'].with_context(
            active_id=self.employee.id,
            active_model='hr.employee'
        ).create({
            'effective_date': '2026-04-01',
            'revision_type': 'annual_increment',
            'computation_type': 'fixed_amount',
            'increase_amount': 5000.0,
            'revision_basis': 'full_wage',
        })

        wizard.action_confirm_revision()

        # 1. Employee A's contract breakdown is regenerated and balanced
        self.assertEqual(self.contract.wage, 25000.0)
        self.assertEqual(self.contract.basic_salary, 12500.0)
        self.assertEqual(self.contract.hra, 5000.0)
        self.assertEqual(self.contract.fixed_allowance, 7500.0)
        self.assertTrue(self.contract.breakdown_is_equal)

        # 2. Employee B's contract remains completely unchanged (Strict Isolation)
        self.assertEqual(contract_b.wage, 15000.0)
        self.assertEqual(contract_b.basic_salary, 7500.0)
        self.assertEqual(contract_b.hra, 3000.0)
        self.assertEqual(contract_b.fixed_allowance, 4500.0)

    def test_06_keep_existing_breakdown_mode(self):
        """Validates that 'keep_existing' mode updates gross wage but leaves component breakdown untouched."""
        self.contract.write({
            'wage': 20000.0,
            'basic_salary': 15000.0,
            'hra': 3000.0,
            'fixed_allowance': 2000.0,
        })

        wizard = self.env['hds.in.salary.revision.wizard'].with_context(
            active_id=self.employee.id,
            active_model='hr.employee'
        ).create({
            'effective_date': '2026-04-01',
            'revision_type': 'annual_increment',
            'computation_type': 'fixed_amount',
            'increase_amount': 5000.0,
            'revision_basis': 'full_wage',
            'breakdown_distribution_mode': 'keep_existing',
        })

        wizard.action_confirm_revision()

        # Contract wage is updated to ₹25,000, but stored components remain untouched
        self.assertEqual(self.contract.wage, 25000.0)
        self.assertEqual(self.contract.basic_salary, 15000.0)
        self.assertEqual(self.contract.hra, 3000.0)
        self.assertEqual(self.contract.fixed_allowance, 2000.0)

    def test_07_manual_adjust_breakdown_mode(self):
        """Validates manual breakdown allocation mode and strict sum validation."""
        c_vals = {'wage': 20000.0, 'date_start': '2026-01-01'}
        if hasattr(self.contract, 'contract_date_start'):
            c_vals['contract_date_start'] = '2026-01-01'
        self.contract.write(c_vals)

        # 1. Invalid manual sum raises ValidationError
        wizard_invalid = self.env['hds.in.salary.revision.wizard'].with_context(
            active_id=self.employee.id,
            active_model='hr.employee'
        ).create({
            'effective_date': '2026-04-01',
            'revision_type': 'annual_increment',
            'computation_type': 'fixed_amount',
            'increase_amount': 5000.0, # Revised wage = 25,000
            'revision_basis': 'full_wage',
            'breakdown_distribution_mode': 'manual_adjust',
            'manual_basic_salary': 15000.0,
            'manual_hra': 5000.0,
            'manual_fixed_allowance': 4000.0, # Total = 24,000 != 25,000
        })

        with self.assertRaises(ValidationError):
            wizard_invalid.action_confirm_revision()

        # 2. Valid manual sum executes and updates contract components
        wizard_valid = self.env['hds.in.salary.revision.wizard'].with_context(
            active_id=self.employee.id,
            active_model='hr.employee'
        ).create({
            'effective_date': '2026-04-01',
            'revision_type': 'annual_increment',
            'computation_type': 'fixed_amount',
            'increase_amount': 5000.0, # Revised wage = 25,000
            'revision_basis': 'full_wage',
            'breakdown_distribution_mode': 'manual_adjust',
            'manual_basic_salary': 15000.0,
            'manual_hra': 5000.0,
            'manual_fixed_allowance': 5000.0, # Total = 25,000 == 25,000
        })

        wizard_valid.action_confirm_revision()

        self.assertEqual(self.contract.wage, 25000.0)
        self.assertEqual(self.contract.basic_salary, 15000.0)
        self.assertEqual(self.contract.hra, 5000.0)
        self.assertEqual(self.contract.fixed_allowance, 5000.0)
        self.assertTrue(self.contract.breakdown_is_equal)

    def test_08_copy_current_and_auto_balance(self):
        """Validates 'copy_current' mode pre-filling and action_auto_balance_remaining functionality."""
        self.contract.write({
            'wage': 20000.0,
            'basic_salary': 10000.0,
            'hra': 4000.0,
            'fixed_allowance': 6000.0,
        })

        wizard = self.env['hds.in.salary.revision.wizard'].with_context(
            active_id=self.employee.id,
            active_model='hr.employee'
        ).create({
            'effective_date': '2026-04-01',
            'revision_type': 'annual_increment',
            'computation_type': 'fixed_amount',
            'increase_amount': 5000.0, # Revised wage = 25,000
            'revision_basis': 'full_wage',
            'breakdown_distribution_mode': 'copy_current',
        })

        # Trigger onchange to pre-fill current components
        wizard._onchange_breakdown_distribution_mode()

        self.assertEqual(wizard.manual_basic_salary, 10000.0)
        self.assertEqual(wizard.manual_hra, 4000.0)
        self.assertEqual(wizard.manual_fixed_allowance, 6000.0)
        self.assertEqual(wizard.manual_breakdown_remaining, 5000.0)
        self.assertFalse(wizard.manual_breakdown_is_equal)

        # Click Auto Balance Remaining button
        wizard.action_auto_balance_remaining()

        # Fixed Allowance becomes 6,000 + 5,000 = 11,000 to balance revised wage of 25,000
        self.assertEqual(wizard.manual_fixed_allowance, 11000.0)
        self.assertEqual(wizard.manual_breakdown_remaining, 0.0)
        self.assertTrue(wizard.manual_breakdown_is_equal)

        wizard.action_confirm_revision()

        self.assertEqual(self.contract.wage, 250000.0 if hasattr(self, 'abu_contract') else 25000.0)
        self.assertEqual(self.contract.basic_salary, 10000.0)
        self.assertEqual(self.contract.hra, 4000.0)
        self.assertEqual(self.contract.fixed_allowance, 11000.0)

    def test_11_salary_revision_effective_date_and_fixed_increment_not_zero(self):
        """
        Validates that when selecting an employee and changing effective_date to Jan 1
        with a fixed increase of ₹1,00,000, current_wage and revised_wage NEVER drop to 0.
        """
        emp = self.env['hr.employee'].create({
            'name': 'Abu Salary Test Employee',
            'company_id': self.company.id,
        })
        if emp.version_id:
            emp.version_id.write({'wage': 250000.0, 'date_start': '2026-10-01', 'name': 'Contract - Abu Salary Test'})
        else:
            self.env['hr.version'].create({
                'name': 'Contract - Abu Salary Test',
                'employee_id': emp.id,
                'wage': 250000.0,
                'date_start': '2026-10-01',
            })

        # Simulate opening wizard and setting employee
        wizard = self.env['hds.in.salary.revision.wizard'].create({
            'employee_id': emp.id,
        })
        wizard._onchange_employee_id()

        self.assertEqual(wizard.current_wage, 250000.0)

        # User changes effective_date to 2027-01-01 and increase_amount to 1,00,000
        wizard.write({
            'effective_date': '2027-01-01',
            'computation_type': 'fixed_amount',
            'increase_amount': 100000.0,
        })

        self.assertEqual(wizard.current_wage, 250000.0, "Current gross wage must remain 2,50,000 and not drop to 0")
        self.assertEqual(wizard.revised_wage, 350000.0, "Revised wage must be 3,50,000 and not 0")
        self.assertEqual(wizard.wage_difference, 100000.0, "Wage difference must be 1,00,000")

    def test_12_salary_revision_wizard_multi_company_domain(self):
        """
        Validates Issue 2:
        - Wizard company_id defaults to env.company.
        - Wizard default_get with active_id sets company_id from employee.
        - _onchange_company_id clears employee_id if company does not match.
        - ValidationError raised if attempting to save wizard with cross-company employee.
        """
        other_company = self.env['res.company'].create({'name': 'Second Test Company'})
        emp_other = self.env['hr.employee'].create({
            'name': 'Other Company Employee',
            'company_id': other_company.id,
        })
        if emp_other.version_id:
            emp_other.version_id.write({'wage': 50000.0, 'date_start': '2026-01-01', 'name': 'Contract - Other Company Employee'})
        else:
            self.env['hr.version'].create({
                'name': 'Contract - Other Company Employee',
                'employee_id': emp_other.id,
                'wage': 50000.0,
                'date_start': '2026-01-01',
            })

        # 1. Wizard default company = env.company
        defaults = self.env['hds.in.salary.revision.wizard'].default_get(['company_id', 'employee_id'])
        self.assertEqual(defaults.get('company_id'), self.env.company.id)

        # 2. Wizard opened from employee profile sets company_id and locks employee
        defaults_emp = self.env['hds.in.salary.revision.wizard'].with_context(
            active_model='hr.employee',
            active_id=emp_other.id
        ).default_get(['company_id', 'employee_id', 'is_employee_readonly'])
        self.assertEqual(defaults_emp.get('company_id'), other_company.id)
        self.assertEqual(defaults_emp.get('employee_id'), emp_other.id)
        self.assertTrue(defaults_emp.get('is_employee_readonly'))

        # 3. Wizard creation with employee automatically sets company_id
        wizard = self.env['hds.in.salary.revision.wizard'].create({
            'employee_id': self.employee.id,
        })
        self.assertEqual(wizard.company_id.id, self.company.id)

        # 4. Changing company_id on wizard triggers _onchange_company_id and clears employee_id if mismatch
        ui_wiz = self.env['hds.in.salary.revision.wizard'].new({
            'company_id': self.company.id,
            'employee_id': self.employee.id,
        })
        ui_wiz.company_id = other_company
        ui_wiz._onchange_company_id()
        self.assertFalse(ui_wiz.employee_id, "Employee should be cleared when switching to a different company")

        # 5. Cross-company mismatch constraint
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.env['hds.in.salary.revision.wizard'].create({
                'company_id': self.company.id,
                'employee_id': emp_other.id,
            })


# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase


class TestEmployerCost(TransactionCase):

    def setUp(self):
        super().setUp()
        self.country_in = self.env.ref('base.in')
        self.env.company.country_id = self.country_in
        self.SalaryRule = self.env['hr.salary.rule']
        self.Contract = self.env['hr.version']
        self.Employee = self.env['hr.employee']
        self.Structure = self.env['hr.payroll.structure']

        self.rule_epf_er = self.env.ref('hudson_in_payroll.hds_in_rule_epf_er')
        self.rule_edli = self.env.ref('hudson_in_payroll.hds_in_rule_edli')
        self.rule_admin = self.env.ref('hudson_in_payroll.hds_in_rule_epf_admin')

        self.employee = self.Employee.create({
            'name': 'Test Employee CTC',
        })

        self.structure = self.env.ref('hudson_payroll_base.structure_base')

        if hasattr(self.employee, 'version_id') and self.employee.version_id:
            self.contract = self.employee.version_id
            self.contract.write({
                'name': 'Test Contract CTC',
                'wage': 15000.0,
                'struct_id': self.structure.id,
            })
        else:
            self.contract = self.Contract.create({
                'name': 'Test Contract CTC',
                'employee_id': self.employee.id,
                'wage': 15000.0,
                'struct_id': self.structure.id,
            })
            self.employee.contract_id = self.contract.id

    def test_01_salary_rule_ctc_flag(self):
        """Verify salary rules have hds_in_contributes_to_employer_cost flag set correctly."""
        self.assertTrue(self.rule_epf_er.hds_in_contributes_to_employer_cost)
        self.assertTrue(self.rule_edli.hds_in_contributes_to_employer_cost)
        self.assertTrue(self.rule_admin.hds_in_contributes_to_employer_cost)

    def test_02_contract_ctc_computation(self):
        """
        Wage = 15,000.
        Employer PF (12%) = 1,800.0
        Employer EDLI (0.5%) = 75.0
        EPF Admin (0.5%) = 75.0
        Total Employer Statutory = 1,950.0
        Monthly CTC = 15,000 + 1,950 = 16,950.0
        Annual CTC = 16,950 * 12 = 203,400.0
        """
        self.contract._compute_employer_cost()
        self.assertGreater(self.contract.hds_in_employer_cost_monthly, 15000.0)
        self.assertEqual(self.contract.hds_in_employer_cost_annual, self.contract.hds_in_employer_cost_monthly * 12.0)
        self.assertEqual(self.employee.hds_in_employer_cost_annual, self.contract.hds_in_employer_cost_annual)

    def test_03_contract_template_load_employer_cost_sync(self):
        """Validates that loading a contract template populates non-zero Employer Cost figures on contract and syncs to employee."""
        tmpl = self.Contract.create({
            'name': 'Standard Software Engineer Template',
            'wage': 20000.0,
            'struct_id': self.structure.id,
        })

        new_emp = self.Employee.create({
            'name': 'New Employee CTC',
        })
        if hasattr(new_emp, 'version_id') and new_emp.version_id:
            new_contract = new_emp.version_id
            new_contract.write({
                'contract_template_id': tmpl.id,
            })
        else:
            new_contract = self.Contract.create({
                'name': 'Contract - New Employee',
                'employee_id': new_emp.id,
                'contract_template_id': tmpl.id,
            })
        new_contract._onchange_contract_template_id()

        self.assertGreater(new_contract.hds_in_employer_cost_monthly, 20000.0)
        self.assertEqual(new_emp.hds_in_employer_cost_monthly, new_contract.hds_in_employer_cost_monthly)
        self.assertEqual(new_emp.hds_in_employer_cost_annual, new_contract.hds_in_employer_cost_annual)

    def test_04_benefit_employer_cost_computation(self):
        """Verify monthly and yearly employer benefit cost calculation from benefit fields."""
        self.contract.write({
            'benefit_phone': 300.0,
            'benefit_internet': 400.0,
            'benefit_meal_vouchers': 100.0,
            'benefit_transport': 400.0,
        })
        self.assertEqual(self.contract.benefit_employer_cost_monthly, 1200.0)
        self.assertEqual(self.contract.benefit_employer_cost_yearly, 14400.0)
        if hasattr(self.employee, 'benefit_employer_cost_monthly'):
            # When employee delegates to version_id
            if hasattr(self.employee, 'version_id') and self.employee.version_id:
                self.employee.version_id.write({
                    'benefit_phone': 300.0,
                    'benefit_internet': 400.0,
                    'benefit_meal_vouchers': 100.0,
                    'benefit_transport': 400.0,
                })
            self.assertEqual(self.employee.benefit_employer_cost_monthly, 1200.0)
            self.assertEqual(self.employee.benefit_employer_cost_yearly, 14400.0)

    def test_05_medical_insurance_benefit_computation(self):
        """Verify dynamic medical insurance benefit calculation, dependent multiplier, and employer cost inclusion."""
        # 1. Base Employee Only (400 / person)
        self.contract.write({
            'benefit_phone': 300.0,
            'benefit_internet': 400.0,
            'benefit_meal_vouchers': 100.0,
            'benefit_transport': 400.0,
            'benefit_medical_insurance_per_person': 400.0,
            'benefit_insured_spouse': False,
            'benefit_insured_first_child': False,
            'benefit_insured_second_child': False,
        })
        self.assertEqual(self.contract.benefit_medical_insurance_amount, 400.0)
        self.assertEqual(self.contract.benefit_employer_cost_monthly, 1600.0)  # 1200 + 400
        self.assertEqual(self.contract.benefit_employer_cost_yearly, 19200.0)

        # 2. Add Insured Spouse (1 + 1 = 2 persons * 400 = 800)
        self.contract.write({'benefit_insured_spouse': True})
        self.assertEqual(self.contract.benefit_medical_insurance_amount, 800.0)
        self.assertEqual(self.contract.benefit_employer_cost_monthly, 2000.0)  # 1200 + 800
        self.assertEqual(self.contract.benefit_employer_cost_yearly, 24000.0)

        # 3. Add Insured First-Child (1 + 1 + 1 = 3 persons * 400 = 1200)
        self.contract.write({'benefit_insured_first_child': True})
        self.assertEqual(self.contract.benefit_medical_insurance_amount, 1200.0)
        self.assertEqual(self.contract.benefit_employer_cost_monthly, 2400.0)  # 1200 + 1200
        self.assertEqual(self.contract.benefit_employer_cost_yearly, 28800.0)

        # 4. Add Insured Second-Child (1 + 1 + 1 + 1 = 4 persons * 400 = 1600)
        self.contract.write({'benefit_insured_second_child': True})
        self.assertEqual(self.contract.benefit_medical_insurance_amount, 1600.0)
        self.assertEqual(self.contract.benefit_employer_cost_monthly, 2800.0)  # 1200 + 1600
        self.assertEqual(self.contract.benefit_employer_cost_yearly, 33600.0)

        # 5. Reset to Zero Rate
        self.contract.write({'benefit_medical_insurance_per_person': 0.0})
        self.assertEqual(self.contract.benefit_medical_insurance_amount, 0.0)
        self.assertEqual(self.contract.benefit_employer_cost_monthly, 1200.0)
        self.assertEqual(self.contract.benefit_employer_cost_yearly, 14400.0)


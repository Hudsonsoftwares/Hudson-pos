# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestContractTemplateLocalization(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Contract = self.env['hr.version']
        self.Employee = self.env['hr.employee']
        self.Company = self.env['res.company']
        self.StructureType = self.env['hr.payroll.structure.type']

        self.country_in = self.env.ref('base.in')
        self.country_ae = self.env.ref('base.ae')

        # 1. India Company Setup
        self.company_in = self.Company.create({
            'name': 'India Test Corporation Pvt Ltd',
            'country_id': self.country_in.id,
        })

        # 2. UAE Company Setup
        self.company_ae = self.Company.create({
            'name': 'UAE Desert Trading LLC',
            'country_id': self.country_ae.id,
        })

        # 3. Structure Types
        self.struct_type_in = self.StructureType.create({
            'name': 'India Monthly Staff',
            'country_id': self.country_in.id,
        })
        self.struct_type_ae = self.StructureType.create({
            'name': 'UAE Monthly Salaried',
            'country_id': self.country_ae.id,
        })

        self.structure_base = self.env.ref('hr_payroll_community.structure_base')

    def test_01_template_localization_resolution(self):
        """Verify Contract Templates (employee_id=False) resolve localization correctly."""
        # UAE Template via company
        tmpl_ae = self.Contract.create({
            'name': 'UAE Standard Template',
            'employee_id': False,
            'company_id': self.company_ae.id,
            'wage': 12000.0,
        })
        self.assertTrue(tmpl_ae.is_uae_localization)
        self.assertFalse(tmpl_ae.is_india_localization)
        self.assertEqual(tmpl_ae.country_code, 'AE')
        self.assertTrue(tmpl_ae._is_uae_localization())
        self.assertFalse(tmpl_ae._is_india_localization())

        # India Template via company
        tmpl_in = self.Contract.create({
            'name': 'India Standard Template',
            'employee_id': False,
            'company_id': self.company_in.id,
            'wage': 25000.0,
        })
        self.assertTrue(tmpl_in.is_india_localization)
        self.assertFalse(tmpl_in.is_uae_localization)
        self.assertEqual(tmpl_in.country_code, 'IN')
        self.assertTrue(tmpl_in._is_india_localization())
        self.assertFalse(tmpl_in._is_uae_localization())

        # Structure Type takes precedence / resolves country
        tmpl_override = self.Contract.create({
            'name': 'Override Template',
            'employee_id': False,
            'company_id': self.company_in.id,
            'structure_type_id': self.struct_type_ae.id,
            'wage': 15000.0,
        })
        self.assertTrue(tmpl_override.is_uae_localization)
        self.assertFalse(tmpl_override.is_india_localization)
        self.assertEqual(tmpl_override.country_code, 'AE')

    def test_02_employee_contract_version_localization_resolution(self):
        """Verify Employee Contract Versions (employee_id exists) resolve localization identically."""
        emp_ae = self.Employee.create({
            'name': 'Ahmed Al-Farsi',
            'company_id': self.company_ae.id,
        })
        contract_ae = self.Contract.create({
            'name': 'Contract - Ahmed Al-Farsi',
            'employee_id': emp_ae.id,
            'company_id': self.company_ae.id,
            'wage': 18000.0,
        })
        self.assertTrue(contract_ae.is_uae_localization)
        self.assertFalse(contract_ae.is_india_localization)
        self.assertEqual(contract_ae.country_code, 'AE')

        emp_in = self.Employee.create({
            'name': 'Sunita Sharma',
            'company_id': self.company_in.id,
        })
        contract_in = self.Contract.create({
            'name': 'Contract - Sunita Sharma',
            'employee_id': emp_in.id,
            'company_id': self.company_in.id,
            'wage': 30000.0,
        })
        self.assertTrue(contract_in.is_india_localization)
        self.assertFalse(contract_in.is_uae_localization)
        self.assertEqual(contract_in.country_code, 'IN')

    def test_03_uae_contract_template_salary_breakdown_with_airfare(self):
        """Verify UAE contract template correctly incorporates airfare_allowance into breakdown."""
        tmpl_ae = self.Contract.create({
            'name': 'UAE Executive Template',
            'employee_id': False,
            'company_id': self.company_ae.id,
            'wage': 20000.0,
            'basic_salary': 10000.0,
            'hra': 5000.0,               # Housing Allowance
            'travel_allowance': 2000.0,  # Transportation Allowance
            'other_allowance': 1000.0,   # Other Allowance
            'airfare_allowance': 1000.0, # Airfare Allowance (UAE component)
            'fixed_allowance': 1000.0,   # Fixed / Balancing Allowance
        })

        # Breakdown calculations
        self.assertEqual(tmpl_ae.breakdown_total, 20000.0)
        self.assertEqual(tmpl_ae.breakdown_diff, 0.0)
        self.assertTrue(tmpl_ae.breakdown_is_equal)
        self.assertEqual(tmpl_ae.airfare_allowance_percent, 5.0)
        self.assertEqual(tmpl_ae.basic_salary_percent, 50.0)
        self.assertEqual(tmpl_ae.hra_percent, 25.0)

    def test_04_template_to_contract_airfare_inheritance(self):
        """Verify airfare_allowance copies seamlessly from UAE Contract Template to Employee Contract."""
        tmpl_ae = self.Contract.create({
            'name': 'UAE Engineer Template',
            'employee_id': False,
            'company_id': self.company_ae.id,
            'wage': 16000.0,
            'basic_salary': 8000.0,
            'hra': 4000.0,
            'travel_allowance': 2000.0,
            'airfare_allowance': 1000.0,
            'fixed_allowance': 1000.0,
        })

        self.assertIn('airfare_allowance', self.Contract._get_whitelist_fields_from_template())

        emp_ae = self.Employee.create({
            'name': 'Farhan Qureshi',
            'company_id': self.company_ae.id,
        })
        contract = self.Contract.create({
            'name': 'Contract - Farhan Qureshi',
            'employee_id': emp_ae.id,
            'company_id': self.company_ae.id,
            'contract_template_id': tmpl_ae.id,
        })
        contract._onchange_contract_template_id()

        self.assertEqual(contract.airfare_allowance, 1000.0)
        self.assertEqual(contract.breakdown_total, 16000.0)
        self.assertTrue(contract.breakdown_is_equal)

    def test_05_uae_salary_rule_field_mapping_and_payslip_generation(self):
        """
        Verify the complete UAE flow:
        UAE Contract Template -> Employee Contract -> Salary Rules -> Payslip Lines.
        Validates:
        - Wage
        - Basic Salary (BASIC)
        - Housing Allowance (HRA)
        - Transportation Allowance (Travel)
        - Other Allowance (Other)
        - Airfare Allowance (AIRFARE_ALLOWANCE)
        - Fixed Allowance (FIXED)
        - Gross (GROSS)
        - Net (NET)
        - Zero execution of India-specific rules (DA, EPF, ESIC, PT, etc.)
        """
        struct_monthly = self.env.ref('hudson_ae_payroll.structure_ae_monthly')

        # 1. Create UAE Contract Template
        tmpl_ae = self.Contract.create({
            'name': 'UAE Complete Compensation Template',
            'employee_id': False,
            'company_id': self.company_ae.id,
            'wage': 20000.0,
            'basic_salary': 10000.0,
            'hra': 5000.0,               # Housing Allowance
            'travel_allowance': 2000.0,  # Transportation Allowance
            'other_allowance': 1000.0,   # Other Allowance
            'airfare_allowance': 1000.0, # Airfare Allowance
            'fixed_allowance': 1000.0,   # Fixed Allowance
            'struct_id': struct_monthly.id,
        })

        # 2. Employee and Contract
        emp_expat = self.Employee.create({
            'name': 'Jean Dupont',
            'company_id': self.company_ae.id,
            'country_id': self.env.ref('base.fr').id,
        })
        contract = self.Contract.create({
            'name': 'Contract - Jean Dupont',
            'employee_id': emp_expat.id,
            'company_id': self.company_ae.id,
            'contract_template_id': tmpl_ae.id,
            'date_start': '2026-01-01',
        })
        contract._onchange_contract_template_id()

        self.assertEqual(contract.wage, 20000.0)
        self.assertEqual(contract.basic_salary, 10000.0)
        self.assertEqual(contract.hra, 5000.0)
        self.assertEqual(contract.travel_allowance, 2000.0)
        self.assertEqual(contract.other_allowance, 1000.0)
        self.assertEqual(contract.airfare_allowance, 1000.0)
        self.assertEqual(contract.fixed_allowance, 1000.0)

        # 3. Create Payslip
        payslip = self.env['hr.payslip'].create({
            'name': 'Payslip - Jean Dupont - Jan 2026',
            'employee_id': emp_expat.id,
            'contract_id': contract.id,
            'company_id': self.company_ae.id,
            'struct_id': struct_monthly.id,
            'date_from': '2026-01-01',
            'date_to': '2026-01-31',
        })
        payslip.compute_sheet()

        # 4. Verify Payslip Line Generation & Field Values
        lines_by_code = {line.code: line.total for line in payslip.line_ids}

        # Check all UAE components match contract fields
        self.assertEqual(lines_by_code.get('BASIC'), 10000.0)
        self.assertEqual(lines_by_code.get('HRA'), 5000.0)
        self.assertEqual(lines_by_code.get('Travel'), 2000.0)
        self.assertEqual(lines_by_code.get('Other'), 1000.0)
        self.assertEqual(lines_by_code.get('AIRFARE_ALLOWANCE'), 1000.0)
        self.assertEqual(lines_by_code.get('FIXED'), 1000.0)

        # Gross & Net
        self.assertEqual(lines_by_code.get('GROSS'), 20000.0)
        self.assertEqual(lines_by_code.get('NET'), 20000.0)

        # 5. Verify India-specific rules do NOT exist on the UAE payslip
        india_rule_codes = ['DA', 'Meal', 'Medical', 'HDS_IN_EPF_EE', 'HDS_IN_ESIC_EE', 'HDS_IN_PT', 'HDS_IN_LWF_EE', 'HDS_IN_TDS']
        for code in india_rule_codes:
            self.assertNotIn(code, lines_by_code, f"Indian rule {code} must not appear on UAE payslip")

    def test_06_india_salary_rules_remain_unchanged(self):
        """Verify India contracts compute standard Indian salary rules without UAE interference."""
        emp_in = self.Employee.create({
            'name': 'Anand Verma',
            'company_id': self.company_in.id,
        })
        contract_in = self.Contract.create({
            'name': 'Contract - Anand Verma',
            'employee_id': emp_in.id,
            'company_id': self.company_in.id,
            'wage': 20000.0,
            'basic_salary': 10000.0,
            'hra': 4000.0,
            'da': 2000.0,
            'travel_allowance': 1000.0,
            'meal_allowance': 1000.0,
            'medical_allowance': 1000.0,
            'other_allowance': 500.0,
            'fixed_allowance': 500.0,
            'struct_id': self.structure_base.id,
            'date_start': '2026-01-01',
        })

        payslip_in = self.env['hr.payslip'].create({
            'name': 'Payslip - Anand Verma - Jan 2026',
            'employee_id': emp_in.id,
            'contract_id': contract_in.id,
            'company_id': self.company_in.id,
            'struct_id': self.structure_base.id,
            'date_from': '2026-01-01',
            'date_to': '2026-01-31',
        })
        payslip_in.compute_sheet()

        in_lines = {line.code: line.total for line in payslip_in.line_ids}
        self.assertEqual(in_lines.get('BASIC'), 10000.0)
        self.assertEqual(in_lines.get('HRA'), 4000.0)
        self.assertEqual(in_lines.get('DA'), 2000.0)
        self.assertEqual(in_lines.get('Travel'), 1000.0)
        self.assertEqual(in_lines.get('Meal'), 1000.0)
        self.assertEqual(in_lines.get('Medical'), 1000.0)
        self.assertEqual(in_lines.get('Other'), 500.0)
        self.assertEqual(in_lines.get('FIXED'), 500.0)
        self.assertEqual(in_lines.get('GROSS'), 20000.0)
        # Airfare Allowance must not exist on India payslip
        self.assertNotIn('AIRFARE_ALLOWANCE', in_lines)

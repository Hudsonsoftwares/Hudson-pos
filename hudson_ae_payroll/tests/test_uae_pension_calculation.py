# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests import common, tagged
from ..services.uae_pension_service import UAEPensionCalculationService


@tagged('post_install', '-at_install')
class TestUAEPensionCalculation(common.TransactionCase):
    """
    Test suite for Phase 1 UAE Pension/Social Insurance Calculation for UAE Nationals.
    Validates:
    - Centralized service pipeline & explicit statuses
    - UAE National eligibility vs GCC/Expat ineligibility
    - Fresh company authority enablement check
    - Multi-authority scenarios (GPSSA + ADPF under same company)
    - Shared contribution-base resolver (hds_ae_include_in_gpssa_base flag)
    - Dynamic hr.rule.parameter rate and cap resolution
    - SIEC & SICC separation and payslip execution
    """

    def setUp(self):
        super(TestUAEPensionCalculation, self).setUp()
        self.pension_service = UAEPensionCalculationService(self.env)
        self.param_model = self.env['hr.rule.parameter']

        self.Country = self.env['res.country']
        self.Company = self.env['res.company']
        self.Employee = self.env['hr.employee']
        self.Contract = self.env['hr.version'] if 'hr.version' in self.env else self.env['hr.contract']
        self.Payslip = self.env['hr.payslip']
        self.Emirate = self.env['uae.emirate']
        self.Jurisdiction = self.env['uae.payroll.jurisdiction']
        self.Authority = self.env['uae.pension.authority']
        self.Scheme = self.env['uae.pension.scheme']
        self.SalaryRule = self.env['hr.salary.rule']

        self.country_ae = self.Country.search([('code', '=', 'AE')], limit=1)
        self.country_sa = self.Country.search([('code', '=', 'SA')], limit=1)
        self.country_in = self.Country.search([('code', '=', 'IN')], limit=1)

        self.emirate_dxb = self.Emirate.search([('code', '=', 'DXB')], limit=1)
        self.emirate_auh = self.Emirate.search([('code', '=', 'AUH')], limit=1)

        self.authority_gpssa = self.Authority.search([('code', '=', 'GPSSA')], limit=1)
        self.authority_adpf = self.Authority.search([('code', '=', 'ADPF')], limit=1)

        self.scheme_new_law = self.Scheme.with_context(active_test=False).search([('code', '=', 'new_law')], limit=1)
        self.scheme_legacy = self.Scheme.with_context(active_test=False).search([('code', '=', 'legacy')], limit=1)

        # Standard Company with both authorities enabled
        self.company = self.Company.create({
            'name': 'UAE Federation Trading LLC',
            'country_id': self.country_ae.id,
            'uae_emirate_id': self.emirate_dxb.id,
            'hds_ae_enable_gpssa': True,
            'hds_ae_gpssa_employer_number': 'GPSSA-TEST-1',
            'hds_ae_enable_adpf': True,
            'hds_ae_adpf_employer_number': 'ADPF-TEST-1',
        })

    def _get_or_create_contract(self, employee, wage, basic_salary=None, struct=None):
        """Helper to get employee version contract or create one if not auto-generated."""
        contract = getattr(employee, 'version_id', False) or self.Contract.search([('employee_id', '=', employee.id)], limit=1)
        vals = {
            'wage': wage,
            'basic_salary': basic_salary if basic_salary is not None else wage,
            'company_id': employee.company_id.id,
            'pay_by_attendance': False,
        }
        if struct:
            vals['struct_id'] = struct.id
        if contract:
            contract.write(vals)
            return contract
        vals.update({
            'name': f'Contract {employee.name}',
            'employee_id': employee.id,
            'date_start': '2026-01-01',
        })
        return self.Contract.create(vals)

    def test_01_eligibility_uae_nationals_only(self):
        """Phase 1: UAE Nationals -> ELIGIBLE; GCC/Expats -> NOT_UAE_NATIONAL + 0 contrib."""
        # UAE National
        emp_uae = self.Employee.create({
            'name': 'Ahmed Al Mansoori',
            'company_id': self.company.id,
            'country_id': self.country_ae.id,
            'uae_employee_category': 'uae_national',
            'uae_emirate_id': self.emirate_dxb.id,
        })
        contract_uae = self._get_or_create_contract(emp_uae, wage=20000.0)
        res_uae = self.pension_service.calculate_pension(emp_uae, contract=contract_uae)
        self.assertEqual(res_uae['status'], 'ELIGIBLE')
        self.assertTrue(res_uae['employee_contribution'] > 0)
        self.assertTrue(res_uae['employer_contribution'] > 0)

        # GCC National (Saudi)
        emp_gcc = self.Employee.create({
            'name': 'Fahad Al Ghamdi',
            'company_id': self.company.id,
            'country_id': self.country_sa.id,
            'uae_employee_category': 'gcc_national',
            'uae_emirate_id': self.emirate_dxb.id,
        })
        contract_gcc = self._get_or_create_contract(emp_gcc, wage=20000.0)
        res_gcc = self.pension_service.calculate_pension(emp_gcc, contract=contract_gcc)
        self.assertEqual(res_gcc['status'], 'NOT_UAE_NATIONAL')
        self.assertEqual(res_gcc['employee_contribution'], 0.0)
        self.assertEqual(res_gcc['employer_contribution'], 0.0)

        # Expatriate (India)
        emp_expat = self.Employee.create({
            'name': 'Rahul Sharma',
            'company_id': self.company.id,
            'country_id': self.country_in.id,
            'uae_employee_category': 'expatriate',
            'uae_emirate_id': self.emirate_dxb.id,
        })
        contract_expat = self._get_or_create_contract(emp_expat, wage=20000.0)
        res_expat = self.pension_service.calculate_pension(emp_expat, contract=contract_expat)
        self.assertEqual(res_expat['status'], 'NOT_UAE_NATIONAL')
        self.assertEqual(res_expat['employee_contribution'], 0.0)
        self.assertEqual(res_expat['employer_contribution'], 0.0)

    def test_02_fresh_company_authority_enablement_check(self):
        """Fresh company check at calculation time: disabling authority immediately halts pension."""
        emp = self.Employee.create({
            'name': 'Mariam Al Zaabi',
            'company_id': self.company.id,
            'country_id': self.country_ae.id,
            'uae_employee_category': 'uae_national',
            'uae_emirate_id': self.emirate_dxb.id,
        })
        contract = self._get_or_create_contract(emp, wage=15000.0)

        # Initially GPSSA enabled -> ELIGIBLE
        res1 = self.pension_service.calculate_pension(emp, contract=contract)
        self.assertEqual(res1['status'], 'ELIGIBLE')
        self.assertTrue(res1['employee_contribution'] > 0)

        # Employer disables GPSSA
        self.company.write({'hds_ae_enable_gpssa': False})

        # Calculation MUST perform fresh check on company, not relying on cached employee field
        res2 = self.pension_service.calculate_pension(emp, contract=contract)
        self.assertEqual(res2['status'], 'AUTHORITY_NOT_ENABLED_AT_COMPANY')
        self.assertEqual(res2['employee_contribution'], 0.0)
        self.assertEqual(res2['employer_contribution'], 0.0)

        # Re-enable GPSSA -> immediately ELIGIBLE again
        self.company.write({'hds_ae_enable_gpssa': True})
        res3 = self.pension_service.calculate_pension(emp, contract=contract)
        self.assertEqual(res3['status'], 'ELIGIBLE')
        self.assertTrue(res3['employee_contribution'] > 0)

    def test_03_multi_authority_coexistence_gpssa_and_adpf(self):
        """A company with both GPSSA and ADPF enabled resolves each employee independently."""
        # Employee 1 in Dubai -> GPSSA
        emp_dxb = self.Employee.create({
            'name': 'Dubai Employee',
            'company_id': self.company.id,
            'country_id': self.country_ae.id,
            'uae_employee_category': 'uae_national',
            'uae_emirate_id': self.emirate_dxb.id,
            'uae_pension_scheme_id': self.scheme_new_law.id,
        })
        contract_dxb = self._get_or_create_contract(emp_dxb, wage=30000.0)

        # Employee 2 in Abu Dhabi -> ADPF (Legacy Scheme: 9% EE, 15% ER)
        emp_auh = self.Employee.create({
            'name': 'Abu Dhabi Employee',
            'company_id': self.company.id,
            'country_id': self.country_ae.id,
            'uae_employee_category': 'uae_national',
            'uae_emirate_id': self.emirate_auh.id,
            'uae_pension_scheme_id': self.scheme_legacy.id,
        })
        contract_auh = self._get_or_create_contract(emp_auh, wage=30000.0)

        res_dxb = self.pension_service.calculate_pension(emp_dxb, contract=contract_dxb)
        res_auh = self.pension_service.calculate_pension(emp_auh, contract=contract_auh)

        self.assertEqual(res_dxb['status'], 'ELIGIBLE')
        self.assertEqual(res_dxb['authority_code'], 'GPSSA')
        # GPSSA New Law: 11% EE, 12.5% ER -> 30,000 * 0.11 = 3,300; 30,000 * 0.125 = 3,750
        self.assertEqual(res_dxb['employee_contribution'], 3300.0)
        self.assertEqual(res_dxb['employer_contribution'], 3750.0)

        self.assertEqual(res_auh['status'], 'ELIGIBLE')
        self.assertEqual(res_auh['authority_code'], 'ADPF')
        # ADPF New Law: 9% EE, 15% ER -> 30,000 * 0.09 = 2,700; 30,000 * 0.15 = 4,500
        self.assertEqual(res_auh['employee_contribution'], 2700.0)
        self.assertEqual(res_auh['employer_contribution'], 4500.0)

    def test_04_shared_contribution_base_resolver(self):
        """Contribution base dynamically aggregates rules flagged with hds_ae_include_in_gpssa_base."""
        category_alw = self.env.ref('hr_payroll_community.ALW')

        # Create specific allowance rules with flag on/off
        rule_basic = self.SalaryRule.create({
            'name': 'Base Basic Salary',
            'code': 'RULE_BASE_BASIC',
            'category_id': category_alw.id,
            'sequence': 10,
            'amount_select': 'fix',
            'amount_fix': 15000.0,
            'hds_ae_include_in_gpssa_base': True,
        })
        rule_housing = self.SalaryRule.create({
            'name': 'Base Housing Allowance',
            'code': 'RULE_BASE_HRA',
            'category_id': category_alw.id,
            'sequence': 15,
            'amount_select': 'fix',
            'amount_fix': 5000.0,
            'hds_ae_include_in_gpssa_base': True,
        })
        rule_transport = self.SalaryRule.create({
            'name': 'Base Transport Ineligible',
            'code': 'RULE_BASE_TRANS',
            'category_id': category_alw.id,
            'sequence': 20,
            'amount_select': 'fix',
            'amount_fix': 3000.0,
            'hds_ae_include_in_gpssa_base': False,
        })

        emp = self.Employee.create({
            'name': 'Fatima Al Nuaimi',
            'company_id': self.company.id,
            'country_id': self.country_ae.id,
            'uae_employee_category': 'uae_national',
            'uae_emirate_id': self.emirate_dxb.id,
            'uae_pension_scheme_id': self.scheme_new_law.id,
        })

        # Simulate localdict during payslip calculation
        localdict = {
            'RULE_BASE_BASIC': 15000.0,
            'RULE_BASE_HRA': 5000.0,
            'RULE_BASE_TRANS': 3000.0,
        }

        res = self.pension_service.calculate_pension(emp, localdict=localdict)
        self.assertEqual(res['status'], 'ELIGIBLE')
        # Only flagged rules included: 15,000 + 5,000 = 20,000 (3,000 excluded)
        self.assertEqual(res['contributory_wage'], 20000.0)
        self.assertEqual(res['employee_contribution'], 2200.0)  # 20,000 * 11%

    def test_05_parameter_based_wage_capping(self):
        """Wages exceeding statutory max wage parameter are capped before contribution computation."""
        emp_gpssa = self.Employee.create({
            'name': 'High Earner GPSSA',
            'company_id': self.company.id,
            'country_id': self.country_ae.id,
            'uae_employee_category': 'uae_national',
            'uae_emirate_id': self.emirate_dxb.id,
            'uae_pension_scheme_id': self.scheme_new_law.id,
        })
        # Wage 90,000 > GPSSA New Law max wage (70,000)
        contract_high = self._get_or_create_contract(emp_gpssa, wage=90000.0)
        res_gpssa = self.pension_service.calculate_pension(emp_gpssa, contract=contract_high)
        self.assertEqual(res_gpssa['status'], 'ELIGIBLE')
        self.assertEqual(res_gpssa['contributory_wage'], 90000.0)
        self.assertEqual(res_gpssa['capped_wage'], 70000.0)
        # 70,000 * 11% = 7,700; 70,000 * 12.5% = 8,750
        self.assertEqual(res_gpssa['employee_contribution'], 7700.0)
        self.assertEqual(res_gpssa['employer_contribution'], 8750.0)

        # ADPF High Earner: Wage 90,000 > ADPF max wage (60,000) (Legacy Scheme: 9% EE, 15% ER)
        emp_adpf = self.Employee.create({
            'name': 'High Earner ADPF',
            'company_id': self.company.id,
            'country_id': self.country_ae.id,
            'uae_employee_category': 'uae_national',
            'uae_emirate_id': self.emirate_auh.id,
            'uae_pension_scheme_id': self.scheme_legacy.id,
        })
        contract_adpf = self._get_or_create_contract(emp_adpf, wage=90000.0)
        res_adpf = self.pension_service.calculate_pension(emp_adpf, contract=contract_adpf)
        self.assertEqual(res_adpf['status'], 'ELIGIBLE')
        self.assertEqual(res_adpf['contributory_wage'], 90000.0)
        self.assertEqual(res_adpf['capped_wage'], 60000.0)
        # 60,000 * 9% = 5,400; 60,000 * 15% = 9,000
        self.assertEqual(res_adpf['employee_contribution'], 5400.0)
        self.assertEqual(res_adpf['employer_contribution'], 9000.0)

    def test_06_siec_and_sicc_salary_rules_execution_in_payslip(self):
        """SIEC returns negative deduction reducing net; SICC returns positive COMP without reducing net."""
        structure = self.env.ref('hudson_ae_payroll.structure_ae_monthly')
        emp = self.Employee.create({
            'name': 'Sultan Al Qasimi',
            'company_id': self.company.id,
            'country_id': self.country_ae.id,
            'uae_employee_category': 'uae_national',
            'uae_emirate_id': self.emirate_dxb.id,
            'uae_pension_scheme_id': self.scheme_new_law.id,
        })
        contract = self._get_or_create_contract(emp, wage=25000.0, struct=structure)

        payslip = self.Payslip.create({
            'name': 'Payslip Sultan - January',
            'employee_id': emp.id,
            'contract_id': contract.id,
            'company_id': self.company.id,
            'struct_id': structure.id,
            'date_from': '2026-01-01',
            'date_to': '2026-01-31',
        })
        payslip.compute_sheet()

        line_codes = payslip.line_ids.mapped('code')
        self.assertIn('SIEC', line_codes, "SIEC salary rule must be computed on UAE national payslip.")
        self.assertIn('SICC', line_codes, "SICC salary rule must be computed on UAE national payslip.")

        siec_line = payslip.line_ids.filtered(lambda l: l.code == 'SIEC')
        sicc_line = payslip.line_ids.filtered(lambda l: l.code == 'SICC')
        basic_line = payslip.line_ids.filtered(lambda l: l.code == 'BASIC')
        net_line = payslip.line_ids.filtered(lambda l: l.code == 'NET')

        # 25,000 * 11% = 2,750 (SIEC is a deduction, so total is -2,750)
        self.assertEqual(siec_line.total, -2750.0, "SIEC must be a negative deduction of 2,750 AED.")

        # 25,000 * 12.5% = 3,125 (SICC is company contribution, so total is +3,125)
        self.assertEqual(sicc_line.total, 3125.0, "SICC must be a positive company contribution of 3,125 AED.")

        # NET salary must be reduced by SIEC (25,000 - 2,750 = 22,250), not affected by SICC
        self.assertEqual(net_line.total, 22250.0, "Net salary must equal Basic - SIEC, unaffected by SICC.")

    def test_07_explicit_statuses_edge_cases(self):
        """Verify explicit statuses: NO_PENSION_AUTHORITY, NO_ACTIVE_SCHEME, NO_CONTRIBUTION_BASE."""
        company_empty = self.Company.create({
            'name': 'Empty UAE Co',
            'country_id': self.country_ae.id,
            'uae_emirate_id': False,
        })

        # 1. NO_PENSION_AUTHORITY
        emp_no_auth = self.Employee.create({
            'name': 'No Auth Employee',
            'company_id': company_empty.id,
            'country_id': self.country_ae.id,
            'uae_employee_category': 'uae_national',
            'uae_emirate_id': False,
            'uae_jurisdiction_id': False,
        })
        res_no_auth = self.pension_service.calculate_pension(emp_no_auth)
        self.assertEqual(res_no_auth['status'], 'NO_PENSION_AUTHORITY')
        self.assertEqual(res_no_auth['employee_contribution'], 0.0)

        # 2. NO_ACTIVE_SCHEME
        # Archive all schemes temporarily to trigger status
        all_schemes = self.Scheme.search([])
        all_schemes.write({'active': False})
        try:
            emp_active = self.Employee.create({
                'name': 'Active UAE Emp',
                'company_id': self.company.id,
                'country_id': self.country_ae.id,
                'uae_employee_category': 'uae_national',
                'uae_emirate_id': self.emirate_dxb.id,
                'uae_pension_scheme_id': False,
            })
            contract = self._get_or_create_contract(emp_active, wage=10000.0)
            res_no_scheme = self.pension_service.calculate_pension(emp_active, contract=contract)
            self.assertEqual(res_no_scheme['status'], 'NO_ACTIVE_SCHEME')
            self.assertEqual(res_no_scheme['employee_contribution'], 0.0)
        finally:
            all_schemes.write({'active': True})

        # 3. NO_CONTRIBUTION_BASE (Wage <= 0)
        emp_zero = self.Employee.create({
            'name': 'Zero Wage Employee',
            'company_id': self.company.id,
            'country_id': self.country_ae.id,
            'uae_employee_category': 'uae_national',
            'uae_emirate_id': self.emirate_dxb.id,
            'uae_pension_scheme_id': self.scheme_new_law.id,
        })
        contract_zero = self._get_or_create_contract(emp_zero, wage=0.0)
        res_zero = self.pension_service.calculate_pension(emp_zero, contract=contract_zero)
        self.assertEqual(res_zero['status'], 'NO_CONTRIBUTION_BASE')
        self.assertEqual(res_zero['employee_contribution'], 0.0)
        self.assertEqual(res_zero['employer_contribution'], 0.0)

# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from ..services.tds.employee_tax_declaration_validation_service import EmployeeTaxDeclarationValidationService


class TestTdsPhase3Declarations(TransactionCase):
    """
    Automated Test Suite for Hudson Indian Payroll TDS Engine Phase 3
    (Employee Tax Profile, FY Tax Regime Locking, & Tax Declaration Framework).
    """

    def setUp(self):
        super().setUp()
        self.val_service = EmployeeTaxDeclarationValidationService(self.env)
        self.fy = self.env['tds.financial.year'].search([('code', '=', '2025-2026')], limit=1)
        if not self.fy:
            self.fy = self.env['tds.financial.year'].create({
                'name': 'FY 2025-26',
                'code': '2025-2026',
                'assessment_year': '2026-2027',
                'start_date': '2025-04-01',
                'end_date': '2026-03-31',
            })

        self.regime_new = self.env['tds.tax.regime'].search([('code', '=', 'new')], limit=1)
        self.regime_old = self.env['tds.tax.regime'].search([('code', '=', 'old')], limit=1)

        self.employee = self.env['hr.employee'].create({
            'name': 'Test TDS Employee',
            'hds_in_pan': 'ABCDE9999F',
            'hds_in_aadhaar': '123456789012',
            'hds_in_residential_status': 'ror',
        })

    def test_01_pan_and_aadhaar_validation(self):
        """Test PAN regex validation and Aadhaar format checks."""
        # Valid PAN
        self.assertEqual(self.employee.hds_in_pan, 'ABCDE9999F')

        # Invalid PAN format
        with self.assertRaises(ValidationError):
            self.env['hr.employee'].create({
                'name': 'Invalid PAN Emp',
                'hds_in_pan': 'INVALID123',
            })

        # Invalid Aadhaar format
        with self.assertRaises(ValidationError):
            self.env['hr.employee'].create({
                'name': 'Invalid Aadhaar Emp',
                'hds_in_aadhaar': '12345',
            })

    def test_02_tax_regime_selection_per_fy(self):
        """Test employee regime selection per Financial Year."""
        regime_selection = self.env['tds.employee.tax.regime'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_old.id,
        })
        self.assertEqual(regime_selection.regime_code, 'old', "Employee regime selection for FY 2025-26 must be Old Regime.")

    def test_03_tax_regime_locking_when_payslips_exist(self):
        """Test server-side tax regime locking when payslips exist for the employee in FY date bounds."""
        regime_sel = self.env['tds.employee.tax.regime'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_old.id,
        })

        # Create a processed payslip for employee in FY 2025-26
        payslip = self.env['hr.payslip'].create({
            'name': 'June 2025 Payslip',
            'employee_id': self.employee.id,
            'date_from': '2025-06-01',
            'date_to': '2025-06-30',
            'state': 'done',
        })

        # Attempting to mutate regime without override context must raise ValidationError
        with self.assertRaises(ValidationError):
            regime_sel.write({'regime_id': self.regime_new.id})

        # Administrative unlock override must succeed
        regime_sel.with_context(ignore_regime_lock=True).write({'regime_id': self.regime_new.id})
        self.assertEqual(regime_sel.regime_code, 'new', "Regime selection updated via administrative override.")

    def test_04_new_regime_declaration_rejection(self):
        """Test that unpermitted deductions under New Regime are rejected by validation service."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'declaration_line_ids': [(0, 0, {
                'category': '80c',
                'description': 'PPF Contribution',
                'declared_amount': 150000.0,
            }), (0, 0, {
                'category': '80d_self',
                'description': 'Health Insurance',
                'declared_amount': 25000.0,
            })],
        })

        # Associate employee with New Regime
        self.env['tds.employee.tax.regime'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_new.id,
        })

        res = self.val_service.validate_declaration(decl)
        self.assertFalse(res.is_compliant, "New Regime declaration containing 80C/80D must be marked non-compliant.")
        self.assertEqual(decl.total_approved_amount, 0.0, "New Regime unpermitted deductions must be approved at ₹0.")
        self.assertFalse(decl.declaration_line_ids[0].is_regime_permitted, "80C must be marked not regime permitted.")

    def test_05_old_regime_declaration_capping(self):
        """Test that Old Regime declarations are validated and capped at statutory parameter limits."""
        # Create Old Regime selection
        self.env['tds.employee.tax.regime'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_old.id,
        })

        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'declaration_line_ids': [(0, 0, {
                'category': '80c',
                'description': 'LIC + PPF Claim Exceeding Ceiling',
                'declared_amount': 200000.0,  # ₹2 Lakhs (exceeds ₹1.5L cap)
            })],
        })

        res = self.val_service.validate_declaration(decl)
        self.assertTrue(res.is_compliant, "Old Regime 80C declaration should be compliant.")
        self.assertEqual(decl.declaration_line_ids[0].approved_amount, 150000.0, "Section 80C must be capped at ₹1,50,000 ceiling.")
        self.assertEqual(decl.declaration_line_ids[0].validation_status, 'exceeds_limit', "Status must be 'exceeds_limit'.")

    def test_06_declaration_workflow_transitions(self):
        """Test multi-stage declaration approval workflow (Draft -> Submitted -> Approved)."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'declaration_line_ids': [(0, 0, {
                'category': 'leave_encashment',
                'description': 'Retirement Leave Encashment Exemption',
                'declared_amount': 1000000.0,
            })],
        })

        self.assertEqual(decl.state, 'draft')
        decl.action_submit()
        self.assertEqual(decl.state, 'submitted')

        decl.action_review()
        self.assertEqual(decl.state, 'under_review')

        decl.action_approve()
        self.assertEqual(decl.state, 'approved')
        self.assertTrue(decl.approval_date)

    def test_07_regime_neutral_income_declarations(self):
        """Test Module 2 regime-neutral income declaration computations."""
        inc_decl = self.env['tds.employee.income.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'savings_bank_interest': 12000.0,
            'fixed_deposit_interest': 25000.0,
            'dividend_income': 5000.0,
            'annual_let_out_rent': 240000.0,
            'municipal_taxes_paid': 20000.0,
            'let_out_interest_paid': 150000.0,
            'prev_employer_taxable_gross': 300000.0,
        })

        # Other sources total: 12k + 25k + 5k = 42,000
        self.assertEqual(inc_decl.total_other_sources_income, 42000.0)

        # Property NAV: 240k - 20k = 220,000. 30% Std Ded = 66,000. Net Property: 220k - 66k - 150k = 4,000.
        self.assertEqual(inc_decl.net_annual_value, 220000.0)
        self.assertEqual(inc_decl.property_standard_deduction, 66000.0)
        self.assertEqual(inc_decl.net_house_property_income_loss, 4000.0)

        # Total Net Additional Income: 42,000 (Other) + 4,000 (Property) + 300,000 (Prev Salary) = 346,000
        self.assertEqual(inc_decl.total_net_additional_income, 346000.0)

    def test_08_section_80d_senior_and_non_senior_citizen_validation(self):
        """Test Section 80D senior citizen vs non-senior citizen limit resolution for Self and Parents."""
        # 1. Non-Senior Employee (DOB 1995 -> 30 years old) claiming Self (Limit ₹25,000)
        emp_young = self.env['hr.employee'].create({
            'name': 'Young Employee (Non-Senior)',
            'birthday': '1995-05-15',
        })
        decl_young = self.env['tds.employee.declaration'].create({
            'employee_id': emp_young.id,
            'financial_year_id': self.fy.id,
            'declaration_line_ids': [
                (0, 0, {'category': '80d_self', 'description': 'Medical Self', 'declared_amount': 40000.0, 'is_senior_citizen': False}),
                (0, 0, {'category': '80d_parents', 'description': 'Senior Citizen Parents Medical', 'declared_amount': 60000.0, 'is_senior_citizen': True}),
            ],
        })

        # Register Old Regime
        self.env['tds.employee.tax.regime'].create({
            'employee_id': emp_young.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_old.id,
        })

        self.val_service.validate_declaration(decl_young)
        # Self non-senior capped at ₹25,000
        self.assertEqual(decl_young.declaration_line_ids[0].approved_amount, 25000.0)
        # Senior citizen parents capped at ₹50,000 even though employee is non-senior
        self.assertEqual(decl_young.declaration_line_ids[1].approved_amount, 50000.0)

        # 2. Senior Citizen Employee (DOB 1960 -> 65 years old) claiming Self (Limit ₹50,000)
        emp_senior = self.env['hr.employee'].create({
            'name': 'Senior Citizen Employee',
            'birthday': '1960-01-10',
        })
        decl_senior = self.env['tds.employee.declaration'].create({
            'employee_id': emp_senior.id,
            'financial_year_id': self.fy.id,
            'declaration_line_ids': [
                (0, 0, {'category': '80d_self', 'description': 'Senior Medical Self', 'declared_amount': 60000.0, 'is_senior_citizen': True}),
            ],
        })
        self.env['tds.employee.tax.regime'].create({
            'employee_id': emp_senior.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_old.id,
        })
        self.val_service.validate_declaration(decl_senior)
        # Senior employee self capped at ₹50,000
        self.assertEqual(decl_senior.declaration_line_ids[0].approved_amount, 50000.0)

    def test_09_section_80ccd1_vs_80ccd2_regime_validation(self):
        """Test Section 80CCD(1) Employee NPS vs Section 80CCD(2) Employer NPS regime compatibility."""
        emp = self.env['hr.employee'].create({'name': 'NPS Test Employee'})
        
        # 1. Under New Tax Regime
        self.env['tds.employee.tax.regime'].create({
            'employee_id': emp.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_new.id,
        })
        
        decl_new = self.env['tds.employee.declaration'].create({
            'employee_id': emp.id,
            'financial_year_id': self.fy.id,
            'declaration_line_ids': [
                (0, 0, {'category': 'nps_employee', 'description': 'Employee NPS 80CCD(1)', 'declared_amount': 50000.0}),
                (0, 0, {'category': '80ccd2', 'description': 'Employer NPS 80CCD(2)', 'declared_amount': 75000.0}),
            ],
        })

        self.val_service.validate_declaration(decl_new)
        # Employee NPS 80CCD(1) MUST BE REJECTED under New Regime
        self.assertFalse(decl_new.declaration_line_ids[0].is_regime_permitted)
        self.assertEqual(decl_new.declaration_line_ids[0].approved_amount, 0.0)
        self.assertEqual(decl_new.declaration_line_ids[0].validation_status, 'ineligible_regime')

        # Employer NPS 80CCD(2) MUST BE PERMITTED under New Regime
        self.assertTrue(decl_new.declaration_line_ids[1].is_regime_permitted)
        self.assertEqual(decl_new.declaration_line_ids[1].approved_amount, 75000.0)
        self.assertEqual(decl_new.declaration_line_ids[1].validation_status, 'valid')

    def test_10_section_80d_fy_senior_citizen_eligibility_rule(self):
        """
        Test CBDT Circular 19/2015 statutory rule:
        An employee turning 60 at ANY time during the Financial Year qualifies as Senior Citizen
        for the entire Financial Year (even when evaluated months before their birthday).
        """
        # Employee born 15-Dec-1965 (Turns 60 on 15-Dec-2025 during FY 2025-26)
        emp_turning_60 = self.env['hr.employee'].create({
            'name': 'Employee Turning 60 in Dec 2025',
            'birthday': '1965-12-15',
        })
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': emp_turning_60.id,
            'financial_year_id': self.fy.id,
            'declaration_line_ids': [
                (0, 0, {'category': '80d_self', 'description': 'Self Insurance Claim', 'declared_amount': 60000.0}),
            ],
        })
        self.env['tds.employee.tax.regime'].create({
            'employee_id': emp_turning_60.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_old.id,
        })

        # Evaluate on May 15, 2025 (Employee is currently 59 years 5 months old)
        eval_date = self.env['fields'].Date.from_string('2025-05-15')
        self.val_service.validate_declaration(decl, eval_date=eval_date)

        # Because employee turns 60 by March 31, 2026 (end of FY 2025-26), ₹50,000 Senior limit applies!
        self.assertEqual(decl.declaration_line_ids[0].approved_amount, 50000.0, "Employee turning 60 during FY 2025-26 must get ₹50,000 senior citizen limit for the entire FY.")

    def test_11_section_80dd_normal_and_severe_disability_validation(self):
        """Test Section 80DD Dependent Disability normal (₹75k) vs severe (₹1.25L) capping."""
        emp = self.env['hr.employee'].create({'name': '80DD Test Employee'})
        self.env['tds.employee.tax.regime'].create({
            'employee_id': emp.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_old.id,
        })

        decl = self.env['tds.employee.declaration'].create({
            'employee_id': emp.id,
            'financial_year_id': self.fy.id,
            'declaration_line_ids': [
                (0, 0, {'category': '80dd', 'description': 'Normal Disability Claim', 'declared_amount': 90000.0, 'is_severe_disability': False}),
                (0, 0, {'category': '80dd', 'description': 'Severe Disability Claim', 'declared_amount': 150000.0, 'is_severe_disability': True}),
                (0, 0, {'category': '80dd', 'description': 'Boundary Normal Claim', 'declared_amount': 75000.0, 'is_severe_disability': False}),
                (0, 0, {'category': '80dd', 'description': 'Boundary Severe Claim', 'declared_amount': 125000.0, 'is_severe_disability': True}),
            ],
        })

        self.val_service.validate_declaration(decl)

        # 1. Normal disability declared 90,000 capped at ₹75,000
        self.assertEqual(decl.declaration_line_ids[0].approved_amount, 75000.0)
        self.assertEqual(decl.declaration_line_ids[0].validation_status, 'exceeds_limit')

        # 2. Severe disability declared 1,50,000 capped at ₹1,25,000
        self.assertEqual(decl.declaration_line_ids[1].approved_amount, 125000.0)
        self.assertEqual(decl.declaration_line_ids[1].validation_status, 'exceeds_limit')

        # 3. Boundary normal declared 75,000 approved fully at ₹75,000
        self.assertEqual(decl.declaration_line_ids[2].approved_amount, 75000.0)
        self.assertEqual(decl.declaration_line_ids[2].validation_status, 'valid')

        # 4. Boundary severe declared 1,25,000 approved fully at ₹1,25,000
        self.assertEqual(decl.declaration_line_ids[3].approved_amount, 125000.0)
        self.assertEqual(decl.declaration_line_ids[3].validation_status, 'valid')

    def test_12_section_80tta_and_80ttb_mutual_exclusivity_and_age_rules(self):
        """Test Section 80TTA vs 80TTB age eligibility and mutual exclusivity under Old Tax Regime."""
        # 1. Non-Senior Employee (Age 30)
        emp_young = self.env['hr.employee'].create({'name': 'Young Emp 80TTA', 'birthday': '1995-05-15'})
        self.env['tds.employee.tax.regime'].create({
            'employee_id': emp_young.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_old.id,
        })
        decl_young = self.env['tds.employee.declaration'].create({
            'employee_id': emp_young.id,
            'financial_year_id': self.fy.id,
            'declaration_line_ids': [
                (0, 0, {'category': '80tta', 'description': 'Savings Interest 80TTA', 'declared_amount': 15000.0}),
                (0, 0, {'category': '80ttb', 'description': 'Senior Deposit Interest 80TTB', 'declared_amount': 30000.0}),
            ],
        })

        self.val_service.validate_declaration(decl_young)
        # 80TTA valid and capped at ₹10,000
        self.assertEqual(decl_young.declaration_line_ids[0].approved_amount, 10000.0)
        self.assertEqual(decl_young.declaration_line_ids[0].validation_status, 'exceeds_limit')
        # 80TTB strictly rejected for non-senior employee
        self.assertEqual(decl_young.declaration_line_ids[1].approved_amount, 0.0)
        self.assertEqual(decl_young.declaration_line_ids[1].validation_status, 'ineligible_regime')

        # 2. Senior Citizen Employee (Age 65)
        emp_senior = self.env['hr.employee'].create({'name': 'Senior Emp 80TTB', 'birthday': '1960-01-10'})
        self.env['tds.employee.tax.regime'].create({
            'employee_id': emp_senior.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_old.id,
        })
        decl_senior = self.env['tds.employee.declaration'].create({
            'employee_id': emp_senior.id,
            'financial_year_id': self.fy.id,
            'declaration_line_ids': [
                (0, 0, {'category': '80tta', 'description': 'Savings Interest 80TTA', 'declared_amount': 15000.0}),
                (0, 0, {'category': '80ttb', 'description': 'Senior Deposit Interest 80TTB', 'declared_amount': 60000.0}),
            ],
        })

        self.val_service.validate_declaration(decl_senior)
        # Under Section 80TTA(2), 80TTA is strictly rejected for Senior Citizen
        self.assertEqual(decl_senior.declaration_line_ids[0].approved_amount, 0.0)
        self.assertEqual(decl_senior.declaration_line_ids[0].validation_status, 'ineligible_regime')
        # 80TTB valid for Senior Citizen and capped at ₹50,000
        self.assertEqual(decl_senior.declaration_line_ids[1].approved_amount, 50000.0)
        self.assertEqual(decl_senior.declaration_line_ids[1].validation_status, 'exceeds_limit')

    def test_13_priority4_section10_exemptions_and_validation(self):
        """Test HRA calculation engine, Children Education, Hostel, and LTA validation."""
        from hudson_in_payroll.services.tds.section10_hra_exemption_service import Section10HraExemptionService
        from hudson_in_payroll.services.tds.section10_lta_exemption_service import Section10LtaExemptionService

        # 1. HRA Exemption Engine Calculation:
        # Rent: ₹1,80,000, Basic: ₹5,00,000, Actual HRA: ₹1,20,000, Metro=True
        # Component 1: Actual HRA = ₹1,20,000
        # Component 2: Rent - 10% Basic = ₹1,80,000 - ₹50,000 = ₹1,30,000
        # Component 3: 50% Basic = ₹2,50,000
        # Statutory Exemption = min(1.2L, 1.3L, 2.5L) = ₹1,20,000
        hra_svc = Section10HraExemptionService(self.env)
        res = hra_svc.calculate_exemption(annual_rent_paid=180000.0, actual_hra_received=120000.0, annual_basic_salary=500000.0, is_metro=True)
        self.assertEqual(res.exempt_amount, 120000.0)

        # 2. Children Education & Hostel Allowance Capping
        emp = self.env['hr.employee'].create({'name': 'Allowance Test Employee'})
        self.env['tds.employee.tax.regime'].create({
            'employee_id': emp.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_old.id,
        })
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': emp.id,
            'financial_year_id': self.fy.id,
            'declaration_line_ids': [
                (0, 0, {'category': 'children_edu', 'description': 'Children Education Claim', 'declared_amount': 5000.0}),
                (0, 0, {'category': 'hostel', 'description': 'Hostel Expenditure Claim', 'declared_amount': 10000.0}),
                (0, 0, {'category': 'lta', 'description': 'LTA Fare Claim', 'declared_amount': 25000.0}),
            ],
        })

        self.val_service.validate_declaration(decl)
        # Children Edu capped at ₹2,400 p.a.
        self.assertEqual(decl.declaration_line_ids[0].approved_amount, 2400.0)
        self.assertEqual(decl.declaration_line_ids[0].validation_status, 'exceeds_limit')

        # Hostel Allowance capped at ₹7,200 p.a.
        self.assertEqual(decl.declaration_line_ids[1].approved_amount, 7200.0)
        self.assertEqual(decl.declaration_line_ids[1].validation_status, 'exceeds_limit')

        # LTA approved at declared fare ₹25,000
        self.assertEqual(decl.declaration_line_ids[2].approved_amount, 25000.0)
        self.assertEqual(decl.declaration_line_ids[2].validation_status, 'valid')








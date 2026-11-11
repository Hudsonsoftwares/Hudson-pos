# -*- coding: utf-8 -*-
from datetime import date
from odoo.tests.common import TransactionCase
from odoo.addons.hudson_in_payroll.services.tds.section_80u_deduction_service import Section80UDeductionService
from odoo.addons.hudson_in_payroll.services.tds.tds_parameter_service import TdsParameterService


class TestSection80UEngine(TransactionCase):
    """
    Exhaustive Statutory & Business Rule Unit Test Suite for Section 80U
    (Deduction for Person with Disability - Employee's Own Disability).
    """

    def setUp(self):
        super().setUp()
        self.u_service = Section80UDeductionService(self.env)
        self.param_service = TdsParameterService(self.env)
        self.company = self.env.company

        # Active Financial Year 2025-2026
        self.fy = self.env['tds.financial.year'].search([('name', '=', '2025-2026')], limit=1)
        if not self.fy:
            self.fy = self.env['tds.financial.year'].create({
                'name': '2025-2026',
                'code': 'FY2025-26',
                'assessment_year': '2026-2027',
                'start_date': '2025-04-01',
                'end_date': '2026-03-31',
                'active': True,
            })

        self.regime_old = self.env['tds.tax.regime'].search([('code', '=', 'old')], limit=1)
        if not self.regime_old:
            self.regime_old = self.env['tds.tax.regime'].create({'name': 'Old Tax Regime', 'code': 'old'})

        self.regime_new = self.env['tds.tax.regime'].search([('code', '=', 'new')], limit=1)
        if not self.regime_new:
            self.regime_new = self.env['tds.tax.regime'].create({'name': 'New Tax Regime', 'code': 'new'})

        # Resident Employee (ROR)
        self.emp_resident = self.env['hr.employee'].create({
            'name': 'Section 80U Resident Test Employee',
            'company_id': self.company.id,
            'hds_in_residential_status': 'ror',
        })

        # RNOR Employee (Resident but Not Ordinarily Resident)
        self.emp_rnor = self.env['hr.employee'].create({
            'name': 'Section 80U RNOR Test Employee',
            'company_id': self.company.id,
            'hds_in_residential_status': 'rnor',
        })

        # Non-Resident Employee
        self.emp_non_resident = self.env['hr.employee'].create({
            'name': 'Section 80U Non-Resident Test Employee',
            'company_id': self.company.id,
            'hds_in_residential_status': 'nre',
        })

    def _create_declaration(self, employee, regime='old', percentage=60.0, state='draft', cert_type='permanent',
                            cert_num='CERT-80U-001', issue_date='2025-04-15', expiry_date=None, authority='Medical Board',
                            has_cert=True, approved_amt=0.0):
        target_regime = self.regime_old if regime == 'old' else self.regime_new
        emp_regime = self.env['tds.employee.tax.regime'].search([
            ('employee_id', '=', employee.id),
            ('financial_year_id', '=', self.fy.id)
        ], limit=1)
        if emp_regime:
            emp_regime.write({'regime_id': target_regime.id})
        else:
            self.env['tds.employee.tax.regime'].create({
                'employee_id': employee.id,
                'financial_year_id': self.fy.id,
                'regime_id': target_regime.id
            })

        decl = self.env['tds.employee.declaration'].create({
            'employee_id': employee.id,
            'financial_year_id': self.fy.id,
            'tax_regime_id': target_regime.id,
            'state': state,
            'decl_80u_disability_percentage': percentage,
            'decl_80u_disability_category': 'autism',
            'decl_80u_has_certificate': has_cert,
            'decl_80u_cert_type': cert_type,
            'decl_80u_cert_number': cert_num if has_cert else False,
            'decl_80u_cert_issue_date': issue_date if has_cert else False,
            'decl_80u_cert_expiry_date': expiry_date if (has_cert and cert_type == 'temporary') else False,
            'decl_80u_issuing_authority': authority if has_cert else False,
        })
        if approved_amt > 0.0 or state in ('proof_verified', 'approved'):
            self.env['tds.employee.declaration.line'].create({
                'declaration_id': decl.id,
                'category': '80u',
                'description': 'Section 80U Disability Claim Proof',
                'declared_amount': 75000.0,
                'tax_firm_approved_amount': approved_amt,
            })
        return decl

    def test_01_regime_gating(self):
        """Validates Section 80U is allowed under Old Regime and disallowed under New Regime."""
        decl_old = self._create_declaration(self.emp_resident, regime='old', percentage=60.0)
        res_old = self.u_service.validate_and_trace(decl_old, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(res_old.is_eligible)
        self.assertEqual(res_old.allowed_deduction, 75000.0)

        decl_new = self._create_declaration(self.emp_resident, regime='new', percentage=60.0)
        res_new = self.u_service.validate_and_trace(decl_new, eval_date='2025-05-31', financial_year=self.fy)
        self.assertFalse(res_new.is_eligible)
        self.assertEqual(res_new.allowed_deduction, 0.0)

    def test_02_disability_boundary_behavior(self):
        """Validates boundary percentage behaviors: 39% -> 0, 39.99% -> 0, 40% -> 75k, 60% -> 75k, 79.99% -> 75k, 80% -> 125k, 100% -> 125k."""
        # 39.00% -> Ineligible (₹0)
        d_39_int = self._create_declaration(self.emp_resident, percentage=39.00)
        res_39_int = self.u_service.validate_and_trace(d_39_int, eval_date='2025-05-31', financial_year=self.fy)
        self.assertFalse(res_39_int.is_eligible)
        self.assertEqual(res_39_int.allowed_deduction, 0.0)
        d_39_int._compute_totals()
        self.assertEqual(d_39_int.decl_80u_amount, 0.0)

        # 39.99% -> Ineligible (₹0)
        d_39 = self._create_declaration(self.emp_resident, percentage=39.99)
        res_39 = self.u_service.validate_and_trace(d_39, eval_date='2025-05-31', financial_year=self.fy)
        self.assertFalse(res_39.is_eligible)
        self.assertEqual(res_39.allowed_deduction, 0.0)
        d_39._compute_totals()
        self.assertEqual(d_39.decl_80u_amount, 0.0)

        # 40.00% -> Normal Disability (₹75,000)
        d_40 = self._create_declaration(self.emp_resident, percentage=40.00)
        res_40 = self.u_service.validate_and_trace(d_40, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(res_40.is_eligible)
        self.assertEqual(res_40.allowed_deduction, 75000.0)
        self.assertFalse(res_40.is_severe)
        d_40._compute_totals()
        self.assertEqual(d_40.decl_80u_amount, 75000.0)

        # 60.00% -> Normal Disability (₹75,000)
        d_60 = self._create_declaration(self.emp_resident, percentage=60.00)
        res_60 = self.u_service.validate_and_trace(d_60, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(res_60.is_eligible)
        self.assertEqual(res_60.allowed_deduction, 75000.0)
        self.assertFalse(res_60.is_severe)
        d_60._compute_totals()
        self.assertEqual(d_60.decl_80u_amount, 75000.0)

        # 79.99% -> Normal Disability (₹75,000)
        d_79 = self._create_declaration(self.emp_resident, percentage=79.99)
        res_79 = self.u_service.validate_and_trace(d_79, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(res_79.is_eligible)
        self.assertEqual(res_79.allowed_deduction, 75000.0)
        self.assertFalse(res_79.is_severe)
        d_79._compute_totals()
        self.assertEqual(d_79.decl_80u_amount, 75000.0)

        # 80.00% -> Severe Disability (₹1,25,000)
        d_80 = self._create_declaration(self.emp_resident, percentage=80.00)
        res_80 = self.u_service.validate_and_trace(d_80, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(res_80.is_eligible)
        self.assertEqual(res_80.allowed_deduction, 125000.0)
        self.assertTrue(res_80.is_severe)
        d_80._compute_totals()
        self.assertEqual(d_80.decl_80u_amount, 125000.0)

        # 100.00% -> Severe Disability (₹1,25,000)
        d_100 = self._create_declaration(self.emp_resident, percentage=100.00)
        res_100 = self.u_service.validate_and_trace(d_100, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(res_100.is_eligible)
        self.assertEqual(res_100.allowed_deduction, 125000.0)
        self.assertTrue(res_100.is_severe)
        d_100._compute_totals()
        self.assertEqual(d_100.decl_80u_amount, 125000.0)

    def test_03_residency_validation(self):
        """Validates Section 80U is allowed for Resident (ROR) and RNOR, and restricted for Non-Resident (NRE)."""
        # 1. ROR Resident -> Allowed
        d_res = self._create_declaration(self.emp_resident, percentage=60.0)
        res_res = self.u_service.validate_and_trace(d_res, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(res_res.is_eligible)
        self.assertEqual(res_res.allowed_deduction, 75000.0)

        # 2. RNOR + 39% -> Ineligible (₹0)
        d_rnor_39 = self._create_declaration(self.emp_rnor, percentage=39.0)
        res_rnor_39 = self.u_service.validate_and_trace(d_rnor_39, eval_date='2025-05-31', financial_year=self.fy)
        self.assertFalse(res_rnor_39.is_eligible)
        self.assertEqual(res_rnor_39.allowed_deduction, 0.0)

        # 3. RNOR + 40% -> Allowed (₹75,000)
        d_rnor_40 = self._create_declaration(self.emp_rnor, percentage=40.0)
        res_rnor_40 = self.u_service.validate_and_trace(d_rnor_40, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(res_rnor_40.is_eligible)
        self.assertEqual(res_rnor_40.allowed_deduction, 75000.0)
        self.assertFalse(res_rnor_40.is_severe)

        # 4. RNOR + 60% -> Allowed (₹75,000)
        d_rnor_60 = self._create_declaration(self.emp_rnor, percentage=60.0)
        res_rnor_60 = self.u_service.validate_and_trace(d_rnor_60, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(res_rnor_60.is_eligible)
        self.assertEqual(res_rnor_60.allowed_deduction, 75000.0)
        self.assertFalse(res_rnor_60.is_severe)

        # 5. RNOR + 79% -> Allowed (₹75,000)
        d_rnor_79 = self._create_declaration(self.emp_rnor, percentage=79.0)
        res_rnor_79 = self.u_service.validate_and_trace(d_rnor_79, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(res_rnor_79.is_eligible)
        self.assertEqual(res_rnor_79.allowed_deduction, 75000.0)
        self.assertFalse(res_rnor_79.is_severe)

        # 6. RNOR + 80% -> Severe Allowed (₹1,25,000)
        d_rnor_80 = self._create_declaration(self.emp_rnor, percentage=80.0)
        res_rnor_80 = self.u_service.validate_and_trace(d_rnor_80, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(res_rnor_80.is_eligible)
        self.assertEqual(res_rnor_80.allowed_deduction, 125000.0)
        self.assertTrue(res_rnor_80.is_severe)

        # 7. RNOR + 89% -> Severe Allowed (₹1,25,000)
        d_rnor_89 = self._create_declaration(self.emp_rnor, percentage=89.0)
        res_rnor_89 = self.u_service.validate_and_trace(d_rnor_89, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(res_rnor_89.is_eligible)
        self.assertEqual(res_rnor_89.allowed_deduction, 125000.0)
        self.assertTrue(res_rnor_89.is_severe)

        # 8. RNOR + 100% -> Severe Allowed (₹1,25,000)
        d_rnor_100 = self._create_declaration(self.emp_rnor, percentage=100.0)
        res_rnor_100 = self.u_service.validate_and_trace(d_rnor_100, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(res_rnor_100.is_eligible)
        self.assertEqual(res_rnor_100.allowed_deduction, 125000.0)
        self.assertTrue(res_rnor_100.is_severe)

        # 9. Non-Resident -> Rejected (₹0)
        d_non_res = self._create_declaration(self.emp_non_resident, percentage=60.0)
        res_non_res = self.u_service.validate_and_trace(d_non_res, eval_date='2025-05-31', financial_year=self.fy)
        self.assertFalse(res_non_res.is_eligible)
        self.assertEqual(res_non_res.allowed_deduction, 0.0)

    def test_04_medical_certificate_scenarios(self):
        """Tests mandatory medical certificate validations."""
        # 1. Missing certificate -> Rejected
        d_no_cert = self._create_declaration(self.emp_resident, has_cert=False)
        r_no_cert = self.u_service.validate_and_trace(d_no_cert, eval_date='2025-05-31', financial_year=self.fy)
        self.assertFalse(r_no_cert.is_eligible)

        # 2. Missing cert number -> Rejected
        d_no_num = self._create_declaration(self.emp_resident, cert_num=False)
        r_no_num = self.u_service.validate_and_trace(d_no_num, eval_date='2025-05-31', financial_year=self.fy)
        self.assertFalse(r_no_num.is_eligible)

        # 3. Missing issue date -> Rejected
        d_no_issue = self._create_declaration(self.emp_resident, issue_date=False)
        r_no_issue = self.u_service.validate_and_trace(d_no_issue, eval_date='2025-05-31', financial_year=self.fy)
        self.assertFalse(r_no_issue.is_eligible)

        # 4. Missing authority -> Rejected
        d_no_auth = self._create_declaration(self.emp_resident, authority=False)
        r_no_auth = self.u_service.validate_and_trace(d_no_auth, eval_date='2025-05-31', financial_year=self.fy)
        self.assertFalse(r_no_auth.is_eligible)

        # 5. Valid Permanent Cert -> Allowed
        d_perm = self._create_declaration(self.emp_resident, cert_type='permanent')
        r_perm = self.u_service.validate_and_trace(d_perm, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(r_perm.is_eligible)

        # 6. Valid Temporary Cert (expires 2026-06-30 >= FY end 2026-03-31) -> Allowed
        d_temp_valid = self._create_declaration(self.emp_resident, cert_type='temporary', expiry_date='2026-06-30')
        r_temp_valid = self.u_service.validate_and_trace(d_temp_valid, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(r_temp_valid.is_eligible)

        # 7. Expired Temporary Cert (expires 2025-12-31 < FY end 2026-03-31) -> Rejected
        d_temp_exp = self._create_declaration(self.emp_resident, cert_type='temporary', expiry_date='2025-12-31')
        r_temp_exp = self.u_service.validate_and_trace(d_temp_exp, eval_date='2025-05-31', financial_year=self.fy)
        self.assertFalse(r_temp_exp.is_eligible)

        # 8. Temporary Cert with Missing Expiry Date in Post-Proof State -> Rejected (Must require expiry date)
        d_temp_no_exp_proof = self._create_declaration(self.emp_resident, cert_type='temporary', expiry_date=None, state='approved', approved_amt=75000.0)
        r_temp_no_exp_proof = self.u_service.validate_and_trace(d_temp_no_exp_proof, eval_date='2025-05-31', financial_year=self.fy)
        self.assertFalse(r_temp_no_exp_proof.is_eligible)

    def test_05_flat_statutory_deduction_not_capped(self):
        """Validates that Section 80U is a flat statutory deduction and is NEVER capped by approved_amt."""
        # 1. Draft stage -> Full statutory entitlement (₹75,000 for 60% normal disability)
        d_draft = self._create_declaration(self.emp_resident, percentage=60.0, state='draft', approved_amt=0.0)
        r_draft = self.u_service.validate_and_trace(d_draft, eval_date='2025-05-31', financial_year=self.fy)
        self.assertEqual(r_draft.allowed_deduction, 75000.0)

        # 2. Approved stage with approved_amt = 50,000 -> Still grants full flat statutory entitlement ₹75,000
        d_appr_50 = self._create_declaration(self.emp_resident, percentage=60.0, state='approved', approved_amt=50000.0)
        r_appr_50 = self.u_service.validate_and_trace(d_appr_50, eval_date='2025-05-31', financial_year=self.fy)
        self.assertEqual(r_appr_50.allowed_deduction, 75000.0)

        # 3. Severe disability approved stage -> Full flat statutory entitlement ₹1,25,000
        d_appr_sev = self._create_declaration(self.emp_resident, percentage=85.0, state='approved', approved_amt=100000.0)
        r_appr_sev = self.u_service.validate_and_trace(d_appr_sev, eval_date='2025-05-31', financial_year=self.fy)
        self.assertEqual(r_appr_sev.allowed_deduction, 125000.0)

    def test_06_decl_80u_amount_draft_submitted_display(self):
        """Validates that decl_80u_amount stored field is computed in draft and submitted states."""
        d_draft = self._create_declaration(self.emp_resident, percentage=60.0, state='draft')
        d_draft._compute_totals()
        self.assertEqual(d_draft.decl_80u_amount, 75000.0)

        d_sub = self._create_declaration(self.emp_resident, percentage=80.0, state='submitted')
        d_sub._compute_totals()
        self.assertEqual(d_sub.decl_80u_amount, 125000.0)

    def test_07_section_80dd_behavior_unchanged(self):
        """Validates that Section 80DD behavior remains completely unchanged."""
        decl_dd = self.env['tds.employee.declaration'].create({
            'employee_id': self.emp_resident.id,
            'financial_year_id': self.fy.id,
            'tax_regime_id': self.regime_old.id,
            'state': 'draft',
            'decl_80dd_disability_exists': True,
            'decl_80dd_dependent_name': 'Dependent Relative',
            'decl_80dd_relationship': 'son',
            'decl_80dd_disability_percentage': 70.0,
            'decl_80dd_has_certificate': True,
            'decl_80dd_cert_type': 'permanent',
            'decl_80dd_cert_number': 'DD-CERT-001',
            'decl_80dd_cert_issue_date': '2025-04-01',
            'decl_80dd_issuing_authority': 'Medical Board',
        })
        decl_dd._compute_totals()
        # 80DD stored field remains 0.0 in draft state as per existing approval workflow
        self.assertEqual(decl_dd.decl_80dd_amount, 0.0)

        from odoo.addons.hudson_in_payroll.services.tds.chapter6a_deduction_service import Chapter6aDeductionService
        c6a_svc = Chapter6aDeductionService(self.env)
        res_c6a = c6a_svc.calculate_chapter_6a(declaration=decl_dd, eval_date='2025-05-31', regime_code='old')
        self.assertEqual(res_c6a.section_80dd, 75000.0)

    def test_08_annual_recalculation_stability(self):
        """Validates that Section 80U entitlement remains stable across April initial declaration and mid-year recalculations."""
        d_apr = self._create_declaration(self.emp_resident, percentage=60.0, state='draft')

        # April computation
        r_apr = self.u_service.validate_and_trace(d_apr, eval_date='2025-04-30', financial_year=self.fy)
        self.assertEqual(r_apr.allowed_deduction, 75000.0)

        # October recalculation
        r_oct = self.u_service.validate_and_trace(d_apr, eval_date='2025-10-31', financial_year=self.fy)
        self.assertEqual(r_oct.allowed_deduction, 75000.0)

        # January recalculation after proof approval
        d_apr.write({'state': 'approved'})
        line = self.env['tds.employee.declaration.line'].search([('declaration_id', '=', d_apr.id), ('category', '=', '80u')], limit=1)
        if not line:
            line = self.env['tds.employee.declaration.line'].create({
                'declaration_id': d_apr.id,
                'category': '80u',
                'description': 'Section 80U Disability Claim Proof',
                'declared_amount': 75000.0,
                'tax_firm_approved_amount': 75000.0,
            })
        else:
            line.write({'tax_firm_approved_amount': 75000.0})
        r_jan = self.u_service.validate_and_trace(d_apr, eval_date='2026-01-31', financial_year=self.fy)
        self.assertEqual(r_jan.allowed_deduction, 75000.0)

    def test_09_rpwd_21_disability_categories(self):
        """Validates that newly added RPwD statutory disability categories evaluate correctly."""
        new_cats = [
            'chronic_neurological_conditions',
            'multiple_sclerosis',
            'speech_and_language_disability',
            'thalassemia',
            'hemophilia',
            'sickle_cell_disease'
        ]
        for cat in new_cats:
            decl = self._create_declaration(self.emp_resident, percentage=85.0, state='draft')
            decl.write({'decl_80u_disability_category': cat})
            res = self.u_service.validate_and_trace(decl, eval_date='2025-06-30', financial_year=self.fy)
            self.assertTrue(res.is_eligible)
            self.assertEqual(res.allowed_deduction, 125000.0)
            self.assertTrue(res.is_severe)

    def test_10_deduction_calculation_service_no_double_count(self):
        """Validates that DeductionCalculationService counts Section 80U exactly once in total_allowable_deductions."""
        decl = self._create_declaration(self.emp_resident, percentage=60.0, state='draft')
        decl._compute_totals()

        from odoo.addons.hudson_in_payroll.services.tds.deduction_calculation_service import DeductionCalculationService
        from odoo.addons.hudson_in_payroll.services.tds.regime_routing_service import RegimeCalculationContext
        ded_svc = DeductionCalculationService(self.env)
        context = RegimeCalculationContext(regime_code='old', gross_total_income=1200000.0)
        res = ded_svc.calculate_deductions(self.emp_resident, self.fy, regime_context=context, eval_date='2025-05-31')

        self.assertEqual(res.standard_deduction, 50000.0)
        self.assertEqual(res.chapter_6a_deductions.section_80u, 75000.0)
        self.assertEqual(res.total_chapter_6a, 75000.0)
        self.assertEqual(res.other_approved_deductions, 0.0)
        self.assertEqual(res.total_allowable_deductions, 125000.0)

        # Taxable income check: Gross (1,200,000) - Total Deductions (125,000) = 1,075,000
        taxable_income = 1200000.0 - res.total_allowable_deductions
        self.assertEqual(taxable_income, 1075000.0)

    def test_11_temporary_certificate_scenarios_a_to_g(self):
        """Validates Temporary Disability Certificate timeline scenarios A through G."""
        # Scenario A: Certificate fully covers the FY (01-Jun-2023 to 31-May-2027) -> Full FY Eligible (75k)
        dA = self._create_declaration(self.emp_resident, percentage=60.0, cert_type='temporary', issue_date='2023-06-01', expiry_date='2027-05-31')
        rA = self.u_service.validate_and_trace(dA, eval_date='2025-05-31', financial_year=self.fy)
        self.assertTrue(rA.is_eligible)
        self.assertEqual(rA.allowed_deduction, 75000.0)

        # Scenario B: Certificate starts during the FY (Issued 15-Aug-2025) -> Full FY Eligible (75k)
        dB = self._create_declaration(self.emp_resident, percentage=60.0, cert_type='temporary', issue_date='2025-08-15', expiry_date='2027-05-31')
        rB = self.u_service.validate_and_trace(dB, eval_date='2025-09-30', financial_year=self.fy)
        self.assertTrue(rB.is_eligible)
        self.assertEqual(rB.allowed_deduction, 75000.0)

        # Scenario C: Expires during FY & Renewed within FY (Old expires 30-Nov-2026, Renewal 10-Dec-2026, New expiry 09-Dec-2027) -> Full FY Eligible (75k)
        fy_2026 = self.env['tds.financial.year'].search([('name', '=', 'FY 2026-27')], limit=1)
        if not fy_2026:
            fy_2026 = self.env['tds.financial.year'].create({
                'name': 'FY 2026-27',
                'code': 'FY2026-27',
                'start_date': '2026-04-01',
                'end_date': '2027-03-31',
                'active': True
            })
        dC = self.env['tds.employee.declaration'].create({
            'employee_id': self.emp_resident.id,
            'financial_year_id': fy_2026.id,
            'tax_regime_id': self.regime_old.id,
            'state': 'draft',
            'decl_80u_disability_percentage': 60.0,
            'decl_80u_disability_category': 'autism',
            'decl_80u_has_certificate': True,
            'decl_80u_cert_type': 'temporary',
            'decl_80u_cert_number': 'CERT-80U-OLD',
            'decl_80u_cert_issue_date': '2023-06-01',
            'decl_80u_cert_expiry_date': '2026-11-30',
            'decl_80u_renewal_issue_date': '2026-12-10',
            'decl_80u_renewal_expiry_date': '2027-12-09',
            'decl_80u_issuing_authority': 'Medical Board',
        })
        rC = self.u_service.validate_and_trace(dC, eval_date='2026-12-31', financial_year=fy_2026)
        self.assertTrue(rC.is_eligible)
        self.assertEqual(rC.allowed_deduction, 75000.0)

        # Scenario D: Expires during FY & Reassessment Pending -> Full FY Eligible (75k)
        dD = self._create_declaration(self.emp_resident, percentage=60.0, cert_type='temporary', issue_date='2022-06-01', expiry_date='2025-11-30')
        dD.write({'decl_80u_reassessment_pending': True})
        rD = self.u_service.validate_and_trace(dD, eval_date='2025-12-31', financial_year=self.fy)
        self.assertTrue(rD.is_eligible)
        self.assertEqual(rD.allowed_deduction, 75000.0)

        # Scenario E: Expires during FY & No Renewal/Reassessment -> Ineligible (₹0)
        dE = self._create_declaration(self.emp_resident, percentage=60.0, cert_type='temporary', issue_date='2022-06-01', expiry_date='2025-11-30')
        rE = self.u_service.validate_and_trace(dE, eval_date='2025-12-31', financial_year=self.fy)
        self.assertFalse(rE.is_eligible)
        self.assertEqual(rE.allowed_deduction, 0.0)

        # Scenario F: Expired before FY starts (Expired 31-Mar-2025) & Never Renewed -> Ineligible (₹0)
        dF = self._create_declaration(self.emp_resident, percentage=60.0, cert_type='temporary', issue_date='2021-06-01', expiry_date='2025-03-31')
        rF = self.u_service.validate_and_trace(dF, eval_date='2025-05-31', financial_year=self.fy)
        self.assertFalse(rF.is_eligible)
        self.assertEqual(rF.allowed_deduction, 0.0)

        # Scenario G: Severity changes upon renewal (45% Normal -> 85% Severe) -> Single Severe 80U Deduction (125k)
        dG = self._create_declaration(self.emp_resident, percentage=45.0, cert_type='temporary', issue_date='2022-06-01', expiry_date='2025-11-30')
        dG.write({
            'decl_80u_renewal_cert_number': 'CERT-80U-SEVERE-002',
            'decl_80u_renewal_issue_date': '2025-12-10',
            'decl_80u_renewal_expiry_date': '2028-11-30',
            'decl_80u_renewal_disability_percentage': 85.0,
        })
        rG = self.u_service.validate_and_trace(dG, eval_date='2025-12-31', financial_year=self.fy)
        self.assertTrue(rG.is_eligible)
        self.assertTrue(rG.is_severe)
        self.assertEqual(rG.allowed_deduction, 125000.0)

    def test_12_renewal_date_constrains(self):
        """Validates that New Certificate Expiry Date must be later than Renewal / Reassessment Date."""
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.env['tds.employee.declaration'].create({
                'employee_id': self.emp_resident.id,
                'financial_year_id': self.fy.id,
                'tax_regime_id': self.regime_old.id,
                'state': 'draft',
                'decl_80u_disability_percentage': 60.0,
                'decl_80u_disability_category': 'autism',
                'decl_80u_has_certificate': True,
                'decl_80u_cert_type': 'temporary',
                'decl_80u_cert_number': 'CERT-80U-INVALID',
                'decl_80u_cert_issue_date': '2023-06-01',
                'decl_80u_cert_expiry_date': '2026-11-30',
                'decl_80u_renewal_issue_date': '2026-12-10',
                'decl_80u_renewal_expiry_date': '2026-12-05',  # Invalid: Expiry earlier than Renewal Date
                'decl_80u_issuing_authority': 'Medical Board',
            })

    def test_13_scenario_c_renewed_severity_recalculation(self):
        """Validates Scenario C temporary certificate renewal recalculation: 45% (75k) before renewal -> 89% (125k) after renewal."""
        fy_2026 = self.env['tds.financial.year'].search([('name', '=', 'FY 2026-27')], limit=1)
        if not fy_2026:
            fy_2026 = self.env['tds.financial.year'].create({
                'name': 'FY 2026-27',
                'code': 'FY2026-27',
                'start_date': '2026-04-01',
                'end_date': '2027-03-31',
                'active': True
            })

        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.emp_resident.id,
            'financial_year_id': fy_2026.id,
            'tax_regime_id': self.regime_old.id,
            'state': 'draft',
            'decl_80u_disability_percentage': 45.0,
            'decl_80u_disability_category': 'autism',
            'decl_80u_has_certificate': True,
            'decl_80u_cert_type': 'temporary',
            'decl_80u_cert_number': 'CERT-OLD-45',
            'decl_80u_cert_issue_date': '2023-06-01',
            'decl_80u_cert_expiry_date': '2026-11-30',
            'decl_80u_issuing_authority': 'Medical Board',
        })

        # 1. Pre-renewal evaluation (Disability = 45% -> Normal 75k)
        res_pre = self.u_service.validate_and_trace(decl, eval_date='2026-05-31', financial_year=fy_2026)
        self.assertTrue(res_pre.is_eligible)
        self.assertFalse(res_pre.is_severe)
        self.assertEqual(res_pre.allowed_deduction, 75000.0)

        # 2. Add Renewal details (Disability = 89% -> Severe 125k)
        decl.write({
            'decl_80u_renewal_issue_date': '2026-12-10',
            'decl_80u_renewal_expiry_date': '2027-12-29',
            'decl_80u_renewal_disability_percentage': 89.0,
        })
        res_post = self.u_service.validate_and_trace(decl, eval_date='2026-12-31', financial_year=fy_2026)
        self.assertTrue(res_post.is_eligible)
        self.assertTrue(res_post.is_severe)
        self.assertEqual(res_post.allowed_deduction, 125000.0)

        # 3. Verify single-count in DeductionCalculationService (125,000, not 75k+125k=200k)
        decl._compute_totals()
        self.assertEqual(decl.decl_80u_amount, 125000.0)
        self.assertTrue(decl.decl_80u_is_severe_disability)

        from odoo.addons.hudson_in_payroll.services.tds.deduction_calculation_service import DeductionCalculationService
        from odoo.addons.hudson_in_payroll.services.tds.regime_routing_service import RegimeCalculationContext
        ded_svc = DeductionCalculationService(self.env)
        context = RegimeCalculationContext(regime_code='old', gross_total_income=1200000.0)
        ded_res = ded_svc.calculate_deductions(self.emp_resident, fy_2026, regime_context=context, eval_date='2026-12-31')

        self.assertEqual(ded_res.chapter_6a_deductions.section_80u, 125000.0)
        self.assertEqual(ded_res.total_chapter_6a, 125000.0)
        self.assertEqual(ded_res.other_approved_deductions, 0.0)
        self.assertEqual(ded_res.total_allowable_deductions, 175000.0)  # 50,000 Std + 125,000 80U
        self.assertEqual(1200000.0 - ded_res.total_allowable_deductions, 1025000.0)






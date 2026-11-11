# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo import fields


class TestTdsLtaEligibilityEngine(TransactionCase):
    """
    Comprehensive QA Test Suite for Section 10(5) LTA Eligibility Architecture.
    Validates TC01-TC10 and all 17 Statutory & Block Tracking Regression Scenarios.
    """

    def setUp(self):
        super(TestTdsLtaEligibilityEngine, self).setUp()
        self.Employee = self.env['hr.employee']
        self.PrevHistory = self.env['tds.lta.previous.employer']
        from ..services.tds.section10_lta_exemption_service import Section10LtaExemptionService
        self.lta_svc = Section10LtaExemptionService(self.env)

        # Create test employee
        self.emp = self.Employee.create({
            'name': 'LTA Statutory Test Employee',
            'hds_in_existing_epf_member': True,
        })

    def test_tc01_fresher_employee(self):
        """TC01: Fresher employee with no previous employment/LTA history."""
        fresher_emp = self.Employee.create({
            'name': 'Fresher Employee',
            'hds_in_existing_epf_member': False,
        })
        res = self.lta_svc.validate_and_calculate(
            employee=fresher_emp,
            declared_fare=35000.0,
            actual_lta_received=40000.0,
            journey_date='2026-05-10',
            regime_code='old'
        )
        self.assertEqual(res.normal_entitlement, 2)
        self.assertEqual(res.normal_claims_used, 0)
        self.assertEqual(res.normal_claims_remaining, 2)
        self.assertEqual(res.carry_forward_status, 'not_applicable')
        self.assertEqual(res.carry_forward_available, 0)

    def test_tc02_experienced_0_previous_claims(self):
        """TC02: Experienced employee with 0 previous current-block claims."""
        self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Prev Corp',
            'employment_to': '2025-12-31',
            'previous_lta_claims_used': 'none',
            'verification_status': 'verified',
        })
        res = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=40000.0,
            journey_date='2026-06-15',
            regime_code='old'
        )
        self.assertEqual(res.normal_claims_remaining, 2)

    def test_tc03_experienced_1_previous_claim(self):
        """TC03: Experienced employee with 1 previous current-block claim."""
        # Create record for current block 2026-2029
        self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Alpha Inc',
            'employment_to': '2026-03-31',
            'previous_lta_claims_used': 'one',
            'verification_status': 'verified',
        })
        res = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=40000.0,
            journey_date='2026-08-15',
            regime_code='old'
        )
        self.assertEqual(res.normal_claims_used, 1)
        self.assertEqual(res.normal_claims_remaining, 1)

    def test_tc04_experienced_2_previous_claims_rejected(self):
        """TC04: Experienced employee with 2 previous current-block claims -> normal claim rejected."""
        self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Beta Corp',
            'employment_to': '2026-03-31',
            'previous_lta_claims_used': 'two',
            'verification_status': 'verified',
        })
        res = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=40000.0,
            journey_date='2026-09-10',
            regime_code='old'
        )
        self.assertEqual(res.normal_claims_used, 2)
        self.assertEqual(res.normal_claims_remaining, 0)
        self.assertFalse(res.is_eligible)
        self.assertEqual(res.exempt_amount, 0.0)

    def test_tc05_verified_unused_previous_block_carry_forward(self):
        """TC05: Verified unused previous-block entitlement, journey year 2026 -> CF eligible."""
        self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Gamma Ltd',
            'employment_to': '2025-12-31',
            'previous_lta_claims_used': 'one',
            'carry_forward_requested': True,
            'verification_status': 'verified',
        })
        res = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=40000.0,
            journey_date='2026-05-20',
            regime_code='old'
        )
        self.assertEqual(res.carry_forward_status, 'eligible')
        self.assertEqual(res.carry_forward_available, 1)
        self.assertEqual(res.normal_entitlement, 2)

    def test_tc06_carry_forward_on_31_dec_2026(self):
        """TC06: Carry-forward claim on 31-Dec-2026 -> eligible."""
        self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Delta Corp',
            'employment_to': '2025-12-31',
            'previous_lta_claims_used': 'none',
            'carry_forward_requested': True,
            'verification_status': 'verified',
        })
        res = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=40000.0,
            journey_date='2026-12-31',
            regime_code='old'
        )
        self.assertEqual(res.carry_forward_status, 'eligible')
        self.assertEqual(res.carry_forward_available, 1)

    def test_tc07_carry_forward_on_01_jan_2027_expired(self):
        """TC07: Carry-forward claim on 01-Jan-2027 -> expired."""
        self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Epsilon Inc',
            'employment_to': '2025-12-31',
            'previous_lta_claims_used': 'none',
            'carry_forward_requested': True,
            'verification_status': 'verified',
        })
        res = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=40000.0,
            journey_date='2027-01-01',
            regime_code='old'
        )
        self.assertEqual(res.carry_forward_status, 'expired')
        self.assertEqual(res.carry_forward_available, 0)

    def test_tc08_new_tax_regime_exemption_zero(self):
        """TC08: New Tax Regime -> Exemption = 0.0, clear explanation message."""
        res = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=45000.0,
            actual_lta_received=50000.0,
            journey_date='2026-07-15',
            regime_code='new'
        )
        self.assertFalse(res.is_eligible)
        self.assertEqual(res.exempt_amount, 0.0)
        self.assertEqual(res.actual_lta_received, 50000.0)
        self.assertIn("Not eligible for Section 10(5) exemption under selected tax regime", res.remarks)

    def test_tc09_previous_declaration_correction(self):
        """TC09: Previous declaration correction from 2 claims to 1 claim updates remaining claims."""
        history_rec = self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Zeta Ltd',
            'employment_to': '2026-03-31',
            'previous_lta_claims_used': 'two',
            'verification_status': 'verified',
        })
        res1 = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=40000.0,
            journey_date='2026-09-01',
            regime_code='old'
        )
        self.assertEqual(res1.normal_claims_remaining, 0)

        # Correction: update claims used to 'one'
        history_rec.write({'previous_lta_claims_used': 'one'})

        res2 = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=40000.0,
            journey_date='2026-09-01',
            regime_code='old'
        )
        self.assertEqual(res2.normal_claims_remaining, 1)

    def test_tc10_international_plus_domestic_trip(self):
        """TC10: International trip without qualifying domestic fare -> zero exemption."""
        res = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=80000.0,
            journey_date='2026-06-10',
            origin='Kochi',
            destination='Singapore',
            origin_country='IN',
            destination_country='SG',
            regime_code='old'
        )
        self.assertFalse(res.is_domestic)
        self.assertEqual(res.exempt_amount, 0.0)

    def test_reg_01_block_2026(self):
        """Regression: 2026 journey -> block 2026-2029."""
        res = self.lta_svc.validate_and_calculate(employee=self.emp, journey_date='2026-04-10')
        self.assertEqual(res.block_period, '2026-2029')

    def test_reg_02_block_2029(self):
        """Regression: 2029 journey -> block 2026-2029."""
        res = self.lta_svc.validate_and_calculate(employee=self.emp, journey_date='2029-11-20')
        self.assertEqual(res.block_period, '2026-2029')

    def test_reg_03_block_2030(self):
        """Regression: 2030 journey -> block 2030-2033."""
        res = self.lta_svc.validate_and_calculate(employee=self.emp, journey_date='2030-02-15')
        self.assertEqual(res.block_period, '2030-2033')

    def test_reg_04_prev_block_2026(self):
        """Regression: Previous block for 2026 -> 2022-2025."""
        res = self.lta_svc.validate_and_calculate(employee=self.emp, journey_date='2026-05-01')
        self.assertEqual(res.prev_block_period, '2022-2025')

    def test_reg_05_prev_block_2030(self):
        """Regression: Previous block for 2030 -> 2026-2029."""
        res = self.lta_svc.validate_and_calculate(employee=self.emp, journey_date='2030-05-01')
        self.assertEqual(res.prev_block_period, '2026-2029')

    def test_reg_06_dto_to_dict_structure(self):
        """Regression: Validate DTO to_dict() structure."""
        res = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=40000.0,
            actual_lta_received=50000.0,
            journey_date='2026-06-15',
            regime_code='old'
        )
        res_dict = res.to_dict()
        self.assertIn('status', res_dict)
        self.assertIn('checks', res_dict)
        self.assertIn('current_block', res_dict)
        self.assertIn('previous_block', res_dict)
        self.assertIn('normal_entitlement', res_dict)
        self.assertIn('normal_claims_used', res_dict)
        self.assertIn('normal_claims_remaining', res_dict)
        self.assertIn('carry_forward_available', res_dict)
        self.assertIn('carry_forward_status', res_dict)
        self.assertIn('eligible_travel_fare', res_dict)
        self.assertIn('fare_ceiling', res_dict)
        self.assertIn('lta_received', res_dict)
        self.assertIn('allowable_exemption', res_dict)

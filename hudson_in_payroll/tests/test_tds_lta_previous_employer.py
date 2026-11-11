# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo import fields


class TestTdsLtaPreviousEmployer(TransactionCase):
    """
    Test suite for Previous Employer LTA History & Carry-Forward Verification Engine.
    Covers all 14 statutory test scenarios.
    """

    def setUp(self):
        super(TestTdsLtaPreviousEmployer, self).setUp()
        self.Employee = self.env['hr.employee']
        self.PrevHistory = self.env['tds.lta.previous.employer']
        self.LtaService = self.env['tds.tax.regime']  # Environment context for LTA Service
        from ..services.tds.section10_lta_exemption_service import Section10LtaExemptionService
        self.lta_svc = Section10LtaExemptionService(self.env)

        # Create test employee
        self.emp = self.Employee.create({
            'name': 'Test Previous LTA Employee',
        })

    def test_01_new_employee_no_previous_history(self):
        """TC01: New employee with no previous history -> Carry-forward NOT granted automatically."""
        res = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=40000.0,
            actual_lta_received=50000.0,
            journey_date='2026-05-15',
            regime_code='old'
        )
        self.assertFalse(res.carry_forward_available)
        self.assertFalse(res.carry_forward_used)

    def test_02_previous_history_unknown(self):
        """TC02: Previous history = Unknown -> carry_forward_eligible = pending."""
        rec = self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Acme Corp',
            'employment_to': '2025-12-31',
            'previous_lta_claims_used': 'unknown',
            'carry_forward_requested': True,
        })
        self.assertEqual(rec.carry_forward_eligible, 'pending')

    def test_03_previous_history_0_claims_used(self):
        """TC03: Previous history = 0 claims used ('none'), requested & verified -> eligible."""
        rec = self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Tech Corp',
            'employment_to': '2025-12-31',
            'previous_lta_claims_used': 'none',
            'carry_forward_requested': True,
        })
        rec.action_verify()
        self.assertEqual(rec.carry_forward_eligible, 'eligible')

    def test_04_previous_history_1_claim_used(self):
        """TC04: Previous history = 1 claim used ('one'), requested & verified -> eligible."""
        rec = self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Beta LLC',
            'employment_to': '2025-12-31',
            'previous_lta_claims_used': 'one',
            'carry_forward_requested': True,
        })
        rec.action_verify()
        self.assertEqual(rec.carry_forward_eligible, 'eligible')

    def test_05_previous_history_2_claims_used(self):
        """TC05: Previous history = 2 claims used ('two') -> ineligible."""
        rec = self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Gamma Inc',
            'employment_to': '2025-12-31',
            'previous_lta_claims_used': 'two',
            'carry_forward_requested': True,
        })
        rec.action_verify()
        self.assertEqual(rec.carry_forward_eligible, 'ineligible')

    def test_06_previous_history_pending_verification(self):
        """TC06: Previous history = Pending verification -> carry_forward_eligible = pending."""
        rec = self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Delta Systems',
            'employment_to': '2025-12-31',
            'previous_lta_claims_used': 'none',
            'carry_forward_requested': True,
            'verification_status': 'pending'
        })
        self.assertEqual(rec.carry_forward_eligible, 'pending')

    def test_07_previous_history_verified(self):
        """TC07: Previous history = Verified -> grants carry forward when eligible."""
        rec = self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Epsilon Ltd',
            'employment_to': '2025-12-31',
            'previous_lta_claims_used': 'one',
            'carry_forward_requested': True,
        })
        rec.action_verify()
        res = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=40000.0,
            actual_lta_received=50000.0,
            journey_date='2026-05-15',
            regime_code='old'
        )
        self.assertTrue(res.carry_forward_available)

    def test_08_previous_history_rejected(self):
        """TC08: Previous history = Rejected -> carry_forward_eligible = ineligible."""
        rec = self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Zeta Ltd',
            'employment_to': '2025-12-31',
            'previous_lta_claims_used': 'none',
            'carry_forward_requested': True,
        })
        rec.action_reject()
        self.assertEqual(rec.carry_forward_eligible, 'ineligible')

    def test_09_2026_current_block(self):
        """TC09: 2026 journey -> current block = 2026-2029."""
        res = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            journey_date='2026-04-10',
            regime_code='old'
        )
        self.assertEqual(res.block_period, '2026-2029')

    def test_10_previous_block_for_2026(self):
        """TC10: Previous block for 2026 journey -> 2022-2025."""
        from ..services.tds.tds_parameter_service import TdsParameterService
        param_svc = TdsParameterService(self.env)
        prev_block = param_svc.get_lta_prev_block_period(eval_date='2026-04-10')
        self.assertEqual(prev_block, '2022-2025')

    def test_11_2030_current_block(self):
        """TC11: 2030 journey -> current block = 2030-2033."""
        res = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            journey_date='2030-01-15',
            regime_code='old'
        )
        self.assertEqual(res.block_period, '2030-2033')

    def test_12_previous_block_for_2030(self):
        """TC12: Previous block for 2030 journey -> 2026-2029."""
        from ..services.tds.tds_parameter_service import TdsParameterService
        param_svc = TdsParameterService(self.env)
        prev_block = param_svc.get_lta_prev_block_period(eval_date='2030-01-15')
        self.assertEqual(prev_block, '2026-2029')

    def test_13_carry_forward_only_first_year(self):
        """TC13: Carry-forward is ONLY considered in Year 1 of block (2026 vs 2027)."""
        rec = self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Omega Corp',
            'employment_to': '2025-12-31',
            'previous_lta_claims_used': 'none',
            'carry_forward_requested': True,
        })
        rec.action_verify()

        # Year 1 (2026) -> Carry forward available
        res_2026 = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=40000.0,
            journey_date='2026-06-15',
            regime_code='old'
        )
        self.assertTrue(res_2026.carry_forward_available)

        # Year 2 (2027) -> Carry forward expired / unavailable
        res_2027 = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=40000.0,
            journey_date='2027-06-15',
            regime_code='old'
        )
        self.assertFalse(res_2027.carry_forward_available)

    def test_14_carry_forward_does_not_consume_normal_claims(self):
        """TC14: Carry-forward claim in Year 1 permits up to 3 total claims without consuming 2 normal claims."""
        rec = self.PrevHistory.create({
            'employee_id': self.emp.id,
            'previous_employer_name': 'Alpha Inc',
            'employment_to': '2025-12-31',
            'previous_lta_claims_used': 'none',
            'carry_forward_requested': True,
        })
        rec.action_verify()

        # Calculation with 2 existing claims in current block + 1 carry-forward claim available = 3 permitted claims
        res = self.lta_svc.validate_and_calculate(
            employee=self.emp,
            declared_fare=40000.0,
            actual_lta_received=50000.0,
            claims_in_block=2,
            journey_date='2026-06-15',
            regime_code='old'
        )
        self.assertTrue(res.is_eligible)
        self.assertTrue(res.carry_forward_used)
        self.assertEqual(res.exempt_amount, 40000.0)

# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo import fields


class TestTdsLtaUiEligibility(TransactionCase):
    """
    Comprehensive 20-point Test Suite for Section 10(5) LTA UI Eligibility Check & Rule 2B Engine.
    """

    def setUp(self):
        super(TestTdsLtaUiEligibility, self).setUp()
        self.Employee = self.env['hr.employee']
        self.Declaration = self.env['tds.employee.declaration']
        self.FinancialYear = self.env['tds.financial.year']
        self.LtaService = self.env['hudson.in.payroll.section10.lta.exemption.service']
        self.ParamService = self.env['hudson.in.payroll.tds.parameter.service']

        # 1. Setup Employee
        self.emp = self.Employee.create({
            'name': 'Emma Granger (LTA Test)',
            'work_email': 'emma.lta.test@hudson.com',
            'hds_in_pan_number': 'ABCDE1234F',
            'hds_in_residence_status': 'resident',
        })

        # 2. Setup Financial Year 2025-2026
        self.fy = self.FinancialYear.search([('code', '=', 'FY2025-26')], limit=1)
        if not self.fy:
            self.fy = self.FinancialYear.create({
                'name': 'Financial Year 2025-2026',
                'code': 'FY2025-26',
                'start_date': '2025-04-01',
                'end_date': '2026-03-31',
                'assessment_year': 'AY 2026-27',
                'active': True,
            })

    def _create_lta_declaration(self, **kwargs):
        defaults = {
            'employee_id': self.emp.id,
            'financial_year_id': self.fy.id,
            'regime_code': 'old',
            'state': 'draft',
            'decl_lta_declared_fare': 40000.0,
            'decl_lta_journey_date': '2025-06-15',
            'decl_lta_travel_mode': 'air',
            'decl_lta_origin': 'Mumbai',
            'decl_lta_destination': 'Delhi',
            'decl_lta_origin_country': 'IN',
            'decl_lta_destination_country': 'IN',
            'decl_lta_family_members_count': 2,
            'decl_lta_amount_received': 50000.0,
        }
        defaults.update(kwargs)
        return self.Declaration.create(defaults)

    def test_01_valid_domestic_lta_claim_eligible(self):
        """TC01: Valid domestic LTA claim -> ELIGIBLE."""
        decl = self._create_lta_declaration()
        decl._compute_lta_statutory_fields()
        self.assertEqual(decl.lta_eligibility_status, 'eligible')
        self.assertTrue(decl.decl_lta_amount > 0.0)

    def test_02_missing_journey_date_ineligible_final(self):
        """TC02: Missing journey date in post-proof -> NOT ELIGIBLE."""
        decl = self._create_lta_declaration(decl_lta_journey_date=False, state='proof_verified')
        decl._compute_lta_statutory_fields()
        self.assertEqual(decl.lta_eligibility_status, 'ineligible')
        self.assertEqual(decl.decl_lta_amount, 0.0)
        self.assertIn("journey date", decl.lta_ineligibility_reason.lower())

    def test_03_foreign_destination_ineligible(self):
        """TC03: Foreign destination -> NOT ELIGIBLE."""
        decl = self._create_lta_declaration(decl_lta_destination_country='US')
        decl._compute_lta_statutory_fields()
        self.assertEqual(decl.lta_eligibility_status, 'ineligible')
        self.assertEqual(decl.decl_lta_amount, 0.0)
        self.assertIn("domestic travel", decl.lta_ineligibility_reason.lower())

    def test_04_first_claim_in_4year_block_eligible(self):
        """TC04: First claim in 4-year block -> ELIGIBLE."""
        decl = self._create_lta_declaration()
        decl._compute_lta_statutory_fields()
        self.assertEqual(decl.lta_eligibility_status, 'eligible')
        self.assertIn("Claim 1", decl.lta_claim_sequence)

    def test_05_second_claim_in_block_eligible(self):
        """TC05: Second claim in block -> ELIGIBLE."""
        prior_decl = self._create_lta_declaration(state='approved', decl_lta_journey_date='2023-05-10')
        decl = self._create_lta_declaration(decl_lta_journey_date='2025-06-15')
        decl._compute_lta_statutory_fields()
        self.assertEqual(decl.lta_eligibility_status, 'eligible')

    def test_06_third_claim_in_same_block_ineligible(self):
        """TC06: Third claim in same block -> NOT ELIGIBLE."""
        decl1 = self._create_lta_declaration(state='approved', decl_lta_journey_date='2022-05-10')
        decl2 = self._create_lta_declaration(state='approved', decl_lta_journey_date='2023-06-10')
        decl3 = self._create_lta_declaration(decl_lta_journey_date='2024-07-10')
        decl3._compute_lta_statutory_fields()
        self.assertEqual(decl3.lta_eligibility_status, 'ineligible')
        self.assertEqual(decl3.decl_lta_amount, 0.0)

    def test_07_carry_forward_claim(self):
        """TC07: Carry-forward claim evaluation."""
        decl = self._create_lta_declaration(decl_lta_journey_date='2022-05-10')
        decl._compute_lta_statutory_fields()
        self.assertTrue(hasattr(decl, 'lta_carry_forward_used'))

    def test_08_air_travel_correct_ceiling(self):
        """TC08: Air travel economy ceiling check."""
        decl = self._create_lta_declaration(decl_lta_travel_mode='air', decl_lta_declared_fare=60000.0)
        decl._compute_lta_statutory_fields()
        self.assertEqual(decl.lta_statutory_fare_ceiling, 50000.0)
        self.assertEqual(decl.decl_lta_amount, 50000.0)

    def test_09_rail_travel_correct_ceiling(self):
        """TC09: Rail travel AC1 ceiling check."""
        decl = self._create_lta_declaration(decl_lta_travel_mode='rail', decl_lta_declared_fare=20000.0)
        decl._compute_lta_statutory_fields()
        self.assertEqual(decl.lta_statutory_fare_ceiling, 15000.0)
        self.assertEqual(decl.decl_lta_amount, 15000.0)

    def test_10_public_transport_correct_ceiling(self):
        """TC10: Public transport ceiling check."""
        decl = self._create_lta_declaration(decl_lta_travel_mode='public_transport', decl_lta_declared_fare=15000.0)
        decl._compute_lta_statutory_fields()
        self.assertEqual(decl.lta_statutory_fare_ceiling, 10000.0)
        self.assertEqual(decl.decl_lta_amount, 10000.0)

    def test_11_actual_fare_below_ceiling_controls(self):
        """TC11: Actual fare below ceiling -> actual fare controls."""
        decl = self._create_lta_declaration(decl_lta_travel_mode='air', decl_lta_declared_fare=35000.0)
        decl._compute_lta_statutory_fields()
        self.assertEqual(decl.decl_lta_amount, 35000.0)

    def test_12_actual_fare_above_ceiling_controls(self):
        """TC12: Actual fare above ceiling -> statutory ceiling controls."""
        decl = self._create_lta_declaration(decl_lta_travel_mode='air', decl_lta_declared_fare=75000.0)
        decl._compute_lta_statutory_fields()
        self.assertEqual(decl.decl_lta_amount, 50000.0)

    def test_13_lta_received_below_eligible_fare_controls(self):
        """TC13: LTA received below eligible fare -> received amount controls."""
        decl = self._create_lta_declaration(decl_lta_declared_fare=40000.0, decl_lta_amount_received=25000.0)
        decl._compute_lta_statutory_fields()
        self.assertEqual(decl.decl_lta_amount, 25000.0)

    def test_14_child_count_restriction(self):
        """TC14: Child count restriction (>2 children born after Oct 1998)."""
        decl = self._create_lta_declaration(
            decl_lta_has_children=True,
            decl_lta_children_count=3,
            decl_lta_children_born_after_oct1998=3,
            decl_lta_has_multiple_births=False
        )
        decl._compute_lta_statutory_fields()
        self.assertFalse(decl.lta_pass_child_limit)

    def test_15_multiple_births_exception(self):
        """TC15: Multiple-birth exception permits exemption."""
        decl = self._create_lta_declaration(
            decl_lta_has_children=True,
            decl_lta_children_count=3,
            decl_lta_children_born_after_oct1998=3,
            decl_lta_has_multiple_births=True
        )
        decl._compute_lta_statutory_fields()
        self.assertTrue(decl.lta_pass_child_limit)

    def test_16_new_regime_prohibited(self):
        """TC16: New Regime -> PROHIBITED / INELIGIBLE."""
        decl = self._create_lta_declaration(regime_code='new')
        decl._compute_lta_statutory_fields()
        self.assertEqual(decl.lta_eligibility_status, 'ineligible')
        self.assertEqual(decl.decl_lta_amount, 0.0)
        self.assertIn("prohibited under new tax regime", decl.lta_ineligibility_reason.lower())

    def test_17_pre_proof_projected_calculation_phase(self):
        """TC17: Draft declaration -> PRE-PROOF / PROJECTED phase."""
        decl = self._create_lta_declaration(state='draft')
        decl._compute_lta_statutory_fields()
        self.assertEqual(decl.lta_calculation_phase, 'pre_proof')

    def test_18_post_proof_verified_calculation_phase(self):
        """TC18: Verified declaration -> POST-PROOF / VERIFIED phase."""
        decl = self._create_lta_declaration(state='proof_verified')
        decl._compute_lta_statutory_fields()
        self.assertEqual(decl.lta_calculation_phase, 'post_proof')

    def test_19_missing_lta_parameter_resolution(self):
        """TC19: Parameter Service resolves configured parameter HDS_IN_TDS_LTA_AIR_FARE_CEILING."""
        val = self.ParamService.get_parameter('LTA_AIR_FARE_CEILING', eval_date=fields.Date.today())
        self.assertTrue(val >= 0.0)

    def test_20_emma_granger_current_case_verification(self):
        """TC20: Emma Granger current case ₹40,000 LTA -> verify exact eligibility path & final amount."""
        decl = self._create_lta_declaration(
            employee_id=self.emp.id,
            decl_lta_declared_fare=40000.0,
            decl_lta_amount_received=50000.0,
            decl_lta_travel_mode='air',
            regime_code='old',
            state='draft'
        )
        decl._compute_lta_statutory_fields()
        self.assertEqual(decl.lta_eligibility_status, 'eligible')
        self.assertEqual(decl.decl_lta_amount, 40000.0)
        self.assertEqual(decl.lta_calculation_phase, 'pre_proof')
        self.assertTrue(decl.lta_pass_regime)
        self.assertTrue(decl.lta_pass_domestic)

    def test_21_dynamic_journey_year_block_derivation(self):
        """TC21: Dynamic journey-year block derivation (CY 2025 -> 2022-2025, CY 2026 -> 2026-2029)."""
        decl_2025 = self._create_lta_declaration(decl_lta_journey_date='2025-06-15')
        decl_2025._compute_lta_statutory_fields()
        self.assertEqual(decl_2025.lta_block_period, '2022-2025')

        decl_2026 = self._create_lta_declaration(decl_lta_journey_date='2026-05-15')
        decl_2026._compute_lta_statutory_fields()
        self.assertEqual(decl_2026.lta_block_period, '2026-2029')

        decl_no_date = self._create_lta_declaration(decl_lta_journey_date=False)
        decl_no_date._compute_lta_statutory_fields()
        self.assertEqual(decl_no_date.lta_block_period, 'PENDING_JOURNEY_DATE')

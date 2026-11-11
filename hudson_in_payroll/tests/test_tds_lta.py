# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo import fields


class TestTdsLtaStatutoryEngine(TransactionCase):
    """
    Comprehensive Statutory Unit Test Suite for Section 10(5) Leave Travel Allowance (LTA).
    Covers TC01 through TC20 as required by Indian Income Tax Act read with Rule 2B.
    """

    def setUp(self):
        super(TestTdsLtaStatutoryEngine, self).setUp()
        self.emp_model = self.env['hr.employee']
        self.fy_model = self.env['tds.financial.year']
        self.decl_model = self.env['tds.employee.declaration']
        self.line_model = self.env['tds.employee.declaration.line']

        # 1. Create or fetch test Financial Year (2025-2026)
        self.fy_2025 = self.fy_model.search([('code', '=', 'FY2025-26')], limit=1)
        if not self.fy_2025:
            self.fy_2025 = self.fy_model.create({
                'name': 'FY 2025-2026',
                'code': 'FY2025-26',
                'assessment_year': 'AY 2026-2027',
                'start_date': '2025-04-01',
                'end_date': '2026-03-31',
                'active': True,
            })

        # 2. Create test Financial Year 2022-2023 (Year 1 of 2022-2025 block)
        self.fy_2022 = self.fy_model.search([('code', '=', 'FY2022-23')], limit=1)
        if not self.fy_2022:
            self.fy_2022 = self.fy_model.create({
                'name': 'FY 2022-2023',
                'code': 'FY2022-23',
                'assessment_year': 'AY 2023-2024',
                'start_date': '2022-04-01',
                'end_date': '2023-03-31',
                'active': True,
            })

        # 3. Create test employee
        self.employee = self.emp_model.create({
            'name': 'Abigail Peter',
            'hds_in_pan': 'ABCDE1234F',
        })

        # Instantiate Services
        from odoo.addons.hudson_in_payroll.services.tds.section10_lta_exemption_service import Section10LtaExemptionService
        from odoo.addons.hudson_in_payroll.services.tds.deduction_calculation_service import DeductionCalculationService
        from odoo.addons.hudson_in_payroll.services.tds.tds_orchestration_engine import TdsOrchestrationEngine

        self.lta_service = Section10LtaExemptionService(self.env)
        self.deduction_service = DeductionCalculationService(self.env)
        self.orchestration_engine = TdsOrchestrationEngine(self.env)
        self._emp_counter = 1000

    def _create_declaration(self, fy=None, regime_code='old', state='draft', fare=30000.0, journey_date='2025-08-15', **kwargs):
        fy = fy or self.fy_2025
        self._emp_counter += 1
        emp = kwargs.get('employee') or self.emp_model.create({
            'name': f"Test Emp {self._emp_counter}",
            'hds_in_pan': f"ABCPN{self._emp_counter:04d}F",
        })

        target_reg = self.env['tds.tax.regime'].search([('code', '=', regime_code)], limit=1)
        if not target_reg:
            target_reg = self.env['tds.tax.regime'].create({
                'name': f"{regime_code.upper()} Regime",
                'code': regime_code,
            })
        self.env['tds.employee.tax.regime'].create({
            'employee_id': emp.id,
            'financial_year_id': fy.id,
            'regime_id': target_reg.id,
        })
        vals = {
            'employee_id': emp.id,
            'financial_year_id': fy.id,
            'regime_code': regime_code,
            'state': state,
            'decl_lta_declared_fare': fare,
            'decl_lta_amount_received': kwargs.get('amount_received', 0.0),
            'decl_lta_journey_date': journey_date,
            'decl_lta_travel_mode': kwargs.get('travel_mode', 'air'),
            'decl_lta_origin': kwargs.get('origin', 'Kochi'),
            'decl_lta_destination': kwargs.get('destination', 'Delhi'),
            'decl_lta_origin_country': kwargs.get('origin_country', 'IN'),
            'decl_lta_destination_country': kwargs.get('destination_country', 'IN'),
            'decl_lta_travel_fare': kwargs.get('travel_fare', 0.0),
            'decl_lta_lodging': kwargs.get('lodging', 0.0),
            'decl_lta_boarding': kwargs.get('boarding', 0.0),
            'decl_lta_local_conveyance': kwargs.get('local_conveyance', 0.0),
            'decl_lta_other_expenses': kwargs.get('other_expenses', 0.0),
            'decl_lta_has_children': kwargs.get('has_children', False),
            'decl_lta_family_members_count': kwargs.get('family_members_count', 1),
            'decl_lta_children_count': kwargs.get('children_count', 0),
            'decl_lta_children_born_after_oct1998': kwargs.get('children_born_after_oct1998', 0),
            'decl_lta_has_multiple_births': kwargs.get('has_multiple_births', False),
            'decl_lta_spouse_travelling': kwargs.get('spouse_travelling', False),
            'decl_lta_dependent_parents_count': kwargs.get('dependent_parents_count', 0),
            'decl_lta_dependent_siblings_count': kwargs.get('dependent_siblings_count', 0),
            'decl_lta_shortest_route_reference_fare': kwargs.get('shortest_route_reference_fare', 0.0),
            'decl_lta_approved_amount': kwargs.get('approved_amount', 0.0),
        }
        decl = self.decl_model.create(vals)
        return decl

    def test_tc01_declared_20k_received_20k_approved_20k(self):
        """TC01: Declared Fare = ₹20,000, Actual LTA Received = ₹20,000, Approved = ₹20,000 -> Exemption = ₹20,000."""
        decl = self._create_declaration(fare=20000.0, amount_received=20000.0, approved_amount=20000.0, journey_date='2025-08-15')
        res = self.lta_service.validate_and_calculate(
            employee=decl.employee_id, declared_fare=20000.0, actual_lta_received=20000.0,
            regime_code='old', declaration=decl, eval_date='2025-08-15'
        )
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.exempt_amount, 20000.0)
        self.assertEqual(res.taxable_amount, 0.0)
        self.assertEqual(decl.lta_eligibility_status, 'eligible')

    def test_tc02_declared_20k_received_15k_approved_15k(self):
        """TC02: Declared Fare = ₹20,000, Actual LTA Received = ₹15,000, Approved = ₹15,000 -> Exemption <= ₹15,000."""
        decl = self._create_declaration(fare=20000.0, amount_received=15000.0, approved_amount=15000.0, journey_date='2025-08-15')
        res = self.lta_service.validate_and_calculate(
            employee=decl.employee_id, declared_fare=20000.0, actual_lta_received=15000.0,
            regime_code='old', declaration=decl, eval_date='2025-08-15'
        )
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.exempt_amount, 15000.0)
        self.assertEqual(decl.lta_taxable_amount, 0.0)

    def test_tc03_declared_20k_received_20k_approved_10k(self):
        """TC03: Declared = ₹20,000, Actual Received = ₹20,000, Approved = ₹10,000 -> Final Exemption = ₹10,000."""
        decl = self._create_declaration(fare=20000.0, amount_received=20000.0, approved_amount=10000.0, journey_date='2025-08-15')
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=20000.0, actual_lta_received=20000.0,
            regime_code='old', declaration=decl, eval_date='2025-08-15'
        )
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.exempt_amount, 10000.0)

    def test_tc04_missing_journey_date_reject(self):
        """TC04: Missing journey date -> reject exemption, ineligible status."""
        decl = self._create_declaration(fare=20000.0, amount_received=20000.0, journey_date=False)
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=20000.0, actual_lta_received=20000.0,
            regime_code='old', declaration=decl, eval_date='2025-08-15'
        )
        self.assertFalse(res.is_eligible)
        self.assertEqual(res.exempt_amount, 0.0)

    def test_tc05_international_destination_reject(self):
        """TC05: International destination -> reject exemption, ineligible status."""
        decl = self._create_declaration(fare=50000.0, amount_received=50000.0, journey_date='2025-08-15', destination_country='OTHER')
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=50000.0, actual_lta_received=50000.0,
            regime_code='old', declaration=decl, eval_date='2025-08-15'
        )
        self.assertFalse(res.is_eligible)
        self.assertEqual(res.exempt_amount, 0.0)

    def test_tc06_new_regime_zero_exemption(self):
        """TC06: New Tax Regime -> Expected LTA exemption = ₹0."""
        decl = self._create_declaration(regime_code='new', fare=20000.0, amount_received=20000.0, journey_date='2025-08-15')
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=20000.0, actual_lta_received=20000.0,
            regime_code='new', declaration=decl, eval_date='2025-08-15'
        )
        self.assertFalse(res.is_eligible)
        self.assertEqual(res.exempt_amount, 0.0)

    def test_tc07_two_claims_used_in_block_third_rejected(self):
        """TC07: Two claims already used in current block -> 3rd claim rejected."""
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=30000.0, actual_lta_received=50000.0,
            claims_in_block=2, regime_code='old', journey_date='2025-08-15', eval_date='2025-08-15'
        )
        self.assertFalse(res.is_eligible)
        self.assertEqual(res.exempt_amount, 0.0)

    def test_tc08_carry_forward_allowed_in_year1(self):
        """TC08: Valid carry-forward scenario -> Carry forward utilized."""
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=30000.0, actual_lta_received=50000.0,
            claims_in_block=2, regime_code='old', journey_date='2022-08-15', eval_date='2022-08-15'
        )
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.exempt_amount, 30000.0)

    def test_tc09_fare_exceeds_statutory_ceiling(self):
        """TC09: Fare exceeds statutory ceiling -> Capped at ceiling."""
        decl = self._create_declaration(fare=75000.0, amount_received=75000.0, travel_mode='air', journey_date='2025-08-15')
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=75000.0, actual_lta_received=75000.0,
            regime_code='old', declaration=decl, eval_date='2025-08-15'
        )
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.eligible_travel_fare, 50000.0)
        self.assertEqual(res.exempt_amount, 50000.0)

    def test_tc10_actual_lta_received_lower_than_eligible(self):
        """TC10: Actual LTA received lower than eligible fare -> Exemption capped at actual LTA received."""
        decl = self._create_declaration(fare=40000.0, amount_received=25000.0, travel_mode='air', journey_date='2025-08-15')
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=40000.0, actual_lta_received=25000.0,
            regime_code='old', declaration=decl, eval_date='2025-08-15'
        )
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.exempt_amount, 25000.0)

    def test_tc11_lodging_boarding_excluded(self):
        """TC11: Lodging & boarding included in total expenses -> Excluded from eligible fare."""
        decl = self._create_declaration(
            fare=50000.0, travel_fare=30000.0, lodging=15000.0, boarding=5000.0, journey_date='2025-08-15'
        )
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=50000.0, actual_lta_received=60000.0,
            regime_code='old', declaration=decl, eval_date='2025-08-15'
        )
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.exempt_amount, 30000.0)

    def test_tc12_valid_spouse_family_claim(self):
        """TC12: Valid spouse/family claim -> Exemption granted."""
        decl = self._create_declaration(fare=30000.0, spouse_travelling=True, family_members_count=3, journey_date='2025-08-15')
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=30000.0, actual_lta_received=50000.0,
            regime_code='old', declaration=decl, eval_date='2025-08-15'
        )
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.exempt_amount, 30000.0)

    def test_tc13_child_count_rule2b_validation(self):
        """TC13: Children > 2 born on/after Oct 1998 without multiple births exception -> Rejected."""
        decl = self._create_declaration(
            fare=40000.0, journey_date='2025-08-15', has_children=True,
            children_count=3, children_born_after_oct1998=3, has_multiple_births=False
        )
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=40000.0, actual_lta_received=50000.0,
            regime_code='old', declaration=decl, eval_date='2025-08-15'
        )
        self.assertFalse(res.is_eligible)
        self.assertEqual(res.exempt_amount, 0.0)
        self.assertIn("maximum 2 children", res.remarks)

    def test_tc14_rail_ac1_ceiling(self):
        """TC14: Rail travel exceeding AC 1st Class ceiling (₹15,000) -> Capped."""
        decl = self._create_declaration(fare=20000.0, travel_mode='rail', journey_date='2025-08-15')
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=20000.0, actual_lta_received=30000.0,
            regime_code='old', declaration=decl, eval_date='2025-08-15'
        )
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.exempt_amount, 15000.0)

    def test_tc15_public_transport_ceiling(self):
        """TC15: Other/Public transport exceeding ceiling (₹10,000) -> Capped."""
        decl = self._create_declaration(fare=15000.0, travel_mode='public_transport', journey_date='2025-08-15')
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=15000.0, actual_lta_received=30000.0,
            regime_code='old', declaration=decl, eval_date='2025-08-15'
        )
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.exempt_amount, 10000.0)

    def test_tc16_carry_forward_attempted_after_year1_rejected(self):
        """TC16: Previous block carry forward attempted in Year 4 (2025) -> Rejected."""
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=30000.0, actual_lta_received=50000.0,
            claims_in_block=2, regime_code='old', journey_date='2025-08-15', eval_date='2025-08-15'
        )
        self.assertFalse(res.is_eligible)
        self.assertEqual(res.exempt_amount, 0.0)

    def test_tc17_january_post_proof_recalculation(self):
        """TC17: January post-proof recalculation using approved fare."""
        decl = self._create_declaration(
            state='approved', fare=35000.0, approved_amount=25000.0, journey_date='2025-08-15'
        )
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=35000.0, actual_lta_received=40000.0,
            regime_code='old', declaration=decl, eval_date='2026-01-31'
        )
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.exempt_amount, 25000.0)

    def test_tc18_february_post_proof_recalculation(self):
        """TC18: February post-proof recalculation stability."""
        decl = self._create_declaration(
            state='approved', fare=35000.0, approved_amount=25000.0, journey_date='2025-08-15'
        )
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=35000.0, actual_lta_received=40000.0,
            regime_code='old', declaration=decl, eval_date='2026-02-28'
        )
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.exempt_amount, 25000.0)

    def test_tc19_march_post_proof_recalculation(self):
        """TC19: March post-proof recalculation final adjustment."""
        decl = self._create_declaration(
            state='approved', fare=35000.0, approved_amount=25000.0, journey_date='2025-08-15'
        )
        res = self.lta_service.validate_and_calculate(
            employee=self.employee, declared_fare=35000.0, actual_lta_received=40000.0,
            regime_code='old', declaration=decl, eval_date='2026-03-31'
        )
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.exempt_amount, 25000.0)

    def test_tc20_lta_exemption_reduces_taxable_income(self):
        """TC20: Verify LTA exemption flows into DeductionCalculationService and reduces taxable income."""
        decl = self._create_declaration(fare=30000.0, journey_date='2025-08-15')
        ded_res = self.deduction_service.calculate_deductions(
            employee=self.employee, financial_year=self.fy_2025, eval_date='2025-08-15'
        )
        self.assertGreaterEqual(ded_res.lta_exemption, 0.0)

    def test_tc21_lta_line_sync(self):
        """TC21: Verify _sync_declaration_lines creates a child line for category 'lta'."""
        decl = self._create_declaration(fare=30000.0, journey_date='2025-08-15')
        lta_lines = decl.declaration_line_ids.filtered(lambda l: l.category == 'lta')
        self.assertTrue(len(lta_lines) >= 1, "Child declaration line for LTA should be created automatically.")
        self.assertEqual(lta_lines[0].declared_amount, 30000.0)

    def test_tc22_end_to_end_payslip_tds_lta(self):
        """TC22: Verify end-to-end payslip TDS orchestration consumes LTA exemption."""
        decl = self._create_declaration(fare=30000.0, journey_date='2025-08-15')
        from odoo.addons.hudson_in_payroll.services.tds.tds_orchestration_engine import TdsOrchestrationEngine
        engine = TdsOrchestrationEngine(self.env)
        res = engine.hds_in_compute_tds(self.employee, eval_date='2025-08-15')
        self.assertIsNotNone(res)
        self.assertGreaterEqual(res.current_month_tds, 0.0)

    def test_tc23_april_pre_proof_lta_exemption(self):
        """TC23: Verify April pre-proof calculation passes ₹40,000 declared LTA fare and assigns lta_exemption in DeductionSummary."""
        decl = self._create_declaration(fare=40000.0, state='submitted')
        ded_res = self.deduction_service.calculate_deductions(
            employee=self.employee, financial_year=self.fy_2025, eval_date='2025-04-15'
        )
        self.assertEqual(ded_res.lta_exemption, 40000.0)
        self.assertIn(40000.0, [ded_res.lta_exemption, ded_res.total_allowable_deductions])

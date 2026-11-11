# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from ..services.tds.tds_parameter_service import TdsParameterService


class TestTdsPhase2Parameters(TransactionCase):
    """
    Automated Test Suite for Hudson Indian Payroll TDS Engine Phase 2
    (Enterprise Tax Master & Rule Parameter Framework).
    """

    def setUp(self):
        super().setUp()
        self.tds_service = TdsParameterService(self.env)
        self.eval_date = '2025-06-01'  # FY 2025-26

    def test_01_standard_deduction_resolution(self):
        """Test standard deduction resolution for New Regime (₹75,000) and Old Regime (₹50,000)."""
        std_new = self.tds_service.get_parameter('STD_DEDUCTION', eval_date=self.eval_date, regime='new')
        self.assertEqual(std_new, 75000.0, "New Regime standard deduction must resolve to ₹75,000 for FY 2025-26.")

        std_old = self.tds_service.get_parameter('STD_DEDUCTION', eval_date=self.eval_date, regime='old')
        self.assertEqual(std_old, 50000.0, "Old Regime standard deduction must resolve to ₹50,000.")

    def test_02_section_87a_limits_and_rebates(self):
        """Test Section 87A income limit and rebate limits for New vs Old Regimes."""
        limit_new = self.tds_service.get_parameter('87A_LIMIT', eval_date=self.eval_date, regime='new')
        self.assertEqual(limit_new, 1200000.0, "New Regime 87A income limit must resolve to ₹12,00,000.")

        rebate_new = self.tds_service.get_parameter('87A_MAX_REBATE', eval_date=self.eval_date, regime='new')
        self.assertEqual(rebate_new, 60000.0, "New Regime 87A max rebate must resolve to ₹60,000.")

        limit_old = self.tds_service.get_parameter('87A_LIMIT', eval_date=self.eval_date, regime='old')
        self.assertEqual(limit_old, 500000.0, "Old Regime 87A income limit must resolve to ₹5,00,000.")

        rebate_old = self.tds_service.get_parameter('87A_MAX_REBATE', eval_date=self.eval_date, regime='old')
        self.assertEqual(rebate_old, 12500.0, "Old Regime 87A max rebate must resolve to ₹12,500.")

    def test_03_health_education_cess(self):
        """Test shared Health & Education Cess parameter (4%)."""
        cess = self.tds_service.get_parameter('HEALTH_CESS', eval_date=self.eval_date)
        self.assertEqual(cess, 4.0, "Health & Education Cess must resolve to 4%.")

        cess_dec = self.tds_service.get_parameter('HEALTH_CESS', eval_date=self.eval_date, as_decimal=True)
        self.assertEqual(cess_dec, 0.04, "Health & Education Cess decimal must resolve to 0.04.")

    def test_04_employer_nps_limits(self):
        """Test regime and employer-type aware NPS contribution limits."""
        nps_new = self.tds_service.get_employer_nps_limit(regime='new', employer_type='private', eval_date=self.eval_date)
        self.assertEqual(nps_new, 14.0, "New Regime employer NPS limit must be 14% for all employers.")

        nps_old_pvt = self.tds_service.get_employer_nps_limit(regime='old', employer_type='private', eval_date=self.eval_date)
        self.assertEqual(nps_old_pvt, 10.0, "Old Regime private sector employer NPS limit must be 10%.")

        nps_old_govt = self.tds_service.get_employer_nps_limit(regime='old', employer_type='govt_central', eval_date=self.eval_date)
        self.assertEqual(nps_old_govt, 14.0, "Old Regime Govt sector employer NPS limit must be 14%.")

    def test_05_combined_employer_contribution_ceiling(self):
        """Test Section 17(2)(vii) statutory combined ceiling (₹7,50,000)."""
        ceiling = self.tds_service.get_combined_employer_contribution_limit(eval_date=self.eval_date)
        self.assertEqual(ceiling, 750000.0, "Combined employer PF + NPS + Superannuation ceiling must resolve to ₹7,50,000.")

    def test_06_financial_year_resolution(self):
        """Test Financial Year master resolution."""
        fy = self.tds_service.get_financial_year(eval_date=self.eval_date)
        self.assertTrue(fy, "Financial year must be resolved.")
        self.assertEqual(fy.code, '2025-2026', "FY code must be '2025-2026'.")
        self.assertEqual(fy.assessment_year, '2026-2027', "AY must be '2026-2027'.")

    def test_07_tax_slabs_resolution(self):
        """Test retrieving tax slabs for New vs Old Regime."""
        fy = self.tds_service.get_financial_year(eval_date=self.eval_date)

        new_slabs = self.tds_service.get_tax_slabs(financial_year=fy, regime='new')
        self.assertEqual(len(new_slabs), 7, "AY 2026-27 New Regime must have 7 tax slabs.")
        self.assertEqual(new_slabs[0].rate, 0.0, "New Regime Slab 1 rate must be 0%.")
        self.assertEqual(new_slabs[1].rate, 5.0, "New Regime Slab 2 rate must be 5%.")
        self.assertEqual(new_slabs[-1].rate, 30.0, "New Regime top slab rate must be 30%.")

        old_slabs = self.tds_service.get_tax_slabs(financial_year=fy, regime='old')
        self.assertEqual(len(old_slabs), 4, "Old Regime must have 4 tax slabs.")
        self.assertEqual(old_slabs[0].rate, 0.0, "Old Regime Slab 1 rate must be 0%.")

    def test_08_surcharge_slabs_resolution(self):
        """Test retrieving surcharge slabs for New vs Old Regime."""
        fy = self.tds_service.get_financial_year(eval_date=self.eval_date)

        new_surcharges = self.tds_service.get_surcharge_slabs(financial_year=fy, regime='new')
        self.assertEqual(len(new_surcharges), 4, "New Regime must have 4 surcharge slabs.")
        self.assertEqual(new_surcharges[-1].surcharge_rate, 25.0, "New Regime surcharge top slab must be capped at 25%.")

        old_surcharges = self.tds_service.get_surcharge_slabs(financial_year=fy, regime='old')
        self.assertEqual(len(old_surcharges), 5, "Old Regime must have 5 surcharge slabs.")
        self.assertEqual(old_surcharges[-1].surcharge_rate, 37.0, "Old Regime surcharge top slab must be 37%.")

    def test_09_overlapping_tax_slab_validation(self):
        """Test constraint preventing overlapping tax slab ranges."""
        fy = self.tds_service.get_financial_year(eval_date=self.eval_date)
        with self.assertRaises(ValidationError):
            self.env['tds.tax.slab'].create({
                'financial_year_id': fy.id,
                'regime_code': 'new',
                'income_from': 500000.0,  # Overlaps with 4L-8L slab
                'income_to': 900000.0,
                'rate': 8.0,
            })

    def test_10_additional_statutory_declaration_parameters(self):
        """Test additional statutory parameters for employee tax declarations & exemptions."""
        self.assertEqual(self.tds_service.get_80c_limit(eval_date=self.eval_date), 150000.0, "Sec 80C limit must be ₹1,50,000.")
        self.assertEqual(self.tds_service.get_80ccd1b_limit(eval_date=self.eval_date), 50000.0, "Sec 80CCD(1B) limit must be ₹50,000.")
        self.assertEqual(self.tds_service.get_hra_percentage(is_metro=True, eval_date=self.eval_date), 50.0, "HRA Metro % must be 50%.")
        self.assertEqual(self.tds_service.get_hra_percentage(is_metro=False, eval_date=self.eval_date), 40.0, "HRA Non-Metro % must be 40%.")
        self.assertEqual(self.tds_service.get_80d_limit(is_senior=False, is_parents=False, eval_date=self.eval_date), 25000.0, "80D Self Limit must be ₹25,000.")
        self.assertEqual(self.tds_service.get_80d_limit(is_senior=True, is_parents=True, eval_date=self.eval_date), 50000.0, "80D Parents Senior Limit must be ₹50,000.")
        self.assertEqual(self.tds_service.get_home_loan_interest_limit(eval_date=self.eval_date), 200000.0, "Sec 24(b) Home Loan Interest Limit must be ₹2,00,000.")
        self.assertEqual(self.tds_service.get_leave_encashment_ceiling(eval_date=self.eval_date), 2500000.0, "Leave Encashment Ceiling must be ₹25,00,000.")

    def test_11_section_80eea_eligibility_validation(self):
        """Test Section80EEAEligibilityService validation rules (Category B eligibility vs parameter ceiling)."""
        from ..services.tds.section_80eea_eligibility_service import Section80EEAEligibilityService
        svc = Section80EEAEligibilityService(self.env)

        # 1. Eligible Declaration: Sanctioned June 2020, Stamp 40L, First-time buyer, Claimed 2L
        eligible_decl = {
            'loan_sanction_date': '2020-06-15',
            'property_stamp_value': 4000000.0,
            'is_first_time_home_buyer': True,
            'claimed_interest_amount': 200000.0
        }
        res_eligible = svc.validate_eligibility(eligible_decl, eval_date='2025-06-01')
        self.assertTrue(res_eligible.is_eligible, "Loan sanctioned in June 2020 with stamp 40L must be Section 80EEA eligible.")
        self.assertEqual(res_eligible.max_statutory_ceiling, 150000.0, "Section 80EEA max ceiling must be ₹1,50,000.")
        self.assertEqual(res_eligible.allowed_deduction, 150000.0, "Allowed deduction must be capped at ₹1,50,000 ceiling.")

        # 2. Ineligible Case 1: Loan Sanctioned after 31-Mar-2022 (Scheme expired)
        expired_decl = {
            'loan_sanction_date': '2022-04-15',
            'property_stamp_value': 4000000.0,
            'is_first_time_home_buyer': True,
            'claimed_interest_amount': 200000.0
        }
        res_expired = svc.validate_eligibility(expired_decl, eval_date='2025-06-01')
        self.assertFalse(res_expired.is_eligible, "Loan sanctioned after 31-Mar-2022 must be ineligible.")
        self.assertEqual(res_expired.allowed_deduction, 0.0, "Ineligible loan must receive ₹0 deduction.")

        # 3. Ineligible Case 2: Stamp Value exceeds 45 Lakhs
        expensive_decl = {
            'loan_sanction_date': '2020-06-15',
            'property_stamp_value': 5000000.0,  # ₹50 Lakhs
            'is_first_time_home_buyer': True,
            'claimed_interest_amount': 200000.0
        }
        res_expensive = svc.validate_eligibility(expensive_decl, eval_date='2025-06-01')
        self.assertFalse(res_expensive.is_eligible, "Stamp duty value exceeding ₹45L must be ineligible.")

        # 4. Ineligible Case 3: Not a first-time home buyer
        second_home_decl = {
            'loan_sanction_date': '2020-06-15',
            'property_stamp_value': 4000000.0,
            'is_first_time_home_buyer': False,
            'claimed_interest_amount': 200000.0
        }
        res_second = svc.validate_eligibility(second_home_decl, eval_date='2025-06-01')
        self.assertFalse(res_second.is_eligible, "Non first-time home buyer must be ineligible.")



# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo import fields
from odoo.addons.hudson_in_payroll.services.tds.payroll_period_service import PayrollPeriodService
from odoo.addons.hudson_in_payroll.services.tds.monthly_tds_distribution_service import MonthlyTDSDistributionService
from odoo.addons.hudson_in_payroll.services.tds.salary_projection_service import SalaryProjectionService


class TestTdsPhase10MonthlyDistribution(TransactionCase):

    def setUp(self):
        super(TestTdsPhase10MonthlyDistribution, self).setUp()
        self.fy = self.env['tds.financial.year'].search([('code', '=', '2025-2026')], limit=1)
        if not self.fy:
            self.fy = self.env['tds.financial.year'].create({
                'name': 'Financial Year 2025-2026',
                'code': '2025-2026',
                'assessment_year': '2026-2027',
                'start_date': '2025-04-01',
                'end_date': '2026-03-31',
                'active': True,
            })

        self.employee = self.env['hr.employee'].create({
            'name': 'Phase 10 Monthly TDS Test Employee',
            'birthday': '1990-05-15',
        })

    def test_01_payroll_period_service_dynamic_periods(self):
        """Test PayrollPeriodService resolving remaining periods dynamically across all 12 months under Section 192."""
        period_svc = PayrollPeriodService(self.env)

        # April evaluation date (month 4) = 12 periods
        eval_april = fields.Date.from_string('2025-04-15')
        self.assertEqual(period_svc.calculate_remaining_periods(self.employee, self.fy, eval_date=eval_april), 12)

        # May evaluation date (month 5) = 11 periods
        eval_may = fields.Date.from_string('2025-05-15')
        self.assertEqual(period_svc.calculate_remaining_periods(self.employee, self.fy, eval_date=eval_may), 11)

        # August evaluation date (month 8) = 8 periods
        eval_aug = fields.Date.from_string('2025-08-15')
        self.assertEqual(period_svc.calculate_remaining_periods(self.employee, self.fy, eval_date=eval_aug), 8)

        # October evaluation date (month 10) = 6 periods
        eval_oct = fields.Date.from_string('2025-10-15')
        self.assertEqual(period_svc.calculate_remaining_periods(self.employee, self.fy, eval_date=eval_oct), 6)

        # December evaluation date (month 12) = 4 periods
        eval_dec = fields.Date.from_string('2025-12-15')
        self.assertEqual(period_svc.calculate_remaining_periods(self.employee, self.fy, eval_date=eval_dec), 4)

        # January evaluation date (month 1) = 3 distribution periods
        eval_jan = fields.Date.from_string('2026-01-15')
        self.assertEqual(period_svc.calculate_remaining_periods(self.employee, self.fy, eval_date=eval_jan), 3)

        # February evaluation date (month 2) = 2 distribution periods
        eval_feb = fields.Date.from_string('2026-02-15')
        self.assertEqual(period_svc.calculate_remaining_periods(self.employee, self.fy, eval_date=eval_feb), 2)

        # March evaluation date (month 3) = 1 distribution period
        eval_march = fields.Date.from_string('2026-03-15')
        self.assertEqual(period_svc.calculate_remaining_periods(self.employee, self.fy, eval_date=eval_march), 1)

    def test_02_monthly_tds_distribution_service_without_previous_employer(self):
        """Test MonthlyTDSDistributionService without Form 12B or YTD TDS."""
        dist_svc = MonthlyTDSDistributionService(self.env)

        eval_april = fields.Date.from_string('2025-04-15')
        annual_tax = 120000.0  # ₹1,20,000 annual tax liability

        res = dist_svc.calculate_monthly_tds(self.employee, self.fy, total_annual_tax_liability=annual_tax, eval_date=eval_april)
        self.assertEqual(res.remaining_payroll_periods, 12)
        self.assertEqual(res.ytd_tds_deducted, 0.0)
        self.assertEqual(res.prev_employer_tds, 0.0)
        self.assertEqual(res.remaining_annual_tax_liability, 120000.0)
        self.assertEqual(res.current_month_tds, 10000.0)  # 1,20,000 / 12 = 10,000 / month

    def test_03_monthly_tds_distribution_with_form12b_prev_employer_tds(self):
        """Test MonthlyTDSDistributionService with Form 12B previous employer TDS adjustment."""
        dist_svc = MonthlyTDSDistributionService(self.env)

        # Create Form 12B declaration with ₹30,000 previous employer TDS deducted
        self.env['tds.employee.income.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'prev_employer_taxable_gross': 250000.0,
            'prev_employer_tds': 30000.0,
        })

        eval_january = fields.Date.from_string('2026-01-15')  # 3 remaining distribution periods for K=3
        annual_tax = 90000.0

        res = dist_svc.calculate_monthly_tds(self.employee, self.fy, total_annual_tax_liability=annual_tax, eval_date=eval_january)
        self.assertEqual(res.prev_employer_tds, 30000.0)
        self.assertEqual(res.remaining_annual_tax_liability, 60000.0)  # 90,000 - 30,000 = 60,000
        self.assertEqual(res.remaining_payroll_periods, 3)
        self.assertEqual(res.current_month_tds, 20000.0)  # 60,000 / 3 = 20,000 / month

    def test_04_zero_floor_remaining_liability(self):
        """Test that remaining liability does not become negative when TDS paid exceeds annual liability."""
        dist_svc = MonthlyTDSDistributionService(self.env)

        self.env['tds.employee.income.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'prev_employer_tds': 50000.0,
        })

        eval_april = fields.Date.from_string('2025-04-15')
        annual_tax = 40000.0  # Annual tax liability is 40k, but 50k already deducted

        res = dist_svc.calculate_monthly_tds(self.employee, self.fy, total_annual_tax_liability=annual_tax, eval_date=eval_april)
        self.assertEqual(res.remaining_annual_tax_liability, 0.0)
        self.assertEqual(res.current_month_tds, 0.0)

    def test_05_missing_input_validation(self):
        """Test error handling when required parameters are missing."""
        dist_svc = MonthlyTDSDistributionService(self.env)

        with self.assertRaises(ValidationError):
            dist_svc.calculate_monthly_tds(False, self.fy, 50000.0)

    def test_06_countdown_remaining_periods(self):
        """Test countdown of dynamic remaining periods."""
        period_svc = PayrollPeriodService(self.env)

        eval_nov = fields.Date.from_string('2025-11-15')
        eval_dec = fields.Date.from_string('2025-12-15')
        eval_jan = fields.Date.from_string('2026-01-15')

        self.assertEqual(period_svc.calculate_remaining_periods(self.employee, self.fy, eval_date=eval_nov), 5)
        self.assertEqual(period_svc.calculate_remaining_periods(self.employee, self.fy, eval_date=eval_dec), 4)
        self.assertEqual(period_svc.calculate_remaining_periods(self.employee, self.fy, eval_date=eval_jan), 3)

    def test_07_mid_year_salary_hike_dynamic_amortization(self):
        """
        Test Section 192 dynamic TDS redistribution when employee receives a mid-year salary hike in August.
        - Apr-Jul: TDS ₹10,000/mo deducted (Total YTD TDS = ₹40,000)
        - In August: Salary hike occurs. Projected annual tax increases to ₹2,00,000.
        - Remaining tax = ₹2,00,000 - ₹40,000 = ₹1,60,000.
        - Remaining periods = 8 (Aug to Mar).
        - August TDS = ₹1,60,000 / 8 = ₹20,000 (NOT the buggy ₹2,00,000 / 12 = ₹16,666.67).
        """
        dist_svc = MonthlyTDSDistributionService(self.env)

        # Mock previous employer / YTD TDS: create Form 12B or payslips
        self.env['tds.employee.income.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'prev_employer_tds': 40000.0,  # Represents ₹40,000 TDS deducted during Apr-Jul
        })

        eval_august = fields.Date.from_string('2025-08-15')
        new_annual_tax = 200000.0

        res = dist_svc.calculate_monthly_tds(
            self.employee,
            self.fy,
            total_annual_tax_liability=new_annual_tax,
            eval_date=eval_august
        )

        self.assertEqual(res.remaining_payroll_periods, 8)
        self.assertEqual(res.total_tds_paid_so_far, 40000.0)
        self.assertEqual(res.remaining_annual_tax_liability, 160000.0)
        self.assertEqual(res.current_month_tds, 20000.0)

    def test_08_mid_year_joiner_dynamic_amortization(self):
        """
        Test mid-year joiner (joining date = 2025-08-01).
        In August (month 8 of calendar, month 5 of FY), remaining periods must be 8.
        In September, remaining periods must be 7.
        """
        period_svc = PayrollPeriodService(self.env)
        dist_svc = MonthlyTDSDistributionService(self.env)

        mid_year_employee = self.env['hr.employee'].create({
            'name': 'Mid Year Joiner Employee',
            'birthday': '1995-08-20',
        })
        # Set joining date on employee (or first contract start date)
        if hasattr(mid_year_employee, 'first_contract_date'):
            mid_year_employee.first_contract_date = fields.Date.from_string('2025-08-01')
        if hasattr(mid_year_employee, 'joining_date'):
            mid_year_employee.joining_date = fields.Date.from_string('2025-08-01')

        eval_august = fields.Date.from_string('2025-08-15')
        remaining_periods_aug = period_svc.calculate_remaining_periods(mid_year_employee, self.fy, eval_date=eval_august)
        self.assertEqual(remaining_periods_aug, 8)

        eval_september = fields.Date.from_string('2025-09-15')
        remaining_periods_sep = period_svc.calculate_remaining_periods(mid_year_employee, self.fy, eval_date=eval_september)
        self.assertEqual(remaining_periods_sep, 7)

        # Test monthly TDS calculation for mid-year joiner in August (annual tax ₹1,60,000 for 8 months)
        res = dist_svc.calculate_monthly_tds(
            mid_year_employee,
            self.fy,
            total_annual_tax_liability=160000.0,
            eval_date=eval_august
        )
        self.assertEqual(res.remaining_payroll_periods, 8)
        self.assertEqual(res.remaining_annual_tax_liability, 160000.0)
        self.assertEqual(res.current_month_tds, 20000.0)

    def test_09_early_departure_employee_remaining_periods(self):
        """
        Test employee departing before FY end (resignation / departure date = 2025-11-30).
        In August, remaining periods should be 4 (Aug, Sep, Oct, Nov).
        In November, remaining periods should be 1.
        """
        period_svc = PayrollPeriodService(self.env)

        leaver_emp = self.env['hr.employee'].create({
            'name': 'Early Leaver Employee',
            'birthday': '1992-03-10',
        })
        if hasattr(leaver_emp, 'departure_date'):
            leaver_emp.departure_date = fields.Date.from_string('2025-11-30')

        eval_aug = fields.Date.from_string('2025-08-15')
        rem_aug = period_svc.calculate_remaining_periods(leaver_emp, self.fy, eval_date=eval_aug)
        self.assertEqual(rem_aug, 4)

        eval_nov = fields.Date.from_string('2025-11-15')
        rem_nov = period_svc.calculate_remaining_periods(leaver_emp, self.fy, eval_date=eval_nov)
        self.assertEqual(rem_nov, 1)

    def test_10_october_joiner_salary_projection_and_remaining_months(self):
        """
        User Requirement Test:
        When an employee joins in October with monthly salary ₹2,00,000:
        1. Total FY periods for employee must be 6 (Oct to Mar).
        2. In October (eval_date = 2025-10-15), SalaryProjectionService must project
           salary for 6 months: 6 * ₹2,00,000 = ₹12,00,000 (NOT the hardcoded 12 * ₹2,00,000 = ₹24,00,000).
        3. Remaining payroll periods under Section 192 must be 6.
        4. Payslip remaining future months (rem_periods - 1) must be 5 (Nov, Dec, Jan, Feb, Mar).
        """
        period_svc = PayrollPeriodService(self.env)
        salary_svc = SalaryProjectionService(self.env)

        oct_employee = self.env['hr.employee'].create({
            'name': 'October Joiner ₹2L Salary',
            'birthday': '1993-10-10',
        })
        if hasattr(oct_employee, 'first_contract_date'):
            oct_employee.first_contract_date = fields.Date.from_string('2025-10-01')
        if hasattr(oct_employee, 'joining_date'):
            oct_employee.joining_date = fields.Date.from_string('2025-10-01')

        contract = self.env['hr.contract'].create({
            'name': 'October Joiner Contract',
            'employee_id': oct_employee.id,
            'wage': 200000.0,
            'state': 'open',
            'date_start': '2025-10-01',
        })
        if hasattr(oct_employee, 'contract_id'):
            oct_employee.contract_id = contract.id

        # 1. Verify total periods in FY
        total_fy_periods = period_svc.calculate_total_periods_in_fy(oct_employee, self.fy)
        self.assertEqual(total_fy_periods, 6, "October joiner must have exactly 6 employment periods in the FY")

        # 2. Evaluate in October (2025-10-15)
        eval_oct = fields.Date.from_string('2025-10-15')
        sal_proj = salary_svc.project_salary(oct_employee, self.fy, eval_date=eval_oct)

        # Expected: 6 * 2,00,000 = 12,00,000 (NOT 24,00,000)
        self.assertEqual(sal_proj.total_projected_current_salary, 1200000.0,
                         "Projected annual salary for October joiner at ₹2L/month must be ₹12,00,000 (6 months), NOT ₹24,00,000")
        self.assertEqual(sal_proj.months_elapsed, 1)
        self.assertEqual(sal_proj.months_remaining, 5)

        # 3. Verify remaining periods for TDS
        rem_periods = period_svc.calculate_remaining_periods(oct_employee, self.fy, eval_date=eval_oct)
        self.assertEqual(rem_periods, 6, "October payroll run must have 6 remaining periods (Oct, Nov, Dec, Jan, Feb, Mar)")

        # 4. Verify payslip future remaining months: 6 - 1 = 5
        payslip_future_months = max(0, rem_periods - 1)
        self.assertEqual(payslip_future_months, 5, "Payslip future remaining months after October must be 5")

    def test_11_october_joiner_with_form12b_prev_salary_and_tds(self):
        """
        Critical User Fix Verification:
        When an October joiner declares 6 months of previous salary + TDS via Form 12B:
        1. Current employer projects ONLY 6 remaining months (Oct-Mar), NOT a full 12 months.
        2. Total projected salary is 12 months (6 months current + 6 months previous), NOT 18 months.
        3. Monthly distribution takes previous employer TDS into account.
        4. Divisor is 6 (remaining months: Oct to Mar), NOT 12.
        """
        from odoo.addons.hudson_in_payroll.services.tds.annual_income_projection_service import AnnualIncomeProjectionService

        period_svc = PayrollPeriodService(self.env)
        salary_svc = SalaryProjectionService(self.env)
        dist_svc = MonthlyTDSDistributionService(self.env)
        annual_svc = AnnualIncomeProjectionService(self.env)

        oct_emp = self.env['hr.employee'].create({
            'name': 'October Joiner Form 12B Employee',
            'birthday': '1992-06-15',
        })
        if hasattr(oct_emp, 'first_contract_date'):
            oct_emp.first_contract_date = fields.Date.from_string('2025-10-01')
        if hasattr(oct_emp, 'joining_date'):
            oct_emp.joining_date = fields.Date.from_string('2025-10-01')

        contract = self.env['hr.contract'].create({
            'name': 'October Joiner Contract',
            'employee_id': oct_emp.id,
            'wage': 100000.0,  # ₹1,00,000 / month
            'state': 'open',
            'date_start': '2025-10-01',
        })
        if hasattr(oct_emp, 'contract_id'):
            oct_emp.contract_id = contract.id

        # Declare 6 months of previous employer salary (₹6,00,000) and TDS (₹30,000) via Form 12B
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': oct_emp.id,
            'financial_year_id': self.fy.id,
            'prev_employer_taxable_gross': 600000.0,
            'prev_employer_tds': 30000.0,
            'status': 'approved',
        })

        eval_oct = fields.Date.from_string('2025-10-15')

        # 1. Verify current employer projection is 6 months (6 * 1,00,000 = 6,00,000)
        sal_proj = salary_svc.project_salary(oct_emp, self.fy, eval_date=eval_oct)
        self.assertEqual(sal_proj.total_projected_current_salary, 600000.0,
                         "Current employer projected salary must be 6 months (₹6,00,000), NOT 12 months (₹12,00,000)")

        # 2. Verify total annual salary is 12 months (6L current + 6L previous = 12L), NOT 18 months (18L)
        ann_proj = annual_svc.project_annual_income(oct_emp, eval_date=eval_oct)
        self.assertEqual(ann_proj.current_employer_salary, 600000.0)
        self.assertEqual(ann_proj.previous_employer_income.taxable_salary, 600000.0)
        self.assertEqual(ann_proj.projected_annual_salary, 1200000.0,
                         "Projected annual salary must be exactly 12 months (₹12,00,000), NOT 18 months")

        # 3. Verify remaining periods for TDS is 6 (Oct to Mar)
        rem_periods = period_svc.calculate_remaining_periods(oct_emp, self.fy, eval_date=eval_oct)
        self.assertEqual(rem_periods, 6, "Remaining periods for October joiner must be 6, NOT 12")

        # 4. Verify monthly TDS distribution incorporates previous employer TDS (₹30,000) and divides by 6
        # Assume total annual tax is ₹1,14,400
        annual_tax = 114400.0
        res = dist_svc.calculate_monthly_tds(oct_emp, self.fy, total_annual_tax_liability=annual_tax, eval_date=eval_oct)

        self.assertEqual(res.prev_employer_tds, 30000.0, "Previous employer TDS must NOT be ignored (₹30,000)")
        self.assertEqual(res.remaining_annual_tax_liability, 84400.0, "Remaining liability must be 114400 - 30000 = 84400")
        self.assertEqual(res.remaining_payroll_periods, 6, "Divisor must be 6, NOT 12")
        self.assertEqual(res.current_month_tds, round(84400.0 / 6.0, 2))

    def test_12_october_joiner_form12b_on_employee_fields_without_contract_joining_date(self):
        """
        Verify fallback when employee record doesn't have contract/joining date set,
        but declares Form 12B previous income on hr.employee fields.
        """
        period_svc = PayrollPeriodService(self.env)
        salary_svc = SalaryProjectionService(self.env)
        dist_svc = MonthlyTDSDistributionService(self.env)

        oct_emp2 = self.env['hr.employee'].create({
            'name': 'October Joiner Fallback Employee',
            'birthday': '1995-02-20',
        })
        # Set previous employer fields directly on employee
        oct_emp2.hds_in_prev_taxable_gross = 300000.0
        oct_emp2.hds_in_prev_tds_deducted = 15000.0

        contract = self.env['hr.contract'].create({
            'name': 'October Contract 2',
            'employee_id': oct_emp2.id,
            'wage': 50000.0,
            'state': 'open',
        })
        if hasattr(oct_emp2, 'contract_id'):
            oct_emp2.contract_id = contract.id

        eval_oct = fields.Date.from_string('2025-10-15')

        # When evaluated in October, total periods for current employer must be 6
        total_fy = period_svc.calculate_total_periods_in_fy(oct_emp2, self.fy, eval_date=eval_oct)
        self.assertEqual(total_fy, 6, "Total periods in FY with previous employer declaration evaluated in Oct must be 6")

        sal_proj = salary_svc.project_salary(oct_emp2, self.fy, eval_date=eval_oct)
        self.assertEqual(sal_proj.total_projected_current_salary, 300000.0,
                         "Projected current employer salary must be 6 * 50,000 = 300,000 (NOT 12 * 50,000)")

        # Monthly TDS distribution
        res = dist_svc.calculate_monthly_tds(oct_emp2, self.fy, total_annual_tax_liability=45000.0, eval_date=eval_oct)
        self.assertEqual(res.prev_employer_tds, 15000.0)
        self.assertEqual(res.remaining_annual_tax_liability, 30000.0)
        self.assertEqual(res.remaining_payroll_periods, 6)
        self.assertEqual(res.current_month_tds, 5000.0)  # 30,000 / 6 = 5,000


    def test_13_october_joiner_user_spec_475800_total_tax(self):
        """
        User Specification Verification Test (Exact Expected Values):
        =============================================================
        Employee: October-1 joiner, ₹2,50,000/month current employer salary.
        Form 12B: ₹15,00,000 previous employer taxable salary, ₹97,500 previous TDS.

        Expected results per the user specification:
          Total FY Salary         : ₹30,00,000  (6 × ₹2.5L current + ₹15L previous)
          Standard Deduction      : ₹75,000      (New Regime FY 2025-26)
          Taxable Income          : ₹29,25,000
          Total Tax Liability     : ₹4,75,800    (slab + 4% cess, new regime)
          Previous Employer TDS   : ₹97,500      (credit, subtracted from liability)
          Remaining TDS Liability : ₹3,78,300    (4,75,800 − 97,500)
          Remaining Months        : 6             (Oct–Mar, INCLUDING current month)
          Monthly TDS             : ₹63,050       (3,78,300 ÷ 6)

        This test verifies the distribution layer only (tax liability is passed in as
        the pre-computed ₹4,75,800 figure; the slab calculation is separately verified).
        """
        period_svc = PayrollPeriodService(self.env)
        dist_svc = MonthlyTDSDistributionService(self.env)

        # ── Create employee with October joining date ──────────────────────────
        emp = self.env['hr.employee'].create({
            'name': 'October Joiner Spec Employee (2.5L)',
            'birthday': '1990-03-20',
        })
        for field in ('first_contract_date', 'joining_date', 'hds_in_doj'):
            if hasattr(emp, field):
                setattr(emp, field, fields.Date.from_string('2025-10-01'))

        # ── Contract: ₹2,50,000 / month ──────────────────────────────────────
        contract = self.env['hr.contract'].create({
            'name': 'October Joiner 2.5L Contract',
            'employee_id': emp.id,
            'wage': 250000.0,
            'state': 'open',
            'date_start': '2025-10-01',
        })
        if hasattr(emp, 'contract_id'):
            emp.contract_id = contract.id

        # ── Form 12B declaration: ₹15L taxable + ₹97,500 TDS ────────────────
        # Write via tds.employee.income.declaration (the authoritative Form 12B store)
        inc_decl = self.env['tds.employee.income.declaration'].create({
            'employee_id': emp.id,
            'financial_year_id': self.fy.id,
            'prev_employer_taxable_gross': 1500000.0,   # ₹15,00,000
            'prev_employer_tds': 97500.0,               # ₹97,500
            'state': 'approved',
        })

        eval_oct = fields.Date.from_string('2025-10-01')

        # ── Guard 1: remaining periods must be 6 (Oct–Mar) ───────────────────
        rem_periods = period_svc.calculate_remaining_periods(emp, self.fy, eval_date=eval_oct)
        self.assertEqual(
            rem_periods, 6,
            f"Remaining payroll periods for Oct-1 joiner must be 6, got {rem_periods}"
        )

        # ── Guard 2: distribution engine with total tax = ₹4,75,800 ──────────
        total_annual_tax = 475800.0   # computed by slab engine (passed in)
        res = dist_svc.calculate_monthly_tds(
            emp, self.fy,
            total_annual_tax_liability=total_annual_tax,
            eval_date=eval_oct
        )

        # Previous employer TDS credit
        self.assertEqual(
            res.prev_employer_tds, 97500.0,
            f"prev_employer_tds must be ₹97,500 (Form 12B credit), got {res.prev_employer_tds}"
        )

        # Remaining TDS = total − prev_tds (no current YTD in October first payslip)
        expected_remaining = 475800.0 - 97500.0   # = 3,78,300
        self.assertAlmostEqual(
            res.remaining_annual_tax_liability, expected_remaining, places=1,
            msg=f"Remaining TDS must be ₹3,78,300, got {res.remaining_annual_tax_liability}"
        )

        # Divisor: 6 months (Oct–Mar, INCLUDING October)
        self.assertEqual(
            res.remaining_payroll_periods, 6,
            f"remaining_payroll_periods must be 6 (Oct–Mar), got {res.remaining_payroll_periods}"
        )

        # Monthly TDS = ₹3,78,300 ÷ 6 = ₹63,050
        expected_monthly = round(expected_remaining / 6.0, 2)   # 63050.0
        self.assertAlmostEqual(
            res.current_month_tds, expected_monthly, places=1,
            msg=(
                f"Monthly TDS must be ₹63,050 (3,78,300 ÷ 6), got {res.current_month_tds}. "
                "Standard deduction must be applied ONCE on combined FY income; "
                "previous TDS is a credit only — never added to income."
            )
        )


    def test_14_full_engine_e2e_october_joiner_30L_income(self):
        """
        Full End-to-End Engine Test — calls TdsOrchestrationEngine.hds_in_compute_tds()
        with a complete October-1 joiner setup and Form 12B data.

        Verifies the ENTIRE pipeline:
          - SalaryProjectionService computes 6 × ₹2.5L = ₹15L (current employer)
          - PreviousEmployerIncomeService picks up ₹15L prev salary from tds.employee.income.declaration
          - AnnualIncomeProjectionService GTI = ₹30L (15L + 15L)
          - Standard deduction = ₹75,000 (applied ONCE on ₹30L aggregate)
          - Taxable income = ₹29,25,000
          - Total tax (slab + 4% cess, new regime) = ₹4,75,800
          - MonthlyTDSDistributionService: prev TDS credit ₹97,500, remaining ₹3,78,300, 6 months, monthly ₹63,050
        """
        from odoo.addons.hudson_in_payroll.services.tds.tds_orchestration_engine import TdsOrchestrationEngine

        # ── New Regime record (required for regime resolution) ──────────────────
        new_regime = self.env['tds.tax.regime'].search([('code', '=', 'new')], limit=1)
        if not new_regime:
            new_regime = self.env['tds.tax.regime'].create({
                'name': 'New Tax Regime (115BAC)',
                'code': 'new',
            })

        # ── Employee ─────────────────────────────────────────────────────────────
        emp = self.env['hr.employee'].create({
            'name': 'E2E Test Oct Joiner 30L FY2526',
            'birthday': '1990-03-20',
        })
        # Set joining date on every supported field
        for field in ('first_contract_date', 'joining_date', 'hds_in_doj'):
            if field in self.env['hr.employee']._fields:
                emp.write({field: fields.Date.from_string('2025-10-01')})

        # ── Contract: ₹2,50,000/month ────────────────────────────────────────────
        contract = self.env['hr.contract'].create({
            'name': 'E2E 2.5L Oct Contract',
            'employee_id': emp.id,
            'wage': 250000.0,
            'state': 'open',
            'date_start': '2025-10-01',
        })
        if 'contract_id' in self.env['hr.employee']._fields:
            emp.write({'contract_id': contract.id})

        # ── Tax Regime: New Regime ────────────────────────────────────────────────
        self.env['tds.employee.tax.regime'].create({
            'employee_id': emp.id,
            'financial_year_id': self.fy.id,
            'regime_id': new_regime.id,
        })

        # ── Form 12B: ₹15L taxable salary + ₹97,500 TDS ─────────────────────────
        self.env['tds.employee.income.declaration'].create({
            'employee_id': emp.id,
            'financial_year_id': self.fy.id,
            'prev_employer_taxable_gross': 1500000.0,
            'prev_employer_tds': 97500.0,
            'state': 'approved',
        })

        eval_oct = fields.Date.from_string('2025-10-01')
        engine = TdsOrchestrationEngine(self.env)
        tds_res = engine.hds_in_compute_tds(emp, eval_date=eval_oct)

        proj = tds_res.annual_income_projection
        monthly = tds_res.monthly_tds_distribution

        # ── Assert: GTI = ₹30L ────────────────────────────────────────────────────
        gti = float(getattr(proj, 'gross_total_income', 0.0) or 0.0)
        self.assertAlmostEqual(
            gti, 3000000.0, places=0,
            msg=f"GTI must be ₹30,00,000 (₹15L current + ₹15L previous), got {gti}"
        )

        # ── Assert: net taxable income = ₹29,25,000 ──────────────────────────────
        tax_inc = tds_res.taxable_income
        nti = float(getattr(tax_inc, 'net_taxable_income', 0.0) or 0.0)
        self.assertAlmostEqual(
            nti, 2925000.0, places=0,
            msg=f"Net taxable income must be ₹29,25,000 (₹30L − ₹75,000 std ded), got {nti}"
        )

        # ── Assert: total tax = ₹4,75,800 ────────────────────────────────────────
        total_tax = float(tds_res.total_annual_tax_liability or 0.0)
        self.assertAlmostEqual(
            total_tax, 475800.0, places=0,
            msg=f"Total annual tax must be ₹4,75,800 (new regime slabs + 4% cess on ₹29.25L), got {total_tax}"
        )

        # ── Assert: prev employer TDS credit = ₹97,500 ───────────────────────────
        prev_tds = float(getattr(monthly, 'prev_employer_tds', 0.0) or 0.0)
        self.assertAlmostEqual(
            prev_tds, 97500.0, places=0,
            msg=f"prev_employer_tds must be ₹97,500, got {prev_tds}"
        )

        # ── Assert: remaining TDS = ₹3,78,300 ────────────────────────────────────
        remaining = float(getattr(monthly, 'remaining_annual_tax_liability', 0.0) or 0.0)
        self.assertAlmostEqual(
            remaining, 378300.0, places=0,
            msg=f"Remaining TDS must be ₹3,78,300 (₹4,75,800 − ₹97,500), got {remaining}"
        )

        # ── Assert: remaining months = 6 ─────────────────────────────────────────
        rem_periods = int(getattr(monthly, 'remaining_payroll_periods', 0) or 0)
        self.assertEqual(
            rem_periods, 6,
            f"Remaining months must be 6 (Oct–Mar), got {rem_periods}"
        )

        # ── Assert: monthly TDS = ₹63,050 ────────────────────────────────────────
        monthly_tds = float(tds_res.current_month_tds or 0.0)
        self.assertAlmostEqual(
            monthly_tds, 63050.0, places=0,
            msg=(
                f"Monthly TDS must be ₹63,050 (₹3,78,300 ÷ 6), got {monthly_tds}. "
                "Standard deduction applied ONCE on aggregate ₹30L income."
            )
        )

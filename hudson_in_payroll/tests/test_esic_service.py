# -*- coding: utf-8 -*-
import datetime
from odoo.tests.common import TransactionCase
from ..services.esic.esic_service import ESICService
from ..services.esic.validator import ESICValidator
from ..services.esic.contribution_period_service import ESICContributionPeriodService


class TestESICComprehensive(TransactionCase):
    """
    Comprehensive Statutory Test Suite for ESIC (Employees' State Insurance Corporation) Compliance
    covering Indian Statutory Law (ESI Act, 1948 & ESI (General) Regulations, 1950):
    
    1. Standard Wage Ceiling (₹21,000)
    2. PWD Wage Ceiling (₹25,000)
    3. Contribution Rates (EE 0.75%, ER 3.25%, Total 4.00%)
    4. Regulation 31 Continuity: April - September Contribution Period
    5. Regulation 31 Continuity: October - March Contribution Period
    6. Next Contribution Period Exit (automatic cessation upon period transition)
    7. Mid-Period Joiners (Eligible vs Ineligible)
    8. Direct Contract In-Place Wage Hike Guard
    9. Approved Salary Revision Wizard Continuity
    10. Company-level & Employee-level Statutory Disablement
    11. Employee Exit / Resignation Date Enforcement
    12. Actual Earned Wage vs Contract Wage Calculation (LOP / Worked Days)
    13. ESI Wage Composition (Basic, HRA, Overtime, Allowances)
    14. Contribution Period Bound Helpers (April-Sep & Oct-Mar)
    """

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.hds_in_esic_applicable = True
        self.company.hds_in_esic_contribution_period_type = 'apr_sep_oct_mar'

        self.employee = self.env['hr.employee'].create({
            'name': 'Ramesh Kumar (Standard)',
            'company_id': self.company.id,
            'hds_in_esic_applicable': True,
            'hds_in_esic_ip_status': 'active',
            'hds_in_esic_ip_number': '1234567890',
            'hds_in_is_pwd': False,
            'wage': 20000.0,
        })

        self.pwd_employee = self.env['hr.employee'].create({
            'name': 'Suresh Menon (PWD)',
            'company_id': self.company.id,
            'hds_in_esic_applicable': True,
            'hds_in_esic_ip_status': 'active',
            'hds_in_esic_ip_number': '9876543210',
            'hds_in_is_pwd': True,
            'wage': 23000.0,
        })

        self.validator = ESICValidator(self.env)
        self.period_service = ESICContributionPeriodService(self.env)

    # -------------------------------------------------------------------------
    # TEST 1: Standard Ceiling Limit (₹21,000)
    # -------------------------------------------------------------------------
    def test_01_standard_ceiling_eligible_and_rate_calculation(self):
        """Standard employee earning <= ₹21,000: EE 0.75%, ER 3.25%."""
        payslip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'date_from': '2026-04-01',
            'date_to': '2026-04-30',
        })
        service = ESICService(self.env, localdict={'BASIC': 15000.0, 'HRA': 5000.0})

        wage = service.compute_esic_wage(payslip)
        self.assertEqual(wage, 20000.0)

        # EE = 20000 * 0.75% = 150.0
        ee_deduction = service.compute_esic_employee(payslip)
        self.assertEqual(ee_deduction, 150.0)

        # ER = 20000 * 3.25% = 650.0
        er_contribution = service.compute_esic_employer(payslip)
        self.assertEqual(er_contribution, 650.0)

        self.assertTrue(self.validator.is_esic_eligible(payslip, gross_wage=20000.0))

    def test_02_standard_ceiling_exceeded_at_joining(self):
        """Standard employee hired > ₹21,000 is not eligible (returns 0.0)."""
        high_earner = self.env['hr.employee'].create({
            'name': 'Vikram High Earner',
            'company_id': self.company.id,
            'wage': 25000.0,
            'hds_in_is_pwd': False,
        })
        # Employee creation automatically flags exempt for new hire > 21k
        self.assertFalse(high_earner.hds_in_esic_applicable)
        self.assertEqual(high_earner.hds_in_esic_ip_status, 'exempt')

        payslip = self.env['hr.payslip'].create({
            'employee_id': high_earner.id,
            'date_from': '2026-04-01',
            'date_to': '2026-04-30',
        })
        service = ESICService(self.env, localdict={'BASIC': 20000.0, 'HRA': 5000.0})
        self.assertEqual(service.compute_esic_wage(payslip), 0.0)
        self.assertEqual(service.compute_esic_employee(payslip), 0.0)
        self.assertEqual(service.compute_esic_employer(payslip), 0.0)
        self.assertFalse(self.validator.is_esic_eligible(payslip, gross_wage=25000.0))

    # -------------------------------------------------------------------------
    # TEST 2: PWD Ceiling Limit (₹25,000)
    # -------------------------------------------------------------------------
    def test_03_pwd_employee_ceiling_handling(self):
        """
        PWD employee:
        - Gross ₹23,000 (> ₹21,000 standard ceiling, but <= ₹25,000 PWD ceiling): ELIGIBLE.
        - Gross ₹26,000 (> ₹25,000 PWD ceiling): EXEMPT.
        """
        payslip = self.env['hr.payslip'].create({
            'employee_id': self.pwd_employee.id,
            'date_from': '2026-04-01',
            'date_to': '2026-04-30',
        })
        service = ESICService(self.env, localdict={'BASIC': 18000.0, 'HRA': 5000.0})

        # Eligible under PWD ceiling
        self.assertTrue(self.validator.is_esic_eligible(payslip, gross_wage=23000.0))
        self.assertEqual(service.compute_esic_wage(payslip), 23000.0)

        # EE = 23000 * 0.0075 = 172.5 -> 173.0 (rounded up)
        self.assertEqual(service.compute_esic_employee(payslip), 173.0)
        # ER = 23000 * 0.0325 = 747.5 -> 748.0 (rounded up)
        self.assertEqual(service.compute_esic_employer(payslip), 748.0)

        # When PWD wage exceeds ₹25,000 ceiling:
        pwd_exceed = self.env['hr.employee'].create({
            'name': 'PWD Exceeded',
            'company_id': self.company.id,
            'hds_in_is_pwd': True,
            'wage': 26000.0,
        })
        self.assertFalse(pwd_exceed.hds_in_esic_applicable)
        self.assertEqual(pwd_exceed.hds_in_esic_ip_status, 'exempt')

    # -------------------------------------------------------------------------
    # TEST 3: Regulation 31 Continuity (April – September Period)
    # -------------------------------------------------------------------------
    def test_04_regulation_31_april_september_hike_continuity(self):
        """
        Statutory Regulation 31 Test:
        - Employee starts April 1 at ₹20,000 (<= ₹21,000).
        - Receives salary hike to ₹26,000 in July.
        - ESIC deductions MUST CONTINUE on full ₹26,000 for July, August, September.
        - October 1 (New Contribution Period): Deductions MUST STOP because wage on Oct 1 > ₹21,000.
        """
        contract = self.employee.version_id or self.env['hr.version'].search([('employee_id', '=', self.employee.id)], limit=1)
        contract.write({
            'name': 'April Contract',
            'wage': 20000.0,
            'date_start': '2026-04-01',
            'date_version': '2026-04-01',
        })
        self.employee.write({'hds_in_esic_applicable': True, 'hds_in_esic_ip_status': 'active'})

        # Confirm April Payslip
        apr_slip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'date_from': '2026-04-01',
            'date_to': '2026-04-30',
        })
        self.assertTrue(self.validator.is_esic_eligible(apr_slip, gross_wage=20000.0))

        # Mid-Period Salary Hike in July: 20k -> 26k
        contract.write({'wage': 26000.0})
        self.env['hds.in.salary.revision'].create({
            'employee_id': self.employee.id,
            'contract_id': contract.id,
            'effective_date': '2026-07-01',
            'old_wage': 20000.0,
            'new_wage': 26000.0,
            'revision_type': 'annual_increment',
            'revision_basis': 'full_wage',
            'computation_type': 'fixed_amount',
            'state': 'approved',
        })

        # Check Employee applicability remained True
        self.assertTrue(self.employee.hds_in_esic_applicable)
        self.assertEqual(self.employee.hds_in_esic_ip_status, 'active')

        # July Payslip (Mid-period)
        jul_slip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'date_from': '2026-07-01',
            'date_to': '2026-07-31',
        })
        self.assertTrue(self.validator.is_esic_eligible(jul_slip, gross_wage=26000.0))
        jul_svc = ESICService(self.env, localdict={'BASIC': 20000.0, 'HRA': 6000.0})
        self.assertEqual(jul_svc.compute_esic_wage(jul_slip), 26000.0)
        self.assertEqual(jul_svc.compute_esic_employee(jul_slip), 195.0)  # 26000 * 0.75%
        self.assertEqual(jul_svc.compute_esic_employer(jul_slip), 845.0)  # 26000 * 3.25%

        # September Payslip (End of period)
        sep_slip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'date_from': '2026-09-01',
            'date_to': '2026-09-30',
        })
        self.assertTrue(self.validator.is_esic_eligible(sep_slip, gross_wage=26000.0))
        sep_svc = ESICService(self.env, localdict={'BASIC': 20000.0, 'HRA': 6000.0})
        self.assertEqual(sep_svc.compute_esic_wage(sep_slip), 26000.0)
        self.assertEqual(sep_svc.compute_esic_employee(sep_slip), 195.0)

        # October Payslip (New Contribution Period: Oct 1 - Mar 31)
        oct_slip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'date_from': '2026-10-01',
            'date_to': '2026-10-31',
        })
        self.assertFalse(self.validator.is_esic_eligible(oct_slip, gross_wage=26000.0))
        oct_svc = ESICService(self.env, localdict={'BASIC': 20000.0, 'HRA': 6000.0})
        self.assertEqual(oct_svc.compute_esic_wage(oct_slip), 0.0)
        self.assertEqual(oct_svc.compute_esic_employee(oct_slip), 0.0)
        self.assertEqual(oct_svc.compute_esic_employer(oct_slip), 0.0)

    # -------------------------------------------------------------------------
    # TEST 4: Regulation 31 Continuity (October – March Period)
    # -------------------------------------------------------------------------
    def test_05_regulation_31_october_march_hike_continuity(self):
        """
        Statutory Regulation 31 Test:
        - Employee starts October 1 at ₹19,000 (<= ₹21,000).
        - Receives salary hike to ₹28,000 in January.
        - ESIC deductions MUST CONTINUE on full ₹28,000 for January, February, March.
        - April 1 (Next Contribution Period): Deductions MUST STOP.
        """
        oct_emp = self.env['hr.employee'].create({
            'name': 'Kavitha Oct Joiner',
            'company_id': self.company.id,
            'wage': 19000.0,
            'hds_in_esic_applicable': True,
            'hds_in_esic_ip_status': 'active',
            'hds_in_is_pwd': False,
        })
        contract = oct_emp.version_id or self.env['hr.version'].search([('employee_id', '=', oct_emp.id)], limit=1)
        contract.write({
            'name': 'October Contract',
            'wage': 19000.0,
            'date_start': '2026-10-01',
            'date_version': '2026-10-01',
        })

        # November Payslip (Within ceiling)
        nov_slip = self.env['hr.payslip'].create({
            'employee_id': oct_emp.id,
            'date_from': '2026-11-01',
            'date_to': '2026-11-30',
        })
        self.assertTrue(self.validator.is_esic_eligible(nov_slip, gross_wage=19000.0))

        # January Salary Hike: 19k -> 28k via Approved Salary Revision
        self.env['hds.in.salary.revision'].create({
            'employee_id': oct_emp.id,
            'contract_id': contract.id,
            'effective_date': '2027-01-01',
            'old_wage': 19000.0,
            'new_wage': 28000.0,
            'revision_type': 'annual_increment',
            'revision_basis': 'full_wage',
            'computation_type': 'fixed_amount',
            'state': 'approved',
        })
        contract.write({'wage': 28000.0})
        oct_emp.write({'hds_in_esic_applicable': oct_emp._evaluate_default_esic_applicable(eval_date='2027-01-01')})
        self.assertTrue(oct_emp.hds_in_esic_applicable, "Employee must remain ESIC applicable under Regulation 31")

        # February Payslip (Hike mid-period: must continue deductions)
        feb_slip = self.env['hr.payslip'].create({
            'employee_id': oct_emp.id,
            'date_from': '2027-02-01',
            'date_to': '2027-02-28',
        })
        self.assertTrue(self.validator.is_esic_eligible(feb_slip, gross_wage=28000.0))
        feb_svc = ESICService(self.env, localdict={'BASIC': 22000.0, 'HRA': 6000.0})
        self.assertEqual(feb_svc.compute_esic_wage(feb_slip), 28000.0)
        self.assertEqual(feb_svc.compute_esic_employee(feb_slip), 210.0)  # 28000 * 0.75% = 210
        self.assertEqual(feb_svc.compute_esic_employer(feb_slip), 910.0)  # 28000 * 3.25% = 910

        # March Payslip (End of period: must continue deductions)
        mar_slip = self.env['hr.payslip'].create({
            'employee_id': oct_emp.id,
            'date_from': '2027-03-01',
            'date_to': '2027-03-31',
        })
        self.assertTrue(self.validator.is_esic_eligible(mar_slip, gross_wage=28000.0))

        # April Payslip (Subsequent Period: must STOP)
        apr_slip = self.env['hr.payslip'].create({
            'employee_id': oct_emp.id,
            'date_from': '2027-04-01',
            'date_to': '2027-04-30',
        })
        self.assertFalse(self.validator.is_esic_eligible(apr_slip, gross_wage=28000.0))
        apr_svc = ESICService(self.env, localdict={'BASIC': 22000.0, 'HRA': 6000.0})
        self.assertEqual(apr_svc.compute_esic_wage(apr_slip), 0.0)

    # -------------------------------------------------------------------------
    # TEST 5: Direct Contract In-Place Wage Modification Guard
    # -------------------------------------------------------------------------
    def test_06_direct_contract_inplace_wage_edit_guard(self):
        """
        When HR directly edits contract wage on the contract form without a salary revision wizard:
        Regulation 31 guard in _sync_employee_esic_default & _onchange_wage_sync_esic
        must NOT drop ESIC applicability mid-period!
        """
        contract = self.employee.version_id or self.env['hr.version'].search([('employee_id', '=', self.employee.id)], limit=1)
        contract.write({
            'name': 'Contract Inplace Test',
            'wage': 20000.0,
            'date_start': '2026-04-01',
        })
        self.employee.write({'hds_in_esic_applicable': True, 'hds_in_esic_ip_status': 'active'})

        # Directly update contract wage to 27,000
        contract.write({'wage': 27000.0})

        # Employee ESIC must remain True
        self.assertTrue(self.employee.hds_in_esic_applicable)
        self.assertEqual(self.employee.hds_in_esic_ip_status, 'active')

    # -------------------------------------------------------------------------
    # TEST 6: Mid-Period Joiners
    # -------------------------------------------------------------------------
    def test_07_mid_period_joiner_coverage(self):
        """
        Mid-Period Joiner:
        - Joins May 15 @ ₹18,000 <= ₹21,000 -> Enrolled till September 30.
        - Joins May 15 @ ₹26,000 > ₹21,000 -> Exempt immediately.
        """
        joiner_eligible = self.env['hr.employee'].create({
            'name': 'May Eligible Joiner',
            'company_id': self.company.id,
            'wage': 18000.0,
        })
        self.assertTrue(joiner_eligible.hds_in_esic_applicable)
        self.assertEqual(joiner_eligible.hds_in_esic_ip_status, 'active')

        joiner_contract = joiner_eligible.version_id or self.env['hr.version'].search([('employee_id', '=', joiner_eligible.id)], limit=1)
        joiner_contract.write({
            'name': 'May Contract',
            'wage': 18000.0,
            'date_start': '2026-05-15',
        })
        self.assertTrue(self.period_service.is_covered_for_contribution_period(joiner_eligible, eval_date='2026-06-30'))

        joiner_exempt = self.env['hr.employee'].create({
            'name': 'May Exempt Joiner',
            'company_id': self.company.id,
            'wage': 26000.0,
        })
        self.assertFalse(joiner_exempt.hds_in_esic_applicable)
        self.assertEqual(joiner_exempt.hds_in_esic_ip_status, 'exempt')

    # -------------------------------------------------------------------------
    # TEST 7: Company-level and Employee-level Disablement
    # -------------------------------------------------------------------------
    def test_08_statutory_disablement_checks(self):
        """Disabling ESIC on company or employee stops calculations completely."""
        payslip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'date_from': '2026-04-01',
            'date_to': '2026-04-30',
        })

        # Company Disabled
        self.company.hds_in_esic_applicable = False
        self.company.invalidate_recordset()
        payslip.invalidate_recordset()
        self.assertFalse(self.validator.is_esic_eligible(payslip, gross_wage=20000.0))
        service = ESICService(self.env, localdict={'BASIC': 20000.0})
        self.assertEqual(service.compute_esic_wage(payslip), 0.0)

        # Re-enable Company, Disable Employee
        self.company.hds_in_esic_applicable = True
        self.company.invalidate_recordset()
        self.employee.hds_in_esic_applicable = False
        self.employee.invalidate_recordset()
        payslip.invalidate_recordset()
        self.assertFalse(self.validator.is_esic_eligible(payslip, gross_wage=20000.0))
        self.assertEqual(service.compute_esic_wage(payslip), 0.0)

    # -------------------------------------------------------------------------
    # TEST 8: Resignation / Exit Date Handling
    # -------------------------------------------------------------------------
    def test_09_employee_exit_date_and_resignation(self):
        """If employee resigned with exit date, payslips after exit date are not eligible."""
        self.employee.write({
            'hds_in_esic_exit_date': '2026-05-15',
            'hds_in_esic_ip_status': 'resigned',
        })

        # June Payslip (After exit date)
        jun_slip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'date_from': '2026-06-01',
            'date_to': '2026-06-30',
        })
        self.assertFalse(self.validator.is_esic_eligible(jun_slip, gross_wage=20000.0))

    # -------------------------------------------------------------------------
    # TEST 9: Loss of Pay (LOP) / Actual Earned Wage Calculation
    # -------------------------------------------------------------------------
    def test_10_actual_earned_wage_vs_contract_wage(self):
        """
        ESI contributions must be computed on ACTUAL earned gross wages,
        not nominal contract wage (e.g. when unpaid leaves reduce salary).
        """
        payslip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'date_from': '2026-04-01',
            'date_to': '2026-04-30',
        })
        # Employee took unpaid leave, actual gross reduced from 20k to 12k
        service = ESICService(self.env, localdict={'BASIC': 9000.0, 'HRA': 3000.0, 'GROSS': 12000.0})
        self.assertEqual(service.compute_esic_wage(payslip), 12000.0)
        self.assertEqual(service.compute_esic_employee(payslip), 90.0)  # 12000 * 0.75% = 90
        self.assertEqual(service.compute_esic_employer(payslip), 390.0)  # 12000 * 3.25% = 390

    # -------------------------------------------------------------------------
    # TEST 10: Contribution Period Bounds Helper
    # -------------------------------------------------------------------------
    def test_11_contribution_period_bounds_helper(self):
        """Validates April-Sep and Oct-Mar date boundary derivations."""
        # Month 5 (May) -> 2026-04-01 to 2026-09-30
        start, end = self.period_service.get_contribution_period_bounds(datetime.date(2026, 5, 10))
        self.assertEqual(start, datetime.date(2026, 4, 1))
        self.assertEqual(end, datetime.date(2026, 9, 30))

        # Month 9 (September) -> 2026-04-01 to 2026-09-30
        start, end = self.period_service.get_contribution_period_bounds(datetime.date(2026, 9, 30))
        self.assertEqual(start, datetime.date(2026, 4, 1))
        self.assertEqual(end, datetime.date(2026, 9, 30))

        # Month 10 (October) -> 2026-10-01 to 2027-03-31
        start, end = self.period_service.get_contribution_period_bounds(datetime.date(2026, 10, 1))
        self.assertEqual(start, datetime.date(2026, 10, 1))
        self.assertEqual(end, datetime.date(2027, 3, 31))

        # Month 2 (February 2027) -> 2026-10-01 to 2027-03-31
        start, end = self.period_service.get_contribution_period_bounds(datetime.date(2027, 2, 15))
        self.assertEqual(start, datetime.date(2026, 10, 1))
        self.assertEqual(end, datetime.date(2027, 3, 31))

    # -------------------------------------------------------------------------
    # TEST 11: Rule 51-B Daily-Wage Exemption (Configurable Threshold)
    # -------------------------------------------------------------------------
    def test_12_rule_51b_daily_wage_exemption(self):
        """
        ESI Rule 51-B: Employees with average daily wage <= ₹176/day are completely
        exempt from employee share of contribution. Employer share remains 3.25%.
        """
        # Case A: High Earner (₹15,000 / 30 days = ₹500/day > ₹176) -> NOT exempt
        slip_high = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'date_from': '2026-04-01',
            'date_to': '2026-04-30',
        })
        svc_high = ESICService(self.env, localdict={'ESIC_WAGE': 15000.0})
        is_exempt_a, avg_wage_a, paid_days_a, thresh = svc_high.check_daily_wage_exemption(slip_high, esic_wage=15000.0)
        self.assertFalse(is_exempt_a)
        self.assertEqual(avg_wage_a, 500.0)
        self.assertEqual(svc_high.compute_esic_employee(slip_high), 113.0)
        self.assertEqual(svc_high.compute_esic_employer(slip_high), 488.0)

        # Case B: Low Earner (₹4,000 / 26 days = ₹153.85/day <= ₹176) -> EXEMPT
        slip_low = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'date_from': '2026-04-01',
            'date_to': '2026-04-26',
        })
        svc_low = ESICService(self.env, localdict={'ESIC_WAGE': 4000.0})
        is_exempt_b, avg_wage_b, paid_days_b, _ = svc_low.check_daily_wage_exemption(slip_low, esic_wage=4000.0)
        self.assertTrue(is_exempt_b)
        self.assertEqual(avg_wage_b, 153.85)
        self.assertEqual(svc_low.compute_esic_employee(slip_low), 0.0)
        self.assertEqual(svc_low.compute_esic_employer(slip_low), 130.0)  # 3.25% of 4000 remains active

    # -------------------------------------------------------------------------
    # TEST 12: Rule 51-B LOP and Mid-Month Adjustments
    # -------------------------------------------------------------------------
    def test_13_rule_51b_lop_and_snapshot_persistence(self):
        """Validates that LOP reduces payable days and triggers exemption properly with audit snapshot."""
        slip_lop = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'date_from': '2026-05-01',
            'date_to': '2026-05-31',
            'worked_days_line_ids': [
                (0, 0, {'name': 'Attendance', 'code': 'WORK100', 'number_of_days': 5, 'number_of_hours': 40}),
                (0, 0, {'name': 'Loss of Pay', 'code': 'LOP', 'number_of_days': 26, 'number_of_hours': 208}),
            ]
        })
        svc = ESICService(self.env, localdict={'ESIC_WAGE': 800.0})
        ee_ded = svc.compute_esic_employee(slip_lop)
        er_ded = svc.compute_esic_employer(slip_lop)
        self.assertEqual(ee_ded, 0.0)
        self.assertEqual(er_ded, 26.0)
        self.assertTrue(slip_lop.hds_in_esic_daily_wage_exempt)
        self.assertEqual(slip_lop.hds_in_esic_average_daily_wage, 160.0)  # 800 / 5 days = 160 <= 176
        self.assertEqual(slip_lop.hds_in_esic_paid_days, 5.0)

    # -------------------------------------------------------------------------
    # TEST 13: Zero Wage Guard on Employee Form
    # -------------------------------------------------------------------------
    def test_14_zero_wage_esic_onchange_warning(self):
        """Validates that enabling ESIC when wage is 0 resets applicability to False and yields a warning."""
        zero_wage_emp = self.env['hr.employee'].create({
            'name': 'Zero Wage Employee',
            'company_id': self.company.id,
            'wage': 0.0,
        })
        zero_wage_emp.hds_in_esic_applicable = True
        res = zero_wage_emp._onchange_esic_applicable()
        self.assertFalse(zero_wage_emp.hds_in_esic_applicable)
        self.assertEqual(zero_wage_emp.hds_in_esic_ip_status, 'exempt')
        self.assertIn('warning', res)
        self.assertEqual(res['warning']['title'], "ESIC Not Applicable")


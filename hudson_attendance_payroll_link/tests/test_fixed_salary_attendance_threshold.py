# -*- coding: utf-8 -*-
"""
Unit Tests: Hybrid Attendance Threshold for Fixed Salary (Option B)
===================================================================
Tests verify:
    1. Full month unpaid leave (0 days worked) -> 0.0 factor, ₹0 salary, WORK100 exists with 0.
    2. Below threshold (e.g. worked 6 days < 14 days threshold) -> Salary prorated to actual worked days.
    3. Above threshold (e.g. worked 15 days >= 14 days threshold) -> 100% full fixed salary (grace period).
    4. Mid-month joiner -> Threshold scales proportionally with active contract scheduled days.
    5. Pay by attendance is ON -> 100% untouched and isolated (earned proration model).
    6. Threshold disabled (enable_attendance_threshold=False) -> Standard fixed salary behavior.
    7. Statutory integration -> No double deduction of unpaid leave in EPF / ESIC / PT.
"""

from unittest.mock import MagicMock, patch
from datetime import date
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase, tagged


@tagged('-at_install', 'post_install', 'hudson_threshold')
class TestFixedSalaryAttendanceThreshold(TransactionCase):
    """Unit tests for fixed salary attendance threshold calculation and payslip integration."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'enable_attendance_threshold': True,
            'min_attendance_threshold_days': 14.0,
        })

        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'Test Calendar 8h',
            'company_id': cls.company.id,
            'hours_per_day': 8.0,
            'tz': 'Asia/Kolkata',
        })

        cls.dept = cls.env['hr.department'].create({'name': 'Threshold Test Dept'})
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Fixed Salary Employee',
            'company_id': cls.company.id,
            'department_id': cls.dept.id,
            'resource_calendar_id': cls.calendar.id,
        })

        # Base structure
        cls.structure = cls.env.ref('hudson_payroll_base.structure_base', raise_if_not_found=False)
        if not cls.structure:
            cls.structure = cls.env['hr.payroll.structure'].create({
                'name': 'Base Test Structure',
                'type_id': cls.env['hr.payroll.structure.type'].search([], limit=1).id or False,
            })

        # Contract with fixed salary (pay_by_attendance=False)
        contract_vals = {
            'name': 'Fixed Salary Contract',
            'wage': 50000.0,
            'basic_salary': 25000.0,
            'hra': 12500.0,
            'da': 7500.0,
            'fixed_allowance': 5000.0,
            'pay_by_attendance': False,
            'enable_attendance_threshold': True,
            'min_attendance_threshold_days': 14.0,
            'date_start': date(2026, 9, 1),
            'resource_calendar_id': cls.calendar.id,
            'struct_id': cls.structure.id if cls.structure else False,
        }
        if cls.employee.version_id:
            cls.employee.version_id.write(contract_vals)
            cls.contract = cls.employee.version_id
        else:
            contract_vals['employee_id'] = cls.employee.id
            cls.contract = cls.env['hr.version'].create(contract_vals)

        cls.payslip = cls.env['hr.payslip'].create({
            'name': 'September 2026 Payslip',
            'employee_id': cls.employee.id,
            'contract_id': cls.contract.id,
            'struct_id': cls.structure.id if cls.structure else False,
            'date_from': date(2026, 9, 1),
            'date_to': date(2026, 9, 30),
        })

    def test_01_full_month_unpaid_leave_zero_salary(self):
        """When an employee takes full month unpaid leave (worked days = 0), factor is 0.0 and salary is 0."""
        mock_sched = {
            'scheduled_hours': 176.0,
            'scheduled_days': 22.0,
            'total_period_scheduled_hours': 176.0,
            'total_period_scheduled_days': 22.0,
            'out_of_contract_hours': 0.0,
            'out_of_contract_days': 0.0,
            'unpaid_hours': 176.0,
            'unpaid_days': 22.0,
            'earned_hours': 0.0,
            'earned_days': 0.0,
        }
        with patch.object(type(self.payslip), '_get_attendance_vs_schedule', return_value=mock_sched):
            factor = self.payslip._get_fixed_salary_attendance_factor(self.contract)
            self.assertEqual(factor, 0.0, "Factor must be 0.0 when employee took full month unpaid leave")

            # Check worked day lines
            lines = self.payslip.get_worked_day_lines(self.contract, date(2026, 9, 1), date(2026, 9, 30))
            work100 = next((l for l in lines if l['code'] == 'WORK100'), None)
            self.assertIsNotNone(work100, "WORK100 must still exist even if 0 days worked")
            self.assertEqual(work100['number_of_days'], 0.0)
            self.assertEqual(work100['number_of_hours'], 0.0)
            self.assertEqual(work100['amount'], 0.0)

    def test_02_below_threshold_prorated_salary(self):
        """When worked days fall below threshold (e.g. 6 days < 14 days), salary is prorated to 6 days."""
        # 22 scheduled days (176 hrs), 16 unpaid days (128 hrs) -> 6 worked days (48 hrs)
        mock_sched = {
            'scheduled_hours': 176.0,
            'scheduled_days': 22.0,
            'total_period_scheduled_hours': 176.0,
            'total_period_scheduled_days': 22.0,
            'out_of_contract_hours': 0.0,
            'out_of_contract_days': 0.0,
            'unpaid_hours': 128.0,
            'unpaid_days': 16.0,
            'earned_hours': 48.0,
            'earned_days': 6.0,
        }
        with patch.object(type(self.payslip), '_get_attendance_vs_schedule', return_value=mock_sched):
            factor = self.payslip._get_fixed_salary_attendance_factor(self.contract)
            expected_factor = 48.0 / 176.0  # 6 / 22 = 0.272727...
            self.assertAlmostEqual(factor, expected_factor, places=4,
                                   msg="Below threshold should prorate strictly to actual worked days")

            # Check worked day lines amount
            lines = self.payslip.get_worked_day_lines(self.contract, date(2026, 9, 1), date(2026, 9, 30))
            work100 = next((l for l in lines if l['code'] == 'WORK100'), None)
            self.assertIsNotNone(work100)
            self.assertEqual(work100['number_of_days'], 6.0)
            self.assertEqual(work100['number_of_hours'], 48.0)
            self.assertEqual(work100['amount'], round(50000.0 * (48.0 / 176.0), 2))

    def test_03_above_threshold_full_fixed_salary(self):
        """When worked days meet or exceed threshold (e.g. 15 days >= 14 days), employee receives 100% full fixed salary."""
        # 22 scheduled days (176 hrs), 7 unpaid days (56 hrs) -> 15 worked days (120 hrs)
        mock_sched = {
            'scheduled_hours': 176.0,
            'scheduled_days': 22.0,
            'total_period_scheduled_hours': 176.0,
            'total_period_scheduled_days': 22.0,
            'out_of_contract_hours': 0.0,
            'out_of_contract_days': 0.0,
            'unpaid_hours': 56.0,
            'unpaid_days': 7.0,
            'earned_hours': 120.0,
            'earned_days': 15.0,
        }
        with patch.object(type(self.payslip), '_get_attendance_vs_schedule', return_value=mock_sched):
            factor = self.payslip._get_fixed_salary_attendance_factor(self.contract)
            self.assertEqual(factor, 1.0, "Threshold met (15 >= 14) must award 100% full fixed salary")

            lines = self.payslip.get_worked_day_lines(self.contract, date(2026, 9, 1), date(2026, 9, 30))
            work100 = next((l for l in lines if l['code'] == 'WORK100'), None)
            self.assertIsNotNone(work100)
            self.assertEqual(work100['number_of_days'], 15.0)
            self.assertEqual(work100['number_of_hours'], 120.0)
            self.assertEqual(work100['amount'], 50000.0, "Full monthly wage must be paid when threshold is met")

    def test_04_mid_month_joiner_scaled_threshold(self):
        """Mid-month joiners scale the threshold proportionally:
        Total month: 22 days. Contract scheduled: 11 days. Threshold: 14 days -> Effective threshold = 14 * (11/22) = 7.0 days.
        """
        # Joiner worked 8 days (>= 7.0 effective threshold) -> Should get full mid-month fixed salary (11 / 22 = 0.5)
        mock_sched_qualified = {
            'scheduled_hours': 88.0,
            'scheduled_days': 11.0,
            'total_period_scheduled_hours': 176.0,
            'total_period_scheduled_days': 22.0,
            'out_of_contract_hours': 88.0,
            'out_of_contract_days': 11.0,
            'unpaid_hours': 24.0,
            'unpaid_days': 3.0,
            'earned_hours': 64.0,
            'earned_days': 8.0,
        }
        with patch.object(type(self.payslip), '_get_attendance_vs_schedule', return_value=mock_sched_qualified):
            factor = self.payslip._get_fixed_salary_attendance_factor(self.contract)
            # Met scaled threshold (8 >= 7.0): gets full tenure factor 88 / 176 = 0.5
            self.assertEqual(factor, 0.5, "Joiner meeting scaled threshold should get full mid-month tenure salary (0.5)")

        # Joiner worked only 3 days (< 7.0 effective threshold) -> Should get prorated factor 3 / 22 (24 hrs / 176 hrs)
        mock_sched_below = {
            'scheduled_hours': 88.0,
            'scheduled_days': 11.0,
            'total_period_scheduled_hours': 176.0,
            'total_period_scheduled_days': 22.0,
            'out_of_contract_hours': 88.0,
            'out_of_contract_days': 11.0,
            'unpaid_hours': 64.0,
            'unpaid_days': 8.0,
            'earned_hours': 24.0,
            'earned_days': 3.0,
        }
        with patch.object(type(self.payslip), '_get_attendance_vs_schedule', return_value=mock_sched_below):
            factor = self.payslip._get_fixed_salary_attendance_factor(self.contract)
            expected_factor = 24.0 / 176.0
            self.assertAlmostEqual(factor, expected_factor, places=4,
                                   msg="Joiner below scaled threshold should get prorated to actual worked days")

    def test_05_pay_by_attendance_active_isolated(self):
        """When pay_by_attendance is True, fixed salary threshold logic is completely bypassed."""
        self.contract.write({'pay_by_attendance': True})
        mock_sched = {
            'scheduled_hours': 176.0,
            'scheduled_days': 22.0,
            'total_period_scheduled_hours': 176.0,
            'total_period_scheduled_days': 22.0,
            'out_of_contract_hours': 0.0,
            'out_of_contract_days': 0.0,
            'unpaid_hours': 0.0,
            'unpaid_days': 0.0,
            'earned_hours': 100.0,  # Biometric earned hours
            'earned_days': 12.5,
        }
        with patch.object(type(self.payslip), '_get_attendance_vs_schedule', return_value=mock_sched):
            lines = self.payslip.get_worked_day_lines(self.contract, date(2026, 9, 1), date(2026, 9, 30))
            work100 = next((l for l in lines if l['code'] == 'WORK100'), None)
            self.assertIsNotNone(work100)
            self.assertEqual(work100['number_of_hours'], 100.0)
            self.assertEqual(work100['amount'], round(50000.0 * (100.0 / 176.0), 2))

    def test_06_threshold_disabled_on_contract(self):
        """When enable_attendance_threshold is False, employee gets standard fixed salary (unless 0 days worked)."""
        self.contract.write({'enable_attendance_threshold': False})

        # Case 1: 0 days worked still yields 0.0
        mock_zero = {
            'scheduled_hours': 176.0,
            'scheduled_days': 22.0,
            'total_period_scheduled_hours': 176.0,
            'total_period_scheduled_days': 22.0,
            'out_of_contract_hours': 0.0,
            'out_of_contract_days': 0.0,
            'unpaid_hours': 176.0,
            'unpaid_days': 22.0,
            'earned_hours': 0.0,
            'earned_days': 0.0,
        }
        with patch.object(type(self.payslip), '_get_attendance_vs_schedule', return_value=mock_zero):
            factor = self.payslip._get_fixed_salary_attendance_factor(self.contract)
            self.assertEqual(factor, 0.0, "Zero days worked must always yield 0.0 factor even if threshold is disabled")

        # Case 2: Worked 6 days (threshold disabled -> legacy fixed salary returns 1.0, UNPAID rule deducts)
        mock_worked = {
            'scheduled_hours': 176.0,
            'scheduled_days': 22.0,
            'total_period_scheduled_hours': 176.0,
            'total_period_scheduled_days': 22.0,
            'out_of_contract_hours': 0.0,
            'out_of_contract_days': 0.0,
            'unpaid_hours': 128.0,
            'unpaid_days': 16.0,
            'earned_hours': 48.0,
            'earned_days': 6.0,
        }
        with patch.object(type(self.payslip), '_get_attendance_vs_schedule', return_value=mock_worked):
            factor = self.payslip._get_fixed_salary_attendance_factor(self.contract)
            self.assertEqual(factor, 1.0, "When threshold is disabled, nominal salary factor is 1.0")

    def test_07_statutory_earned_wage_ratio_prevents_double_deduction(self):
        """When enable_attendance_threshold is True, hds_in_get_earned_wage_ratio returns 1.0 to prevent double deduction in PF/ESIC."""
        if hasattr(self.payslip, 'hds_in_get_earned_wage_ratio'):
            self.contract.write({'enable_attendance_threshold': True, 'pay_by_attendance': False})
            ratio = self.payslip.hds_in_get_earned_wage_ratio()
            self.assertEqual(ratio, 1.0, "Statutory earned wage ratio must be 1.0 when attendance threshold is enabled")

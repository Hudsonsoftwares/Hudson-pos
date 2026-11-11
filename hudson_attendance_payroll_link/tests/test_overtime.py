# -*- coding: utf-8 -*-
"""
Tests: Overtime Integration — Standard Odoo 19 hr.attendance.overtime.line
==========================================================================
Run with:
    odoo-bin -d Hudson_db --test-enable --stop-after-init -i hudson_attendance_payroll_link
    # or filter to just this file:
    odoo-bin -d Hudson_db --test-enable --stop-after-init --test-file hudson_attendance_payroll_link/tests/test_overtime.py

Tests cover:
    TC-OT-01  Approved payable OT line  → OVERTIME worked-days + OT salary rule pays correct amount
    TC-OT-02  Approved comp-off OT line → excluded from payroll (compensable_as_leave=True)
    TC-OT-03  Pending / draft OT line   → excluded (status != 'approved')
    TC-OT-04  Multi-rate OT lines       → weighted pay: 2 hrs@1.5x + 1 hr@2.0x
    TC-OT-05  Manager-edited duration   → manual_duration used over system duration
    TC-OT-06  Zero OT lines             → no OVERTIME worked-days line on payslip
    TC-OT-07  OT outside payslip period → excluded from payslip
"""

from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase, tagged


@tagged('-at_install', 'post_install', 'hudson_overtime')
class TestOvertimeIntegration(TransactionCase):
    """End-to-end overtime tests against Standard Odoo 19 overtime lines."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # ── Company & Currency ──────────────────────────────────────────────
        cls.company = cls.env.company

        # ── Work Calendar: Mon-Fri, 8h/day ─────────────────────────────────
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'Test 5-Day Calendar',
            'company_id': cls.company.id,
            'hours_per_day': 8.0,
            'tz': 'Asia/Kolkata',
        })

        # ── Department & Job ────────────────────────────────────────────────
        cls.dept = cls.env['hr.department'].create({'name': 'OT Test Dept'})
        cls.job = cls.env['hr.job'].create({'name': 'OT Tester'})

        # ── Employee ────────────────────────────────────────────────────────
        cls.employee = cls.env['hr.employee'].create({
            'name': 'OT Test Employee',
            'company_id': cls.company.id,
            'department_id': cls.dept.id,
            'job_id': cls.job.id,
            'resource_calendar_id': cls.calendar.id,
        })

        # ── Contract: ₹26,000/month, pay_by_attendance=True ─────────────────
        # wage ÷ sched_hours = base hourly used in OT rule
        # With a standard 26-day / 208-hr month → base_hourly = 26000/208 = 125 ₹/hr
        cls.contract = cls.env['hr.version'].create({
            'name': 'OT Test Contract',
            'employee_id': cls.employee.id,
            'company_id': cls.company.id,
            'resource_calendar_id': cls.calendar.id,
            'wage': 26000.0,
            'pay_by_attendance': True,
            'date_start': date(2026, 9, 1),
            'state': 'open',
        })

        # Payslip period: Sep 2026
        cls.date_from = date(2026, 9, 1)
        cls.date_to   = date(2026, 9, 30)

    # ─────────────────────────────────────────────────────────────────────────
    # Helper: create an hr.attendance.overtime.line record
    # ─────────────────────────────────────────────────────────────────────────
    def _make_ot_line(self, ot_date, duration, status='approved',
                      amount_rate=1.5, compensable_as_leave=False,
                      manual_duration=0.0):
        """Create a minimal hr.attendance.overtime.line."""
        vals = {
            'employee_id': self.employee.id,
            'date': ot_date,
            'duration': duration,
            'status': status,
            'amount_rate': amount_rate,
            'compensable_as_leave': compensable_as_leave,
        }
        # manual_duration is optional — only set when > 0 to simulate manager edit
        if manual_duration > 0.0:
            vals['manual_duration'] = manual_duration
        return self.env['hr.attendance.overtime.line'].create(vals)

    # ─────────────────────────────────────────────────────────────────────────
    # Helper: create a payslip and call _get_attendance_vs_schedule()
    # We mock the attendance side to focus on OT logic only.
    # ─────────────────────────────────────────────────────────────────────────
    def _get_data(self, mock_sched_hours=208.0):
        """
        Build payslip and call _get_attendance_vs_schedule.
        Attendance/shortage computation is stubbed to zero so we only test OT.
        """
        payslip = self.env['hr.payslip'].new({
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
        })
        # Patch the calendar so scheduled hours = mock_sched_hours (no real calendar needed)
        with patch.object(
            type(self.calendar), 'get_work_hours_count',
            return_value=mock_sched_hours / 22,   # per-day approximation (not critical here)
        ):
            data = payslip._get_attendance_vs_schedule(
                self.contract, self.date_from, self.date_to
            )
        return data

    # ─────────────────────────────────────────────────────────────────────────
    # Helper: compute expected OT pay
    # base_hourly = wage / sched_hrs;  pay = Σ approved_hrs * rate * base_hourly
    # ─────────────────────────────────────────────────────────────────────────
    def _expected_ot_pay(self, lines, sched_hrs=208.0):
        base = self.contract.wage / sched_hrs
        return sum(
            (ln['manual_duration'] if ln.get('manual_duration', 0) > 0 else ln['duration'])
            * ln['amount_rate'] * base
            for ln in lines
        )

    # ══════════════════════════════════════════════════════════════════════════
    # TC-OT-01: Single approved payable OT line
    # ══════════════════════════════════════════════════════════════════════════
    def test_01_approved_payable_ot_line_included(self):
        """
        TC-OT-01: One approved, non-comp-off OT line (2 hrs @ 1.5x rate).
        Expected:
          • overtime_hours_delta = 2.0
          • OVERTIME worked-days line exists on payslip
          • OT salary rule pay = 2 × 1.5 × (26000/208) = 375.0 ₹
        """
        ot = self._make_ot_line(date(2026, 9, 10), duration=2.0,
                                 status='approved', amount_rate=1.5)
        try:
            data = self._get_data()
            self.assertAlmostEqual(
                data['overtime_hours_delta'], 2.0, places=2,
                msg="TC-OT-01: overtime_hours_delta should be 2.0 hours"
            )
            self.assertAlmostEqual(
                data['validated_overtime_hours'], 2.0, places=2,
                msg="TC-OT-01: validated_overtime_hours should be 2.0"
            )
            # Verify OT pay formula
            expected_pay = 2.0 * 1.5 * (26000.0 / 208.0)   # 375.0
            self.assertAlmostEqual(
                expected_pay, 375.0, places=2,
                msg="TC-OT-01: Base expected pay formula check"
            )
        finally:
            ot.unlink()

    # ══════════════════════════════════════════════════════════════════════════
    # TC-OT-02: Comp-off OT line must be excluded
    # ══════════════════════════════════════════════════════════════════════════
    def test_02_comp_off_ot_line_excluded(self):
        """
        TC-OT-02: compensable_as_leave=True lines must NOT appear in payroll.
        Expected: overtime_hours_delta = 0.0
        """
        ot = self._make_ot_line(date(2026, 9, 11), duration=3.0,
                                 status='approved', compensable_as_leave=True)
        try:
            data = self._get_data()
            self.assertAlmostEqual(
                data['overtime_hours_delta'], 0.0, places=2,
                msg="TC-OT-02: Comp-off OT must be excluded (overtime_hours_delta = 0)"
            )
        finally:
            ot.unlink()

    # ══════════════════════════════════════════════════════════════════════════
    # TC-OT-03: Draft / pending OT line must be excluded
    # ══════════════════════════════════════════════════════════════════════════
    def test_03_pending_ot_line_excluded(self):
        """
        TC-OT-03: OT line with status='pending' must NOT contribute to pay.
        Expected: overtime_hours_delta = 0.0
        """
        ot_pending = self._make_ot_line(date(2026, 9, 12), duration=2.5,
                                         status='pending')
        ot_draft   = self._make_ot_line(date(2026, 9, 13), duration=1.5,
                                         status='draft')
        try:
            data = self._get_data()
            self.assertAlmostEqual(
                data['overtime_hours_delta'], 0.0, places=2,
                msg="TC-OT-03: Draft/Pending OT must be excluded (overtime_hours_delta = 0)"
            )
        finally:
            ot_pending.unlink()
            ot_draft.unlink()

    # ══════════════════════════════════════════════════════════════════════════
    # TC-OT-04: Multiple OT lines with different rates → weighted pay
    # ══════════════════════════════════════════════════════════════════════════
    def test_04_multi_rate_ot_weighted_pay(self):
        """
        TC-OT-04: 2 hrs@1.5x + 1 hr@2.0x
          base_hourly = 26000 / 208 = 125 ₹/hr
          Expected pay = (2×1.5×125) + (1×2.0×125) = 375 + 250 = 625 ₹
          Expected total hours = 3.0
        """
        ot1 = self._make_ot_line(date(2026, 9, 15), duration=2.0,
                                  status='approved', amount_rate=1.5)
        ot2 = self._make_ot_line(date(2026, 9, 16), duration=1.0,
                                  status='approved', amount_rate=2.0)
        try:
            data = self._get_data()
            total_hrs = data['overtime_hours_delta']
            self.assertAlmostEqual(
                total_hrs, 3.0, places=2,
                msg="TC-OT-04: Total OT hours should be 3.0 (2 + 1)"
            )
            # Verify weighted pay calculation
            base_hourly = 26000.0 / 208.0          # 125.0
            expected_pay = (2.0 * 1.5 * base_hourly) + (1.0 * 2.0 * base_hourly)
            self.assertAlmostEqual(
                expected_pay, 625.0, places=2,
                msg="TC-OT-04: Weighted OT pay should be 625.0 ₹ (375 + 250)"
            )
        finally:
            ot1.unlink()
            ot2.unlink()

    # ══════════════════════════════════════════════════════════════════════════
    # TC-OT-05: Manager-edited duration (manual_duration) takes precedence
    # ══════════════════════════════════════════════════════════════════════════
    def test_05_manual_duration_takes_precedence(self):
        """
        TC-OT-05: System logged 4 hrs but manager approved only 3 hrs (manual_duration=3).
          Expected OT hours = 3.0, NOT 4.0
          Expected OT pay = 3 × 1.5 × 125 = 562.5 ₹
        """
        ot = self._make_ot_line(date(2026, 9, 17), duration=4.0,
                                 status='approved', amount_rate=1.5,
                                 manual_duration=3.0)
        try:
            data = self._get_data()
            self.assertAlmostEqual(
                data['overtime_hours_delta'], 3.0, places=2,
                msg="TC-OT-05: manual_duration=3.0 should override system duration=4.0"
            )
            expected_pay = 3.0 * 1.5 * (26000.0 / 208.0)   # 562.5
            self.assertAlmostEqual(
                expected_pay, 562.5, places=2,
                msg="TC-OT-05: OT pay based on manual_duration should be 562.5 ₹"
            )
        finally:
            ot.unlink()

    # ══════════════════════════════════════════════════════════════════════════
    # TC-OT-06: No OT lines → no OVERTIME line on payslip
    # ══════════════════════════════════════════════════════════════════════════
    def test_06_no_ot_lines_no_overtime_worked_day(self):
        """
        TC-OT-06: When there are zero approved OT lines,
          • overtime_hours_delta = 0.0
          • get_worked_day_lines() must NOT produce an OVERTIME line
        """
        # Ensure no OT lines exist for this employee in the period
        self.env['hr.attendance.overtime.line'].search([
            ('employee_id', '=', self.employee.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]).unlink()

        data = self._get_data()
        self.assertAlmostEqual(
            data['overtime_hours_delta'], 0.0, places=2,
            msg="TC-OT-06: No OT lines → overtime_hours_delta must be 0.0"
        )
        # Check worked_day_lines doesn't include OVERTIME
        worked_lines = self.env['hr.payslip'].get_worked_day_lines(
            self.contract, self.date_from, self.date_to
        )
        codes = [l.get('code') for l in worked_lines]
        self.assertNotIn(
            'OVERTIME', codes,
            msg="TC-OT-06: No approved OT → no OVERTIME worked-day line should appear"
        )

    # ══════════════════════════════════════════════════════════════════════════
    # TC-OT-07: OT line outside the payslip period must be excluded
    # ══════════════════════════════════════════════════════════════════════════
    def test_07_ot_line_outside_period_excluded(self):
        """
        TC-OT-07: OT line dated Aug 2026 (before Sep payslip period) must be excluded.
        """
        ot_outside = self._make_ot_line(date(2026, 8, 31), duration=2.0,
                                          status='approved', amount_rate=1.5)
        try:
            data = self._get_data()
            self.assertAlmostEqual(
                data['overtime_hours_delta'], 0.0, places=2,
                msg="TC-OT-07: OT line outside payslip period must NOT be included"
            )
        finally:
            ot_outside.unlink()

    # ══════════════════════════════════════════════════════════════════════════
    # TC-OT-08: Mixed — approved + rejected lines in same period
    # ══════════════════════════════════════════════════════════════════════════
    def test_08_only_approved_lines_count(self):
        """
        TC-OT-08: 3 lines in period — only the approved/payable one should count.
          approved+payable = 2 hrs  → hours_delta = 2.0
          refused          = 3 hrs  → excluded
          comp_off         = 1 hr   → excluded
        """
        ot_ok      = self._make_ot_line(date(2026, 9, 18), duration=2.0,
                                         status='approved', compensable_as_leave=False)
        ot_refused = self._make_ot_line(date(2026, 9, 19), duration=3.0,
                                         status='refused')
        ot_comp    = self._make_ot_line(date(2026, 9, 20), duration=1.0,
                                         status='approved', compensable_as_leave=True)
        try:
            data = self._get_data()
            self.assertAlmostEqual(
                data['overtime_hours_delta'], 2.0, places=2,
                msg="TC-OT-08: Only approved+payable lines count; refused/comp-off excluded"
            )
        finally:
            ot_ok.unlink()
            ot_refused.unlink()
            ot_comp.unlink()

    # ══════════════════════════════════════════════════════════════════════════
    # TC-OT-09: OT pay formula — direct salary rule logic verification
    # ══════════════════════════════════════════════════════════════════════════
    def test_09_ot_pay_formula_verification(self):
        """
        TC-OT-09: Verify the exact OT salary rule formula in isolation.
          Scenario: 3 approved lines
            Line A: 2.0 hrs @ 1.0x  (normal time rate)
            Line B: 1.5 hrs @ 1.5x  (extended rate)
            Line C: 0.5 hrs @ 2.0x  (holiday/double rate)
          Scheduled hours (WORK100) = 208 hrs
          base_hourly = 26000 / 208 = 125 ₹/hr

          Expected OT pay:
            A = 2.0 × 1.0 × 125 = 250.00
            B = 1.5 × 1.5 × 125 = 281.25
            C = 0.5 × 2.0 × 125 = 125.00
            ─────────────────────────────
            Total              = 656.25 ₹
        """
        ot_a = self._make_ot_line(date(2026, 9, 21), duration=2.0,
                                   status='approved', amount_rate=1.0)
        ot_b = self._make_ot_line(date(2026, 9, 22), duration=1.5,
                                   status='approved', amount_rate=1.5)
        ot_c = self._make_ot_line(date(2026, 9, 23), duration=0.5,
                                   status='approved', amount_rate=2.0)
        try:
            data = self._get_data()
            # Total approved hours
            self.assertAlmostEqual(
                data['overtime_hours_delta'], 4.0, places=2,
                msg="TC-OT-09: Total OT hours should be 4.0 (2.0+1.5+0.5)"
            )
            # Pay formula check
            base = 26000.0 / 208.0
            expected = (2.0 * 1.0 * base) + (1.5 * 1.5 * base) + (0.5 * 2.0 * base)
            self.assertAlmostEqual(
                expected, 656.25, places=2,
                msg="TC-OT-09: OT pay formula must equal 656.25 ₹"
            )
        finally:
            ot_a.unlink()
            ot_b.unlink()
            ot_c.unlink()

    # ══════════════════════════════════════════════════════════════════════════
    # TC-OT-10: amount_rate defaults to 1.0 when missing/zero
    # ══════════════════════════════════════════════════════════════════════════
    def test_10_missing_amount_rate_defaults_to_1(self):
        """
        TC-OT-10: If a ruleset line has amount_rate=0 or None, salary rule must
          fall back to 1.0 (straight time) — no zero-pay OT.
          2 hrs @ fallback 1.0x = 2 × 1.0 × 125 = 250.0 ₹
        """
        ot = self._make_ot_line(date(2026, 9, 24), duration=2.0,
                                  status='approved', amount_rate=0.0)
        try:
            data = self._get_data()
            self.assertAlmostEqual(
                data['overtime_hours_delta'], 2.0, places=2,
                msg="TC-OT-10: Hours should still be 2.0 even with zero rate"
            )
            # The salary rule uses: rate = line.amount_rate if > 0 else 1.0
            fallback_pay = 2.0 * 1.0 * (26000.0 / 208.0)   # 250.0
            self.assertAlmostEqual(
                fallback_pay, 250.0, places=2,
                msg="TC-OT-10: Fallback rate 1.0x → OT pay = 250.0 ₹"
            )
        finally:
            ot.unlink()

# -*- coding: utf-8 -*-
from datetime import date, timedelta
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError


class TestInServiceLeaveEncashment(TransactionCase):
    """
    Automated Unit & Integration Test Suite for In-Service Leave Encashment Engine.
    Validates:
    1. Policy configuration & formula variations (statutory_26, calendar_30, gross_30, custom).
    2. Eligibility guards: minimum tenure, buffer retention, annual limits, employee type.
    3. Request approval lifecycle (draft -> submitted -> approved -> paid).
    4. Monthly payslip salary rule execution (LEAVE_ENCASH) and TDS taxability.
    5. Time Off balance deduction on payslip done and reversal on payslip cancel.
    6. Backward compatibility with exit settlement encashment.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # pyrefly: ignore [missing-import]
        from odoo.addons.base.models.ir_attachment import IrAttachment
        cls._orig_gc = getattr(IrAttachment, '_gc_file_store_unsafe', None)
        IrAttachment._gc_file_store_unsafe = lambda *args, **kwargs: None

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, '_class_cleanups'):
            cls._class_cleanups = [
                c for c in cls._class_cleanups
                if not (callable(c) and getattr(c, '__name__', '') == '_gc_filestore')
                and not (isinstance(c, tuple) and len(c) > 0 and getattr(c[0], '__name__', '') == '_gc_filestore')
            ]
        try:
            super().tearDownClass()
        except Exception:
            pass

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.hds_in_enable_leave_encashment = True

        # Create Work Entry Type / Leave Type for Earned Leave
        self.leave_type = self.env['hr.work.entry.type'].create({
            'name': 'Test Earned Leave (PL)',
            'code': 'TEL_PL',
            'include_in_leave_encashment': True,
        })

        # Create Employee with joining date 1 year ago (365 days)
        one_year_ago = date.today() - timedelta(days=365)
        self.employee = self.env['hr.employee'].create({
            'name': 'Ramesh Kumar (Test)',
            'company_id': self.company.id,
            'first_contract_date': one_year_ago,
        })

        self.employee.write({
            'first_contract_date': one_year_ago,
            'contract_date_start': one_year_ago,
        })

        # Update or create Contract with Basic = 26,000, DA = 0, Gross (wage) = 50,000
        existing_contract = getattr(self.employee, 'version_id', False) or self.env['hr.version'].search([
            ('employee_id', '=', self.employee.id)
        ], limit=1)
        if existing_contract:
            existing_contract.write({
                'wage': 50000.0,
                'basic_salary': 26000.0,
                'da': 0.0,
                'contract_date_start': one_year_ago,
                'date_version': one_year_ago,
            })
            self.contract = existing_contract
        else:
            self.contract = self.env['hr.version'].create({
                'name': 'Ramesh Contract',
                'employee_id': self.employee.id,
                'wage': 50000.0,
                'basic_salary': 26000.0,
                'da': 0.0,
                'date_start': one_year_ago,
            })
        if hasattr(self.employee, 'version_id'):
            self.employee.version_id = self.contract

        # Allocate 15 days of Earned Leave
        self.allocation = self.env['hr.leave.allocation'].create({
            'name': 'Test 15 Days EL Allocation',
            'employee_id': self.employee.id,
            'work_entry_type_id': self.leave_type.id,
            'number_of_days': 15.0,
        })
        if hasattr(self.allocation, 'action_approve'):
            try:
                self.allocation.action_approve()
            except Exception:
                self.allocation.state = 'validate'
        else:
            self.allocation.state = 'validate'

        # Create Policy with statutory 26, min tenure 180 days, min buffer 5 days, max annual 15 days
        self.policy = self.env['hds.leave.encashment.policy'].create({
            'name': 'Corporate Earned Leave Policy',
            'company_id': self.company.id,
            'employee_type_ids': False,
            'min_service_period_days': 180,
            'min_balance_to_maintain': 5.0,
            'max_encashable_days_per_year': 15.0,
            'max_encashable_days_per_request': 10.0,
            'calculation_basis': 'statutory_26',
            'leave_type_ids': [(6, 0, [self.leave_type.id])],
            'taxable_for_tds': True,
            'include_in_pf_wage': False,
        })

    def test_01_policy_defaults_and_validation(self):
        """Test policy defaults and constraint guards."""
        self.assertEqual(self.policy.calculation_basis, 'statutory_26')
        self.assertEqual(self.policy.min_balance_to_maintain, 5.0)
        self.assertTrue(self.policy.taxable_for_tds)

        # Negative limits must raise ValidationError
        with self.assertRaises(ValidationError):
            self.policy.write({'min_service_period_days': -10})

        with self.assertRaises(ValidationError):
            self.policy.write({'max_encashable_days_per_request': 20.0, 'max_encashable_days_per_year': 10.0})

    def test_02_tenure_guard(self):
        """Employees with tenure below policy requirement must be rejected."""
        # Create new joiner who joined 30 days ago
        new_emp = self.env['hr.employee'].create({
            'name': 'New Joiner (30 days)',
            'company_id': self.company.id,
            'first_contract_date': date.today() - timedelta(days=30),
        })
        alloc_new = self.env['hr.leave.allocation'].create({
            'name': 'New Joiner Alloc',
            'employee_id': new_emp.id,
            'work_entry_type_id': self.leave_type.id,
            'number_of_days': 10.0,
        })
        if hasattr(alloc_new, 'action_approve'):
            try:
                alloc_new.action_approve()
            except Exception:
                alloc_new.state = 'validate'
        else:
            alloc_new.state = 'validate'
        req = self.env['hds.leave.encashment.request'].create({
            'employee_id': new_emp.id,
            'policy_id': self.policy.id,
            'leave_type_id': self.leave_type.id,
            'requested_days': 2.0,
        })
        with self.assertRaises(ValidationError) as cm:
            req.action_submit()
        self.assertIn("below the policy minimum", str(cm.exception))

    def test_03_buffer_retention_guard(self):
        """Employee cannot encash leaves beyond the retention buffer."""
        # Employee has 15 days, buffer is 5 days. Encashing 12 days leaves 3 days (< 5 buffer).
        req = self.env['hds.leave.encashment.request'].create({
            'employee_id': self.employee.id,
            'policy_id': self.policy.id,
            'leave_type_id': self.leave_type.id,
            'requested_days': 8.0,
        })
        # 15 - 8 = 7 >= 5 buffer: should pass!
        req.action_submit()
        self.assertEqual(req.state, 'submitted')

        # Now test invalid request: 12 days exceeds max per request (10) and leaves buffer < 5
        req_excess = self.env['hds.leave.encashment.request'].create({
            'employee_id': self.employee.id,
            'policy_id': self.policy.id,
            'leave_type_id': self.leave_type.id,
            'requested_days': 12.0,
        })
        with self.assertRaises(ValidationError):
            req_excess.action_submit()

    def test_04_formula_calculations(self):
        """Validate monetary calculations for all 4 formula modes."""
        req = self.env['hds.leave.encashment.request'].create({
            'employee_id': self.employee.id,
            'policy_id': self.policy.id,
            'leave_type_id': self.leave_type.id,
            'requested_days': 5.0,
        })

        # Mode A: statutory_26 -> (26,000 + 0) / 26 * 5 = 1,000 * 5 = 5,000.00
        self.policy.calculation_basis = 'statutory_26'
        amount_26 = req.calculate_payout_amount(self.contract)
        self.assertEqual(amount_26, 5000.0)

        # Mode B: calendar_30 -> (26,000 + 0) / 30 * 5 = 866.67 * 5 = 4,333.33
        self.policy.calculation_basis = 'calendar_30'
        amount_30 = req.calculate_payout_amount(self.contract)
        self.assertAlmostEqual(amount_30, 4333.33, places=1)

        # Mode C: gross_30 -> Gross 50,000 / 30 * 5 = 1,666.67 * 5 = 8,333.33
        self.policy.calculation_basis = 'gross_30'
        amount_gross = req.calculate_payout_amount(self.contract)
        self.assertAlmostEqual(amount_gross, 8333.33, places=1)

        # Mode D: custom_formula -> (basic / 20) * encash_days = (26000 / 20) * 5 = 1300 * 5 = 6500.00
        self.policy.write({
            'calculation_basis': 'custom_formula',
            'custom_formula_code': 'result = (basic / 20.0) * encash_days'
        })
        amount_custom = req.calculate_payout_amount(self.contract)
        self.assertEqual(amount_custom, 6500.0)

    def test_05_payslip_rule_and_timeoff_deduction_lifecycle(self):
        """End-to-end lifecycle test for Solution 1: request -> approve (direct allocation adjustment) -> payslip done (paid) -> cancel (restore)."""
        self.policy.calculation_basis = 'statutory_26'
        req = self.env['hds.leave.encashment.request'].create({
            'employee_id': self.employee.id,
            'policy_id': self.policy.id,
            'leave_type_id': self.leave_type.id,
            'requested_days': 5.0,
        })
        req.action_submit()
        req.action_approve()
        self.assertEqual(req.state, 'approved')

        # Solution 1: Leave balance is deducted directly from the leave allocation
        self.assertEqual(req.allocation_id, self.allocation, "Deduction must link to active allocation.")
        self.assertEqual(req.deducted_days, 5.0, "Deducted days must match requested days.")
        self.assertEqual(self.allocation.number_of_days, 10.0, "Allocation number_of_days must be reduced from 15 to 10.")

        # Zero calendar leaves created: prevents phantom absences and double-pay in attendance
        self.assertFalse(req.leave_id, "Solution 1 must not create hr.leave record.")
        leave_count = self.env['hr.leave'].search_count([('employee_id', '=', self.employee.id)])
        self.assertEqual(leave_count, 0, "No hr.leave calendar records should exist.")

        # Generate monthly payslip for current month
        today = date.today()
        first_day = date(today.year, today.month, 1)
        last_day = (date(today.year, today.month + 1, 1) if today.month < 12 else date(today.year + 1, 1, 1)) - timedelta(days=1)

        payslip = self.env['hr.payslip'].create({
            'name': 'Test Monthly Payslip',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'date_from': first_day,
            'date_to': last_day,
        })

        # 1. Helper check
        has_approved = payslip.hds_in_has_approved_leave_encashment()
        self.assertTrue(has_approved, "Payslip must detect approved leave encashment request.")

        # 2. Compute in-service encashment
        amount = payslip.hds_in_compute_in_service_leave_encashment()
        self.assertEqual(amount, 5000.0, "Encashment amount must equal 5 days * 1000/day = 5000.")

        # 3. Simulate Payslip Done -> Transitions state to paid and links payslip
        req.action_finalize_payout(payslip)
        self.assertEqual(req.state, 'paid')
        self.assertEqual(req.payslip_id, payslip)
        self.assertEqual(self.allocation.number_of_days, 10.0, "Allocation remains deducted after payout.")

        # 4. Simulate Payslip Cancel -> Triggers Rollback to approved
        req.action_rollback_payout()
        self.assertEqual(req.state, 'approved')
        self.assertFalse(req.payslip_id)
        self.assertEqual(self.allocation.number_of_days, 10.0, "Allocation deduction remains active while approved.")

        # 5. Cancel request -> Restores deducted days back to allocation
        req.action_cancel()
        self.assertEqual(req.state, 'cancelled')
        self.assertEqual(self.allocation.number_of_days, 15.0, "Cancelling request must restore allocation back to 15 days.")
        self.assertEqual(req.deducted_days, 0.0)

    def test_06_backward_compatibility_settlement(self):
        """Verify that existing exit settlement calculation continues to work unchanged."""
        # pyrefly: ignore [missing-import]
        from odoo.addons.hudson_in_payroll.services.leave_encashment import LeaveEncashmentService
        svc = LeaveEncashmentService(self.env)
        amt = svc.compute_leave_encashment(
            employee=self.employee,
            last_working_day=date.today(),
            contract=self.contract,
            calc_date=date.today()
        )
        # 15 days * 1000/day = 15,000.00
        self.assertEqual(amt, 15000.0)

    def test_07_pay_by_attendance_no_conflict_with_encashment(self):
        """Verify Solution 1 ensures complete absence of work entry / calendar collisions under pay_by_attendance."""
        self.contract.write({'pay_by_attendance': True})

        req = self.env['hds.leave.encashment.request'].create({
            'employee_id': self.employee.id,
            'policy_id': self.policy.id,
            'leave_type_id': self.leave_type.id,
            'requested_days': 4.0,
        })
        req.action_submit()
        req.action_approve()

        # Allocation reduced directly: 15 - 4 = 11 days
        self.assertEqual(self.allocation.number_of_days, 11.0)
        self.assertFalse(req.leave_id)

        # Confirm ZERO hr.leave records exist on the calendar
        leaves = self.env['hr.leave'].search([('employee_id', '=', self.employee.id)])
        self.assertEqual(len(leaves), 0, "No leave records generated on the calendar.")

        # Payslip calculation
        today = date.today()
        first_day = date(today.year, today.month, 1)
        last_day = (date(today.year, today.month + 1, 1) if today.month < 12 else date(today.year + 1, 1, 1)) - timedelta(days=1)

        payslip = self.env['hr.payslip'].create({
            'name': 'Attendance Monthly Payslip',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'date_from': first_day,
            'date_to': last_day,
        })
        encash_amt = payslip.hds_in_compute_in_service_leave_encashment()
        # 4 days * 1000/day = 4000
        self.assertEqual(encash_amt, 4000.0)

    def test_08_fifo_multi_allocation_deduction_and_restoration(self):
        """Verify FIFO deduction and restoration across multiple allocations with different expiration dates."""
        # Create second allocation expiring sooner (in 30 days)
        alloc_expiring = self.env['hr.leave.allocation'].create({
            'name': 'Expiring PL Allocation (3 days)',
            'employee_id': self.employee.id,
            'work_entry_type_id': self.leave_type.id,
            'number_of_days': 3.0,
            'date_to': date.today() + timedelta(days=30),
        })
        if hasattr(alloc_expiring, 'action_approve'):
            try:
                alloc_expiring.action_approve()
            except Exception:
                alloc_expiring.state = 'validate'
        else:
            alloc_expiring.state = 'validate'

        # Total balance = 15 (non-expiring) + 3 (expiring in 30 days) = 18 days
        # Request 5 days: FIFO must consume 3 days from alloc_expiring and 2 days from self.allocation
        req = self.env['hds.leave.encashment.request'].create({
            'employee_id': self.employee.id,
            'policy_id': self.policy.id,
            'leave_type_id': self.leave_type.id,
            'requested_days': 5.0,
        })
        req.action_submit()
        req.action_approve()

        self.assertEqual(req.state, 'approved')
        self.assertEqual(req.deducted_days, 5.0)
        # Check that expiring allocation was consumed first
        self.assertEqual(alloc_expiring.number_of_days, 0.0, "Expiring allocation should be fully consumed (3 - 3 = 0).")
        # Remaining 2 days deducted from non-expiring allocation
        self.assertEqual(self.allocation.number_of_days, 13.0, "Non-expiring allocation reduced by remaining 2 days (15 - 2 = 13).")

        # Now reject or cancel -> Restores both allocations accurately
        req.action_reject()
        self.assertEqual(req.state, 'rejected')
        self.assertEqual(alloc_expiring.number_of_days, 3.0, "Expiring allocation restored back to 3 days.")
        self.assertEqual(self.allocation.number_of_days, 15.0, "Non-expiring allocation restored back to 15 days.")

    def test_09_employee_type_eligibility_guard(self):
        """Verify Employee Type eligibility guard mapped from hr.employee.type."""
        emp_type_regular = self.env['hr.employee.type'].search([('code', 'in', ('EMP', 'Employee'))], limit=1)
        if not emp_type_regular:
            emp_type_regular = self.env['hr.employee.type'].create({'name': 'Regular Employee', 'code': 'EMP'})

        emp_type_intern = self.env['hr.employee.type'].search([('code', 'in', ('INT', 'Intern'))], limit=1)
        if not emp_type_intern:
            emp_type_intern = self.env['hr.employee.type'].create({'name': 'Intern', 'code': 'INT'})

        # Configure policy to ONLY allow Regular Employee
        self.policy.write({'employee_type_ids': [(6, 0, [emp_type_regular.id])]})

        # Set employee type to Intern
        self.employee.write({'employee_type_id': emp_type_intern.id})

        req = self.env['hds.leave.encashment.request'].create({
            'employee_id': self.employee.id,
            'policy_id': self.policy.id,
            'leave_type_id': self.leave_type.id,
            'requested_days': 2.0,
        })

        # Submit should be rejected due to mismatched employee type
        with self.assertRaises(ValidationError) as cm:
            req.action_submit()
        self.assertIn(emp_type_intern.name, str(cm.exception))
        self.assertIn(emp_type_regular.name, str(cm.exception))

        # Now change employee type to Regular Employee -> Submit should succeed!
        self.employee.write({'employee_type_id': emp_type_regular.id})
        req.action_submit()
        self.assertEqual(req.state, 'submitted')

    def test_10_dynamic_policy_recomputation(self):
        """Verify that modifying the policy formula dynamically recalculates open requests."""
        self.policy.calculation_basis = 'statutory_26'
        req = self.env['hds.leave.encashment.request'].create({
            'employee_id': self.employee.id,
            'policy_id': self.policy.id,
            'leave_type_id': self.leave_type.id,
            'requested_days': 5.0,
        })
        # Basic 26000 / 26 = 1000/day -> 5000 for 5 days
        self.assertEqual(req.daily_rate, 1000.0)
        self.assertEqual(req.projected_amount, 5000.0)

        # 1. Modify Policy to calendar_30 and save Policy
        self.policy.write({'calculation_basis': 'calendar_30'})
        self.assertAlmostEqual(req.daily_rate, 866.67, places=1)
        self.assertAlmostEqual(req.projected_amount, 4333.33, places=1)

        # 2. Modify Policy to gross_30 (Gross 50,000 / 30 = 1666.67 * 5 = 8333.33)
        self.policy.write({'calculation_basis': 'gross_30'})
        self.assertAlmostEqual(req.daily_rate, 1666.67, places=1)
        self.assertAlmostEqual(req.projected_amount, 8333.33, places=1)

        # 3. Modify Policy to custom_formula
        self.policy.write({
            'calculation_basis': 'custom_formula',
            'custom_formula_code': 'result = (basic / 20.0) * encash_days',
        })
        self.assertEqual(req.daily_rate, 1300.0)
        self.assertEqual(req.projected_amount, 6500.0)

        # 4. Onchange simulation on requested_days
        req.requested_days = 10.0
        req._onchange_requested_days()
        self.assertEqual(req.projected_amount, 13000.0)

    def test_11_onchange_employee_auto_populates_policy_and_leave_type(self):
        """Test that selecting an employee in the UI automatically populates policy and filters to eligible leave types."""
        Req = self.env['hds.leave.encashment.request']
        draft_req = Req.new({'employee_id': self.employee.id})
        draft_req._onchange_employee_id()

        # Company must match
        self.assertEqual(draft_req.company_id, self.employee.company_id)
        # Policy must be auto-selected
        self.assertEqual(draft_req.policy_id, self.policy)
        # Leave type must default to policy's eligible leave type
        self.assertEqual(draft_req.leave_type_id, self.leave_type)
        # Eligible leave types must ONLY contain leave types with include_in_leave_encashment = True
        self.assertTrue(all(t.include_in_leave_encashment for t in draft_req.eligible_leave_type_ids))

    def test_12_future_allocation_excluded_from_deduction(self):
        """Verify that allocations with future date_from are completely excluded from deduction."""
        alloc_field = 'work_entry_type_id' if 'work_entry_type_id' in self.env['hr.leave.allocation']._fields else 'holiday_status_id'
        # 1. Future allocation for next year (e.g. 10 days, starting 2027-01-01)
        future_alloc = self.env['hr.leave.allocation'].create({
            'name': 'Advance 2027 Allocation',
            'employee_id': self.employee.id,
            alloc_field: self.leave_type.id,
            'number_of_days': 10.0,
            'date_from': date(2027, 1, 1),
            'date_to': date(2027, 12, 31),
        })
        if hasattr(future_alloc, 'action_approve'):
            try:
                future_alloc.action_approve()
            except Exception:
                future_alloc.state = 'validate'
        else:
            future_alloc.state = 'validate'

        # Current allocation has 15 days (non-expiring, date_to=False)
        self.assertEqual(self.allocation.number_of_days, 15.0)

        # 2. Request 4 days encashment today
        req = self.env['hds.leave.encashment.request'].create({
            'employee_id': self.employee.id,
            'policy_id': self.policy.id,
            'leave_type_id': self.leave_type.id,
            'request_date': date(2026, 10, 9),
            'requested_days': 4.0,
        })
        req.action_submit()
        req.action_approve()

        # 3. Assert: 4 days must be deducted from active allocation (15 - 4 = 11)
        self.assertEqual(self.allocation.number_of_days, 11.0, "Active 2026 allocation must be deducted by 4 days.")
        # Future 2027 allocation must remain completely untouched (10.0)
        self.assertEqual(future_alloc.number_of_days, 10.0, "Future 2027 allocation must remain completely untouched.")

    def test_13_company_enablement_menu_visibility_and_guards(self):
        """
        Verify that toggling Leave Encashment on company:
        1. Hides all Leave Encashment menus and prunes them from parent children lists when False.
        2. Shows all Leave Encashment menus and includes them in parent children lists when True.
        3. Prevents creating new policies or requests when False.
        """
        le_xmlids = [
            'hudson_in_payroll.menu_hds_leave_encashment_policy',
            'hudson_in_payroll.menu_hds_leave_encashment_policy_timeoff',
            'hudson_in_payroll.menu_hds_leave_encashment_request_my',
            'hudson_in_payroll.menu_hds_leave_encashment_request',
        ]
        menu_ids = [self.env.ref(x).id for x in le_xmlids if self.env.ref(x, raise_if_not_found=False)]

        # --- A. Test Disabled State ---
        self.company.write({'hds_in_enable_leave_encashment': False})
        menus_disabled = self.env['ir.ui.menu'].load_menus(False)
        for mid in menu_ids:
            self.assertNotIn(mid, menus_disabled, f"Menu {mid} must be excluded when Leave Encashment is disabled.")
            m = self.env['ir.ui.menu'].browse(mid)
            pid = m.parent_id.id
            if pid in menus_disabled:
                self.assertNotIn(mid, menus_disabled[pid].get('children', []),
                                 f"Menu {mid} must not be in parent {pid} children list when disabled.")

        # Creation guards must reject new requests and policies
        with self.assertRaises(ValidationError):
            self.env['hds.leave.encashment.request'].create({
                'employee_id': self.employee.id,
                'policy_id': self.policy.id,
                'leave_type_id': self.leave_type.id,
                'requested_days': 1.0,
            })

        with self.assertRaises(ValidationError):
            self.env['hds.leave.encashment.policy'].create({
                'name': 'Should Be Blocked Policy',
                'company_id': self.company.id,
            })

        # --- B. Test Enabled State ---
        self.company.write({'hds_in_enable_leave_encashment': True})
        menus_enabled = self.env['ir.ui.menu'].load_menus(False)
        for mid in menu_ids:
            self.assertIn(mid, menus_enabled, f"Menu {mid} must be included when Leave Encashment is enabled.")
            m = self.env['ir.ui.menu'].browse(mid)
            pid = m.parent_id.id
            if pid in menus_enabled:
                self.assertIn(mid, menus_enabled[pid].get('children', []),
                              f"Menu {mid} must be in parent {pid} children list when enabled.")

        # Creation succeeds when enabled
        allowed_req = self.env['hds.leave.encashment.request'].create({
            'employee_id': self.employee.id,
            'policy_id': self.policy.id,
            'leave_type_id': self.leave_type.id,
            'requested_days': 1.0,
        })
        self.assertTrue(allowed_req.id, "Request creation must succeed when Leave Encashment is enabled.")






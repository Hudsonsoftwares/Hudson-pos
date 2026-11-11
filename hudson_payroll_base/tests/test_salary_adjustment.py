# -*- coding: utf-8 -*-
from datetime import date
from odoo.tests.common import TransactionCase
from odoo.tests import Form
from odoo.exceptions import ValidationError, UserError


class TestSalaryAdjustment(TransactionCase):
    """
    Test suite for Salary Adjustment in Hudson Payroll Base.
    Completely country-independent and localization-agnostic.
    """

    @classmethod
    def _gc_filestore(cls):
        # Override Windows filestore temp file GC assertion
        pass

    def setUp(self):
        super().setUp()
        self.SalaryAdjustment = self.env['hr.salary.adjustment']
        self.SalaryAdjWizard = self.env['hr.salary.adjustment.wizard']
        self.Payslip = self.env['hr.payslip']
        self.Employee = self.env['hr.employee']
        self.Contract = self.env['hr.version']
        self.InputType = self.env['hr.payslip.input.type']
        self.Company = self.env['res.company']

        self.company = self.env.company

        # Ensure base structure exists
        self.structure = self.env.ref('hudson_payroll_base.structure_base', raise_if_not_found=False)
        if not self.structure:
            self.structure = self.env['hr.payroll.structure'].search([], limit=1)

        # Global, country-independent input types (country_id = False)
        self.input_type_child_support = self.InputType.search([('code', '=', 'CHILD_SUPPORT')], limit=1)
        if not self.input_type_child_support:
            self.input_type_child_support = self.InputType.create({
                'name': 'Child Support',
                'code': 'CHILD_SUPPORT',
                'country_id': False,
            })

        self.input_type_deduction = self.InputType.search([('code', '=', 'DEDUCTION')], limit=1)
        if not self.input_type_deduction:
            self.input_type_deduction = self.InputType.create({
                'name': 'Deduction',
                'code': 'DEDUCTION',
                'country_id': False,
            })

        self.input_type_reimbursement = self.InputType.search([('code', '=', 'REIMBURSEMENT')], limit=1)
        if not self.input_type_reimbursement:
            self.input_type_reimbursement = self.InputType.create({
                'name': 'Reimbursement',
                'code': 'REIMBURSEMENT',
                'country_id': False,
            })

        # Test employees (Generic / Country-agnostic)
        self.employee_1 = self.Employee.create({
            'name': 'Alex Morgan',
            'company_id': self.company.id,
        })
        self.employee_2 = self.Employee.create({
            'name': 'Jordan Lee',
            'company_id': self.company.id,
        })

        # Setup contracts
        if self.employee_1.version_id:
            self.contract_1 = self.employee_1.version_id
            self.contract_1.write({
                'wage': 50000.0,
                'basic_salary': 25000.0,
                'struct_id': self.structure.id if self.structure else False,
                'contract_date_start': date(2026, 1, 1),
            })
        else:
            self.contract_1 = self.Contract.create({
                'name': 'Contract - Alex Morgan',
                'employee_id': self.employee_1.id,
                'company_id': self.company.id,
                'wage': 50000.0,
                'basic_salary': 25000.0,
                'struct_id': self.structure.id if self.structure else False,
                'contract_date_start': date(2026, 1, 1),
            })
            self.employee_1.version_id = self.contract_1

        if self.employee_2.version_id:
            self.contract_2 = self.employee_2.version_id
            self.contract_2.write({
                'wage': 40000.0,
                'basic_salary': 20000.0,
                'struct_id': self.structure.id if self.structure else False,
                'contract_date_start': date(2026, 1, 1),
            })
        else:
            self.contract_2 = self.Contract.create({
                'name': 'Contract - Jordan Lee',
                'employee_id': self.employee_2.id,
                'company_id': self.company.id,
                'wage': 40000.0,
                'basic_salary': 20000.0,
                'struct_id': self.structure.id if self.structure else False,
                'contract_date_start': date(2026, 1, 1),
            })
            self.employee_2.version_id = self.contract_2

    def test_01_one_time_adjustment_sync_and_completion(self):
        """Test one-time adjustment syncs into payslip inputs and auto-completes on slip confirmation."""
        adj = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'input_type_id': self.input_type_child_support.id,
            'amount': 5000.0,
            'duration': 'one_time',
            'date_start': date(2026, 9, 1),
            'note': 'Court Ordered Child Support',
        })
        self.assertEqual(adj.state, 'running')

        slip = self.Payslip.create({
            'name': 'Payslip Sep 2026',
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 9, 1),
            'date_to': date(2026, 9, 30),
        })
        slip.action_compute_sheet()

        # Check input line created
        input_line = slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj)
        self.assertTrue(input_line, "Payslip should have an input line linked to the adjustment")
        self.assertEqual(input_line.amount, 5000.0)
        self.assertEqual(input_line.code, 'CHILD_SUPPORT')

        # Confirm payslip
        slip.action_payslip_done()
        self.assertEqual(slip.state, 'done')
        self.assertEqual(adj.state, 'done', "One-time adjustment should be marked done after payslip confirmation")

    def test_02_limited_adjustment_date_boundary(self):
        """Test limited duration adjustment applies within date range and excludes outside."""
        adj = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'input_type_id': self.input_type_reimbursement.id,
            'amount': 2500.0,
            'duration': 'limited',
            'date_start': date(2026, 8, 1),
            'date_end': date(2026, 9, 30),
            'note': 'Internet Reimbursement Q3',
        })

        # Payslip within range (Sep 2026)
        slip_sep = self.Payslip.create({
            'name': 'Payslip Sep 2026',
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 9, 1),
            'date_to': date(2026, 9, 30),
        })
        slip_sep.action_compute_sheet()
        self.assertTrue(slip_sep.input_line_ids.filtered(lambda l: l.adjustment_id == adj))

        # Payslip outside range (Oct 2026)
        slip_oct = self.Payslip.create({
            'name': 'Payslip Oct 2026',
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 10, 1),
            'date_to': date(2026, 10, 31),
        })
        slip_oct.action_compute_sheet()
        self.assertFalse(slip_oct.input_line_ids.filtered(lambda l: l.adjustment_id == adj))

    def test_03_limited_adjustment_with_until_amount_cap(self):
        """Test until_amount capping behavior across multiple payslips."""
        adj = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'input_type_id': self.input_type_deduction.id,
            'amount': 3000.0,
            'duration': 'limited',
            'date_start': date(2026, 1, 1),
            'date_end': date(2026, 12, 31),
            'until_amount': 5000.0,
            'note': 'Equipment Advance Recovery',
        })

        # Period 1: Sep 2026 -> should take full 3000
        slip_1 = self.Payslip.create({
            'name': 'Slip Sep',
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 9, 1),
            'date_to': date(2026, 9, 30),
        })
        slip_1.action_compute_sheet()
        inp_1 = slip_1.input_line_ids.filtered(lambda l: l.adjustment_id == adj)
        self.assertEqual(inp_1.amount, 3000.0)
        slip_1.action_payslip_done()

        # Period 2: Oct 2026 -> should cap remaining at 2000 (5000 - 3000)
        slip_2 = self.Payslip.create({
            'name': 'Slip Oct',
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 10, 1),
            'date_to': date(2026, 10, 31),
        })
        slip_2.action_compute_sheet()
        inp_2 = slip_2.input_line_ids.filtered(lambda l: l.adjustment_id == adj)
        self.assertEqual(inp_2.amount, 2000.0, "Input amount must be capped at remaining until_amount")
        slip_2.action_payslip_done()
        self.assertEqual(adj.state, 'done', "Adjustment should be done once until_amount cap is reached")

    def test_04_unlimited_adjustment(self):
        """Test unlimited adjustment persists indefinitely across payslips."""
        adj = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'input_type_id': self.input_type_reimbursement.id,
            'amount': 1200.0,
            'duration': 'unlimited',
            'date_start': date(2026, 1, 1),
            'note': 'Monthly Mobile Allowance Input',
        })

        for month in (8, 9, 10):
            slip = self.Payslip.create({
                'name': f'Slip {month}',
                'employee_id': self.employee_1.id,
                'contract_id': self.contract_1.id,
                'struct_id': self.structure.id if self.structure else False,
                'date_from': date(2026, month, 1),
                'date_to': date(2026, month, 28),
            })
            slip.action_compute_sheet()
            inp = slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj)
            self.assertTrue(inp)
            self.assertEqual(inp.amount, 1200.0)
            slip.action_payslip_done()
            self.assertEqual(adj.state, 'running', "Unlimited adjustment stays running")

    def test_05_multi_employee_wizard(self):
        """Test batch creation wizard creates adjustments for multiple employees."""
        wizard = self.SalaryAdjWizard.create({
            'employee_ids': [(6, 0, [self.employee_1.id, self.employee_2.id])],
            'input_type_id': self.input_type_reimbursement.id,
            'amount': 4500.0,
            'duration': 'one_time',
            'date_start': date(2026, 9, 15),
            'note': 'Company Performance Bonus Input',
        })
        wizard.action_create_adjustments()

        adj_1 = self.SalaryAdjustment.search([
            ('employee_id', '=', self.employee_1.id),
            ('note', '=', 'Company Performance Bonus Input'),
        ])
        adj_2 = self.SalaryAdjustment.search([
            ('employee_id', '=', self.employee_2.id),
            ('note', '=', 'Company Performance Bonus Input'),
        ])
        self.assertEqual(len(adj_1), 1)
        self.assertEqual(len(adj_2), 1)
        self.assertEqual(adj_1.amount, 4500.0)
        self.assertEqual(adj_2.amount, 4500.0)

    def test_06_negative_value_adjustment(self):
        """Test negative value flag sets negative amount in payslip input."""
        adj = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'input_type_id': self.input_type_deduction.id,
            'amount': 1500.0,
            'negative': True,
            'duration': 'one_time',
            'date_start': date(2026, 9, 1),
        })

        slip = self.Payslip.create({
            'name': 'Slip Negative Value',
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 9, 1),
            'date_to': date(2026, 9, 30),
        })
        slip.action_compute_sheet()
        inp = slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj)
        self.assertEqual(inp.amount, -1500.0, "Negative flag should pass negative amount")

    def test_07_idempotent_recompute(self):
        """Test recomputing sheet multiple times does not duplicate input lines."""
        adj = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'input_type_id': self.input_type_child_support.id,
            'amount': 7500.0,
            'duration': 'one_time',
            'date_start': date(2026, 9, 1),
        })

        slip = self.Payslip.create({
            'name': 'Slip Idempotency',
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 9, 1),
            'date_to': date(2026, 9, 30),
        })
        slip.action_compute_sheet()
        lines_count_first = len(slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj))
        self.assertEqual(lines_count_first, 1)

        # Recompute sheet 2 more times
        slip.action_compute_sheet()
        slip.action_compute_sheet()
        lines_count_after = len(slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj))
        self.assertEqual(lines_count_after, 1, "Recomputing sheet should never duplicate adjustment inputs")

    def test_08_manual_input_preservation(self):
        """Test that manually entered inputs are preserved and not overwritten."""
        slip = self.Payslip.create({
            'name': 'Slip Manual Input',
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 9, 1),
            'date_to': date(2026, 9, 30),
        })
        # Add manual input
        manual_inp = self.env['hr.payslip.input'].create({
            'payslip_id': slip.id,
            'input_type_id': self.input_type_reimbursement.id,
            'code': 'REIMBURSEMENT',
            'name': 'Manual Custom Travel Bill',
            'amount': 999.0,
        })

        # Add separate adjustment with different code
        adj = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'input_type_id': self.input_type_child_support.id,
            'amount': 3000.0,
            'duration': 'one_time',
            'date_start': date(2026, 9, 1),
        })

        slip.action_compute_sheet()
        # Verify manual input still exists with amount 999.0
        self.assertTrue(manual_inp.exists())
        self.assertEqual(manual_inp.amount, 999.0, "Manual input amount must not be altered")
        self.assertFalse(manual_inp.adjustment_id, "Manual input should remain unlinked")

    def test_09_payslip_cancel_reverts_adjustment_status(self):
        """Test cancelling a payslip reverts one-time adjustment status back to running."""
        adj = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'input_type_id': self.input_type_child_support.id,
            'amount': 5000.0,
            'duration': 'one_time',
            'date_start': date(2026, 9, 1),
        })

        slip = self.Payslip.create({
            'name': 'Slip to Cancel',
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 9, 1),
            'date_to': date(2026, 9, 30),
        })
        slip.action_compute_sheet()
        slip.action_payslip_done()
        self.assertEqual(adj.state, 'done')

        # Cancel payslip
        slip.action_payslip_cancel()
        self.assertEqual(slip.state, 'cancel')
        self.assertEqual(adj.state, 'running', "Cancelling payslip should revert adjustment to running")

    def test_10_validation_constraints(self):
        """Test validation constraints on dates and amount."""
        with self.assertRaises(ValidationError):
            self.SalaryAdjustment.create({
                'employee_id': self.employee_1.id,
                'input_type_id': self.input_type_child_support.id,
                'amount': 0.0,
                'duration': 'one_time',
                'date_start': date(2026, 9, 1),
            })

        with self.assertRaises(ValidationError):
            self.SalaryAdjustment.create({
                'employee_id': self.employee_1.id,
                'input_type_id': self.input_type_child_support.id,
                'amount': 1000.0,
                'duration': 'limited',
                'date_start': date(2026, 9, 1),
                'date_end': False,
            })

        with self.assertRaises(ValidationError):
            self.SalaryAdjustment.create({
                'employee_id': self.employee_1.id,
                'input_type_id': self.input_type_child_support.id,
                'amount': 1000.0,
                'duration': 'limited',
                'date_start': date(2026, 9, 15),
                'date_end': date(2026, 9, 1),
            })

    def test_11_smart_button_and_traceability(self):
        """Test smart button action_view_payslips and applied count."""
        adj = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'input_type_id': self.input_type_child_support.id,
            'amount': 2000.0,
            'duration': 'unlimited',
            'date_start': date(2026, 9, 1),
        })

        slip = self.Payslip.create({
            'name': 'Slip Traceability',
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 9, 1),
            'date_to': date(2026, 9, 30),
        })
        slip.action_compute_sheet()

        self.assertEqual(adj.applied_count, 1)
        action = adj.action_view_payslips()
        self.assertEqual(action['res_model'], 'hr.payslip')
        self.assertEqual(action['res_id'], slip.id)

    def test_12_country_independence_multinational(self):
        """Test that salary adjustment functions in multinational and non-Indian companies without any statutory dependency."""
        country_ae = self.env.ref('base.ae', raise_if_not_found=False) or self.env['res.country'].search([('code', '=', 'AE')], limit=1)
        company_ae = self.Company.search([('name', '=', 'Global Horizon FZE')], limit=1)
        if not company_ae:
            partner_ae = self.env['res.partner'].create({'name': 'Global Horizon FZE Partner', 'is_company': True})
            company_ae = self.Company.create({
                'name': 'Global Horizon FZE',
                'partner_id': partner_ae.id,
                'country_id': country_ae.id if country_ae else False,
            })
        else:
            if country_ae and company_ae.country_id != country_ae:
                company_ae.country_id = country_ae.id
        partner_emp = self.env['res.partner'].create({'name': 'Fatima Al-Nuaimi Partner'})
        emp_ae = self.Employee.create({
            'name': 'Fatima Al-Nuaimi',
            'work_contact_id': partner_emp.id,
            'company_id': company_ae.id,
        })
        if emp_ae.version_id:
            contract_ae = emp_ae.version_id
            contract_ae.write({
                'wage': 18000.0,
                'company_id': company_ae.id,
                'struct_id': self.structure.id if self.structure else False,
                'contract_date_start': date(2026, 1, 1),
            })
        else:
            contract_ae = self.Contract.create({
                'name': 'Contract - Fatima',
                'employee_id': emp_ae.id,
                'company_id': company_ae.id,
                'wage': 18000.0,
                'struct_id': self.structure.id if self.structure else False,
                'contract_date_start': date(2026, 1, 1),
            })
            emp_ae.version_id = contract_ae

        # Create salary adjustment for UAE company employee
        adj_ae = self.SalaryAdjustment.create({
            'employee_id': emp_ae.id,
            'company_id': company_ae.id,
            'input_type_id': self.input_type_reimbursement.id,
            'amount': 1500.0,
            'duration': 'one_time',
            'date_start': date(2026, 9, 1),
            'note': 'Relocation Expense',
        })
        self.assertEqual(adj_ae.company_id.id, company_ae.id)
        if country_ae:
            self.assertEqual(adj_ae.country_id.id, country_ae.id)

        # Generate and compute payslip for UAE employee
        slip_ae = self.Payslip.create({
            'name': 'Payslip UAE - Sep 2026',
            'employee_id': emp_ae.id,
            'contract_id': contract_ae.id,
            'company_id': company_ae.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 9, 1),
            'date_to': date(2026, 9, 30),
        })
        slip_ae.action_compute_sheet()

        inp_ae = slip_ae.input_line_ids.filtered(lambda l: l.adjustment_id == adj_ae)
        self.assertTrue(inp_ae, "Salary adjustment must sync for any country's company and employee")
        self.assertEqual(inp_ae.amount, 1500.0)

        # Confirm payslip
        slip_ae.action_payslip_done()
        self.assertEqual(adj_ae.state, 'done', "Adjustment must complete on confirmation regardless of country")

    def test_16_salary_adjustment_multi_company_isolation(self):
        """
        Verify multi-company isolation for salary adjustments:
        1. Consistency constraint: cross-company adjustment creation raises ValidationError.
        2. Wizard isolation: cross-company selection raises UserError.
        3. Multi-company security rule: adjustments of Company B are isolated from Company A.
        4. Payslip sync isolation: payslips only sync adjustments of their own company.
        """
        company_b = self.Company.search([('id', '!=', self.company.id)], limit=1)
        if not company_b:
            company_b = self.Company.create({'name': 'Company B Test'})

        emp_b = self.Employee.create({
            'name': 'Employee of Company B',
            'company_id': company_b.id,
        })

        # 1. Attempt cross-company assignment: emp_b (Company B) with self.company -> ValidationError
        with self.assertRaises(ValidationError):
            self.SalaryAdjustment.create({
                'employee_id': emp_b.id,
                'company_id': self.company.id,
                'input_type_id': self.input_type_reimbursement.id,
                'amount': 500.0,
                'duration': 'one_time',
            })

        # 2. Wizard validation: selecting an employee of Company B when wizard is Company A -> UserError
        wiz = self.SalaryAdjWizard.create({
            'company_id': self.company.id,
            'employee_ids': [(6, 0, [emp_b.id])],
            'input_type_id': self.input_type_reimbursement.id,
            'amount': 300.0,
            'duration': 'one_time',
        })
        with self.assertRaises(UserError):
            wiz.action_create_adjustments()

        # 3. Create legitimate adjustments in Company A and Company B
        adj_a = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'company_id': self.company.id,
            'input_type_id': self.input_type_reimbursement.id,
            'amount': 1000.0,
            'duration': 'one_time',
            'date_start': date(2026, 10, 1),
        })
        adj_b = self.SalaryAdjustment.create({
            'employee_id': emp_b.id,
            'company_id': company_b.id,
            'input_type_id': self.input_type_reimbursement.id,
            'amount': 2000.0,
            'duration': 'one_time',
            'date_start': date(2026, 10, 1),
        })

        # 4. Check multi-company search isolation for a user logged into Company A
        user_vals = {
            'name': 'Test User Company A',
            'login': 'test_user_comp_a_salary_adj',
            'company_id': self.company.id,
            'company_ids': [(6, 0, [self.company.id])],
        }
        if 'group_ids' in self.env['res.users']._fields:
            user_vals['group_ids'] = [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref('hudson_payroll_base.group_payroll_user').id),
            ]
        user_a = self.env['res.users'].create(user_vals)
        search_as_a = self.SalaryAdjustment.with_user(user_a).with_context(allowed_company_ids=[self.company.id]).search([
            ('id', 'in', [adj_a.id, adj_b.id])
        ])
        self.assertIn(adj_a, search_as_a, "Company A adjustments must be visible to Company A user")
        self.assertNotIn(adj_b, search_as_a, "Company B adjustments must NOT be visible to Company A user")

        # 5. Payslip sync isolation: payslip in Company A must not sync Company B adjustment
        slip_a = self.Payslip.create({
            'name': 'Test Slip MC Sync',
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'company_id': self.company.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 10, 1),
            'date_to': date(2026, 10, 31),
        })
        slip_a.action_compute_sheet()
        self.assertTrue(slip_a.input_line_ids.filtered(lambda l: l.adjustment_id == adj_a))
        self.assertFalse(slip_a.input_line_ids.filtered(lambda l: l.adjustment_id == adj_b))

    def test_15_adjustment_payslip_id_never_empty(self):
        """Test that applying salary adjustments never creates hr.payslip.input with empty payslip_id."""
        adj = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'input_type_id': self.input_type_child_support.id,
            'amount': 4500.0,
            'duration': 'one_time',
            'date_start': date(2026, 11, 1),
            'note': 'Child Support Nov',
        })

        # 1. Simulate onchange on an unsaved in-memory payslip
        slip_virtual = self.Payslip.new({
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 11, 1),
            'date_to': date(2026, 11, 30),
        })
        slip_virtual.onchange_employee()

        # Verify in-memory input line was populated
        self.assertTrue(slip_virtual.input_line_ids.filtered(lambda l: l.adjustment_id == adj))

        # Crucial check: verify NO database record was created with empty payslip_id!
        empty_payslip_inputs = self.env['hr.payslip.input'].search([
            ('payslip_id', '=', False),
            ('adjustment_id', '=', adj.id),
        ])
        self.assertFalse(empty_payslip_inputs, "hr.payslip.input must NOT be created in database before payslip is saved")

        # 2. Now generate and save the real payslip
        slip = self.Payslip.create({
            'name': 'Payslip Nov 2026',
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 11, 1),
            'date_to': date(2026, 11, 30),
        })
        slip.action_compute_sheet()

        # Verify input line is linked to the saved payslip
        linked_input = slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj)
        self.assertTrue(linked_input)
        self.assertEqual(linked_input.payslip_id.id, slip.id, "payslip_id must match the saved payslip ID")
        self.assertFalse(
            self.env['hr.payslip.input'].search([('payslip_id', '=', False)]),
            "No hr.payslip.input record should ever have empty payslip_id"
        )

    def test_17_salary_adjustment_reflects_in_inputs_and_computation_and_net(self):
        """
        Verify that a salary adjustment created in the Salary Adjustment section:
        1. Immediately reflects in the draft payslip's Salary Inputs (hr.payslip.input).
        2. Immediately reflects in the Salary Computation (hr.payslip.line).
        3. Correctly impacts Net Salary (NET).
        4. Dynamically cleans up if the adjustment is cancelled or removed.
        """
        # Step 1: Create and compute a draft payslip BEFORE any adjustment is created
        slip = self.Payslip.create({
            'name': 'Payslip Dec 2026',
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 12, 1),
            'date_to': date(2026, 12, 31),
        })
        slip.action_compute_sheet()
        initial_net_line = slip.line_ids.filtered(lambda l: l.code == 'NET')
        self.assertTrue(initial_net_line, "Payslip must have a Net Salary computation line")
        initial_net = initial_net_line.total

        # Step 2: User gives a Salary Adjustment in the Salary Adjustment section
        adj_ded = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'input_type_id': self.input_type_deduction.id,
            'amount': 2000.0,
            'duration': 'one_time',
            'date_start': date(2026, 12, 1),
            'note': 'Special Policy Deduction',
        })

        # Step 3: Verify it reflects in the Salary Input section (input_line_ids)
        input_ded = slip.input_line_ids.filtered(lambda i: i.adjustment_id == adj_ded)
        self.assertTrue(input_ded, "Salary Adjustment must reflect in the Salary Input section")
        self.assertEqual(input_ded.code, 'DEDUCTION')
        self.assertEqual(input_ded.amount, 2000.0)

        # Step 4: Verify it reflects in the Salary Computation section (line_ids) and reduces NET
        ded_comp_line = slip.line_ids.filtered(lambda l: l.code == 'DEDUCTION')
        self.assertTrue(ded_comp_line, "Salary Adjustment must reflect in the Salary Computation section")
        self.assertEqual(ded_comp_line.total, -2000.0)

        net_line_after_ded = slip.line_ids.filtered(lambda l: l.code == 'NET')
        self.assertEqual(net_line_after_ded.total, initial_net - 2000.0, "Net salary must decrease by deduction adjustment amount")

        # Step 5: User gives an additional Reimbursement adjustment
        adj_reimb = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'input_type_id': self.input_type_reimbursement.id,
            'amount': 1500.0,
            'duration': 'one_time',
            'date_start': date(2026, 12, 1),
            'note': 'Expense Reimbursement',
        })
        input_reimb = slip.input_line_ids.filtered(lambda i: i.adjustment_id == adj_reimb)
        self.assertTrue(input_reimb, "Reimbursement adjustment must reflect in Salary Input section")
        self.assertEqual(input_reimb.code, 'REIMBURSEMENT')
        self.assertEqual(input_reimb.amount, 1500.0)

        reimb_comp_line = slip.line_ids.filtered(lambda l: l.code == 'REIMBURSEMENT')
        self.assertTrue(reimb_comp_line, "Reimbursement adjustment must reflect in Salary Computation section")
        self.assertEqual(reimb_comp_line.total, 1500.0)

        net_line_after_reimb = slip.line_ids.filtered(lambda l: l.code == 'NET')
        self.assertEqual(net_line_after_reimb.total, initial_net - 2000.0 + 1500.0, "Net salary must reflect both deduction and reimbursement")

        # Step 6: Cancelling the deduction adjustment removes it from inputs and computation
        adj_ded.action_cancel()
        self.assertFalse(slip.input_line_ids.filtered(lambda i: i.adjustment_id == adj_ded), "Cancelled adjustment must be removed from inputs")
        self.assertFalse(slip.line_ids.filtered(lambda l: l.code == 'DEDUCTION'), "Cancelled adjustment must be removed from computation")
        net_line_after_cancel = slip.line_ids.filtered(lambda l: l.code == 'NET')
        self.assertEqual(net_line_after_cancel.total, initial_net + 1500.0, "Net salary must revert the deduction")

    def test_18_preexisting_adjustment_never_duplicates_on_new_payslip(self):
        """
        Verify that when a salary adjustment exists BEFORE creating a payslip,
        the adjustment NEVER duplicates on the payslip (exactly 1 line in inputs and 1 line in computation).
        """
        # Step 1: Create running salary adjustment first
        adj = self.SalaryAdjustment.create({
            'employee_id': self.employee_2.id,
            'input_type_id': self.input_type_deduction.id,
            'amount': 9000.0,
            'duration': 'one_time',
            'date_start': date(2026, 10, 1),
            'note': 'Advance Deduction Oct',
        })
        self.assertEqual(adj.state, 'running')

        # Step 2: Simulate payslip creation workflow via onchange
        virtual_slip = self.Payslip.new({
            'employee_id': self.employee_2.id,
            'contract_id': self.contract_2.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 10, 1),
            'date_to': date(2026, 10, 31),
        })
        virtual_slip.onchange_employee()
        self.assertEqual(
            len(virtual_slip.input_line_ids.filtered(lambda l: l.code == 'DEDUCTION')),
            1,
            "Onchange must produce exactly 1 deduction input line"
        )

        # Step 3: Save payslip to database
        saved_slip = self.Payslip.create({
            'name': 'Payslip AJC Oct 2026',
            'employee_id': self.employee_2.id,
            'contract_id': self.contract_2.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 10, 1),
            'date_to': date(2026, 10, 31),
        })
        saved_slip.action_compute_sheet()

        ded_inputs = saved_slip.input_line_ids.filtered(lambda l: l.code == 'DEDUCTION')
        self.assertEqual(
            len(ded_inputs),
            1,
            "Saved payslip must have EXACTLY 1 deduction input line, never duplicated"
        )
        self.assertEqual(ded_inputs.amount, 9000.0)
        self.assertEqual(ded_inputs.adjustment_id.id, adj.id)

        # Step 4: Recomputing multiple times never duplicates lines
        saved_slip.action_compute_sheet()
        saved_slip.action_compute_sheet()

        ded_inputs_after = saved_slip.input_line_ids.filtered(lambda l: l.code == 'DEDUCTION')
        self.assertEqual(len(ded_inputs_after), 1, "Recomputing must never produce duplicate inputs")
        self.assertEqual(ded_inputs_after.amount, 9000.0)

        ded_comp_lines = saved_slip.line_ids.filtered(lambda l: l.code == 'DEDUCTION')
        self.assertEqual(len(ded_comp_lines), 1, "Salary computation must have EXACTLY 1 deduction line")
        self.assertEqual(ded_comp_lines.total, -9000.0)

    def test_19_salary_adjustment_deduction_retained_on_validate(self):
        """
        Verify that validating a payslip (action_payslip_done):
        1. Keeps the salary adjustment input line intact on the payslip.
        2. Keeps the deduction line in Salary Computation intact.
        3. Keeps Net Salary reduced by the deduction (does NOT revert back to amount without deduction).
        4. Closes the one-time adjustment cleanly.
        5. Allows 'Set to Draft' without losing the adjustment or deduction.
        """
        # Step 1: Baseline payslip without adjustment
        base_slip = self.Payslip.create({
            'name': 'Base Slip Nov 2026',
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 11, 1),
            'date_to': date(2026, 11, 30),
        })
        base_slip.action_compute_sheet()
        gross_without_ded = base_slip.line_ids.filtered(lambda l: l.code == 'NET').total
        base_slip.unlink()

        # Step 2: Create a deduction salary adjustment
        ded_amount = 4000.0
        adj = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'input_type_id': self.input_type_deduction.id,
            'amount': ded_amount,
            'duration': 'one_time',
            'date_start': date(2026, 11, 1),
            'note': 'Special Disciplinary Deduction',
        })
        self.assertEqual(adj.state, 'running')

        # Step 3: Create payslip and compute
        slip = self.Payslip.create({
            'name': 'Payslip Nov 2026',
            'employee_id': self.employee_1.id,
            'contract_id': self.contract_1.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date(2026, 11, 1),
            'date_to': date(2026, 11, 30),
        })
        slip.action_compute_sheet()

        # Verify deduction is present before validation
        input_line = slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj)
        self.assertTrue(input_line, "Input line linked to adjustment must exist before validation")
        self.assertEqual(input_line.amount, ded_amount)

        net_before_validate = slip.line_ids.filtered(lambda l: l.code == 'NET').total
        self.assertEqual(net_before_validate, gross_without_ded - ded_amount, "Net must be deducted before validation")

        # Step 4: Validate the payslip
        slip.action_payslip_done()
        self.assertEqual(slip.state, 'done', "Payslip should be validated (done)")
        self.assertEqual(adj.state, 'done', "One-time adjustment should be completed")

        # CRITICAL ASSERTIONS: Deduction must NOT be gone from the payslip!
        input_line_after = slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj)
        self.assertTrue(input_line_after, "Deduction input line must NOT disappear when payslip is validated")
        self.assertEqual(input_line_after.amount, ded_amount)

        ded_comp_after = slip.line_ids.filtered(lambda l: l.code == 'DEDUCTION')
        self.assertTrue(ded_comp_after, "Deduction line in Salary Computation must NOT disappear on validation")
        self.assertEqual(ded_comp_after.total, -ded_amount)

        net_after_validate = slip.line_ids.filtered(lambda l: l.code == 'NET').total
        self.assertEqual(
            net_after_validate,
            gross_without_ded - ded_amount,
            "Net salary must NOT revert back to amount without deduction on validate!"
        )

        # Step 5: Calling action_compute_sheet on a validated payslip must not alter lines
        slip.action_compute_sheet()
        self.assertEqual(slip.line_ids.filtered(lambda l: l.code == 'NET').total, gross_without_ded - ded_amount)

        # Step 6: 'Set to Draft' restores adjustment to running and keeps deduction
        slip.action_payslip_draft()
        self.assertEqual(slip.state, 'draft')
        self.assertEqual(adj.state, 'running', "Adjustment should reactivate to running when slip is reset to draft")
        self.assertEqual(slip.line_ids.filtered(lambda l: l.code == 'NET').total, gross_without_ded - ded_amount)

    def test_20_beneficiary_bank_account_dynamic_fetch_and_switch(self):
        """Test beneficiary bank account dynamically defaults to employee's bank account,
        changes when employee changes, and allows custom override for third parties."""
        PartnerBank = self.env['res.partner.bank']
        bank_1 = PartnerBank.create({
            'acc_number': 'EMP1-BANK-1111',
            'partner_id': self.employee_1.work_contact_id.id if self.employee_1.work_contact_id else self.company.partner_id.id,
            'company_id': self.company.id,
        })
        self.employee_1.bank_account_id = bank_1

        bank_2 = PartnerBank.create({
            'acc_number': 'EMP2-BANK-2222',
            'partner_id': self.employee_2.work_contact_id.id if self.employee_2.work_contact_id else self.company.partner_id.id,
            'company_id': self.company.id,
        })
        self.employee_2.bank_account_id = bank_2

        # 1. Creating adjustment for employee_1 auto-computes beneficiary_bank_id to bank_1
        adj = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'input_type_id': self.input_type_reimbursement.id,
            'amount': 2500.0,
            'duration': 'one_time',
            'date_start': date(2026, 10, 1),
        })
        self.assertEqual(adj.beneficiary_bank_id, bank_1, "Beneficiary bank account should dynamically default to Employee 1's bank account")

        # 2. Testing onchange when switching employee to employee_2
        adj.employee_id = self.employee_2
        adj._onchange_employee_id()
        self.assertEqual(adj.beneficiary_bank_id, bank_2, "Beneficiary bank account must dynamically change to Employee 2's bank account on employee change")

        # 3. Testing onchange when clearing employee
        adj.employee_id = False
        adj._onchange_employee_id()
        self.assertFalse(adj.beneficiary_bank_id, "Beneficiary bank account must clear when employee is empty")

        # 4. Testing custom third-party beneficiary bank account
        third_party_bank = PartnerBank.create({
            'acc_number': 'COURT-ORDER-9999',
            'partner_id': self.company.partner_id.id,
            'company_id': self.company.id,
        })
        adj_court = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'beneficiary_bank_id': third_party_bank.id,
            'input_type_id': self.input_type_child_support.id,
            'amount': 5000.0,
            'duration': 'unlimited',
            'date_start': date(2026, 10, 1),
        })
        self.assertEqual(adj_court.beneficiary_bank_id, third_party_bank, "Explicitly set third-party beneficiary bank account must be preserved")

        # 5. Testing wizard batch creation sets beneficiary bank per employee
        wiz = self.SalaryAdjWizard.create({
            'employee_ids': [(6, 0, [self.employee_1.id, self.employee_2.id])],
            'input_type_id': self.input_type_reimbursement.id,
            'amount': 1500.0,
            'duration': 'one_time',
            'date_start': date(2026, 10, 1),
        })
        action = wiz.action_create_adjustments()
        created_adjs = self.SalaryAdjustment.browse(action['domain'][0][2])
        adj_emp1 = created_adjs.filtered(lambda a: a.employee_id == self.employee_1)
        adj_emp2 = created_adjs.filtered(lambda a: a.employee_id == self.employee_2)
        self.assertEqual(adj_emp1.beneficiary_bank_id, bank_1)
        self.assertEqual(adj_emp2.beneficiary_bank_id, bank_2)

    def _make_slip(self, employee, contract, date_from, date_to):
        return self.Payslip.create({
            'name': 'Payslip %s' % date_from.strftime('%b %Y'),
            'employee_id': employee.id,
            'contract_id': contract.id,
            'struct_id': self.structure.id if self.structure else False,
            'date_from': date_from,
            'date_to': date_to,
        })

    def test_21_wizard_repeat_flag_sets_duration(self):
        """Repeat unticked -> one time; ticked with End Date -> limited; ticked without -> unlimited."""
        base_vals = {
            'employee_ids': [(6, 0, [self.employee_1.id])],
            'input_type_id': self.input_type_deduction.id,
            'amount': 1000.0,
            'date_start': date(2026, 10, 1),
        }
        self.assertEqual(self.SalaryAdjWizard.create(dict(base_vals)).duration, 'one_time')
        self.assertEqual(self.SalaryAdjWizard.create(dict(base_vals, repeat=True)).duration, 'unlimited')
        limited = self.SalaryAdjWizard.create(dict(base_vals, repeat=True, date_end=date(2026, 10, 31)))
        self.assertEqual(limited.duration, 'limited')

        limited.action_create_adjustments()
        adj = self.SalaryAdjustment.search([('employee_id', '=', self.employee_1.id)], order='id desc', limit=1)
        self.assertEqual(adj.duration, 'limited')
        self.assertEqual(adj.date_end, date(2026, 10, 31))

        oct_slip = self._make_slip(self.employee_1, self.contract_1, date(2026, 10, 1), date(2026, 10, 31))
        nov_slip = self._make_slip(self.employee_1, self.contract_1, date(2026, 11, 1), date(2026, 11, 30))
        oct_slip.action_compute_sheet()
        nov_slip.action_compute_sheet()
        self.assertTrue(oct_slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj))
        self.assertFalse(nov_slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj),
                         "Repeat with End Date must not apply after the End Date")

        with self.assertRaises(ValidationError):
            self.SalaryAdjWizard.create(dict(base_vals, repeat=True, date_end=date(2026, 9, 30)))

    def test_22_repeat_without_end_date_stops_at_contract_end(self):
        """Repeat without End Date applies every month until the employee's contract ends."""
        self.contract_1.sudo().contract_date_end = date(2026, 11, 30)
        wiz = self.SalaryAdjWizard.create({
            'employee_ids': [(6, 0, [self.employee_1.id])],
            'input_type_id': self.input_type_deduction.id,
            'amount': 750.0,
            'date_start': date(2026, 10, 1),
            'repeat': True,
        })
        wiz.action_create_adjustments()
        adj = self.SalaryAdjustment.search([('employee_id', '=', self.employee_1.id)], order='id desc', limit=1)
        self.assertEqual(adj.duration, 'unlimited')
        self.assertFalse(adj.date_end)
        self.assertEqual(adj._get_effective_date_end(), date(2026, 11, 30))

        oct_slip = self._make_slip(self.employee_1, self.contract_1, date(2026, 10, 1), date(2026, 10, 31))
        nov_slip = self._make_slip(self.employee_1, self.contract_1, date(2026, 11, 1), date(2026, 11, 30))
        dec_slip = self._make_slip(self.employee_1, self.contract_1, date(2026, 12, 1), date(2026, 12, 31))
        for slip in (oct_slip, nov_slip, dec_slip):
            slip.action_compute_sheet()

        self.assertEqual(oct_slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj).amount, 750.0)
        self.assertEqual(nov_slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj).amount, 750.0)
        self.assertFalse(dec_slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj),
                         "Repeat must stop after the contract end date")

        oct_slip.action_payslip_done()
        self.assertEqual(adj.state, 'running', "Repeating adjustment keeps running before contract end")
        nov_slip.action_payslip_done()
        self.assertEqual(adj.state, 'done', "Repeating adjustment closes once the contract end is reached")

    def test_23_payslip_adjustment_from_select_employees(self):
        """Select Employees -> Payslip Adjustment -> Create generates payslips for the ticked employees."""
        run = self.env['hr.payslip.run'].create({
            'name': 'Oct 2026',
            'company_id': self.company.id,
            'date_start': date(2026, 10, 1),
            'date_end': date(2026, 10, 31),
        })
        ctx = {'active_id': run.id, 'active_model': 'hr.payslip.run', 'test_mode': True}
        select_wiz = self.env['hr.payslip.employees'].with_context(ctx).create({
            'payslip_run_id': run.id,
            'company_id': self.company.id,
            'employee_ids': [(6, 0, [self.employee_1.id, self.employee_2.id])],
            'selected_employee_ids_json': '[%d]' % self.employee_1.id,
        })

        action = select_wiz.action_payslip_adjustment()
        self.assertEqual(action['res_model'], 'hr.salary.adjustment.wizard')
        adj_ctx = action['context']
        self.assertEqual(adj_ctx['default_employee_ids'], [(6, 0, [self.employee_1.id])])
        self.assertEqual(adj_ctx['default_date_start'], date(2026, 10, 1))

        adj_wiz = self.SalaryAdjWizard.with_context(ctx, **adj_ctx).create({
            'input_type_id': self.input_type_deduction.id,
            'amount': 1000.0,
            'repeat': True,
        })
        self.assertEqual(adj_wiz.payslip_run_id, run)
        self.assertEqual(adj_wiz.employee_wizard_id, select_wiz)
        result = adj_wiz.action_create_adjustments()
        self.assertEqual(result.get('res_model'), 'hr.payslip.run')

        self.assertEqual(run.slip_ids.employee_id, self.employee_1, "Only the ticked employee gets a payslip")
        slip = run.slip_ids
        adj = self.SalaryAdjustment.search([('employee_id', '=', self.employee_1.id)], order='id desc', limit=1)
        self.assertEqual(adj.duration, 'unlimited')
        self.assertEqual(slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj).amount, 1000.0)
        ded_line = slip.line_ids.filtered(lambda l: l.code == 'DEDUCTION')
        self.assertTrue(ded_line, "Deduction rule must be computed on the payslip")
        self.assertAlmostEqual(ded_line.total, -1000.0)

    def test_24_payslip_adjustment_requires_ticked_employees(self):
        """Payslip Adjustment with nothing ticked raises a clear error."""
        run = self.env['hr.payslip.run'].create({
            'name': 'Oct 2026',
            'company_id': self.company.id,
            'date_start': date(2026, 10, 1),
            'date_end': date(2026, 10, 31),
        })
        select_wiz = self.env['hr.payslip.employees'].create({
            'payslip_run_id': run.id,
            'company_id': self.company.id,
            'employee_ids': [(6, 0, [self.employee_1.id])],
            'selected_employee_ids_json': '[]',
        })
        with self.assertRaises(UserError):
            select_wiz.action_payslip_adjustment()

    def test_25_one_time_adjustment_only_hits_its_own_period(self):
        """A one-time May adjustment must not leak into a later (e.g. August) payslip."""
        adj = self.SalaryAdjustment.create({
            'employee_id': self.employee_1.id,
            'input_type_id': self.input_type_deduction.id,
            'amount': 5000.0,
            'duration': 'one_time',
            'date_start': date(2026, 5, 1),
        })
        aug_slip = self._make_slip(self.employee_1, self.contract_1, date(2026, 8, 1), date(2026, 8, 31))
        aug_slip.action_compute_sheet()
        self.assertFalse(aug_slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj),
                         "One-time May adjustment must not appear on the August payslip")
        self.assertFalse(aug_slip.line_ids.filtered(lambda l: l.code == 'DEDUCTION'))

        may_slip = self._make_slip(self.employee_1, self.contract_1, date(2026, 5, 1), date(2026, 5, 31))
        may_slip.action_compute_sheet()
        self.assertEqual(may_slip.input_line_ids.filtered(lambda l: l.adjustment_id == adj).amount, 5000.0)




    def _make_select_wizard(self, selected_json):
        run = self.env['hr.payslip.run'].create({
            'name': 'Oct 2026 Plan',
            'company_id': self.company.id,
            'date_start': date(2026, 10, 1),
            'date_end': date(2026, 10, 31),
        })
        wizard = self.env['hr.payslip.employees'].create({
            'payslip_run_id': run.id,
            'company_id': self.company.id,
            'employee_ids': [(6, 0, [self.employee_1.id, self.employee_2.id])],
            'selected_employee_ids_json': selected_json,
        })
        return run, wizard

    def test_26_launch_plan_opens_standard_wizard_for_ticked(self):
        """Launch Plan opens core mail.activity.schedule for the ticked employees and schedules on each."""
        run, wizard = self._make_select_wizard('[%d, %d]' % (self.employee_1.id, self.employee_2.id))
        action = wizard.action_launch_plan()
        self.assertEqual(action['res_model'], 'mail.activity.schedule')
        self.assertEqual(action['target'], 'new')
        ctx = action['context']
        self.assertEqual(ctx['active_model'], 'hr.employee')
        self.assertEqual(sorted(ctx['active_ids']), sorted([self.employee_1.id, self.employee_2.id]))

        schedule = self.env['mail.activity.schedule'].with_context(ctx).create({
            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
            'summary': 'Payroll plan test',
        })
        self.assertEqual(schedule.res_model, 'hr.employee')
        schedule.action_schedule_activities()
        for employee in (self.employee_1, self.employee_2):
            self.assertTrue(employee.activity_ids.filtered(lambda a: a.summary == 'Payroll plan test'))

        reopen = wizard.action_reopen_selection()
        self.assertEqual(reopen['res_model'], 'hr.payslip.employees')
        self.assertEqual(reopen['res_id'], wizard.id)
        self.assertEqual(reopen['context']['active_id'], run.id)

    def test_27_launch_plan_requires_ticked_employee(self):
        _run, wizard = self._make_select_wizard('[]')
        with self.assertRaises(UserError):
            wizard.action_launch_plan()

    def test_28_launch_plan_schedule_plan_stays_on_payrun(self):
        """Scheduling a plan from the pay run closes the wizard instead of jumping to the Employees list."""
        _run, wizard = self._make_select_wizard('[%d, %d]' % (self.employee_1.id, self.employee_2.id))
        ctx = wizard.action_launch_plan()['context']
        plan = self.env['mail.activity.plan'].create({
            'name': 'Payroll Test Plan',
            'res_model': 'hr.employee',
            'template_ids': [(0, 0, {
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'summary': 'Plan step',
                'responsible_type': 'other',
                'responsible_id': self.env.user.id,
            })],
        })
        schedule = self.env['mail.activity.schedule'].with_context(ctx).create({'plan_id': plan.id})
        res = schedule.action_schedule_plan()
        self.assertEqual(res, {'type': 'ir.actions.act_window_close'})
        for employee in (self.employee_1, self.employee_2):
            self.assertTrue(employee.activity_ids.filtered(lambda a: a.summary == 'Plan step'))

    def test_29_employee_tab_repeat_maps_to_duration(self):
        """Employee 'Payslip Adjustments' tab: Repeat drives the existing duration (no calculation change)."""
        with Form(self.employee_1) as emp_form:
            with emp_form.salary_adjustment_ids.new() as f:
                f.input_type_id = self.input_type_deduction
                f.amount = 1000.0
                f.date_start = date(2026, 10, 1)
                self.assertEqual(f.duration, 'one_time')
                f.repeat = True
                self.assertEqual(f.duration, 'unlimited', "Repeat without End Date runs until contract end")
                f.date_end = date(2026, 12, 31)
                self.assertEqual(f.duration, 'limited')
                f.date_end = False
                self.assertEqual(f.duration, 'unlimited')
                f.repeat = False
                self.assertEqual(f.duration, 'one_time')
        adj = self.employee_1.salary_adjustment_ids.filtered(lambda a: a.amount == 1000.0)
        self.assertEqual(len(adj), 1)
        self.assertEqual(adj.duration, 'one_time')
        self.assertEqual(adj.company_id, self.employee_1.company_id)

        # Writing repeat directly goes through the inverse
        adj.repeat = True
        self.assertEqual(adj.duration, 'unlimited')
        adj.write({'repeat': False})
        self.assertEqual(adj.duration, 'one_time')

    def test_30_full_form_keeps_manual_limited_duration(self):
        """Outside the employee tab, choosing 'Limited' must not be overridden by the Repeat onchange."""
        with Form(self.SalaryAdjustment) as f:
            f.employee_id = self.employee_1
            f.input_type_id = self.input_type_deduction
            f.amount = 500.0
            f.date_start = date(2026, 10, 1)
            f.duration = 'limited'
            self.assertEqual(f.duration, 'limited')
            f.date_end = date(2026, 11, 30)
        self.assertEqual(f.record.duration, 'limited')
